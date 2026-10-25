"""Synthetic tests for the aggregate decoder-coverage summary."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import inspect_3ds_code_range as ranges  # noqa: E402
import summarize_code_coverage as coverage  # noqa: E402

TITLE = "00040000001B5000"


def build_exheader(text_size=0x100):
    data = bytearray(0x800)
    data[0:8] = b"UltraSun"
    data[0x10:0x1C] = b"".join((
        (0x00100000).to_bytes(4, "little"), (1).to_bytes(4, "little"), text_size.to_bytes(4, "little"),
    ))
    data[0x1C:0x20] = (0x4000).to_bytes(4, "little")
    data[0x20:0x2C] = b"".join((
        (0x00101000).to_bytes(4, "little"), (1).to_bytes(4, "little"), (0x80).to_bytes(4, "little"),
    ))
    data[0x30:0x3C] = b"".join((
        (0x00102000).to_bytes(4, "little"), (1).to_bytes(4, "little"), (0x40).to_bytes(4, "little"),
    ))
    data[0x3C:0x40] = (0x200).to_bytes(4, "little")
    data[0x200:0x208] = int(TITLE, 16).to_bytes(8, "little")
    return bytes(data)


class CoverageSummaryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.exheader = self.root / "exheader.bin"
        self.code = self.root / "code.bin"
        self.exheader.write_bytes(build_exheader())
        self.code.write_bytes(bytes(0x3000))

    def put(self, words, width):
        data = bytearray(0x3000)
        for index, word in enumerate(words):
            data[index * width:(index + 1) * width] = word.to_bytes(width, "little")
        self.code.write_bytes(data)

    def summarize(self, state="thumb", start=0x00100000, per_window=3, windows=2, **kwargs):
        return coverage.summarize_coverage(
            "ultra-sun", self.exheader, self.code, state, start, per_window, windows,
            title_id=TITLE, **kwargs,
        )

    def test_two_windows_aggregate_hand_derived_counts(self):
        # window 1: MOVS, PUSH, 0xBA00 (REV, still unsupported); window 2: LDR literal, BL (pair), BX LR
        self.put([0x2001, 0xB510, 0xBA00, 0x4800, 0xF000, 0xF800, 0x4770], 2)
        result = self.summarize()
        self.assertEqual("coverage-summary-explicit-range", result["status"])
        self.assertEqual(2, result["range"]["windows_counted"])
        self.assertEqual("0x0010000E", result["range"]["end_address"])
        self.assertIsNone(result["range"]["stopped_reason"])
        self.assertEqual({
            "instructions": 6, "decoded": 5, "unsupported": 1, "decoded_ratio": 0.8333,
            "bytes": 14, "decoded_bytes": 12, "unsupported_bytes": 2,
        }, result["coverage"])
        self.assertEqual({"MOVS": 1, "PUSH": 1, "LDR": 1, "BL": 1, "BX": 1}, result["decoded_by_mnemonic"])
        self.assertEqual([{"opcode_class": "0xBAxx", "count": 1}], result["unsupported_by_opcode_class"])
        self.assertEqual({
            "calls": 1, "literal_loads": 1, "literals_inside_their_own_window": 1,
            "returns": 1, "stack_pushes": 1,
        }, result["flow"])

    def test_summary_never_contains_individual_encodings_or_addresses_of_instructions(self):
        self.put([0x2001, 0xB510, 0xBA00, 0x4800, 0xF000, 0xF800, 0x4770], 2)
        text = json.dumps(self.summarize())
        for forbidden in ("0xBA00", "0xB510", "0x2001", "0xF000", "0xF800", "0x4770", "virtual_address", "encoding"):
            self.assertNotIn(forbidden, text)
        self.assertNotIn("instructions\": [", text)

    def test_stops_cleanly_at_the_end_of_declared_text(self):
        self.exheader.write_bytes(build_exheader(text_size=0x10))
        self.put([0x4770] * 8, 2)
        result = self.summarize(windows=5)
        self.assertEqual(2, result["range"]["windows_counted"])
        self.assertEqual(6, result["coverage"]["instructions"])
        self.assertIn("end of declared .text", result["range"]["stopped_reason"])
        self.assertEqual({"returns": 6}, result["flow"])

    def test_arm_state_uses_bits_27_to_20_as_the_class(self):
        self.put([0xE1200070, 0xE12FFF1E], 4)
        result = self.summarize(state="arm", per_window=2, windows=1)
        self.assertEqual([{"opcode_class": "0x12", "count": 1}], result["unsupported_by_opcode_class"])
        self.assertEqual(1, result["coverage"]["decoded"])

    def test_thumb32_pairs_are_classified_by_both_prefixes(self):
        self.put([0xF000, 0x0000, 0x4770], 2)
        result = self.summarize(per_window=2, windows=1)
        self.assertEqual([{"opcode_class": "0xF000/0x0000", "count": 1}], result["unsupported_by_opcode_class"])

    def test_top_limits_the_class_list(self):
        self.put([0xBA00, 0xBA01, 0xB200, 0x4770], 2)   # classes 0xBA, 0xBA, 0xB2 (all unsupported)
        full = self.summarize(per_window=4, windows=1, top=16)["unsupported_by_opcode_class"]
        self.assertEqual("0xBAxx", full[0]["opcode_class"])
        self.assertEqual(2, full[0]["count"])
        self.assertEqual(1, len(self.summarize(per_window=4, windows=1, top=1)["unsupported_by_opcode_class"]))

    def test_first_window_errors_propagate(self):
        self.put([0x4770], 2)
        with self.assertRaisesRegex(ranges.TargetRangeError, "outside declared .text"):
            self.summarize(start=0x00200000)

    def test_rejects_invalid_parameters(self):
        self.put([0x4770], 2)
        for windows in (0, coverage.MAX_WINDOWS + 1, True, "2"):
            with self.subTest(windows=windows), self.assertRaisesRegex(ranges.TargetRangeError, "window count"):
                self.summarize(windows=windows)
        for top in (0, 257, True):
            with self.subTest(top=top), self.assertRaisesRegex(ranges.TargetRangeError, "top"):
                self.summarize(top=top)
        with self.assertRaisesRegex(ranges.TargetRangeError, "instruction count"):
            self.summarize(per_window=0)

    def test_wrong_program_id_is_still_rejected(self):
        data = bytearray(build_exheader())
        data[0x200:0x208] = int("00040000001B5100", 16).to_bytes(8, "little")
        self.exheader.write_bytes(bytes(data))
        self.put([0x4770], 2)
        with self.assertRaises(ranges.TargetRangeError):
            self.summarize(windows=1)

    def test_cli_emits_json_and_refuses_reports_inside_the_repository(self):
        self.put([0x2001, 0x4770, 0x4770], 2)
        base = [
            sys.executable, str(ROOT / "tools" / "summarize_code_coverage.py"),
            "--target", "ultra-sun", "--exheader", str(self.exheader), "--code", str(self.code),
            "--state", "thumb", "--start-address", "0x00100000", "--instructions-per-window", "3",
            "--title-id", TITLE,
        ]
        run = subprocess.run(base, capture_output=True, text=True)
        self.assertEqual(0, run.returncode, msg=run.stderr)
        self.assertEqual(3, json.loads(run.stdout)["coverage"]["instructions"])
        refused = subprocess.run(base + ["--report", str(ROOT / "summary.json")], capture_output=True, text=True)
        self.assertEqual(2, refused.returncode)
        self.assertIn("outside the repository", refused.stderr)
        self.assertFalse((ROOT / "summary.json").exists())
        out = self.root / "summary.json"
        ok = subprocess.run(base + ["--report", str(out)], capture_output=True, text=True)
        self.assertEqual(0, ok.returncode, msg=ok.stderr)
        self.assertEqual(3, json.loads(out.read_text(encoding="utf-8"))["coverage"]["instructions"])


if __name__ == "__main__":
    unittest.main()
