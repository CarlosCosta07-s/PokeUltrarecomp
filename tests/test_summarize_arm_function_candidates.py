"""Synthetic tests for the ARM/Thumb prologue-like site census."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import summarize_arm_function_candidates as scanner  # noqa: E402


class CandidateCensusTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="candidate-census-")
        self.addCleanup(self.tmp.cleanup)
        self.directory = Path(self.tmp.name)
        self.exheader = self.directory / "synthetic.exheader"
        self.code = self.directory / "synthetic.code"

        header = bytearray(0x208)
        header[:8] = b"Synthetic"
        header[0x200:0x208] = int("00040000001B5000", 16).to_bytes(8, "little")
        for (address, pages, size), offset in zip(
            ((0x00100000, 1, 0x80), (0x00200000, 1, 0x40), (0x00300000, 1, 0x20)),
            (0x10, 0x20, 0x30),
        ):
            header[offset:offset + 4] = address.to_bytes(4, "little")
            header[offset + 4:offset + 8] = pages.to_bytes(4, "little")
            header[offset + 8:offset + 12] = size.to_bytes(4, "little")

        code = bytearray(0x3000)
        # Synthetic-only markers: ARM PUSH, ARM SUB SP, Thumb PUSH, Thumb SUB SP.
        code[0:4] = (0xE92D4010).to_bytes(4, "little")
        code[4:8] = (0xE24DD00C).to_bytes(4, "little")
        code[8:10] = (0xB5F0).to_bytes(2, "little")
        code[10:12] = (0xB083).to_bytes(2, "little")
        self.exheader.write_bytes(header)
        self.code.write_bytes(code)

    def test_counts_synthetic_arm_and_thumb_prologue_patterns(self):
        result = scanner.scan_candidates("ultra-sun", self.exheader, self.code)
        summary = result["summary"]
        self.assertEqual("pass", summary["status"])
        self.assertEqual(0x80, summary["text_size_bytes"])
        self.assertEqual(4, summary["candidate_sites_total"])
        self.assertEqual(
            {
                "arm_push_or_stmdb_sp": 1,
                "arm_sub_sp_immediate": 1,
                "thumb_push": 1,
                "thumb_sub_sp_immediate": 1,
            },
            summary["candidate_sites_by_pattern"],
        )
        self.assertFalse(summary["addresses_emitted"])
        self.assertFalse(summary["function_boundaries_verified"])

    def test_private_report_is_opt_in_and_outside_repository(self):
        report = self.directory / "private-candidates.json"
        result = scanner.scan_candidates("ultra-sun", self.exheader, self.code)
        report.write_text(json.dumps({
            **result["summary"],
            "addresses_emitted": True,
            "candidates": result["private_candidates"],
        }), encoding="utf-8")
        stored = json.loads(report.read_text(encoding="utf-8"))
        self.assertEqual(4, len(stored["candidates"]))
        self.assertIn("virtual_address", stored["candidates"][0])

    def test_rejects_address_report_inside_project(self):
        with self.assertRaisesRegex(scanner.CandidateScanError, "outside the repository"):
            scanner._outside_project(ROOT / "unsafe-candidates.json")

    def test_requires_recognized_target_identity(self):
        header = bytearray(self.exheader.read_bytes())
        header[0x200:0x208] = int("0000000000000001", 16).to_bytes(8, "little")
        self.exheader.write_bytes(header)
        with self.assertRaisesRegex(scanner.CandidateScanError, "recognized"):
            scanner.scan_candidates("ultra-sun", self.exheader, self.code)


if __name__ == "__main__":
    unittest.main()
