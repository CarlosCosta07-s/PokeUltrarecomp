"""Synthetic tests for the local-only 3DS code ELF analysis wrapper."""
import struct
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import wrap_retail_code as wrapper  # noqa: E402


class WrapRetailCodeTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="wrap-retail-code-")
        self.addCleanup(self.temporary.cleanup)
        self.work = Path(self.temporary.name)
        self.exheader_path = self.work / "synthetic.exheader"
        self.code_path = self.work / "synthetic.code"
        self.output_path = self.work / "analysis.elf"

        exheader = bytearray(0x208)
        exheader[0:8] = b"TestGame"
        exheader[0x200:0x208] = int("00040000001B5000", 16).to_bytes(8, "little")
        segments = (
            (0x00100000, 1, 0x80),
            (0x00200000, 1, 0x40),
            (0x00300000, 1, 0x20),
        )
        for (address, pages, size), offset in zip(segments, (0x10, 0x20, 0x30)):
            exheader[offset:offset + 4] = address.to_bytes(4, "little")
            exheader[offset + 4:offset + 8] = pages.to_bytes(4, "little")
            exheader[offset + 8:offset + 12] = size.to_bytes(4, "little")
        exheader[0x3C:0x40] = (0x60).to_bytes(4, "little")
        self.exheader_path.write_bytes(exheader)
        self.code = bytes((index * 17 + 3) & 0xFF for index in range(0x3000))
        self.code_path.write_bytes(self.code)

    def test_builds_arm_elf_and_preserves_file_backed_bytes(self):
        report = wrapper.build_analysis_elf(
            "ultra-sun", self.exheader_path, self.code_path, self.output_path,
            confirm_decompressed=True,
        )
        elf = self.output_path.read_bytes()
        header = struct.unpack("<16sHHIIIIIHHHHHH", elf[:52])
        self.assertEqual(b"\x7fELF", header[0][:4])
        self.assertEqual(1, header[0][4])  # ELFCLASS32
        self.assertEqual(1, header[0][5])  # little endian
        self.assertEqual(40, header[2])  # EM_ARM
        self.assertEqual(0x00100000, header[4])
        self.assertEqual(3, header[10])
        self.assertEqual(0x1000, report["memory"]["code_payload_offset_in_elf"])
        self.assertEqual(len(self.code) + 0x1000, len(elf))
        self.assertEqual(self.code, elf[0x1000:])
        expected = (
            (0x1000, 0x00100000, 0x1000, 0x1000, 5),
            (0x2000, 0x00200000, 0x1000, 0x1000, 4),
            (0x3000, 0x00300000, 0x1000, 0x1060, 6),
        )
        for index, item in enumerate(expected):
            start = header[5] + index * header[9]
            phdr = struct.unpack("<IIIIIIII", elf[start:start + header[9]])
            self.assertEqual(1, phdr[0])  # PT_LOAD
            self.assertEqual(item, (phdr[1], phdr[2], phdr[4], phdr[5], phdr[6]))
            source_start = phdr[1] - 0x1000
            self.assertEqual(self.code[source_start:source_start + phdr[4]], elf[phdr[1]:phdr[1] + phdr[4]])
        self.assertTrue(report["verification"]["all_file_backed_segment_bytes_match_input"])
        self.assertFalse(report["output"]["elf_entry_is_game_entrypoint_proof"])

    def test_requires_explicit_confirmation_of_decompressed_input(self):
        with self.assertRaisesRegex(wrapper.RetailCodeWrapError, "confirm-decompressed"):
            wrapper.build_analysis_elf(
                "ultra-sun", self.exheader_path, self.code_path, self.output_path,
                confirm_decompressed=False,
            )
        self.assertFalse(self.output_path.exists())

    def test_rejects_output_inside_repository(self):
        with self.assertRaisesRegex(wrapper.RetailCodeWrapError, "outside the repository"):
            wrapper.build_analysis_elf(
                "ultra-sun", self.exheader_path, self.code_path, ROOT / "private-analysis.elf",
                confirm_decompressed=True,
            )
        self.assertFalse((ROOT / "private-analysis.elf").exists())

    def test_rejects_overwriting_an_input(self):
        with self.assertRaisesRegex(wrapper.RetailCodeWrapError, "must not overwrite"):
            wrapper.build_analysis_elf(
                "ultra-sun", self.exheader_path, self.code_path, self.code_path,
                confirm_decompressed=True,
            )
        self.assertTrue(self.code_path.exists())

    def test_unknown_program_id_requires_opt_in(self):
        exheader = bytearray(self.exheader_path.read_bytes())
        exheader[0x200:0x208] = int("0123456789ABCDEF", 16).to_bytes(8, "little")
        self.exheader_path.write_bytes(exheader)
        with self.assertRaisesRegex(wrapper.RetailCodeWrapError, "ACI Program ID is not recognized"):
            wrapper.build_analysis_elf(
                "ultra-sun", self.exheader_path, self.code_path, self.output_path,
                confirm_decompressed=True,
            )
        report = wrapper.build_analysis_elf(
            "ultra-sun", self.exheader_path, self.code_path, self.output_path,
            confirm_decompressed=True, allow_unverified_target=True,
        )
        self.assertEqual("unrecognized", report["identity"]["program_id_match"])

    def test_reports_compression_flag_without_claiming_to_decompress(self):
        exheader = bytearray(self.exheader_path.read_bytes())
        exheader[0x0D] = 1
        self.exheader_path.write_bytes(exheader)
        report = wrapper.build_analysis_elf(
            "ultra-sun", self.exheader_path, self.code_path, self.output_path,
            confirm_decompressed=True,
        )
        self.assertTrue(report["inputs"]["exheader_original_code_compressed_flag"])
        self.assertTrue(any("cannot independently prove" in warning for warning in report["warnings"]))

    def test_rejects_invalid_segment_allocation_via_preflight(self):
        exheader = bytearray(self.exheader_path.read_bytes())
        exheader[0x14:0x18] = (0).to_bytes(4, "little")
        self.exheader_path.write_bytes(exheader)
        with self.assertRaisesRegex(wrapper.RetailCodeWrapError, "preflight failed"):
            wrapper.build_analysis_elf(
                "ultra-sun", self.exheader_path, self.code_path, self.output_path,
                confirm_decompressed=True,
            )
        self.assertFalse(self.output_path.exists())


if __name__ == "__main__":
    unittest.main()
