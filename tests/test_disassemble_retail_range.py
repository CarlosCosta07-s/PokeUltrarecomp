"""Synthetic contract tests for the local Capstone range-disassembly entry point."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import disassemble_retail_range as disassembler  # noqa: E402


class FakeInstruction:
    def __init__(self, address, raw, mnemonic="fake", op_str="r0, r0"):
        self.address = address
        self.bytes = raw
        self.size = len(raw)
        self.mnemonic = mnemonic
        self.op_str = op_str


class FakeCapstone:
    CS_ARCH_ARM = 1
    CS_MODE_ARM = 0
    CS_MODE_THUMB = 16
    CS_MODE_LITTLE_ENDIAN = 0
    __version__ = "test-double"

    partial = False

    class Cs:
        def __init__(self, architecture, mode):
            self.architecture = architecture
            self.mode = mode

        def disasm(self, code, address):
            stride = 2 if self.mode & FakeCapstone.CS_MODE_THUMB else 4
            limit = len(code) - stride + 1
            for offset in range(0, max(0, limit), stride):
                if FakeCapstone.partial and offset:
                    break
                yield FakeInstruction(address + offset, code[offset:offset + stride])


class DisassembleRetailRangeTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="retail-disassembly-")
        self.addCleanup(self.temporary.cleanup)
        self.work = Path(self.temporary.name)
        self.exheader_path = self.work / "synthetic.exheader"
        self.code_path = self.work / "synthetic.code"
        self.report_path = self.work / "range-report.json"
        exheader = bytearray(0x208)
        exheader[0:8] = b"TestGame"
        exheader[0x200:0x208] = int("00040000001B5000", 16).to_bytes(8, "little")
        for (address, pages, size), offset in zip(
            ((0x00100000, 1, 0x80), (0x00200000, 1, 0x40), (0x00300000, 1, 0x20)),
            (0x10, 0x20, 0x30),
        ):
            exheader[offset:offset + 4] = address.to_bytes(4, "little")
            exheader[offset + 4:offset + 8] = pages.to_bytes(4, "little")
            exheader[offset + 8:offset + 12] = size.to_bytes(4, "little")
        self.exheader_path.write_bytes(exheader)
        self.code = bytes((i * 7 + 1) & 0xFF for i in range(0x3000))
        self.code_path.write_bytes(self.code)
        FakeCapstone.partial = False

    def test_arm_range_reports_contiguous_instruction_coverage(self):
        report = disassembler.disassemble_retail_range(
            "ultra-sun", self.exheader_path, self.code_path, "arm",
            0x00100000, 8, self.report_path, capstone_module=FakeCapstone,
        )
        stored = json.loads(self.report_path.read_text(encoding="utf-8"))
        self.assertEqual(2, len(report["instructions"]))
        self.assertEqual("0x00100000", report["instructions"][0]["address"])
        self.assertEqual("01080f16", report["instructions"][0]["bytes_hex"])
        self.assertEqual(stored["instructions"], report["instructions"])
        self.assertTrue(report["verification"]["decoded_bytes_equal_requested_range"])

    def test_thumb_range_uses_thumb_instruction_alignment(self):
        report = disassembler.disassemble_retail_range(
            "ultra-sun", self.exheader_path, self.code_path, "thumb",
            0x00100002, 6, self.report_path, capstone_module=FakeCapstone,
        )
        self.assertEqual(3, len(report["instructions"]))
        self.assertEqual("thumb", report["range"]["state"])
        self.assertEqual(6, sum(item["size_bytes"] for item in report["instructions"]))

    def test_rejects_range_outside_declared_text_size(self):
        with self.assertRaisesRegex(disassembler.RetailDisassemblyError, "outside declared text"):
            disassembler.disassemble_retail_range(
                "ultra-sun", self.exheader_path, self.code_path, "arm",
                0x0010007C, 8, self.report_path, capstone_module=FakeCapstone,
            )
        self.assertFalse(self.report_path.exists())

    def test_rejects_bad_alignment(self):
        with self.assertRaisesRegex(disassembler.RetailDisassemblyError, "aligned to 4"):
            disassembler.disassemble_retail_range(
                "ultra-sun", self.exheader_path, self.code_path, "arm",
                0x00100002, 4, self.report_path, capstone_module=FakeCapstone,
            )
        self.assertFalse(self.report_path.exists())

    def test_requires_exact_decoder_coverage(self):
        FakeCapstone.partial = True
        with self.assertRaisesRegex(disassembler.RetailDisassemblyError, "covered 4 of 8 bytes"):
            disassembler.disassemble_retail_range(
                "ultra-sun", self.exheader_path, self.code_path, "arm",
                0x00100000, 8, self.report_path, capstone_module=FakeCapstone,
            )
        self.assertFalse(self.report_path.exists())

    def test_report_must_be_outside_repository(self):
        with self.assertRaisesRegex(disassembler.RetailDisassemblyError, "outside the repository"):
            disassembler.disassemble_retail_range(
                "ultra-sun", self.exheader_path, self.code_path, "arm",
                0x00100000, 8, ROOT / "private-disassembly.json", capstone_module=FakeCapstone,
            )
        self.assertFalse((ROOT / "private-disassembly.json").exists())


if __name__ == "__main__":
    unittest.main()
