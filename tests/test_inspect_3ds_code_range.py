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


def build_exheader(program_id="00040000001B5000", text_size=0x100, text_address=0x00100000):
    data = bytearray(0x800)
    data[0:8] = b"UltraSun"
    data[0x10:0x1C] = b"".join((
        text_address.to_bytes(4, "little"), (1).to_bytes(4, "little"),
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

    def test_decodes_a32_bl_as_call_and_reports_target_continuation(self):
        self.put_arm([0xEB000000, 0xE3A00001, 0xE12FFF1E])
        result = ranges.inspect_code_range(
            "ultra-sun", self.exheader, self.code, "arm", 0x00100000, 3,
            title_id="00040000001B5000",
        )
        call = result["instructions"][0]
        self.assertEqual("BL", call["mnemonic"])
        self.assertEqual(["call", "bl", 0], list(call["decoded_ir"]))
        self.assertEqual("0x00100004", call["link_register_value"])
        self.assertEqual("0x00100008", call["branch_target_virtual_address"])
        self.assertEqual("arm", call["branch_target_state"])
        self.assertTrue(call["branch_target_within_selected_range"])
        self.assertTrue(call["branch_target_is_scanned_instruction_start"])
        self.assertEqual("partial", result["dataflow"]["instructions"][0]["status"])
        self.assertEqual("BL", result["control_flow"]["unresolved_transfers"][0]["kind"])
        self.assertEqual("call-return-continuation", result["control_flow"]["edges"][0]["kind"])

    def test_decodes_a32_blx_immediate_and_tracks_thumb_target_state(self):
        for word, expected_target, expected_offset in (
            (0xFA000000, "0x00100008", 0),
            (0xFB000000, "0x0010000A", 2),
        ):
            with self.subTest(word=f"0x{word:08X}"):
                self.put_arm([word, 0xE3A00001, 0xE12FFF1E])
                result = ranges.inspect_code_range(
                    "ultra-sun", self.exheader, self.code, "arm", 0x00100000, 3,
                    title_id="00040000001B5000",
                )
                call = result["instructions"][0]
                self.assertEqual("BLX", call["mnemonic"])
                self.assertEqual(["call", "blx", expected_offset], list(call["decoded_ir"]))
                self.assertEqual("0x00100004", call["link_register_value"])
                self.assertEqual(expected_target, call["branch_target_virtual_address"])
                self.assertEqual("thumb", call["branch_target_state"])

    def test_decodes_a32_bx_and_blx_register_without_inventing_destinations(self):
        self.put_arm([0xE12FFF13, 0xE12FFF33, 0xE12FFF1E])
        result = ranges.inspect_code_range(
            "ultra-sun", self.exheader, self.code, "arm", 0x00100000, 3,
            title_id="00040000001B5000",
        )
        bx, blx = result["instructions"][:2]
        self.assertEqual("BX r3", bx["mnemonic"])
        self.assertEqual(["bx", 3], list(bx["decoded_ir"]))
        self.assertIsNone(bx["branch_target_virtual_address"])
        self.assertTrue(bx["indirect_branch"])
        self.assertEqual("BLX r3", blx["mnemonic"])
        self.assertEqual(["blx_reg", 3], list(blx["decoded_ir"]))
        self.assertIsNone(blx["branch_target_virtual_address"])
        self.assertEqual("0x00100008", blx["link_register_value"])
        self.assertTrue(blx["indirect_branch"])

    def test_decodes_a32_ldr_literal_pc_relative_address_without_reading_it(self):
        self.put_arm([0xE51F0004, 0xE3A01001, 0xE12FFF1E])
        result = ranges.inspect_code_range(
            "ultra-sun", self.exheader, self.code, "arm", 0x00100000, 3,
            title_id="00040000001B5000",
        )
        literal = result["instructions"][0]
        self.assertEqual("LDR r0, [pc, #-4]", literal["mnemonic"])
        self.assertEqual("0x00100004", literal["literal_pool_virtual_address"])
        self.assertEqual(4, literal["literal_width_bytes"])
        self.assertTrue(literal["literal_within_declared_text"])
        self.assertTrue(literal["literal_overlaps_selected_range"])
        self.assertTrue(literal["literal_is_scanned_instruction_start"])
        self.assertFalse(literal["literal_value_read"])
        self.assertTrue(any("literal referenced" in w for w in result["control_flow"]["warnings"]))

    def test_rejects_a32_literal_address_outside_uint32_without_wrapping(self):
        text_start = 0xFFFFE000
        self.exheader.write_bytes(build_exheader(text_size=0x1000, text_address=text_start))
        self.put_arm([0xE59F0FFF], offset=0x0FFC)
        with self.assertRaisesRegex(ranges.TargetRangeError, "A32 literal address.*outside the 32-bit"):
            ranges.inspect_code_range(
                "ultra-sun", self.exheader, self.code, "arm", text_start + 0x0FFC, 1,
                title_id="00040000001B5000",
            )

    def test_decodes_a32_word_and_byte_load_store_with_addressing_modes(self):
        # LDR r0,[r1,#4]; STRB r2,[r3,#-8]!; LDR r4,[r5],#-12
        self.put_arm([0xE5910004, 0xE5632008, 0xE415400C])
        result = ranges.inspect_code_range(
            "ultra-sun", self.exheader, self.code, "arm", 0x00100000, 3,
            title_id="00040000001B5000",
        )
        load, store, post = result["instructions"]
        self.assertEqual("LDR r0, [r1, #+4]", load["mnemonic"])
        self.assertEqual({
            "direction": "load", "width_bytes": 4, "sign_extend": False,
            "addressing_mode": "pre-indexed", "base_register": "r1",
            "data_register": "r0", "offset_register": None, "offset_bytes": 4,
            "base_register_writeback": False,
            "runtime_effective_address_resolved": False, "memory_value_read_by_inspector": False,
        }, load["memory_access"])
        self.assertEqual("STRB r2, [r3, #-8]!", store["mnemonic"])
        self.assertEqual("store", store["memory_access"]["direction"])
        self.assertEqual(1, store["memory_access"]["width_bytes"])
        self.assertTrue(store["memory_access"]["base_register_writeback"])
        self.assertEqual(-8, store["memory_access"]["offset_bytes"])
        self.assertEqual("LDR r4, [r5], #-12", post["mnemonic"])
        self.assertEqual("post-indexed", post["memory_access"]["addressing_mode"])
        self.assertTrue(post["memory_access"]["base_register_writeback"])
        self.assertEqual(-12, post["memory_access"]["offset_bytes"])
        load_effect, store_effect, post_effect = result["dataflow"]["instructions"]
        self.assertEqual("read", load_effect["memory"])
        self.assertEqual(["r1"], load_effect["registers_read"])
        self.assertEqual(["r0"], load_effect["registers_written"])
        self.assertEqual("write", store_effect["memory"])
        self.assertIn("r2", store_effect["registers_read"])
        self.assertIn("r3", store_effect["registers_written"])
        self.assertEqual("read", post_effect["memory"])
        self.assertIn("r5", post_effect["registers_written"])

    def test_a32_pc_relative_literal_keeps_literal_classification(self):
        self.put_arm([0xE51F0004])
        result = ranges.inspect_code_range(
            "ultra-sun", self.exheader, self.code, "arm", 0x00100000, 1,
            title_id="00040000001B5000",
        )
        instruction = result["instructions"][0]
        self.assertEqual("LDR r0, [pc, #-4]", instruction["mnemonic"])
        self.assertNotIn("memory_access", instruction)
        self.assertFalse(instruction["literal_value_read"])

    def test_rejects_unsupported_a32_memory_addressing_conservatively(self):
        # Register-offset form, unprivileged-transfer form, and writeback where
        # Rn==Rt are deliberately outside the current inspector subset.
        for word in (0xE7910002, 0xE4B10004, 0xE5B11004):
            with self.subTest(word=f"0x{word:08X}"):
                self.put_arm([word])
                with self.assertRaisesRegex(ranges.TargetRangeError, "unsupported instruction"):
                    ranges.inspect_code_range(
                        "ultra-sun", self.exheader, self.code, "arm", 0x00100000, 1,
                        title_id="00040000001B5000",
                    )

    def test_a32_load_to_pc_marks_indirect_branch_without_inventing_target(self):
        self.put_arm([0xE591F004])
        result = ranges.inspect_code_range(
            "ultra-sun", self.exheader, self.code, "arm", 0x00100000, 1,
            title_id="00040000001B5000",
        )
        instruction = result["instructions"][0]
        self.assertEqual("LDR pc, [r1, #+4]", instruction["mnemonic"])
        self.assertTrue(instruction["indirect_branch"])
        self.assertIsNone(instruction["branch_target_virtual_address"])
        effect = result["dataflow"]["instructions"][0]
        self.assertEqual("partial", effect["status"])
        self.assertEqual("indirect-branch", effect["control_flow"])
        self.assertEqual("read", effect["memory"])

    def test_decodes_a32_halfword_and_signed_load_immediate_forms(self):
        # LDRH r2,[r1,#0x23]; STRH r2,[r3,#-8]!; LDRSB r4,[r5],#-7; LDRSH r0,[r1,#2]
        self.put_arm([0xE1D122B3, 0xE16320B8, 0xE05540D7, 0xE1D100F2])
        result = ranges.inspect_code_range(
            "ultra-sun", self.exheader, self.code, "arm", 0x00100000, 4,
            title_id="00040000001B5000",
        )
        ldrh, strh, ldrsb, ldrsh = result["instructions"]
        self.assertEqual("LDRH r2, [r1, #+35]", ldrh["mnemonic"])
        self.assertEqual(2, ldrh["memory_access"]["width_bytes"])
        self.assertFalse(ldrh["memory_access"]["sign_extend"])
        self.assertEqual("STRH r2, [r3, #-8]!", strh["mnemonic"])
        self.assertTrue(strh["memory_access"]["base_register_writeback"])
        self.assertEqual(-8, strh["memory_access"]["offset_bytes"])
        self.assertEqual("LDRSB r4, [r5], #-7", ldrsb["mnemonic"])
        self.assertEqual(1, ldrsb["memory_access"]["width_bytes"])
        self.assertTrue(ldrsb["memory_access"]["sign_extend"])
        self.assertEqual("LDRSH r0, [r1, #+2]", ldrsh["mnemonic"])
        self.assertEqual(2, ldrsh["memory_access"]["width_bytes"])
        self.assertTrue(ldrsh["memory_access"]["sign_extend"])
        self.assertEqual(["read", "write", "read", "read"],
                         [item["memory"] for item in result["dataflow"]["instructions"]])

    def test_rejects_unsupported_a32_extra_load_store_conservatively(self):
        # Invalid writeback alias, unprivileged form, reserved signed-store encoding,
        # PC-based literal variants, and an extra-load form targeting SP.
        for word in (0xE1F11B04, 0xE0F120B4, 0xE1C120D3, 0xE1DF20B3, 0xE1D1DBB3):
            with self.subTest(word=f"0x{word:08X}"):
                self.put_arm([word])
                with self.assertRaisesRegex(ranges.TargetRangeError, "unsupported instruction"):
                    ranges.inspect_code_range(
                        "ultra-sun", self.exheader, self.code, "arm", 0x00100000, 1,
                        title_id="00040000001B5000",
                    )

    def test_decodes_a32_stack_multiple_transfer_prologue_epilogue(self):
        self.put_arm([0xE92D40F0, 0xE8BD80F0, 0xE12FFF1E])
        result = ranges.inspect_code_range(
            "ultra-sun", self.exheader, self.code, "arm", 0x00100000, 3,
            title_id="00040000001B5000",
        )
        push, pop = result["instructions"][:2]
        self.assertEqual("STMDB sp!, {r4, r5, r6, r7, lr}", push["mnemonic"])
        self.assertEqual(-20, push["stack_delta_bytes"])
        push_effect = result["dataflow"]["instructions"][0]
        self.assertEqual("write", push_effect["memory"])
        self.assertIn("lr", push_effect["registers_read"])
        self.assertIn("sp", push_effect["registers_written"])
        self.assertEqual("LDMIA sp!, {r4, r5, r6, r7, pc}", pop["mnemonic"])
        self.assertEqual(20, pop["stack_delta_bytes"])
        self.assertTrue(pop["indirect_branch"])
        self.assertIsNone(pop["branch_target_virtual_address"])
        pop_effect = result["dataflow"]["instructions"][1]
        self.assertEqual("read", pop_effect["memory"])
        self.assertIn("pc", pop_effect["registers_written"])
        self.assertEqual("return-or-indirect-branch", pop_effect["control_flow"])

    def test_rejects_a32_stack_multiple_transfer_lists_with_invalid_base_entries(self):
        for word in (0xE92D2000, 0xE92D8000, 0xE8BD2000):
            with self.subTest(word=f"0x{word:08X}"):
                self.put_arm([word])
                with self.assertRaisesRegex(ranges.TargetRangeError, "unsupported instruction"):
                    ranges.inspect_code_range(
                        "ultra-sun", self.exheader, self.code, "arm", 0x00100000, 1,
                        title_id="00040000001B5000",
                    )

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
 
    def test_thumb32_prefix_is_rejected_in_strict_mode_without_splitting(self):
        self.put_thumb([0xF000, 0x0000, 0x4770])
        with self.assertRaisesRegex(ranges.TargetRangeError, "unsupported 32-bit Thumb instruction"):
            ranges.inspect_code_range(
                "ultra-sun", self.exheader, self.code, "thumb", 0x00100000, 2,
                title_id="00040000001B5000",
            )

    def test_include_unsupported_groups_thumb32_and_keeps_following_instruction_aligned(self):
        self.put_thumb([0xF000, 0x0000, 0x4770])
        result = ranges.inspect_code_range(
            "ultra-sun", self.exheader, self.code, "thumb", 0x00100000, 2,
            title_id="00040000001B5000", include_unsupported=True,
        )
        self.assertEqual("partially-decoded-explicit-range", result["status"])
        self.assertEqual(6, result["range"]["byte_count"])
        first, second = result["instructions"]
        self.assertEqual("unsupported-thumb32", first["decode_status"])
        self.assertEqual(4, first["instruction_size_bytes"])
        self.assertEqual(["0xF000", "0x0000"], first["halfwords"])
        self.assertEqual("0x00100004", second["virtual_address"])
        self.assertEqual("decoded", second["decode_status"])
        self.assertEqual("BX LR", second["mnemonic"])

    def test_include_unsupported_records_unknown_thumb16_without_lying_about_mnemonic(self):
        self.put_thumb([0x46C0, 0x4770])
        result = ranges.inspect_code_range(
            "ultra-sun", self.exheader, self.code, "thumb", 0x00100000, 2,
            title_id="00040000001B5000", include_unsupported=True,
        )
        self.assertEqual("partially-decoded-explicit-range", result["status"])
        self.assertEqual("unsupported", result["instructions"][0]["decode_status"])
        self.assertIsNone(result["instructions"][0]["mnemonic"])
        self.assertIsNone(result["instructions"][0]["decoded_ir"])
        self.assertEqual("BX LR", result["instructions"][1]["mnemonic"])

    def test_include_unsupported_records_unknown_arm32_without_lying_about_mnemonic(self):
        self.put_arm([0xE1A00000, 0xE12FFF1E])
        result = ranges.inspect_code_range(
            "ultra-sun", self.exheader, self.code, "arm", 0x00100000, 2,
            title_id="00040000001B5000", include_unsupported=True,
        )
        self.assertEqual("partially-decoded-explicit-range", result["status"])
        self.assertEqual("unsupported", result["instructions"][0]["decode_status"])
        self.assertIsNone(result["instructions"][0]["mnemonic"])
        self.assertEqual("BX LR", result["instructions"][1]["mnemonic"])

    def test_thumb32_prefix_cannot_cross_declared_text_boundary(self):
        self.exheader.write_bytes(build_exheader(text_size=2))
        self.put_thumb([0xF000, 0x0000])
        with self.assertRaisesRegex(ranges.TargetRangeError, "crosses the declared .text boundary"):
            ranges.inspect_code_range(
                "ultra-sun", self.exheader, self.code, "thumb", 0x00100000, 1,
                title_id="00040000001B5000", include_unsupported=True,
            )


    def test_rejects_invalid_instruction_count(self):
        for count in (0, 257, True):
            with self.subTest(count=count), self.assertRaisesRegex(ranges.TargetRangeError, "instruction count"):
                ranges.inspect_code_range("ultra-sun", self.exheader, self.code, "thumb", 0x00100000, count)

    def test_rejects_unknown_instruction_state(self):
        with self.assertRaisesRegex(ranges.TargetRangeError, "instruction state"):
            ranges.inspect_code_range("ultra-sun", self.exheader, self.code, "thumb2", 0x00100000, 1)

    def inspect_thumb(self, count, **kwargs):
        return ranges.inspect_code_range(
            "ultra-sun", self.exheader, self.code, "thumb", 0x00100000, count,
            title_id="00040000001B5000", **kwargs,
        )

    def test_decodes_thumb_bl_pair_as_one_four_byte_call(self):
        self.put_thumb([0xF000, 0xF800, 0x4770])
        result = self.inspect_thumb(2)
        self.assertEqual("decoded-explicit-range", result["status"])
        self.assertEqual(6, result["range"]["byte_count"])
        call, ret = result["instructions"]
        self.assertEqual("BL", call["mnemonic"])
        self.assertEqual(4, call["instruction_size_bytes"])
        self.assertEqual("0xF000 0xF800", call["encoding"])
        self.assertEqual(["call", "bl", 0], list(call["decoded_ir"]))
        self.assertEqual("0x00100005", call["link_register_value"])
        self.assertEqual("0x00100004", call["branch_target_virtual_address"])
        self.assertEqual("thumb", call["branch_target_state"])
        self.assertTrue(call["branch_target_within_declared_text"])
        self.assertTrue(call["branch_target_within_selected_range"])
        self.assertTrue(call["branch_target_is_scanned_instruction_start"])
        self.assertEqual("0x00100004", ret["virtual_address"])
        self.assertEqual("BX LR", ret["mnemonic"])

    def test_blx_target_is_arm_state_and_never_counts_as_scanned_thumb_start(self):
        self.put_thumb([0xF000, 0xE800, 0x4770])   # target 0x00100004 is also a Thumb start
        call = self.inspect_thumb(2)["instructions"][0]
        self.assertEqual("BLX", call["mnemonic"])
        self.assertEqual("0x00100004", call["branch_target_virtual_address"])
        self.assertEqual("arm", call["branch_target_state"])
        self.assertTrue(call["branch_target_within_selected_range"])
        self.assertFalse(call["branch_target_is_scanned_instruction_start"])

    def test_blx_at_halfword_aligned_address_aligns_target_down(self):
        self.put_thumb([0x4770, 0xF000, 0xE800])
        call = self.inspect_thumb(2)["instructions"][1]
        self.assertEqual("0x00100002", call["virtual_address"])
        self.assertEqual("0x00100004", call["branch_target_virtual_address"])   # 0x100006 aligned down

    def test_bl_self_target_and_target_outside_text_are_reported(self):
        self.put_thumb([0x4770, 0xF7FF, 0xFFFE])   # "bl ." at 0x00100002
        call = self.inspect_thumb(2)["instructions"][1]
        self.assertEqual("0x00100002", call["branch_target_virtual_address"])
        self.assertTrue(call["branch_target_is_scanned_instruction_start"])
        self.put_thumb([0xF3FF, 0xFFFF])
        far = self.inspect_thumb(1)["instructions"][0]
        self.assertEqual("0x00500002", far["branch_target_virtual_address"])
        self.assertFalse(far["branch_target_within_declared_text"])
        self.assertFalse(far["branch_target_within_selected_range"])

    def test_call_target_below_address_zero_is_unsupported_not_wrapped(self):
        self.put_thumb([0xF400, 0xF800, 0x4770])   # raw target 0x100004 - 0x400000 < 0
        with self.assertRaisesRegex(ranges.TargetRangeError, "outside the 32-bit address space"):
            self.inspect_thumb(1)
        result = self.inspect_thumb(2, include_unsupported=True)
        first, second = result["instructions"]
        self.assertEqual("unsupported-thumb32", first["decode_status"])
        self.assertIsNone(first["mnemonic"])
        self.assertEqual("0x00100004", second["virtual_address"])
        self.assertEqual("BX LR", second["mnemonic"])

    def test_other_thumb32_pairs_are_not_mistaken_for_calls(self):
        for words in ([0xF000, 0xF000], [0xF000, 0xE801], [0xE800, 0xF800], [0xF800, 0xF800], [0xF000, 0xD000]):
            with self.subTest(words=[hex(w) for w in words]):
                self.put_thumb(words + [0x4770])
                with self.assertRaisesRegex(ranges.TargetRangeError, "unsupported 32-bit Thumb instruction"):
                    self.inspect_thumb(1)
                first, second = self.inspect_thumb(2, include_unsupported=True)["instructions"]
                self.assertEqual("unsupported-thumb32", first["decode_status"])
                self.assertEqual("BX LR", second["mnemonic"])

    def test_bl_exactly_at_text_end_decodes_but_next_pair_may_not_cross(self):
        self.exheader.write_bytes(build_exheader(text_size=4))
        self.put_thumb([0xF000, 0xF800])
        self.assertEqual("BL", self.inspect_thumb(1)["instructions"][0]["mnemonic"])
        with self.assertRaisesRegex(ranges.TargetRangeError, "extends beyond declared .text"):
            self.inspect_thumb(2)

    def test_arm_state_ignores_thumb_call_pairs(self):
        self.put_arm([0xF800F000])
        with self.assertRaisesRegex(ranges.TargetRangeError, "unsupported instruction at 0x00100000"):
            ranges.inspect_code_range("ultra-sun", self.exheader, self.code, "arm", 0x00100000, 1)

    def test_cli_reports_bl_call(self):
        self.put_thumb([0xF000, 0xF800, 0x4770])
        run = subprocess.run([
            sys.executable, str(ROOT / "tools" / "inspect_3ds_code_range.py"),
            "--target", "ultra-sun", "--exheader", str(self.exheader),
            "--code", str(self.code), "--state", "thumb",
            "--start-address", "0x00100000", "--instruction-count", "2",
            "--title-id", "00040000001B5000",
        ], capture_output=True, text=True)
        self.assertEqual(0, run.returncode, msg=run.stderr)
        first = json.loads(run.stdout)["instructions"][0]
        self.assertEqual("BL", first["mnemonic"])
        self.assertEqual(["call", "bl", 0], first["decoded_ir"])

    def test_decodes_bx_blx_register_and_pop_pc_without_inventing_targets(self):
        self.put_thumb([0x4718, 0x4790, 0xBD10, 0xBD03, 0xBD00, 0x4770])
        result = self.inspect_thumb(6)
        self.assertEqual("decoded-explicit-range", result["status"])
        bx, blx, pop1, pop2, pop3, ret = result["instructions"]
        self.assertEqual("BX r3", bx["mnemonic"])
        self.assertTrue(bx["indirect_branch"])
        self.assertFalse(bx["branch_links"])
        self.assertIsNone(bx["branch_target_virtual_address"])
        self.assertEqual("BLX r2", blx["mnemonic"])
        self.assertTrue(blx["branch_links"])
        self.assertEqual("0x00100005", blx["link_register_value"])   # (0x00100002 + 2) | 1
        self.assertEqual("POP {r4, pc}", pop1["mnemonic"])
        self.assertEqual("POP {r0, r1, pc}", pop2["mnemonic"])
        self.assertEqual("POP {pc}", pop3["mnemonic"])
        self.assertEqual(["pop_pc", 0x10], list(pop1["decoded_ir"]))
        self.assertEqual("BX LR", ret["mnemonic"])
        self.assertEqual(10, ret["decompressed_code_file_offset"] - result["range"]["decompressed_code_file_offset"])

    def test_indirect_flow_does_not_stop_the_linear_range(self):
        self.put_thumb([0x4718, 0x2001, 0x4770])
        result = self.inspect_thumb(3)
        self.assertEqual(["BX r3", "MOVS r0, #1", "BX LR"], [i["mnemonic"] for i in result["instructions"]])

    def test_pc_forms_and_pop_without_pc_stay_unsupported(self):
        for word in (0x4778, 0x47F8, 0x4701, 0xBC00, 0xB400, 0xB600):
            with self.subTest(word=hex(word)):
                self.put_thumb([word, 0x4770])
                with self.assertRaisesRegex(ranges.TargetRangeError, "unsupported instruction at 0x00100000"):
                    self.inspect_thumb(1)
                first, second = self.inspect_thumb(2, include_unsupported=True)["instructions"]
                self.assertEqual("unsupported", first["decode_status"])
                self.assertIsNone(first["mnemonic"])
                self.assertEqual("BX LR", second["mnemonic"])

    def test_arm_state_ignores_thumb_indirect_flow_encodings(self):
        self.put_arm([0x00004718])
        with self.assertRaisesRegex(ranges.TargetRangeError, "unsupported instruction"):
            ranges.inspect_code_range("ultra-sun", self.exheader, self.code, "arm", 0x00100000, 1)

    def test_decodes_push_pop_prologue_epilogue_with_stack_deltas(self):
        self.put_thumb([0xB5F0, 0xB401, 0xBC01, 0xB500, 0xBC30, 0xBDF0])
        result = self.inspect_thumb(6)
        self.assertEqual("decoded-explicit-range", result["status"])
        got = [(i["mnemonic"], i["stack_delta_bytes"]) for i in result["instructions"]]
        self.assertEqual([
            ("PUSH {r4, r5, r6, r7, lr}", -20), ("PUSH {r0}", -4), ("POP {r0}", 4),
            ("PUSH {lr}", -4), ("POP {r4, r5}", 8), ("POP {r4, r5, r6, r7, pc}", 20),
        ], got)
        self.assertEqual(["push", 0xF0, True], list(result["instructions"][0]["decoded_ir"]))
        self.assertEqual(["pop", 0x30], list(result["instructions"][4]["decoded_ir"]))
        for item in result["instructions"][:5]:
            self.assertNotIn("indirect_branch", item)
            self.assertNotIn("branch_target_virtual_address", item)
        self.assertTrue(result["instructions"][5]["indirect_branch"])

    def test_non_stack_instructions_have_no_stack_delta(self):
        self.put_thumb([0x2001, 0x4770])
        for item in self.inspect_thumb(2)["instructions"]:
            self.assertNotIn("stack_delta_bytes", item)

    def test_reports_literal_address_without_reading_the_value(self):
        self.put_thumb([0x4805, 0x4770, 0x4770])    # LDR r0,[pc,#20]; literal at 0x100004+0x14
        result = self.inspect_thumb(3)
        load = result["instructions"][0]
        self.assertEqual("LDR r0, [pc, #20]", load["mnemonic"])
        self.assertEqual(["ldr_literal", 0, 20], list(load["decoded_ir"]))
        self.assertEqual("0x00100018", load["literal_pool_virtual_address"])
        self.assertTrue(load["literal_within_declared_text"])
        self.assertFalse(load["literal_value_read"])
        self.assertFalse(load["literal_overlaps_selected_range"])
        self.assertFalse(load["literal_is_scanned_instruction_start"])
        for key in ("indirect_branch", "branch_target_virtual_address", "stack_delta_bytes"):
            self.assertNotIn(key, load)

    def test_literal_overlapping_the_scan_is_flagged_as_possible_data_decoded_as_code(self):
        self.put_thumb([0x4800, 0x4770, 0x4770])    # literal 0x00100004 is the third instruction
        load = self.inspect_thumb(3)["instructions"][0]
        self.assertEqual("0x00100004", load["literal_pool_virtual_address"])
        self.assertTrue(load["literal_overlaps_selected_range"])
        self.assertTrue(load["literal_is_scanned_instruction_start"])

    def test_literal_alignment_from_a_halfword_aligned_load(self):
        self.put_thumb([0x4770, 0x4A01])             # at 0x00100002: PC 0x100006 -> 0x100004, +4
        load = self.inspect_thumb(2)["instructions"][1]
        self.assertEqual("LDR r2, [pc, #4]", load["mnemonic"])
        self.assertEqual("0x00100008", load["literal_pool_virtual_address"])

    def test_literal_outside_or_straddling_declared_text_is_reported_not_rejected(self):
        self.put_thumb([0x4FFF])                      # literal 0x00100400, .text ends at 0x00100100
        far = self.inspect_thumb(1)["instructions"][0]
        self.assertEqual("0x00100400", far["literal_pool_virtual_address"])
        self.assertFalse(far["literal_within_declared_text"])
        self.assertFalse(far["literal_overlaps_selected_range"])
        self.exheader.write_bytes(build_exheader(text_size=6))   # literal 0x100004 needs bytes up to 0x100008
        self.put_thumb([0x4800, 0x4770, 0x4770])
        edge = self.inspect_thumb(3)["instructions"][0]
        self.assertFalse(edge["literal_within_declared_text"])
        self.exheader.write_bytes(build_exheader(text_size=8))
        self.assertTrue(self.inspect_thumb(3)["instructions"][0]["literal_within_declared_text"])

    def test_arm_state_does_not_interpret_thumb_literal_loads(self):
        self.put_arm([0x00004800])
        result = ranges.inspect_code_range(
            "ultra-sun", self.exheader, self.code, "arm", 0x00100000, 1,
            title_id="00040000001B5000", include_unsupported=True,
        )
        item = result["instructions"][0]
        self.assertNotIn("literal_pool_virtual_address", item)

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



    def test_control_flow_graph_reports_conditional_taken_and_fallthrough_edges(self):
        self.put_thumb([0xD100, 0x2001, 0x4770])  # BNE to BX LR; false path falls through MOVS.
        result = self.inspect_thumb(3)
        graph = result["control_flow"]
        self.assertEqual("candidate-cfg", graph["status"])
        self.assertEqual(3, graph["basic_block_count"])
        branch_edges = [edge for edge in graph["edges"] if edge["from_block"] == "B0"]
        self.assertEqual({"conditional-taken", "conditional-not-taken"}, {edge["kind"] for edge in branch_edges})
        self.assertEqual({"B1", "B2"}, {edge["to_block"] for edge in branch_edges})

    def test_formats_three_operand_thumb_add_and_sub_forms(self):
        self.put_thumb([0x1888, 0x1CC8, 0x1A88, 0x1EC8, 0x4770])
        result = self.inspect_thumb(5)
        self.assertEqual(
            ["ADDS r0, r1, r2", "ADDS r0, r1, #3", "SUBS r0, r1, r2", "SUBS r0, r1, #3", "BX LR"],
            [item["mnemonic"] for item in result["instructions"]],
        )

    def test_formats_thumb_immediate_shift_forms(self):
        self.put_thumb([0x07C8, 0x0913, 0x1025, 0x4770])
        result = self.inspect_thumb(4)
        self.assertEqual(
            ["LSL r0, r1, #31", "LSR r3, r2, #4", "ASR r5, r4, #0", "BX LR"],
            [item["mnemonic"] for item in result["instructions"]],
        )

    def test_formats_selected_thumb_data_processing_register_ops(self):
        self.put_thumb([0x4008, 0x4048, 0x4148, 0x4188, 0x4208, 0x4248, 0x4288, 0x42C8, 0x4308, 0x4388, 0x43C8, 0x4770])
        result = self.inspect_thumb(12)
        self.assertEqual(
            ["ANDS r0, r1", "EORS r0, r1", "ADCS r0, r1", "SBCS r0, r1", "TST r0, r1", "RSBS r0, r1, #0", "CMP r0, r1", "CMN r0, r1", "ORRS r0, r1", "BICS r0, r1", "MVNS r0, r1", "BX LR"],
            [item["mnemonic"] for item in result["instructions"]],
        )


    def test_formats_thumb_register_shifts_and_muls(self):
        self.put_thumb([0x4088, 0x40C8, 0x4108, 0x41C8, 0x4348, 0x4770])
        result = self.inspect_thumb(6)
        self.assertEqual(
            [
                "LSLS r0, r1", "LSRS r0, r1", "ASRS r0, r1",
                "RORS r0, r1", "MULS r0, r1", "BX LR",
            ],
            [item["mnemonic"] for item in result["instructions"]],
        )

    def test_formats_thumb_memory_accesses_and_reports_addressing_metadata(self):
        register_ops = [
            0x5000 | (opcode << 9) | (3 << 6) | (2 << 3) | 1
            for opcode in range(8)
        ]
        immediates = [
            0x6000 | (31 << 6) | (1 << 3), 0x6800 | (31 << 6) | (1 << 3),
            0x7000 | (31 << 6) | (1 << 3), 0x7800 | (31 << 6) | (1 << 3),
            0x8000 | (31 << 6) | (1 << 3), 0x8800 | (31 << 6) | (1 << 3),
            0x9000 | (7 << 8) | 0xFF, 0x9800 | (7 << 8) | 0xFF,
        ]
        words = register_ops + immediates + [0x4770]
        self.put_thumb(words)
        result = self.inspect_thumb(len(words))
        self.assertEqual([
            "STR r1, [r2, r3]", "STRH r1, [r2, r3]", "STRB r1, [r2, r3]",
            "LDRSB r1, [r2, r3]", "LDR r1, [r2, r3]", "LDRH r1, [r2, r3]",
            "LDRB r1, [r2, r3]", "LDRSH r1, [r2, r3]",
            "STR r0, [r1, #124]", "LDR r0, [r1, #124]",
            "STRB r0, [r1, #31]", "LDRB r0, [r1, #31]",
            "STRH r0, [r1, #62]", "LDRH r0, [r1, #62]",
            "STR r7, [sp, #1020]", "LDR r7, [sp, #1020]", "BX LR",
        ], [item["mnemonic"] for item in result["instructions"]])
        first = result["instructions"][0]["memory_access"]
        self.assertEqual("store", first["direction"])
        self.assertEqual(4, first["width_bytes"])
        self.assertEqual("register-offset", first["addressing_mode"])
        self.assertEqual("r2", first["base_register"])
        self.assertEqual("r3", first["offset_register"])
        self.assertFalse(first["runtime_effective_address_resolved"])
        signed_load = result["instructions"][3]["memory_access"]
        self.assertEqual(1, signed_load["width_bytes"])
        self.assertTrue(signed_load["sign_extend"])
        immediate_load = result["instructions"][9]["memory_access"]
        self.assertEqual(124, immediate_load["offset_bytes"])
        stack_load = result["instructions"][15]["memory_access"]
        self.assertEqual("sp-relative", stack_load["addressing_mode"])
        self.assertEqual(1020, stack_load["offset_bytes"])
        self.assertFalse(stack_load["memory_value_read_by_inspector"])
    def test_formats_thumb_adr_and_sp_adjustments_with_metadata(self):
        self.put_thumb([0xA001, 0xA901, 0xB001, 0xB081, 0x4770])
        result = self.inspect_thumb(5)
        self.assertEqual(
            ["ADR r0, [pc, #4]", "ADD r1, sp, #4", "ADD sp, #4", "SUB sp, #4", "BX LR"],
            [item["mnemonic"] for item in result["instructions"]],
        )
        adr = result["instructions"][0]["pc_relative_address"]
        self.assertEqual("0x00100004", adr["aligned_pc_base"])
        self.assertEqual("0x00100008", adr["target_virtual_address"])
        self.assertFalse(result["instructions"][1]["address_calculation"]["result_value_resolved"])
        self.assertEqual(4, result["instructions"][2]["stack_pointer_delta_bytes"])
        self.assertEqual(-4, result["instructions"][3]["stack_pointer_delta_bytes"])

    def test_formats_thumb_multiple_transfers_and_reports_register_list_metadata(self):
        self.put_thumb([0xC00E, 0xC80E, 0xC801, 0x4770])
        result = self.inspect_thumb(4)
        self.assertEqual(
            ["STMIA r0!, {r1, r2, r3}", "LDMIA r0!, {r1, r2, r3}", "LDMIA r0, {r0}", "BX LR"],
            [item["mnemonic"] for item in result["instructions"]],
        )
        stored = result["instructions"][0]["memory_access"]
        self.assertEqual("store", stored["direction"])
        self.assertEqual("multiple-increment-after", stored["addressing_mode"])
        self.assertEqual(["r1", "r2", "r3"], stored["registers"])
        self.assertEqual(3, stored["transfer_count"])
        self.assertEqual(12, stored["total_bytes"])
        self.assertTrue(stored["base_register_writeback"])
        self.assertFalse(stored["base_register_stored_value_unknown"])
        loaded = result["instructions"][1]["memory_access"]
        self.assertEqual("load", loaded["direction"])
        self.assertTrue(loaded["base_register_writeback"])
        base_in_list = result["instructions"][2]["memory_access"]
        self.assertTrue(base_in_list["base_register_in_list"])
        self.assertFalse(base_in_list["base_register_writeback"])
        self.assertFalse(base_in_list["memory_value_read_by_inspector"])

if __name__ == "__main__":
    unittest.main()
