"""Synthetic tests for the local-only 3DS target intake inspector."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import inspect_3ds_target as inspector  # noqa: E402


def build_exheader(*, text_size=0x100, text_pages=1, rodata_size=0x80,
                   rodata_pages=1, data_size=0x40, data_pages=1,
                   text_address=0x00100000, rodata_address=0x00101000,
                   data_address=0x00102000, flags=0x01):
    data = bytearray(0x800)
    data[0:8] = b"UltraSun"
    data[0x0D] = flags
    data[0x0E:0x10] = (0x0001).to_bytes(2, "little")
    data[0x10:0x1C] = b"".join((
        text_address.to_bytes(4, "little"),
        text_pages.to_bytes(4, "little"),
        text_size.to_bytes(4, "little"),
    ))
    data[0x1C:0x20] = (0x4000).to_bytes(4, "little")
    data[0x20:0x2C] = b"".join((
        rodata_address.to_bytes(4, "little"),
        rodata_pages.to_bytes(4, "little"),
        rodata_size.to_bytes(4, "little"),
    ))
    data[0x30:0x3C] = b"".join((
        data_address.to_bytes(4, "little"),
        data_pages.to_bytes(4, "little"),
        data_size.to_bytes(4, "little"),
    ))
    data[0x3C:0x40] = (0x200).to_bytes(4, "little")
    return bytes(data)


class TargetProfileTests(unittest.TestCase):
    def test_profiles_identify_both_games_and_their_known_title_ids(self):
        profiles = inspector.load_profiles()
        self.assertEqual({"ultra-sun", "ultra-moon"}, set(profiles))
        self.assertEqual("00040000001B5000", profiles["ultra-sun"]["title_ids"]["base"])
        self.assertEqual("00040000001B5100", profiles["ultra-moon"]["title_ids"]["base"])
        self.assertEqual("Nintendo 3DS", profiles["ultra-sun"]["platform"])
        us_hint = inspector.code_size_hint(profiles["ultra-sun"], 5914624)
        um_update_hint = inspector.code_size_hint(profiles["ultra-moon"], 5922816)
        self.assertEqual("base-v1.0-size-candidate", us_hint["variant"])
        self.assertEqual("update-v1.2-size-candidate", um_update_hint["variant"])
        self.assertFalse(us_hint["verified_revision"])
        self.assertEqual("no-known-size-match", inspector.code_size_hint(profiles["ultra-sun"], 12345)["status"])


class ExHeaderInspectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.exheader_path = self.root / "exheader.bin"
        self.code_path = self.root / "code.bin"
        self.exheader_path.write_bytes(build_exheader())
        self.code_path.write_bytes(bytes(0x3000))

    def test_inspects_valid_ultra_sun_metadata(self):
        report = inspector.inspect_target(
            "ultra-sun", self.exheader_path, self.code_path, "00040000001B5000"
        )
        self.assertEqual("pass", report["status"])
        self.assertEqual("matched", report["identity"]["title_id_match"])
        self.assertEqual("base", report["identity"]["title_kind"])
        self.assertEqual(0x4000, report["memory"]["stack_size_bytes"])
        self.assertEqual(0x200, report["memory"]["bss_size_bytes"])
        self.assertEqual(0x3000, report["memory"]["combined_segment_page_capacity_bytes"])
        self.assertTrue(report["inputs"]["source_exefs_code_was_compressed"])
        self.assertEqual(["text", "rodata", "data"], [x["name"] for x in report["memory"]["segments"]])

    def test_recognizes_ultra_moon_update_title_id(self):
        report = inspector.inspect_target(
            "ultra-moon", self.exheader_path, self.code_path, "0004000E001B5100"
        )
        self.assertEqual("pass", report["status"])
        self.assertEqual("update", report["identity"]["title_kind"])

    def test_rejects_title_id_from_the_other_game(self):
        with self.assertRaisesRegex(inspector.TargetInspectionError, "belongs to Pokémon Ultra Moon"):
            inspector.inspect_target(
                "ultra-sun", self.exheader_path, self.code_path, "00040000001B5100"
            )

    def test_unknown_title_id_is_reported_unverified_not_guessed(self):
        report = inspector.inspect_target(
            "ultra-sun", self.exheader_path, self.code_path, "0004000000ABCDEF"
        )
        self.assertEqual("pass-with-warnings", report["status"])
        self.assertEqual("unrecognized", report["identity"]["title_id_match"])
        self.assertTrue(any("not in the known" in x for x in report["warnings"]))

    def test_missing_title_id_is_reported_as_user_declared(self):
        report = inspector.inspect_target("ultra-sun", self.exheader_path, self.code_path)
        self.assertEqual("pass-with-warnings", report["status"])
        self.assertEqual("not-supplied", report["identity"]["title_id_match"])

    def test_rejects_truncated_exheader(self):
        self.exheader_path.write_bytes(bytes(0x100))
        with self.assertRaisesRegex(inspector.TargetInspectionError, "too short"):
            inspector.inspect_target("ultra-sun", self.exheader_path, self.code_path)

    def test_rejects_segment_larger_than_declared_page_allocation(self):
        self.exheader_path.write_bytes(build_exheader(text_size=0x1001, text_pages=1))
        with self.assertRaisesRegex(inspector.TargetInspectionError, "text segment declares"):
            inspector.inspect_target("ultra-sun", self.exheader_path, self.code_path)

    def test_rejects_overlapping_virtual_page_ranges(self):
        self.exheader_path.write_bytes(build_exheader(rodata_address=0x00100000))
        with self.assertRaisesRegex(inspector.TargetInspectionError, "overlaps text"):
            inspector.inspect_target("ultra-sun", self.exheader_path, self.code_path)

    def test_rejects_code_smaller_than_declared_payload(self):
        self.code_path.write_bytes(bytes(0x100))
        with self.assertRaisesRegex(inspector.TargetInspectionError, "too short"):
            inspector.inspect_target("ultra-sun", self.exheader_path, self.code_path)

    def test_rejects_code_larger_than_combined_page_capacity(self):
        self.code_path.write_bytes(bytes(0x4000))
        with self.assertRaisesRegex(inspector.TargetInspectionError, "larger than the combined page allocation"):
            inspector.inspect_target("ultra-sun", self.exheader_path, self.code_path)

    def test_warns_if_code_fits_payload_but_not_full_page_capacity(self):
        self.code_path.write_bytes(bytes(0x220))
        report = inspector.inspect_target(
            "ultra-sun", self.exheader_path, self.code_path, "00040000001B5000"
        )
        self.assertEqual("pass-with-warnings", report["status"])
        self.assertTrue(any("does not equal total page allocation" in x for x in report["warnings"]))

    def test_report_contains_hashes_but_never_absolute_input_paths(self):
        report = inspector.inspect_target(
            "ultra-sun", self.exheader_path, self.code_path, "00040000001B5000"
        )
        rendered = json.dumps(report)
        self.assertEqual(64, len(report["inputs"]["decompressed_code"]["sha256"]))
        self.assertIn('"filename": "code.bin"', rendered)
        self.assertNotIn(str(self.root), rendered)

    def test_cli_outputs_json_for_synthetic_inputs(self):
        script = str(ROOT / "tools" / "inspect_3ds_target.py")
        result = subprocess.run([
            sys.executable, script,
            "--target", "ultra-sun",
            "--exheader", str(self.exheader_path),
            "--code", str(self.code_path),
            "--title-id", "00040000001B5000",
        ], capture_output=True, text=True, check=False)
        self.assertEqual(0, result.returncode, msg=result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual("ultra-sun", report["target"]["target_id"])
        self.assertEqual("pass", report["status"])


if __name__ == "__main__":
    unittest.main()
