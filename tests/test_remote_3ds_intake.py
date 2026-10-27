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
        self.image_path.write_bytes(b"synthetic input only")
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

    def test_format_mapping(self):
        self.assertEqual(("3ds", "ncsd"), intake.normalize_format(".3DS"))
        self.assertEqual(("cci", "ncsd"), intake.normalize_format("cci"))
        self.assertEqual(("cia", "cia"), intake.normalize_format(".CIA"))

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
