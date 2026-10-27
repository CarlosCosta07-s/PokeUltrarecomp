"""Tests for the remote 3DS intake helpers using synthetic data only."""
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import remote_3ds_intake as intake  # noqa: E402


class Remote3DSIntakeTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="remote-3ds-intake-")
        self.addCleanup(self.temporary.cleanup)
        self.work = Path(self.temporary.name)
        self.fake_ctrtool = self.work / "fake_ctrtool.py"
        self.image_path = self.work / "synthetic.3ds"
        synthetic_ncsd = bytearray(0x1000)
        synthetic_ncsd[0x100:0x104] = b"NCSD"
        synthetic_ncsd[0x120:0x124] = (2).to_bytes(4, "little")
        synthetic_ncsd[0x124:0x128] = (4).to_bytes(4, "little")
        ncch_offset = 2 * 0x200
        synthetic_ncsd[ncch_offset + 0x100:ncch_offset + 0x104] = b"NCCH"
        synthetic_ncsd[ncch_offset + 0x118:ncch_offset + 0x120] = int(
            "00040000001B5000", 16
        ).to_bytes(8, "little")
        self.image_path.write_bytes(synthetic_ncsd)
        self.work_directory = self.work / "processing"

        header = bytearray(0x208)
        header[0:8] = b"TestGame"
        header[0x200:0x208] = int("00040000001B5000", 16).to_bytes(8, "little")
        for (address, pages, size), offset in zip(
            ((0x00100000, 1, 0x80), (0x00200000, 1, 0x40), (0x00300000, 1, 0x20)),
            (0x10, 0x20, 0x30),
        ):
            header[offset:offset + 4] = address.to_bytes(4, "little")
            header[offset + 4:offset + 8] = pages.to_bytes(4, "little")
            header[offset + 8:offset + 12] = size.to_bytes(4, "little")
        self.code = bytes((i * 11 + 9) & 0xFF for i in range(0x3000))
        self.header_fixture = self.work / "fixture.exheader"
        self.code_fixture = self.work / "fixture.code"
        self.header_fixture.write_bytes(header)
        self.code_fixture.write_bytes(self.code)
        self.fake_ctrtool.write_text(
            "import sys\nfrom pathlib import Path\n"
            "args=sys.argv[1:]\n"
            "header=next(a.split('=',1)[1] for a in args if a.startswith('--exheader='))\n"
            "exefs=next(a.split('=',1)[1] for a in args if a.startswith('--exefsdir='))\n"
            f"Path(header).write_bytes(Path({str(self.header_fixture)!r}).read_bytes())\n"
            "out=Path(exefs); out.mkdir(parents=True, exist_ok=True)\n"
            f"(out/'code.bin').write_bytes(Path({str(self.code_fixture)!r}).read_bytes())\n",
            encoding="utf-8",
        )

    def test_extract_container_title_id_from_ncsd_ncch_header(self):
        self.assertEqual(
            "00040000001b5000",
            intake.extract_container_title_id(self.image_path, "cci", 0),
        )

    def test_cia_container_title_id_is_not_claimed_without_tmd_parser(self):
        self.assertIsNone(intake.extract_container_title_id(self.image_path, "cia", 0))

    def test_ncsd_title_id_rejects_invalid_magic(self):
        invalid = self.work / "invalid.3ds"
        invalid.write_bytes(b"X" * 0x1000)
        with self.assertRaisesRegex(intake.IntakeError, "NCSD header"):
            intake.extract_container_title_id(invalid, "3ds", 0)

    def test_ncsd_title_id_rejects_absent_partition_and_bad_index(self):
        no_partition = self.work / "no-partition.cci"
        empty = bytearray(0x1000)
        empty[0x100:0x104] = b"NCSD"
        no_partition.write_bytes(empty)
        with self.assertRaisesRegex(intake.IntakeError, "partition is absent"):
            intake.extract_container_title_id(no_partition, "cci", 0)
        with self.assertRaisesRegex(intake.IntakeError, "index must be from 0 to 7"):
            intake.extract_container_title_id(self.image_path, "cci", 8)

    def test_format_mapping(self):
        self.assertEqual(("3ds", "ncsd"), intake.normalize_format(".3DS"))
        self.assertEqual(("cci", "ncsd"), intake.normalize_format("cci"))
        self.assertEqual(("cia", "cia"), intake.normalize_format(".CIA"))

    def test_google_drive_share_link_uses_gdown(self):
        from types import SimpleNamespace
        from unittest.mock import patch

        link = "https://drive.google.com/file/d/AbCdEf1234567890/view?usp=sharing&resourcekey=key_123"
        self.assertEqual(
            ("AbCdEf1234567890", "key_123"),
            intake.google_drive_file_details(link),
        )
        destination = self.work / "remote.cci"
        observed = {}

        def fake_download(**kwargs):
            observed.update(kwargs)
            kwargs["progress"](16, 16)
            Path(kwargs["output"]).write_bytes(b"synthetic cci image")
            return kwargs["output"]

        with patch.dict(sys.modules, {"gdown": SimpleNamespace(download=fake_download)}):
            size = intake.download(link, destination)

        self.assertEqual(len(b"synthetic cci image"), size)
        self.assertEqual(b"synthetic cci image", destination.read_bytes())
        self.assertEqual(link, observed["url"])
        self.assertEqual(str(destination), observed["output"])
        self.assertTrue(observed["quiet"])
        self.assertFalse(observed["use_cookies"])
        self.assertTrue(observed["resume"])
        self.assertEqual(3, observed["retries"])

    def test_google_drive_download_failure_does_not_echo_secret_url(self):
        from types import SimpleNamespace
        from unittest.mock import patch

        link = "https://drive.google.com/file/d/AbCdEf1234567890/view?private-secret=never-log-this"
        destination = self.work / "failed.cci"

        def fake_download(**kwargs):
            raise RuntimeError("request failed for " + kwargs["url"])

        with patch.dict(sys.modules, {"gdown": SimpleNamespace(download=fake_download)}):
            with self.assertRaises(intake.IntakeError) as raised:
                intake.download(link, destination)

        self.assertNotIn("never-log-this", str(raised.exception))
        self.assertFalse(destination.exists())

    def test_google_drive_download_enforces_size_limit(self):
        from types import SimpleNamespace
        from unittest.mock import patch

        link = "https://drive.google.com/file/d/AbCdEf1234567890/view"
        destination = self.work / "too-large.cci"

        def fake_download(**kwargs):
            kwargs["progress"](intake.MAX_BYTES + 1, intake.MAX_BYTES + 1)
            return kwargs["output"]

        with patch.dict(sys.modules, {"gdown": SimpleNamespace(download=fake_download)}):
            with self.assertRaisesRegex(intake.IntakeError, "8 GiB limit"):
                intake.download(link, destination)

        self.assertFalse(destination.exists())

    def test_ccd_has_actionable_error(self):
        with self.assertRaisesRegex(intake.IntakeError, r"\.ccd is not a Nintendo 3DS"):
            intake.normalize_format(".ccd")

    def test_unknown_formats_fail_closed(self):
        for name in ("rom", "cxi", "3dsx", ""):
            with self.subTest(name=name), self.assertRaisesRegex(intake.IntakeError, "supported formats"):
                intake.normalize_format(name)

    def test_https_url_policy(self):
        invalid_urls = (
            "http://example.test/game.3ds", "file:///tmp/game.3ds", "",
            "https:///missing-host", "https://user:password@example.test/game.3ds",
            "https://example.test:8443/game.3ds", "https://127.0.0.1/game.3ds",
            "https://192.168.1.10/game.3ds", "https://localhost/game.3ds",
        )
        for url in invalid_urls:
            with self.subTest(url=url), self.assertRaises(intake.IntakeError):
                intake.validate_url(url)

    def test_download_rejects_non_https_without_network_access(self):
        with self.assertRaisesRegex(intake.IntakeError, "direct-download"):
            intake.download("http://example.test/game.3ds", self.work / "not-created.bin")
        self.assertFalse((self.work / "not-created.bin").exists())

    def test_code_locator_requires_single_code_file(self):
        exefs = self.work / "exefs"
        exefs.mkdir()
        (exefs / "code.bin").write_bytes(b"fake")
        self.assertEqual(exefs / "code.bin", intake._locate_code_file(exefs))
        (exefs / ".code").write_bytes(b"ambiguous")
        with self.assertRaisesRegex(intake.IntakeError, "exactly one"):
            intake._locate_code_file(exefs)

    def test_fake_ctrtool_extracts_synthetic_image(self):
        result = intake.extract_and_inspect(
            self.image_path, "ultra-sun", ".3ds",
            [sys.executable, str(self.fake_ctrtool)], self.work_directory,
        )
        self.assertEqual("pass", result["status"])
        self.assertEqual(".3ds", result["format"])
        self.assertTrue(result["container_title_id_supplied"])
        self.assertEqual("matched", result["container_title_id_match"])
        self.assertEqual("base", result["container_title_kind"])
        self.assertEqual(0x80, result["text_size_bytes"])
        self.assertTrue(result["no_game_bytes_or_disassembly_uploaded"])

    def test_work_directory_cannot_be_inside_repository(self):
        with self.assertRaisesRegex(intake.IntakeError, "outside the repository"):
            intake.extract_and_inspect(
                self.image_path, "ultra-sun", ".3ds",
                [sys.executable, str(self.fake_ctrtool)], ROOT / "unsafe-output",
            )


if __name__ == "__main__":
    unittest.main()
