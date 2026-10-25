"""Synthetic tests for explicit local ARM/Thumb code-range inspection."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import inspect_3ds_code_range as ranges  # noqa: E402


def build_exheader(program_id="00040000001B5000", text_size=0x100):
    data = bytearray(0x800)
    data[0:8] = b"UltraSun"
    data[0x10:0x1C] = b"".join((
        (0x00100000).to_bytes(4, "little"), (1).to_bytes(4, "little"),
        text_size.to_bytes(4, "little"),
    ))
    data[0x1C:0x20] = (0x4000).to_bytes(4, "little")
    data[0x20:0x2C] = b"".join((
        (0x00101000).to_bytes(4, "little"), (1).to_bytes(4, "little"),
        (0x80).to_bytes(4, "little"),
    ))
    data[0x30:0x3C] = b"".join((
        (0x00102000).to_bytes(4, "little"), (1).to_bytes(4, "little"),
        (0x40).to_bytes(4, "little"),
    ))
    data[0x3C:0x40] = (0x200).to_bytes(4, "little")
    data[0x200:0x208] = int(program_id, 16).to_bytes(8, "little")
    return bytes(data)


def put_units(code, offset, words, width):
    for index, word in enumerate(words):
        start = offset + index * width
        code[start:start + width] = word.to_bytes(width, "little")


class ExplicitRangeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.exheader = self.root / "exheader.bin"
        self.code = self.root / "code.bin"
        self.exheader.write_bytes(build_exheader())
        self.code.write_bytes(bytes(0x3000))

    def put_thumb(self, words, offset=0):
        data = bytearray(0x3000)
        put_units(data, offset, words, 2)
        self.code.write_bytes(data)

    def put_arm(self, words, offset=0):
        data = bytearray(0x3000)
        put_units(data, offset, words, 4)
        self.code.write_bytes(data)

    def test_decodes_explicit_thumb_range(self):
        self.put_thumb([0x200C, 0x3808, 0x3003, 0x2807, 0x4770])
        result = ranges.inspect_code_range(
            "ultra-sun", self.exheader, self.code, "thumb", 0x00100000, 5,
            title_id="00040000001B5000",
        )
        self.assertEqual("decoded-explicit-range", result["status"])
        self.assertEqual(
            ["MOVS r0, #12", "SUBS r0, #8", "ADDS r0, #3", "CMP r0, #7", "BX LR"],
            [item["mnemonic"] for item in result["instructions"]],
        )
        self.assertEqual([0, 2, 4, 6, 8],
                         [item["decompressed_code_file_offset"] for item in result["instructions"]])

    def test_decodes_explicit_arm_range(self):
        words = [0xE3A0000C, 0xE2400008, 0xE2800003, 0xE2000007, 0xE3800008,
                 0xE2200001, 0xE3C00002, 0xE3E01000, 0xE201000C, 0xE12FFF1E]
        self.put_arm(words)
        result = ranges.inspect_code_range(
            "ultra-sun", self.exheader, self.code, "arm", 0x00100000, 10,
            title_id="00040000001B5000",
        )
        self.assertEqual(10, len(result["instructions"]))
        self.assertEqual("MOV r0, #12", result["instructions"][0]["mnemonic"])
        self.assertEqual("BX LR", result["instructions"][-1]["mnemonic"])
        self.assertEqual(36, result["instructions"][-1]["decompressed_code_file_offset"])

    def test_maps_virtual_address_to_code_file_offset(self):
        self.put_thumb([0x2005], offset=4)
        result = ranges.inspect_code_range(
            "ultra-sun", self.exheader, self.code, "thumb", 0x00100004, 1,
            title_id="00040000001B5000",
        )
        self.assertEqual(4, result["instructions"][0]["decompressed_code_file_offset"])
        self.assertEqual("0x00100004", result["instructions"][0]["virtual_address"])

    def test_reports_branch_target(self):
        self.put_thumb([0xD000, 0x2001, 0x4770])
        result = ranges.inspect_code_range(
            "ultra-sun", self.exheader, self.code, "thumb", 0x00100000, 3,
            title_id="00040000001B5000",
        )
        branch = result["instructions"][0]
        self.assertEqual("0x00100004", branch["branch_target_virtual_address"])
        self.assertTrue(branch["branch_target_within_selected_range"])
        self.assertTrue(branch["branch_target_within_declared_text"])

    def test_rejects_unrecognized_embedded_program_id(self):
        self.exheader.write_bytes(build_exheader(program_id="0004000000ABCDEF"))
        self.put_thumb([0x4770])
        with self.assertRaisesRegex(ranges.TargetRangeError, "Program ID is unrecognized"):
            ranges.inspect_code_range("ultra-sun", self.exheader, self.code, "thumb", 0x00100000, 1)

    def test_allows_unknown_program_id_only_with_explicit_override(self):
        self.exheader.write_bytes(build_exheader(program_id="0004000000ABCDEF"))
        self.put_thumb([0x4770])
        result = ranges.inspect_code_range(
            "ultra-sun", self.exheader, self.code, "thumb", 0x00100000, 1,
            allow_unverified_target=True,
        )
        self.assertEqual("unrecognized", result["target"]["program_id_match"])

    def test_rejects_program_id_from_other_game(self):
        self.exheader.write_bytes(build_exheader(program_id="00040000001B5100"))
        self.put_thumb([0x4770])
        with self.assertRaisesRegex(ranges.TargetRangeError, "belongs to Pokémon Ultra Moon"):
            ranges.inspect_code_range("ultra-sun", self.exheader, self.code, "thumb", 0x00100000, 1)

    def test_rejects_start_outside_declared_text(self):
        with self.assertRaisesRegex(ranges.TargetRangeError, "outside declared .text"):
            ranges.inspect_code_range("ultra-sun", self.exheader, self.code, "thumb", 0x00100100, 1)

    def test_rejects_ranges_into_page_padding(self):
        self.exheader.write_bytes(build_exheader(text_size=10))
        self.put_thumb([0x4770] * 8)
        with self.assertRaisesRegex(ranges.TargetRangeError, "page padding is not code"):
            ranges.inspect_code_range("ultra-sun", self.exheader, self.code, "thumb", 0x00100000, 6)

    def test_rejects_unaligned_address(self):
        with self.assertRaisesRegex(ranges.TargetRangeError, "not aligned"):
            ranges.inspect_code_range("ultra-sun", self.exheader, self.code, "thumb", 0x00100001, 1)

    def test_rejects_unimplemented_instruction_with_address(self):
        self.put_thumb([0x46C0])
        with self.assertRaisesRegex(ranges.TargetRangeError, "unsupported instruction at 0x00100000"):
            ranges.inspect_code_range("ultra-sun", self.exheader, self.code, "thumb", 0x00100000, 1)

    def test_rejects_invalid_instruction_count(self):
        for count in (0, 257, True):
            with self.subTest(count=count), self.assertRaisesRegex(ranges.TargetRangeError, "instruction count"):
                ranges.inspect_code_range("ultra-sun", self.exheader, self.code, "thumb", 0x00100000, count)

    def test_rejects_unknown_instruction_state(self):
        with self.assertRaisesRegex(ranges.TargetRangeError, "instruction state"):
            ranges.inspect_code_range("ultra-sun", self.exheader, self.code, "thumb2", 0x00100000, 1)

    def test_cli_emits_json_for_synthetic_inputs(self):
        self.put_thumb([0x4770])
        run = subprocess.run([
            sys.executable, str(ROOT / "tools" / "inspect_3ds_code_range.py"),
            "--target", "ultra-sun", "--exheader", str(self.exheader),
            "--code", str(self.code), "--state", "thumb",
            "--start-address", "0x00100000", "--instruction-count", "1",
            "--title-id", "00040000001B5000",
        ], capture_output=True, text=True, check=False)
        self.assertEqual(0, run.returncode, msg=run.stderr)
        result = json.loads(run.stdout)
        self.assertEqual("BX LR", result["instructions"][0]["mnemonic"])

    def test_cli_rejects_report_inside_repository(self):
        self.put_thumb([0x4770])
        run = subprocess.run([
            sys.executable, str(ROOT / "tools" / "inspect_3ds_code_range.py"),
            "--target", "ultra-sun", "--exheader", str(self.exheader),
            "--code", str(self.code), "--state", "thumb",
            "--start-address", "0x00100000", "--instruction-count", "1",
            "--title-id", "00040000001B5000",
            "--report", str(ROOT / "local-range-report.json"),
        ], capture_output=True, text=True, check=False)
        self.assertEqual(2, run.returncode)
        self.assertIn("outside the repository", run.stderr)


if __name__ == "__main__":
    unittest.main()
