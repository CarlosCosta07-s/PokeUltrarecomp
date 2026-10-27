"""Synthetic, clean-room tests for the ARM A32 subset demonstrator."""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import arm_subset_poc as poc  # noqa: E402


class DecoderTests(unittest.TestCase):
    def test_default_fixture_decodes_to_mov_sub_add_orr_eor_bic_mvn_and_return(self):
        decoded = [poc.decode_word(word) for word in poc.DEFAULT_WORDS]
        self.assertEqual(
            [("mov", 0, 12), ("sub", 0, 0, 8), ("add", 0, 0, 3), ("and", 0, 0, 7), ("orr", 0, 0, 8), ("eor", 0, 0, 1), ("bic", 0, 0, 2), ("mvn", 1, 0), ("and", 0, 1, 12), ("return",)],
            decoded,
        )

    def test_rotated_immediate_is_decoded(self):
        self.assertEqual(("mov", 0, 0x80000000), poc.decode_word(0xE3A00102))

    def test_decodes_conditional_instruction_as_predicated(self):
        self.assertEqual(
            ("predicated", "ne", ("mov", 0, 3)),
            poc.decode_word(0x13A00003),  # MOVNE r0, #3
        )

    def test_rejects_condition_f_for_data_processing(self):
        with self.assertRaisesRegex(poc.UnsupportedInstruction, "condition code 0xF"):
            poc.decode_word(0xF3A00003)

    def test_rejects_unsupported_register(self):
        with self.assertRaises(poc.UnsupportedInstruction):
            poc.decode_word(0xE3A04003)  # MOV r4, #3

    def test_decodes_adds_with_flags(self):
        self.assertEqual(("adds", 0, 0, 1), poc.decode_word(0xE2900001))

    def test_decodes_subs_with_flags(self):
        self.assertEqual(("subs", 0, 0, 1), poc.decode_word(0xE2500001))

    def test_decodes_cmn_immediate(self):
        self.assertEqual(("cmn", 0, 0x80000000), poc.decode_word(0xE3700102))

    def test_decodes_cmp_immediate(self):
        self.assertEqual(("cmp", 0, 1), poc.decode_word(0xE3500001))

    def test_decodes_unconditional_and_conditional_branches(self):
        self.assertEqual(("branch", "al", 0), poc.decode_word(0xEA000000))
        self.assertEqual(("branch", "eq", 1), poc.decode_word(0x0A000001))
        self.assertEqual(("branch", "ne", -1), poc.decode_word(0x1AFFFFFF))

    def test_rejects_branch_with_link(self):
        with self.assertRaisesRegex(poc.UnsupportedInstruction, "branch-with-link"):
            poc.decode_word(0xEB000000)

    def test_rejects_unsupported_branch_condition(self):
        with self.assertRaisesRegex(poc.UnsupportedInstruction, "branch condition"):
            poc.decode_word(0xFA000000)  # cond=0xF is not a valid A32 branch condition (BLX-immediate space)

    def test_rejects_unsupported_flag_setting_instruction(self):
        with self.assertRaisesRegex(poc.UnsupportedInstruction, "flag-setting form"):
            poc.decode_word(0xE3B00001)  # MOVS remains unsupported

    def test_rejects_cmn_without_s_bit(self):
        with self.assertRaisesRegex(poc.UnsupportedInstruction, "CMN requires"):
            poc.decode_word(0xE3600001)

    def test_rejects_cmp_without_s_bit(self):
        with self.assertRaisesRegex(poc.UnsupportedInstruction, "CMP requires"):
            poc.decode_word(0xE3400001)

    def test_rejects_noncanonical_cmp_destination(self):
        with self.assertRaisesRegex(poc.UnsupportedInstruction, "CMP encoding with Rd=0"):
            poc.decode_word(0xE3501001)

    def test_rejects_cmp_with_source_outside_supported_registers(self):
        with self.assertRaisesRegex(poc.UnsupportedInstruction, "source register r4"):
            poc.decode_word(0xE3540001)

    def test_rejects_noncanonical_cmn_destination(self):
        with self.assertRaisesRegex(poc.UnsupportedInstruction, "CMN encoding with Rd=0"):
            poc.decode_word(0xE3711001)

    def test_decodes_preindexed_immediate_word_byte_and_halfword_ldr_str(self):
        self.assertEqual(("ldr_imm", 0, 1, 4, True), poc.decode_word(0xE5910004))
        self.assertEqual(("str_imm", 2, 3, 8, False), poc.decode_word(0xE5032008))
        self.assertEqual(("ldrb_imm", 0, 1, 4, True), poc.decode_word(0xE5D10004))
        self.assertEqual(("strb_imm", 2, 3, 8, True), poc.decode_word(0xE5C32008))
        self.assertEqual(("ldrh_imm", 0, 1, 4, True), poc.decode_word(0xE1D100B4))
        self.assertEqual(("strh_imm", 2, 3, 8, True), poc.decode_word(0xE1C320B8))
        self.assertEqual(("ldrh_imm", 0, 1, 4, False), poc.decode_word(0xE15100B4))

    def test_rejects_unsupported_a32_single_and_halfword_data_transfer_forms(self):
        cases = (
            (0xE7910004, "register-offset memory access"),
            (0xE4910004, "post-indexed or writeback memory access"),
            (0xE5B10004, "post-indexed or writeback memory access"),
            (0xE5914004, "destination register r4"),
            (0xE5940004, "base register r4"),
            (0xE19100B2, "register-offset halfword memory access"),
            (0xE0D100B4, "post-indexed or writeback halfword memory access"),
            (0xE1F100B4, "post-indexed or writeback halfword memory access"),
            (0xE1D140B4, "destination register r4"),
            (0xE1D400B4, "base register r4"),
            (0xE1D000D0, "signed or doubleword A32 extra memory transfer"),
        )
        for word, message in cases:
            with self.subTest(word=f"0x{word:08X}"), self.assertRaisesRegex(poc.UnsupportedInstruction, message):
                poc.decode_word(word)

    def test_translator_requires_explicit_memory_model_for_all_supported_memory_widths(self):
        for word in (0xE5802004, 0xE5C02004, 0xE1C020B4):
            with self.subTest(word=f"0x{word:08X}"), self.assertRaisesRegex(poc.UnsupportedInstruction, "runtime_memory_io=True"):
                poc.translate([word, 0xE12FFF1E])

    def test_decodes_plain_register_operand_data_processing(self):
        cases = (
            (0xE1A01000, ("mov_reg", 1, 0)),
            (0xE1E01000, ("mvn_reg", 1, 0)),
            (0xE0000001, ("and_reg", 0, 0, 1)),
            (0xE1800001, ("orr_reg", 0, 0, 1)),
            (0xE0200001, ("eor_reg", 0, 0, 1)),
            (0xE1C00001, ("bic_reg", 0, 0, 1)),
            (0xE0800001, ("add_reg", 0, 0, 1)),
            (0xE0900001, ("adds_reg", 0, 0, 1)),
            (0xE0400001, ("sub_reg", 0, 0, 1)),
            (0xE0500001, ("subs_reg", 0, 0, 1)),
            (0xE1700001, ("cmn_reg", 0, 1)),
            (0xE1500001, ("cmp_reg", 0, 1)),
        )
        for word, expected in cases:
            with self.subTest(word=f"0x{word:08X}"):
                self.assertEqual(expected, poc.decode_word(word))

    def test_decodes_register_logical_flag_and_test_operations(self):
        cases = (
            (0xE1B00001, ("movs_reg", 0, 1)),
            (0xE1F00001, ("mvns_reg", 0, 1)),
            (0xE0100001, ("ands_reg", 0, 0, 1)),
            (0xE1900001, ("orrs_reg", 0, 0, 1)),
            (0xE0300001, ("eors_reg", 0, 0, 1)),
            (0xE1D00001, ("bics_reg", 0, 0, 1)),
            (0xE1100001, ("tst_reg", 0, 1)),
            (0xE1300001, ("teq_reg", 0, 1)),
        )
        for word, expected in cases:
            with self.subTest(word=f"0x{word:08X}"):
                self.assertEqual(expected, poc.decode_word(word))

    def test_rejects_register_tst_without_s_bit_and_noncanonical_rd(self):
        with self.assertRaisesRegex(poc.UnsupportedInstruction, "TST requires"):
            poc.decode_word(0xE1000001)
        with self.assertRaisesRegex(poc.UnsupportedInstruction, "TEQ register encoding with Rd=0"):
            poc.decode_word(0xE1311001)

    def test_predicates_plain_register_operand_instructions(self):
        self.assertEqual(
            ("predicated", "ne", ("mov_reg", 0, 1)),
            poc.decode_word(0x11A00001),
        )

    def test_rejects_register_operand_shifts_and_flag_setting_logic(self):
        with self.assertRaisesRegex(poc.UnsupportedInstruction, "register Operand2 shifts"):
            poc.decode_word(0xE0800081)  # ADD r0,r0,r1,LSL #1
        with self.assertRaisesRegex(poc.UnsupportedInstruction, "flag-setting form"):
            poc.decode_word(0xE3B00001)  # MOVS immediate remains outside this register-only extension

    def test_rejects_register_operand_registers_outside_r0_to_r3(self):
        with self.assertRaisesRegex(poc.UnsupportedInstruction, "source register r4"):
            poc.decode_word(0xE0800004)  # ADD r0,r0,r4
        with self.assertRaisesRegex(poc.UnsupportedInstruction, "destination register r4"):
            poc.decode_word(0xE1A04001)  # MOV r4,r1

    def test_rejects_noncanonical_register_cmp_and_mov(self):
        with self.assertRaisesRegex(poc.UnsupportedInstruction, "CMP register encoding with Rd=0"):
            poc.decode_word(0xE1511001)  # Rd=1 is noncanonical for CMP
        with self.assertRaisesRegex(poc.UnsupportedInstruction, "canonical MOV register encoding with Rn=0"):
            poc.decode_word(0xE1A10001)

    def test_decodes_sub_immediate(self):
        self.assertEqual(("sub", 0, 0, 3), poc.decode_word(0xE2400003))

    def test_decodes_and_immediate(self):
        self.assertEqual(("and", 0, 0, 7), poc.decode_word(0xE2000007))

    def test_rejects_and_with_source_outside_supported_registers(self):
        with self.assertRaisesRegex(poc.UnsupportedInstruction, "source register r4"):
            poc.decode_word(0xE2040001)  # AND r0, r4, #1

    def test_decodes_orr_immediate(self):
        self.assertEqual(("orr", 0, 0, 8), poc.decode_word(0xE3800008))

    def test_rejects_orr_with_source_outside_supported_registers(self):
        with self.assertRaisesRegex(poc.UnsupportedInstruction, "source register r4"):
            poc.decode_word(0xE3840001)  # ORR r0, r4, #1

    def test_decodes_eor_immediate(self):
        self.assertEqual(("eor", 0, 0, 1), poc.decode_word(0xE2200001))

    def test_rejects_eor_with_source_outside_supported_registers(self):
        with self.assertRaisesRegex(poc.UnsupportedInstruction, "source register r4"):
            poc.decode_word(0xE2240001)  # EOR r0, r4, #1

    def test_decodes_bic_immediate(self):
        self.assertEqual(("bic", 0, 0, 2), poc.decode_word(0xE3C00002))

    def test_rejects_bic_with_source_outside_supported_registers(self):
        with self.assertRaisesRegex(poc.UnsupportedInstruction, "source register r4"):
            poc.decode_word(0xE3C40002)  # BIC r0, r4, #2

    def test_decodes_mvn_immediate(self):
        self.assertEqual(("mvn", 1, 0), poc.decode_word(0xE3E01000))

    def test_rejects_mvn_with_noncanonical_rn(self):
        with self.assertRaisesRegex(poc.UnsupportedInstruction, "canonical MVN"):
            poc.decode_word(0xE3E11000)  # Noncanonical Rn=1

    def test_rejects_sub_with_source_outside_supported_registers(self):
        with self.assertRaisesRegex(poc.UnsupportedInstruction, "source register r4"):
            poc.decode_word(0xE2440001)  # SUB r0, r4, #1


class TranslationTests(unittest.TestCase):
    def test_emits_c_with_expected_operations(self):
        source = poc.translate(list(poc.DEFAULT_WORDS))
        self.assertIn("r0 = UINT32_C(12);", source)
        self.assertIn("r0 = (uint32_t)(r0 - UINT32_C(8));", source)
        self.assertIn("r0 = (uint32_t)(r0 + UINT32_C(3));", source)
        self.assertIn("r0 = (uint32_t)(r0 & UINT32_C(7));", source)
        self.assertIn("r0 = (uint32_t)(r0 | UINT32_C(8));", source)
        self.assertIn("r0 = (uint32_t)(r0 ^ UINT32_C(1));", source)
        self.assertIn("r0 = (uint32_t)(r0 & ~UINT32_C(2));", source)
        self.assertIn("r1 = (uint32_t)~UINT32_C(0);", source)
        self.assertIn("r0 = (uint32_t)(r1 & UINT32_C(12));", source)
        self.assertIn("return r0;", source)

    def test_emits_register_operand_c_operations(self):
        source = poc.translate([
            0xE1A01000,  # MOV r1,r0
            0xE1E02001,  # MVN r2,r1
            0xE0000001,  # AND r0,r0,r1
            0xE1800001,  # ORR r0,r0,r1
            0xE0200001,  # EOR r0,r0,r1
            0xE1C00001,  # BIC r0,r0,r1
            0xE0800001,  # ADD r0,r0,r1
            0xE0400001,  # SUB r0,r0,r1
            0xE12FFF1E,
        ])
        self.assertIn("r1 = r0;", source)
        self.assertIn("r2 = (uint32_t)~r1;", source)
        self.assertIn("r0 = (uint32_t)(r0 & r1);", source)
        self.assertIn("r0 = (uint32_t)(r0 | r1);", source)
        self.assertIn("r0 = (uint32_t)(r0 ^ r1);", source)
        self.assertIn("r0 = (uint32_t)(r0 & ~r1);", source)
        self.assertIn("r0 = (uint32_t)(r0 + r1);", source)
        self.assertIn("r0 = (uint32_t)(r0 - r1);", source)

    def test_plain_register_operations_execute_natively_and_preserve_nzcv(self):
        compiler = next((shutil.which(name) for name in (os.environ.get("CC", ""), "cc", "gcc", "clang") if name and shutil.which(name)), None)
        if not compiler:
            self.skipTest("no C compiler found; register-operation proof requires cc, gcc, or clang")

        operations = (
            ("mov_register", [0xE3A0000F, 0xE3A01005, 0xE1A00001, 0xE12FFF1E], 5),
            ("mvn_register", [0xE3A0000F, 0xE3A01005, 0xE1E00001, 0xE12FFF1E], 0xFFFFFFFA),
            ("and_register", [0xE3A0000F, 0xE3A01005, 0xE0000001, 0xE12FFF1E], 5),
            ("orr_register", [0xE3A0000F, 0xE3A01005, 0xE1800001, 0xE12FFF1E], 15),
            ("eor_register", [0xE3A0000F, 0xE3A01005, 0xE0200001, 0xE12FFF1E], 10),
            ("bic_register", [0xE3A0000F, 0xE3A01005, 0xE1C00001, 0xE12FFF1E], 10),
            ("add_register", [0xE3A00007, 0xE3A01005, 0xE0800001, 0xE12FFF1E], 12),
            ("sub_register", [0xE3A0000F, 0xE3A01005, 0xE0400001, 0xE12FFF1E], 10),
        )
        sources = []
        checks = []
        for name, words, expected in operations:
            generated = poc.translate(words, initial_nzcv=0xB)
            sources.append(generated.replace("uint32_t synthetic_entry(", f"uint32_t {name}("))
            checks.append(
                f"    {{ uint8_t flags = 0; if ({name}(&flags) != UINT32_C({expected}) || flags != UINT8_C(11)) return {len(checks)+1}; }}"
            )
        harness = chr(10).join(sources) + chr(10) + "int main(void) {" + chr(10) + chr(10).join(checks) + chr(10) + "    return 0;" + chr(10) + "}" + chr(10)
        with tempfile.TemporaryDirectory() as directory:
            src = Path(directory) / "register_operations.c"
            exe = Path(directory) / ("register_operations.exe" if os.name == "nt" else "register_operations")
            src.write_text(harness, encoding="utf-8")
            compiled = subprocess.run([compiler, str(src), "-std=c11", "-Wall", "-Wextra", "-Werror", "-o", str(exe)], capture_output=True, text=True)
            self.assertEqual(0, compiled.returncode, msg=compiled.stdout + compiled.stderr)
            executed = subprocess.run([str(exe)], capture_output=True, text=True)
            self.assertEqual(0, executed.returncode, msg=executed.stdout + executed.stderr)

    def test_register_logical_flags_preserve_carry_and_overflow(self):
        compiler = next((shutil.which(name) for name in (os.environ.get("CC", ""), "cc", "gcc", "clang") if name and shutil.which(name)), None)
        if not compiler:
            self.skipTest("no C compiler found; logical NZCV proof requires cc, gcc, or clang")
        operations = (
            ("movs_register", [0xE3A0000F, 0xE3A01005, 0xE1B00001, 0xE12FFF1E], 5, 3),
            ("mvns_register", [0xE3A0000F, 0xE3A01005, 0xE1F00001, 0xE12FFF1E], 0xFFFFFFFA, 11),
            ("ands_register", [0xE3A00102, 0xE3A01102, 0xE0100001, 0xE12FFF1E], 0x80000000, 11),
            ("orrs_register", [0xE3A00102, 0xE3A01000, 0xE1900001, 0xE12FFF1E], 0x80000000, 11),
            ("eors_register", [0xE3A00005, 0xE3A01005, 0xE0300001, 0xE12FFF1E], 0, 7),
            ("bics_register", [0xE3A0000F, 0xE3A01005, 0xE1D00001, 0xE12FFF1E], 10, 3),
            ("tst_register", [0xE3A00000, 0xE3A01001, 0xE1100001, 0xE12FFF1E], 0, 7),
            ("teq_register", [0xE3A0000F, 0xE3A01005, 0xE1300001, 0xE12FFF1E], 15, 3),
        )
        sources = []
        checks = []
        for name, words, expected, expected_flags in operations:
            generated = poc.translate(words, initial_nzcv=0xB)
            sources.append(generated.replace("uint32_t synthetic_entry(", f"uint32_t {name}("))
            checks.append(
                f"    {{ uint8_t flags = 0; if ({name}(&flags) != UINT32_C({expected}) || flags != UINT8_C({expected_flags})) return {len(checks)+1}; }}"
            )
        harness = chr(10).join(sources) + chr(10) + "int main(void) {" + chr(10) + chr(10).join(checks) + chr(10) + "    return 0;" + chr(10) + "}" + chr(10)
        with tempfile.TemporaryDirectory() as directory:
            src = Path(directory) / "register_logical_flags.c"
            exe = Path(directory) / ("register_logical_flags.exe" if os.name == "nt" else "register_logical_flags")
            src.write_text(harness, encoding="utf-8")
            compiled = subprocess.run([compiler, str(src), "-std=c11", "-Wall", "-Wextra", "-Werror", "-o", str(exe)], capture_output=True, text=True)
            self.assertEqual(0, compiled.returncode, msg=compiled.stdout + compiled.stderr)
            executed = subprocess.run([str(exe)], capture_output=True, text=True)
            self.assertEqual(0, executed.returncode, msg=executed.stdout + executed.stderr)

    def test_a32_ldr_str_use_bounded_little_endian_guest_memory(self):
        compiler = next((shutil.which(name) for name in (os.environ.get("CC", ""), "cc", "gcc", "clang") if name and shutil.which(name)), None)
        if not compiler:
            self.skipTest("no C compiler found; A32 bounded-memory proof requires cc, gcc, or clang")
        generated = poc.translate(
            [0xE5802004, 0xE5903004, 0xE12FFF1E],  # STR r2,[r0,#4]; LDR r3,[r0,#4]; BX LR
            max_execution_steps=8,
            runtime_state_io=True,
            runtime_memory_io=True,
        )
        harness = generated + chr(10) + """
#include <stddef.h>
int main(void) {
    uint32_t registers[4] = { UINT32_C(0x1000), UINT32_C(0x11111111), UINT32_C(0xA1B2C3D4), UINT32_C(0x33333333) };
    uint32_t output[4] = { 0U, 0U, 0U, 0U };
    uint8_t memory[16];
    for (size_t i = 0; i < sizeof(memory); ++i) memory[i] = UINT8_C(0xEE);
    uint8_t flags = 0U, status = UINT8_C(0xFF);
    uint32_t steps = 0U;
    uint32_t result = synthetic_entry_bounded(registers, UINT8_C(0xB), &flags, &steps, &status,
        output, memory, UINT32_C(0x1000), ((uint32_t)sizeof(memory)));
    return result == UINT32_C(0x1000) && flags == UINT8_C(0xB)
        && status == UINT8_C(0) && steps == UINT32_C(3)
        && output[0] == UINT32_C(0x1000) && output[2] == UINT32_C(0xA1B2C3D4)
        && output[3] == UINT32_C(0xA1B2C3D4)
        && memory[4] == UINT8_C(0xD4) && memory[5] == UINT8_C(0xC3)
        && memory[6] == UINT8_C(0xB2) && memory[7] == UINT8_C(0xA1) ? 0 : 1;
}
"""
        with tempfile.TemporaryDirectory() as directory:
            src = Path(directory) / "a32_bounded_memory.c"
            exe = Path(directory) / ("a32_bounded_memory.exe" if os.name == "nt" else "a32_bounded_memory")
            src.write_text(harness, encoding="utf-8")
            compiled = subprocess.run([compiler, str(src), "-std=c11", "-Wall", "-Wextra", "-Werror", "-o", str(exe)], capture_output=True, text=True)
            self.assertEqual(0, compiled.returncode, msg=compiled.stdout + compiled.stderr)
            executed = subprocess.run([str(exe)], capture_output=True, text=True)
            self.assertEqual(0, executed.returncode, msg=executed.stdout + executed.stderr)

    def test_a32_ldrb_strb_use_unaligned_byte_access_and_zero_extend(self):
        compiler = next((shutil.which(name) for name in (os.environ.get("CC", ""), "cc", "gcc", "clang") if name and shutil.which(name)), None)
        if not compiler:
            self.skipTest("no C compiler found; A32 byte-memory proof requires cc, gcc, or clang")
        generated = poc.translate(
            [0xE5C02005, 0xE5D03005, 0xE12FFF1E],  # STRB r2,[r0,#5]; LDRB r3,[r0,#5]; BX LR
            max_execution_steps=8,
            runtime_state_io=True,
            runtime_memory_io=True,
        )
        harness = generated + chr(10) + """
#include <stddef.h>
int main(void) {
    uint32_t registers[4] = { UINT32_C(0x1001), 0U, UINT32_C(0xA1B2C3D4), 0U };
    uint32_t output[4] = { 0U, 0U, 0U, 0U };
    uint8_t memory[16];
    for (size_t i = 0; i < sizeof(memory); ++i) memory[i] = UINT8_C(0xEE);
    uint8_t flags = 0U, status = UINT8_C(0xFF);
    uint32_t steps = 0U;
    uint32_t result = synthetic_entry_bounded(registers, UINT8_C(0xB), &flags, &steps, &status,
        output, memory, UINT32_C(0x1000), ((uint32_t)sizeof(memory)));
    return result == UINT32_C(0x1001) && flags == UINT8_C(0xB)
        && status == UINT8_C(0) && steps == UINT32_C(3)
        && output[0] == UINT32_C(0x1001) && output[3] == UINT32_C(0xD4)
        && memory[6] == UINT8_C(0xD4) && memory[5] == UINT8_C(0xEE)
        ? 0 : 1;
}
"""
        with tempfile.TemporaryDirectory() as directory:
            src = Path(directory) / "a32_bounded_byte_memory.c"
            exe = Path(directory) / ("a32_bounded_byte_memory.exe" if os.name == "nt" else "a32_bounded_byte_memory")
            src.write_text(harness, encoding="utf-8")
            compiled = subprocess.run([compiler, str(src), "-std=c11", "-Wall", "-Wextra", "-Werror", "-o", str(exe)], capture_output=True, text=True)
            self.assertEqual(0, compiled.returncode, msg=compiled.stdout + compiled.stderr)
            executed = subprocess.run([str(exe)], capture_output=True, text=True)
            self.assertEqual(0, executed.returncode, msg=executed.stdout + executed.stderr)

    def test_a32_ldrh_strh_use_bounded_aligned_little_endian_halfword_memory(self):
        compiler = next((shutil.which(name) for name in (os.environ.get("CC", ""), "cc", "gcc", "clang") if name and shutil.which(name)), None)
        if not compiler:
            self.skipTest("no C compiler found; A32 halfword-memory proof requires cc, gcc, or clang")
        generated = poc.translate(
            [0xE1C020B2, 0xE1D030B2, 0xE12FFF1E],  # STRH r2,[r0,#2]; LDRH r3,[r0,#2]; BX LR
            max_execution_steps=8,
            runtime_state_io=True,
            runtime_memory_io=True,
        )
        harness = generated + chr(10) + """
#include <stddef.h>
int main(void) {
    uint32_t registers[4] = { UINT32_C(0x1000), 0U, UINT32_C(0xA1B2C3D4), 0U };
    uint32_t output[4] = { 0U, 0U, 0U, 0U };
    uint8_t memory[16];
    for (size_t i = 0; i < sizeof(memory); ++i) memory[i] = UINT8_C(0xEE);
    uint8_t flags = 0U, status = UINT8_C(0xFF);
    uint32_t steps = 0U;
    uint32_t result = synthetic_entry_bounded(registers, UINT8_C(0xB), &flags, &steps, &status,
        output, memory, UINT32_C(0x1000), ((uint32_t)sizeof(memory)));
    return result == UINT32_C(0x1000) && flags == UINT8_C(0xB)
        && status == UINT8_C(0) && steps == UINT32_C(3)
        && output[0] == UINT32_C(0x1000) && output[2] == UINT32_C(0xA1B2C3D4)
        && output[3] == UINT32_C(0xC3D4)
        && memory[1] == UINT8_C(0xEE) && memory[2] == UINT8_C(0xD4)
        && memory[3] == UINT8_C(0xC3) && memory[4] == UINT8_C(0xEE) ? 0 : 1;
}
"""
        with tempfile.TemporaryDirectory() as directory:
            src = Path(directory) / "a32_bounded_halfword_memory.c"
            exe = Path(directory) / ("a32_bounded_halfword_memory.exe" if os.name == "nt" else "a32_bounded_halfword_memory")
            src.write_text(harness, encoding="utf-8")
            compiled = subprocess.run([compiler, str(src), "-std=c11", "-Wall", "-Wextra", "-Werror", "-o", str(exe)], capture_output=True, text=True)
            self.assertEqual(0, compiled.returncode, msg=compiled.stdout + compiled.stderr)
            executed = subprocess.run([str(exe)], capture_output=True, text=True)
            self.assertEqual(0, executed.returncode, msg=executed.stdout + executed.stderr)

    def test_a32_ldrh_rejects_unaligned_halfword_access(self):
        compiler = next((shutil.which(name) for name in (os.environ.get("CC", ""), "cc", "gcc", "clang") if name and shutil.which(name)), None)
        if not compiler:
            self.skipTest("no C compiler found; A32 halfword-alignment proof requires cc, gcc, or clang")
        generated = poc.translate(
            [0xE1D030B1, 0xE12FFF1E],  # LDRH r3,[r0,#1]; BX LR
            max_execution_steps=8,
            runtime_state_io=True,
            runtime_memory_io=True,
        )
        harness = generated + chr(10) + """
#include <stddef.h>
int main(void) {
    uint32_t registers[4] = { UINT32_C(0x1000), 0U, UINT32_C(0x12345678), 0U };
    uint32_t output[4] = { 0U, 0U, 0U, 0U };
    uint8_t memory[16];
    for (size_t i = 0; i < sizeof(memory); ++i) memory[i] = UINT8_C(0xEE);
    uint8_t flags = 0U, status = UINT8_C(0xFF);
    uint32_t steps = 0U;
    (void)synthetic_entry_bounded(registers, UINT8_C(0x6), &flags, &steps, &status,
        output, memory, UINT32_C(0x1000), ((uint32_t)sizeof(memory)));
    return status == UINT8_C(4) && steps == UINT32_C(1)
        && output[0] == UINT32_C(0x1000) && output[2] == UINT32_C(0x12345678)
        && flags == UINT8_C(0x6) ? 0 : 1;
}
"""
        with tempfile.TemporaryDirectory() as directory:
            src = Path(directory) / "a32_halfword_alignment.c"
            exe = Path(directory) / ("a32_halfword_alignment.exe" if os.name == "nt" else "a32_halfword_alignment")
            src.write_text(harness, encoding="utf-8")
            compiled = subprocess.run([compiler, str(src), "-std=c11", "-Wall", "-Wextra", "-Werror", "-o", str(exe)], capture_output=True, text=True)
            self.assertEqual(0, compiled.returncode, msg=compiled.stdout + compiled.stderr)
            executed = subprocess.run([str(exe)], capture_output=True, text=True)
            self.assertEqual(0, executed.returncode, msg=executed.stdout + executed.stderr)

    def test_a32_memory_faults_do_not_partially_modify_memory(self):
        compiler = next((shutil.which(name) for name in (os.environ.get("CC", ""), "cc", "gcc", "clang") if name and shutil.which(name)), None)
        if not compiler:
            self.skipTest("no C compiler found; A32 memory-fault proof requires cc, gcc, or clang")
        generated = poc.translate(
            [0xE5802004, 0xE12FFF1E],  # STR r2,[r0,#4]; BX LR
            max_execution_steps=8,
            runtime_state_io=True,
            runtime_memory_io=True,
        )
        harness = generated + chr(10) + """
#include <stddef.h>
static int run_fault(uint32_t base_register, uint32_t region_base, uint32_t region_size,
                     uint8_t expected_status, uint8_t *memory, uint8_t *saved_memory) {
    uint32_t registers[4] = { base_register, 0U, UINT32_C(0x11223344), 0U };
    uint32_t output[4] = { 0U, 0U, 0U, 0U };
    uint8_t flags = 0U, status = UINT8_C(0xFF);
    uint32_t steps = 0U;
    (void)synthetic_entry_bounded(registers, UINT8_C(0x6), &flags, &steps, &status,
        output, memory, region_base, region_size);
    for (size_t i = 0; i < region_size; ++i) if (memory[i] != saved_memory[i]) return 1;
    if (status != expected_status || steps != UINT32_C(1)
        || output[0] != base_register || output[2] != UINT32_C(0x11223344)
        || flags != UINT8_C(0x6)) return 2;
    return 0;
}
int main(void) {
    uint8_t memory[16], saved[16];
    for (size_t i = 0; i < sizeof(memory); ++i) memory[i] = UINT8_C(0xEE);
    for (size_t i = 0; i < sizeof(saved); ++i) saved[i] = UINT8_C(0xEE);
    if (run_fault(UINT32_C(0x1004), UINT32_C(0x1000), UINT32_C(8),
                  UINT8_C(3), memory, saved) != 0) return 1; /* bounds fault */
    if (run_fault(UINT32_C(0x1001), UINT32_C(0x1000), UINT32_C(16),
                  UINT8_C(4), memory, saved) != 0) return 2; /* alignment fault */
    if (run_fault(UINT32_C(0xFFFFFFFC), UINT32_C(0x1000), UINT32_C(16),
                  UINT8_C(3), memory, saved) != 0) return 3; /* address overflow */
    uint32_t registers[4] = { UINT32_C(0x1000), 0U, UINT32_C(0x12345678), 0U };
    uint32_t output[4] = { 0U, 0U, 0U, 0U };
    uint8_t flags = 0U, status = 0U;
    uint32_t steps = UINT32_C(99);
    (void)synthetic_entry_bounded(registers, UINT8_C(0x0), &flags, &steps, &status,
        output, memory, UINT32_C(0xFFFFFFF8), UINT32_C(16));
    if (status != UINT8_C(2) || steps != UINT32_C(0)) return 4; /* mapping overflow */
    return 0;
}
"""
        with tempfile.TemporaryDirectory() as directory:
            src = Path(directory) / "a32_memory_faults.c"
            exe = Path(directory) / ("a32_memory_faults.exe" if os.name == "nt" else "a32_memory_faults")
            src.write_text(harness, encoding="utf-8")
            compiled = subprocess.run([compiler, str(src), "-std=c11", "-Wall", "-Wextra", "-Werror", "-o", str(exe)], capture_output=True, text=True)
            self.assertEqual(0, compiled.returncode, msg=compiled.stdout + compiled.stderr)
            executed = subprocess.run([str(exe)], capture_output=True, text=True)
            self.assertEqual(0, executed.returncode, msg=executed.stdout + executed.stderr)

    def test_predicated_register_operand_respects_entry_nzcv(self):
        compiler = next((shutil.which(name) for name in (os.environ.get("CC", ""), "cc", "gcc", "clang") if name and shutil.which(name)), None)
        if not compiler:
            self.skipTest("no C compiler found; predicated register proof requires cc, gcc, or clang")
        words = [0xE3A00000, 0xE3A01009, 0x11A00001, 0xE12FFF1E]  # MOVNE r0,r1
        skipped = poc.translate(words, initial_nzcv=0x4).replace("uint32_t synthetic_entry(", "uint32_t movne_skipped(")
        executed = poc.translate(words, initial_nzcv=0x0).replace("uint32_t synthetic_entry(", "uint32_t movne_executed(")
        harness = chr(10).join((skipped, executed)) + chr(10) + """
int main(void) {
    uint8_t skipped_flags = 0, executed_flags = 0;
    return movne_skipped(&skipped_flags) == UINT32_C(0) && skipped_flags == UINT8_C(4)
        && movne_executed(&executed_flags) == UINT32_C(9) && executed_flags == UINT8_C(0)
        ? 0 : 1;
}
"""
        with tempfile.TemporaryDirectory() as directory:
            src = Path(directory) / "predicated_register.c"
            exe = Path(directory) / ("predicated_register.exe" if os.name == "nt" else "predicated_register")
            src.write_text(harness, encoding="utf-8")
            compiled = subprocess.run([compiler, str(src), "-std=c11", "-Wall", "-Wextra", "-Werror", "-o", str(exe)], capture_output=True, text=True)
            self.assertEqual(0, compiled.returncode, msg=compiled.stdout + compiled.stderr)
            executed_run = subprocess.run([str(exe)], capture_output=True, text=True)
            self.assertEqual(0, executed_run.returncode, msg=executed_run.stdout + executed_run.stderr)

    def test_register_add_sub_and_compare_flags_match_reference_when_compiler_exists(self):
        compiler = next((shutil.which(name) for name in (os.environ.get("CC", ""), "cc", "gcc", "clang") if name and shutil.which(name)), None)
        if not compiler:
            self.skipTest("no C compiler found; register-operand flag proof requires cc, gcc, or clang")
        add = poc.translate([
            0xE3A00007, 0xE3A01005, 0xE0900001, 0xE12FFF1E,
        ]).replace("uint32_t synthetic_entry(", "uint32_t adds_register(")
        sub = poc.translate([
            0xE3A00102, 0xE3A01001, 0xE0500001, 0xE12FFF1E,
        ]).replace("uint32_t synthetic_entry(", "uint32_t subs_register(")
        cmp = poc.translate([
            0xE3A00005, 0xE3A01005, 0xE1500001, 0xE12FFF1E,
        ]).replace("uint32_t synthetic_entry(", "uint32_t cmp_register(")
        cmn = poc.translate([
            0xE3E00000, 0xE3A01001, 0xE1700001, 0xE12FFF1E,
        ]).replace("uint32_t synthetic_entry(", "uint32_t cmn_register(")
        harness = "\n".join((add, sub, cmp, cmn)) + """
int main(void) {
    uint8_t add_flags = 255, sub_flags = 255, cmp_flags = 255, cmn_flags = 255;
    return adds_register(&add_flags) == UINT32_C(12) && add_flags == UINT8_C(0)
        && subs_register(&sub_flags) == UINT32_C(0x7fffffff) && sub_flags == UINT8_C(3)
        && cmp_register(&cmp_flags) == UINT32_C(5) && cmp_flags == UINT8_C(6)
        && cmn_register(&cmn_flags) == UINT32_C(0xffffffff) && cmn_flags == UINT8_C(6)
        ? 0 : 1;
}
"""
        with tempfile.TemporaryDirectory() as directory:
            src = Path(directory) / "register_arithmetic.c"
            exe = Path(directory) / ("register_arithmetic.exe" if os.name == "nt" else "register_arithmetic")
            src.write_text(harness, encoding="utf-8")
            result = subprocess.run([compiler, str(src), "-std=c11", "-Wall", "-Wextra", "-Werror", "-o", str(exe)], capture_output=True, text=True)
            self.assertEqual(0, result.returncode, msg=result.stdout + result.stderr)
            run = subprocess.run([str(exe)], capture_output=True, text=True)
            self.assertEqual(0, run.returncode, msg=run.stdout + run.stderr)

    def test_requires_bx_lr_as_final_instruction(self):
        with self.assertRaises(poc.UnsupportedInstruction):
            poc.translate([0xE3A00003])
        with self.assertRaises(poc.UnsupportedInstruction):
            poc.translate([0xE12FFF1E, 0xE3A00003])

    def test_enforces_instruction_limit(self):
        with self.assertRaises(poc.UnsupportedInstruction):
            poc.translate([0xE3A00003] * (poc.MAX_INSTRUCTIONS + 1))

    def test_rejects_branch_target_outside_fixture(self):
        with self.assertRaisesRegex(poc.UnsupportedInstruction, "out-of-range instruction"):
            poc.translate([0xEA000001, 0xE12FFF1E])

    def test_rejects_backward_or_self_targeting_branches_to_prevent_unbounded_loops(self):
        with self.assertRaisesRegex(poc.UnsupportedInstruction, "backward or self-targeting branch"):
            poc.translate([0xEAFFFFFE, 0xE12FFF1E])

    def test_rejects_branch_target_one_past_end_and_negative_target(self):
        with self.assertRaisesRegex(poc.UnsupportedInstruction, "out-of-range instruction 2"):
            poc.translate([0xEA000000, 0xE12FFF1E])  # target == len(words)
        with self.assertRaisesRegex(poc.UnsupportedInstruction, "out-of-range instruction -2"):
            poc.translate([0xEAFFFFFC, 0xE12FFF1E])  # target < 0

    def test_rejects_true_backward_branch(self):
        with self.assertRaisesRegex(poc.UnsupportedInstruction, "backward or self-targeting branch"):
            poc.translate([0xE3A00001, 0xE3A00002, 0xEAFFFFFD, 0xE12FFF1E])  # B at index 2 -> index 1

    def test_branch_codegen_and_sign_extension_without_compiler(self):
        self.assertEqual(("branch", "al", 0x7FFFFF), poc.decode_word(0xEA7FFFFF))
        self.assertEqual(("branch", "al", -0x800000), poc.decode_word(0xEA800000))
        beq = poc.translate([0x0A000000, 0xE3A00001, 0xE12FFF1E])
        self.assertIn("if (flag_z != 0U) goto arm_label_2;", beq)
        self.assertIn("arm_label_2: ;", beq)
        bne = poc.translate([0x1A000000, 0xE3A00001, 0xE12FFF1E])
        self.assertIn("if (flag_z == 0U) goto arm_label_2;", bne)
        self.assertIn("arm_label_2: ;", bne)

    def test_decodes_all_standard_branch_conditions(self):
        names = ["eq", "ne", "cs", "cc", "mi", "pl", "vs", "vc", "hi", "ls", "ge", "lt", "gt", "le"]
        for code, name in enumerate(names):
            with self.subTest(condition=name):
                self.assertEqual(("branch", name, 0), poc.decode_word((code << 28) | 0x0A000000))
        self.assertEqual(("branch", "al", 0), poc.decode_word(0xEA000000))

    def test_branches_and_data_predication_match_arm_condition_table_for_all_flag_states_when_compiler_exists(self):
        compiler = next((shutil.which(name) for name in (os.environ.get("CC", ""), "cc", "gcc", "clang") if name and shutil.which(name)), None)
        if not compiler:
            self.skipTest("no C compiler found; native branch proof requires cc, gcc, or clang")
        # Independent statement of the ARM condition table (ARM ARM, "Condition codes"),
        # written over booleans rather than copied from the translator's C expressions.
        spec = [
            lambda n, z, c, v: z,                      # EQ
            lambda n, z, c, v: not z,                  # NE
            lambda n, z, c, v: c,                      # CS
            lambda n, z, c, v: not c,                  # CC
            lambda n, z, c, v: n,                      # MI
            lambda n, z, c, v: not n,                  # PL
            lambda n, z, c, v: v,                      # VS
            lambda n, z, c, v: not v,                  # VC
            lambda n, z, c, v: c and not z,            # HI
            lambda n, z, c, v: (not c) or z,           # LS
            lambda n, z, c, v: n == v,                 # GE
            lambda n, z, c, v: n != v,                 # LT
            lambda n, z, c, v: (not z) and n == v,     # GT
            lambda n, z, c, v: z or n != v,            # LE
        ]
        sources = []
        checks = []
        for code, taken_for in enumerate(spec):
            # Bcc +0 targets the final BX LR; fall-through runs MOV r0,#1. Taken => r0 == 0.
            words = [(code << 28) | 0x0A000000, 0xE3A00001, 0xE12FFF1E]
            for nzcv in range(16):
                name = f"entry_c{code:X}_n{nzcv:X}"
                text = poc.translate(words, initial_nzcv=nzcv).replace("uint32_t synthetic_entry(", f"uint32_t {name}(")
                sources.append(text)
                n, z, c, v = (bool(nzcv & 8), bool(nzcv & 4), bool(nzcv & 2), bool(nzcv & 1))
                expected = 0 if taken_for(n, z, c, v) else 1
                checks.append(f"    {{ uint8_t f = 0; if (!({name}(&f) == UINT32_C({expected}) && f == UINT8_C({nzcv}))) bad++; }}")

                # Conditional data-processing must use the same condition truth table.
                pred_name = f"pred_entry_c{code:X}_n{nzcv:X}"
                predicated_words = [(code << 28) | 0x03A00001, 0xE12FFF1E]  # MOV{cond} r0,#1
                pred_source = poc.translate(predicated_words, initial_nzcv=nzcv).replace(
                    "uint32_t synthetic_entry(", f"uint32_t {pred_name}("
                )
                sources.append(pred_source)
                pred_expected = 1 if taken_for(n, z, c, v) else 0
                checks.append(
                    f"    {{ uint8_t f = 0; if (!({pred_name}(&f) == UINT32_C({pred_expected}) && f == UINT8_C({nzcv}))) bad++; }}"
                )
        harness = chr(10).join(sources) + chr(10) + "int main(void) {" + chr(10) + "    int bad = 0;" + chr(10) + chr(10).join(checks) + chr(10) + "    return bad;" + chr(10) + "}" + chr(10)
        with tempfile.TemporaryDirectory() as directory:
            src = Path(directory) / "conditions.c"
            exe = Path(directory) / ("conditions.exe" if os.name == "nt" else "conditions")
            src.write_text(harness, encoding="utf-8")
            result = subprocess.run([compiler, str(src), "-std=c11", "-Wall", "-Wextra", "-Werror", "-o", str(exe)], capture_output=True, text=True)
            self.assertEqual(0, result.returncode, msg=result.stdout + result.stderr)
            run = subprocess.run([str(exe)], capture_output=True, text=True)
            self.assertEqual(0, run.returncode, msg=f"{run.returncode} of {len(checks)} condition/flag cases mismatched")

    def test_predicated_flag_setting_updates_nzcv_only_when_condition_is_true(self):
        compiler = next((shutil.which(name) for name in (os.environ.get("CC", ""), "cc", "gcc", "clang") if name and shutil.which(name)), None)
        if not compiler:
            self.skipTest("no C compiler found; native predication proof requires cc, gcc, or clang")
        # ADDEQS r0,r0,#1: with Z=0 it is skipped and preserves entry NZCV=0x8;
        # with Z=1 it executes, producing r0=1 and NZCV=0.
        skipped = poc.translate([0x02900001, 0xE12FFF1E], initial_nzcv=0x8).replace(
            "uint32_t synthetic_entry(", "uint32_t predicated_skipped("
        )
        executed = poc.translate([0x02900001, 0xE12FFF1E], initial_nzcv=0x4).replace(
            "uint32_t synthetic_entry(", "uint32_t predicated_executed("
        )
        harness = chr(10).join((skipped, executed)) + chr(10) + """
int main(void) {
    uint8_t skipped_flags = 0;
    uint8_t executed_flags = 0;
    return predicated_skipped(&skipped_flags) == UINT32_C(0)
        && skipped_flags == UINT8_C(8)
        && predicated_executed(&executed_flags) == UINT32_C(1)
        && executed_flags == UINT8_C(0) ? 0 : 1;
}
"""
        with tempfile.TemporaryDirectory() as directory:
            src = Path(directory) / "predicated_flags.c"
            exe = Path(directory) / ("predicated_flags.exe" if os.name == "nt" else "predicated_flags")
            src.write_text(harness, encoding="utf-8")
            result = subprocess.run([compiler, str(src), "-std=c11", "-Wall", "-Wextra", "-Werror", "-o", str(exe)], capture_output=True, text=True)
            self.assertEqual(0, result.returncode, msg=result.stdout + result.stderr)
            run = subprocess.run([str(exe)], capture_output=True, text=True)
            self.assertEqual(0, run.returncode, msg=run.stdout + run.stderr)

    def test_predicated_cmp_preserves_or_updates_flags_according_to_condition(self):
        compiler = next((shutil.which(name) for name in (os.environ.get("CC", ""), "cc", "gcc", "clang") if name and shutil.which(name)), None)
        if not compiler:
            self.skipTest("no C compiler found; native conditional-CMP proof requires cc, gcc, or clang")
        # CMPEQ r0,#0 is skipped for entry NZCV=0x8 (Z=0), preserving N.
        # CMPNE r0,#0 executes for the same entry state, yielding Z=1 and C=1.
        skipped = poc.translate([0x03500000, 0xE12FFF1E], initial_nzcv=0x8).replace(
            "uint32_t synthetic_entry(", "uint32_t conditional_cmp_skipped("
        )
        executed = poc.translate([0x13500000, 0xE12FFF1E], initial_nzcv=0x8).replace(
            "uint32_t synthetic_entry(", "uint32_t conditional_cmp_executed("
        )
        harness = chr(10).join((skipped, executed)) + chr(10) + """
int main(void) {
    uint8_t skipped_flags = 0;
    uint8_t executed_flags = 0;
    return conditional_cmp_skipped(&skipped_flags) == UINT32_C(0)
        && skipped_flags == UINT8_C(8)
        && conditional_cmp_executed(&executed_flags) == UINT32_C(0)
        && executed_flags == UINT8_C(6) ? 0 : 1;
}
"""
        with tempfile.TemporaryDirectory() as directory:
            src = Path(directory) / "conditional_cmp.c"
            exe = Path(directory) / ("conditional_cmp.exe" if os.name == "nt" else "conditional_cmp")
            src.write_text(harness, encoding="utf-8")
            result = subprocess.run([compiler, str(src), "-std=c11", "-Wall", "-Wextra", "-Werror", "-o", str(exe)], capture_output=True, text=True)
            self.assertEqual(0, result.returncode, msg=result.stdout + result.stderr)
            run = subprocess.run([str(exe)], capture_output=True, text=True)
            self.assertEqual(0, run.returncode, msg=run.stdout + run.stderr)

    def test_initial_nzcv_sets_entry_flags_and_defaults_to_zero(self):
        words = [0xE3A00001, 0xE12FFF1E]
        self.assertEqual(poc.translate(words), poc.translate(words, initial_nzcv=0))
        source = poc.translate(words, initial_nzcv=0b1010)
        self.assertIn("uint32_t flag_n = 1;", source)
        self.assertIn("uint32_t flag_z = 0;", source)
        self.assertIn("uint32_t flag_c = 1;", source)
        self.assertIn("uint32_t flag_v = 0;", source)

    def test_rejects_invalid_initial_nzcv(self):
        for bad in (-1, 16, True, "4", None):
            with self.subTest(bad=bad), self.assertRaisesRegex(poc.UnsupportedInstruction, "initial NZCV"):
                poc.translate([0xE3A00001, 0xE12FFF1E], initial_nzcv=bad)

    def test_cli_initial_nzcv_option(self):
        script = str(ROOT / "tools" / "arm_subset_poc.py")
        ok = subprocess.run([sys.executable, script, "--initial-nzcv", "0x4"], capture_output=True, text=True, check=False)
        self.assertEqual(0, ok.returncode, msg=ok.stderr)
        self.assertIn("uint32_t flag_z = 1;", ok.stdout)
        bad = subprocess.run([sys.executable, script, "--initial-nzcv", "16"], capture_output=True, text=True, check=False)
        self.assertNotEqual(0, bad.returncode)
        self.assertIn("NZCV", bad.stderr)

    def test_generated_c_beq_uses_caller_entry_flags_when_compiler_exists(self):
        compiler = next((shutil.which(name) for name in (os.environ.get("CC", ""), "cc", "gcc", "clang") if name and shutil.which(name)), None)
        if not compiler:
            self.skipTest("no C compiler found; native branch proof requires cc, gcc, or clang")
        # BEQ with no earlier flag-setting instruction: the outcome is decided only by the entry Z flag.
        words = [0x0A000000, 0xE3A00001, 0xE12FFF1E]
        cases = ((0b0000, 1, 0), (0b0100, 0, 4))
        for initial_nzcv, expected_result, expected_flags in cases:
            with self.subTest(initial_nzcv=initial_nzcv), tempfile.TemporaryDirectory() as directory:
                src = Path(directory) / "entry_flags.c"
                exe = Path(directory) / ("entry_flags.exe" if os.name == "nt" else "entry_flags")
                source = poc.translate(words, initial_nzcv=initial_nzcv)
                harness = source + f"\nint main(void) {{ uint8_t flags = 0; return synthetic_entry(&flags) == UINT32_C({expected_result}) && flags == UINT8_C({expected_flags}) ? 0 : 1; }}\n"
                src.write_text(harness, encoding="utf-8")
                result = subprocess.run([compiler, str(src), "-std=c11", "-Wall", "-Wextra", "-Werror", "-o", str(exe)], capture_output=True, text=True)
                self.assertEqual(0, result.returncode, msg=result.stdout + result.stderr)
                run = subprocess.run([str(exe)], capture_output=True, text=True)
                self.assertEqual(0, run.returncode, msg=run.stdout + run.stderr)

    def test_generated_c_unconditional_branch_skips_instruction_when_compiler_exists(self):
        compiler = next((shutil.which(name) for name in (os.environ.get("CC", ""), "cc", "gcc", "clang") if name and shutil.which(name)), None)
        if not compiler:
            self.skipTest("no C compiler found; native branch proof requires cc, gcc, or clang")
        words = [0xE3A00001, 0xEA000000, 0xE3A00002, 0xE12FFF1E]
        source = poc.translate(words)
        harness = source + "\nint main(void) { uint8_t flags = 0; return synthetic_entry(&flags) == UINT32_C(1) && flags == UINT8_C(0) ? 0 : 1; }\n"
        with tempfile.TemporaryDirectory() as directory:
            src = Path(directory) / "branch.c"
            exe = Path(directory) / ("branch.exe" if os.name == "nt" else "branch")
            src.write_text(harness, encoding="utf-8")
            result = subprocess.run([compiler, str(src), "-std=c11", "-Wall", "-Wextra", "-Werror", "-o", str(exe)], capture_output=True, text=True)
            self.assertEqual(0, result.returncode, msg=result.stdout + result.stderr)
            run = subprocess.run([str(exe)], capture_output=True, text=True)
            self.assertEqual(0, run.returncode, msg=run.stdout + run.stderr)

    def test_generated_c_beq_taken_uses_cmp_flags_when_compiler_exists(self):
        compiler = next((shutil.which(name) for name in (os.environ.get("CC", ""), "cc", "gcc", "clang") if name and shutil.which(name)), None)
        if not compiler:
            self.skipTest("no C compiler found; native branch proof requires cc, gcc, or clang")
        # CMP sets Z; BEQ branches to MOV #2 and bypasses MOV #1.
        words = [0xE3A00000, 0xE3500000, 0x0A000001, 0xE3A00001, 0xEA000000, 0xE3A00002, 0xE12FFF1E]
        source = poc.translate(words)
        harness = source + "\nint main(void) { uint8_t flags = 0; return synthetic_entry(&flags) == UINT32_C(2) && flags == UINT8_C(6) ? 0 : 1; }\n"
        with tempfile.TemporaryDirectory() as directory:
            src = Path(directory) / "beq.c"
            exe = Path(directory) / ("beq.exe" if os.name == "nt" else "beq")
            src.write_text(harness, encoding="utf-8")
            result = subprocess.run([compiler, str(src), "-std=c11", "-Wall", "-Wextra", "-Werror", "-o", str(exe)], capture_output=True, text=True)
            self.assertEqual(0, result.returncode, msg=result.stdout + result.stderr)
            run = subprocess.run([str(exe)], capture_output=True, text=True)
            self.assertEqual(0, run.returncode, msg=run.stdout + run.stderr)

    def test_generated_c_beq_not_taken_falls_through_when_compiler_exists(self):
        compiler = next((shutil.which(name) for name in (os.environ.get("CC", ""), "cc", "gcc", "clang") if name and shutil.which(name)), None)
        if not compiler:
            self.skipTest("no C compiler found; native branch proof requires cc, gcc, or clang")
        # CMP r0,#0 with r0=1 clears Z; BEQ is not taken, so MOV #2 runs and B skips MOV #3.
        words = [0xE3A00001, 0xE3500000, 0x0A000001, 0xE3A00002, 0xEA000000, 0xE3A00003, 0xE12FFF1E]
        source = poc.translate(words)
        harness = source + "\nint main(void) { uint8_t flags = 0; return synthetic_entry(&flags) == UINT32_C(2) && flags == UINT8_C(2) ? 0 : 1; }\n"
        with tempfile.TemporaryDirectory() as directory:
            src = Path(directory) / "beq_nt.c"
            exe = Path(directory) / ("beq_nt.exe" if os.name == "nt" else "beq_nt")
            src.write_text(harness, encoding="utf-8")
            result = subprocess.run([compiler, str(src), "-std=c11", "-Wall", "-Wextra", "-Werror", "-o", str(exe)], capture_output=True, text=True)
            self.assertEqual(0, result.returncode, msg=result.stdout + result.stderr)
            run = subprocess.run([str(exe)], capture_output=True, text=True)
            self.assertEqual(0, run.returncode, msg=run.stdout + run.stderr)

    def test_generated_c_bne_taken_and_not_taken_when_compiler_exists(self):
        compiler = next((shutil.which(name) for name in (os.environ.get("CC", ""), "cc", "gcc", "clang") if name and shutil.which(name)), None)
        if not compiler:
            self.skipTest("no C compiler found; native branch proof requires cc, gcc, or clang")
        cases = (
            ([0xE3A00001, 0xE3500000, 0x1A000001, 0xE3A00002, 0xEA000000, 0xE3A00003, 0xE12FFF1E], 3, 2),
            ([0xE3A00000, 0xE3500000, 0x1A000001, 0xE3A00001, 0xEA000000, 0xE3A00003, 0xE12FFF1E], 1, 6),
        )
        for index, (words, expected_result, expected_flags) in enumerate(cases):
            with self.subTest(index=index), tempfile.TemporaryDirectory() as directory:
                src = Path(directory) / "bne.c"
                exe = Path(directory) / ("bne.exe" if os.name == "nt" else "bne")
                source = poc.translate(words)
                harness = source + f"\nint main(void) {{ uint8_t flags = 0; return synthetic_entry(&flags) == UINT32_C({expected_result}) && flags == UINT8_C({expected_flags}) ? 0 : 1; }}\n"
                src.write_text(harness, encoding="utf-8")
                result = subprocess.run([compiler, str(src), "-std=c11", "-Wall", "-Wextra", "-Werror", "-o", str(exe)], capture_output=True, text=True)
                self.assertEqual(0, result.returncode, msg=result.stdout + result.stderr)
                run = subprocess.run([str(exe)], capture_output=True, text=True)
                self.assertEqual(0, run.returncode, msg=run.stdout + run.stderr)

    def test_cli_emits_c_for_the_default_synthetic_fixture(self):
        result = subprocess.run(
            [sys.executable, str(ROOT / "tools" / "arm_subset_poc.py")],
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(0, result.returncode, msg=result.stderr)
        self.assertIn("uint32_t synthetic_entry(uint8_t *nzcv_out)", result.stdout)
        self.assertIn("*nzcv_out = (uint8_t)((flag_n << 3) | (flag_z << 2) | (flag_c << 1) | flag_v);", result.stdout)
        self.assertIn("UINT32_C(12)", result.stdout)
        self.assertIn("UINT32_C(8)", result.stdout)
        self.assertIn("UINT32_C(3)", result.stdout)
        self.assertIn("r0 & UINT32_C(7)", result.stdout)
        self.assertIn("r0 | UINT32_C(8)", result.stdout)
        self.assertIn("r0 ^ UINT32_C(1)", result.stdout)
        self.assertIn("r0 & ~UINT32_C(2)", result.stdout)
        self.assertIn("~UINT32_C(0)", result.stdout)
        self.assertIn("r1 & UINT32_C(12)", result.stdout)
        self.assertIn("return r0;", result.stdout)

    def test_cli_returns_nonzero_for_incomplete_sequence(self):
        result = subprocess.run(
            [sys.executable, str(ROOT / "tools" / "arm_subset_poc.py"), "E3A00003"],
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(2, result.returncode)
        self.assertIn("sequence must end with BX LR", result.stderr)

    def test_generated_c_compiles_and_returns_twelve_when_compiler_exists(self):
        compiler = next((shutil.which(name) for name in (os.environ.get("CC", ""), "cc", "gcc", "clang") if name and shutil.which(name)), None)
        if not compiler:
            self.skipTest("no C compiler found; native-code proof must be run on a compiler-enabled host")
        source = poc.translate(list(poc.DEFAULT_WORDS))
        harness = source + "\nint main(void) { uint8_t flags = UINT8_C(255); return synthetic_entry(&flags) == UINT32_C(12) && flags == UINT8_C(0) ? 0 : 1; }\n"
        with tempfile.TemporaryDirectory() as directory:
            src = Path(directory) / "poc.c"
            exe = Path(directory) / ("poc.exe" if os.name == "nt" else "poc")
            src.write_text(harness, encoding="utf-8")
            result = subprocess.run([compiler, str(src), "-std=c11", "-Wall", "-Wextra", "-Werror", "-o", str(exe)], capture_output=True, text=True)
            self.assertEqual(0, result.returncode, msg=result.stdout + result.stderr)
            run = subprocess.run([str(exe)], capture_output=True, text=True)
            self.assertEqual(0, run.returncode, msg=run.stdout + run.stderr)


    def test_generated_c_reports_adds_overflow_flags_when_compiler_exists(self):
        compiler = next((shutil.which(name) for name in (os.environ.get("CC", ""), "cc", "gcc", "clang") if name and shutil.which(name)), None)
        if not compiler:
            self.skipTest("no C compiler found; native-code proof must be run on a compiler-enabled host")
        words = [0xE3A00102, 0xE2400001, 0xE2900001, 0xE12FFF1E]
        source = poc.translate(words)
        harness = source + "\nint main(void) { uint8_t flags = 0; return synthetic_entry(&flags) == UINT32_C(0x80000000) && flags == UINT8_C(9) ? 0 : 1; }\n"
        with tempfile.TemporaryDirectory() as directory:
            src = Path(directory) / "adds.c"
            exe = Path(directory) / ("adds.exe" if os.name == "nt" else "adds")
            src.write_text(harness, encoding="utf-8")
            result = subprocess.run([compiler, str(src), "-std=c11", "-Wall", "-Wextra", "-Werror", "-o", str(exe)], capture_output=True, text=True)
            self.assertEqual(0, result.returncode, msg=result.stdout + result.stderr)
            run = subprocess.run([str(exe)], capture_output=True, text=True)
            self.assertEqual(0, run.returncode, msg=run.stdout + run.stderr)

    def test_generated_c_reports_subs_no_borrow_and_overflow_when_compiler_exists(self):
        compiler = next((shutil.which(name) for name in (os.environ.get("CC", ""), "cc", "gcc", "clang") if name and shutil.which(name)), None)
        if not compiler:
            self.skipTest("no C compiler found; native-code proof must be run on a compiler-enabled host")
        words = [0xE3A00102, 0xE2500001, 0xE12FFF1E]
        source = poc.translate(words)
        harness = source + "\nint main(void) { uint8_t flags = 0; return synthetic_entry(&flags) == UINT32_C(0x7FFFFFFF) && flags == UINT8_C(3) ? 0 : 1; }\n"
        with tempfile.TemporaryDirectory() as directory:
            src = Path(directory) / "subs.c"
            exe = Path(directory) / ("subs.exe" if os.name == "nt" else "subs")
            src.write_text(harness, encoding="utf-8")
            result = subprocess.run([compiler, str(src), "-std=c11", "-Wall", "-Wextra", "-Werror", "-o", str(exe)], capture_output=True, text=True)
            self.assertEqual(0, result.returncode, msg=result.stdout + result.stderr)
            run = subprocess.run([str(exe)], capture_output=True, text=True)
            self.assertEqual(0, run.returncode, msg=run.stdout + run.stderr)

    def test_generated_c_reports_cmp_flags_without_writing_destination_when_compiler_exists(self):
        compiler = next((shutil.which(name) for name in (os.environ.get("CC", ""), "cc", "gcc", "clang") if name and shutil.which(name)), None)
        if not compiler:
            self.skipTest("no C compiler found; native-code proof must be run on a compiler-enabled host")
        words = [0xE3A00102, 0xE3500001, 0xE12FFF1E]
        source = poc.translate(words)
        harness = source + "\nint main(void) { uint8_t flags = 0; return synthetic_entry(&flags) == UINT32_C(0x80000000) && flags == UINT8_C(3) ? 0 : 1; }\n"
        with tempfile.TemporaryDirectory() as directory:
            src = Path(directory) / "cmp.c"
            exe = Path(directory) / ("cmp.exe" if os.name == "nt" else "cmp")
            src.write_text(harness, encoding="utf-8")
            result = subprocess.run([compiler, str(src), "-std=c11", "-Wall", "-Wextra", "-Werror", "-o", str(exe)], capture_output=True, text=True)
            self.assertEqual(0, result.returncode, msg=result.stdout + result.stderr)
            run = subprocess.run([str(exe)], capture_output=True, text=True)
            self.assertEqual(0, run.returncode, msg=run.stdout + run.stderr)

    def test_generated_c_reports_cmn_flags_without_writing_destination_when_compiler_exists(self):
        compiler = next((shutil.which(name) for name in (os.environ.get("CC", ""), "cc", "gcc", "clang") if name and shutil.which(name)), None)
        if not compiler:
            self.skipTest("no C compiler found; native-code proof must be run on a compiler-enabled host")
        words = [0xE3A00102, 0xE2400001, 0xE2900001, 0xE3700102, 0xE12FFF1E]
        source = poc.translate(words)
        harness = source + "\nint main(void) { uint8_t flags = 0; return synthetic_entry(&flags) == UINT32_C(0x80000000) && flags == UINT8_C(7) ? 0 : 1; }\n"
        with tempfile.TemporaryDirectory() as directory:
            src = Path(directory) / "cmn.c"
            exe = Path(directory) / ("cmn.exe" if os.name == "nt" else "cmn")
            src.write_text(harness, encoding="utf-8")
            result = subprocess.run([compiler, str(src), "-std=c11", "-Wall", "-Wextra", "-Werror", "-o", str(exe)], capture_output=True, text=True)
            self.assertEqual(0, result.returncode, msg=result.stdout + result.stderr)
            run = subprocess.run([str(exe)], capture_output=True, text=True)
            self.assertEqual(0, run.returncode, msg=run.stdout + run.stderr)


    def test_bounded_loop_returns_or_reports_budget_exhaustion_when_compiler_exists(self):
        compiler = next((shutil.which(name) for name in (os.environ.get("CC", ""), "cc", "gcc", "clang") if name and shutil.which(name)), None)
        if not compiler:
            self.skipTest("no C compiler found; bounded-loop proof requires cc, gcc, or clang")
        # MOV r0,#3; SUBS r0,r0,#1; BNE back to SUBS; BX LR.
        words = [0xE3A00003, 0xE2500001, 0x1AFFFFFD, 0xE12FFF1E]
        successful = poc.translate(words, max_execution_steps=8).replace(
            "uint32_t synthetic_entry_bounded(", "uint32_t loop_success("
        )
        exhausted = poc.translate(words, max_execution_steps=2).replace(
            "uint32_t synthetic_entry_bounded(", "uint32_t loop_exhausted("
        )
        harness = "\n".join((successful, exhausted)) + """
int main(void) {
    uint8_t flags = 0, status = 255;
    uint32_t steps = 0;
    if (!(loop_success(&flags, &steps, &status) == UINT32_C(0)
        && flags == UINT8_C(6) && status == UINT8_C(0)
        && steps == UINT32_C(8))) return 1;
    flags = 0; status = 255; steps = 0;
    if (!(loop_exhausted(&flags, &steps, &status) == UINT32_C(2)
        && flags == UINT8_C(2) && status == UINT8_C(1)
        && steps == UINT32_C(2))) return 2;
    return 0;
}
"""
        with tempfile.TemporaryDirectory() as directory:
            src = Path(directory) / "bounded_loop.c"
            exe = Path(directory) / ("bounded_loop.exe" if os.name == "nt" else "bounded_loop")
            src.write_text(harness, encoding="utf-8")
            result = subprocess.run([compiler, str(src), "-std=c11", "-Wall", "-Wextra", "-Werror", "-o", str(exe)], capture_output=True, text=True)
            self.assertEqual(0, result.returncode, msg=result.stdout + result.stderr)
            run = subprocess.run([str(exe)], capture_output=True, text=True)
            self.assertEqual(0, run.returncode, msg=run.stdout + run.stderr)

    def test_rejects_invalid_execution_budgets(self):
        for bad in (0, -1, True, "4", 100001):
            with self.subTest(bad=bad), self.assertRaisesRegex(poc.UnsupportedInstruction, "execution budget"):
                poc.translate([0xE12FFF1E], max_execution_steps=bad)

    def test_cli_execution_budget_option(self):
        script = str(ROOT / "tools" / "arm_subset_poc.py")
        words = ["E3A00003", "E2500001", "1AFFFFFD", "E12FFF1E"]
        ok = subprocess.run([sys.executable, script, "--max-execution-steps", "8", *words], capture_output=True, text=True, check=False)
        self.assertEqual(0, ok.returncode, msg=ok.stderr)
        self.assertIn("synthetic_entry_bounded", ok.stdout)
        self.assertIn("UINT32_C(8)", ok.stdout)
        bad = subprocess.run([sys.executable, script, "--max-execution-steps", "0", *words], capture_output=True, text=True, check=False)
        self.assertNotEqual(0, bad.returncode)
        self.assertIn("execution budget", bad.stderr)


    def test_bounded_budget_counts_predicated_instruction_when_condition_is_false(self):
        compiler = next((shutil.which(name) for name in (os.environ.get("CC", ""), "cc", "gcc", "clang") if name and shutil.which(name)), None)
        if not compiler:
            self.skipTest("no C compiler found; bounded-predication proof requires cc, gcc, or clang")
        # MOVNE r0,#5 is skipped when Z=1, but fetching it still consumes one step.
        source = poc.translate(
            [0x13A00005, 0xE3A00007, 0xE12FFF1E],
            initial_nzcv=0x4,
            max_execution_steps=1,
        ).replace("uint32_t synthetic_entry_bounded(", "uint32_t predicated_budget(")
        harness = source + """
int main(void) {
    uint8_t flags = 0, status = 255;
    uint32_t steps = 0;
    return predicated_budget(&flags, &steps, &status) == UINT32_C(0)
        && flags == UINT8_C(4)
        && status == UINT8_C(1)
        && steps == UINT32_C(1) ? 0 : 1;
}
"""
        with tempfile.TemporaryDirectory() as directory:
            src = Path(directory) / "bounded_predication.c"
            exe = Path(directory) / ("bounded_predication.exe" if os.name == "nt" else "bounded_predication")
            src.write_text(harness, encoding="utf-8")
            result = subprocess.run([compiler, str(src), "-std=c11", "-Wall", "-Wextra", "-Werror", "-o", str(exe)], capture_output=True, text=True)
            self.assertEqual(0, result.returncode, msg=result.stdout + result.stderr)
            run = subprocess.run([str(exe)], capture_output=True, text=True)
            self.assertEqual(0, run.returncode, msg=run.stdout + run.stderr)


    def test_runtime_state_io_uses_live_registers_and_returns_registers_flags_and_steps(self):
        compiler = next((shutil.which(name) for name in (os.environ.get("CC", ""), "cc", "gcc", "clang") if name and shutil.which(name)), None)
        if not compiler:
            self.skipTest("no C compiler found; A32 runtime-state proof requires cc, gcc, or clang")
        add = poc.translate(
            [0xE2800005, 0xE12FFF1E],
            max_execution_steps=2,
            runtime_state_io=True,
        ).replace("uint32_t synthetic_entry_bounded(", "uint32_t a32_runtime_add(")
        skipped = poc.translate(
            [0x12800005, 0xE12FFF1E],  # ADDNE r0,r0,#5
            max_execution_steps=2,
            runtime_state_io=True,
        ).replace("uint32_t synthetic_entry_bounded(", "uint32_t a32_runtime_add_ne(")
        harness = "\n".join((add, skipped)) + """
int main(void) {
    const uint32_t input[4] = {
        UINT32_C(37), UINT32_C(0x12345678), UINT32_C(0x80000000), UINT32_C(0xDEADBEEF)
    };
    uint32_t output[4] = {0U, 0U, 0U, 0U};
    uint8_t flags = UINT8_C(255), status = UINT8_C(255);
    uint32_t steps = 0U;
    if (!(a32_runtime_add(input, UINT8_C(11), &flags, &steps, &status, output) == UINT32_C(42)
        && flags == UINT8_C(11) && status == UINT8_C(0) && steps == UINT32_C(2)
        && output[0] == UINT32_C(42) && output[1] == input[1]
        && output[2] == input[2] && output[3] == input[3])) return 1;
    if (!(input[0] == UINT32_C(37))) return 2;
    output[0] = output[1] = output[2] = output[3] = 0U;
    flags = UINT8_C(255); status = UINT8_C(255); steps = 0U;
    if (!(a32_runtime_add_ne(input, UINT8_C(4), &flags, &steps, &status, output) == UINT32_C(37)
        && flags == UINT8_C(4) && status == UINT8_C(0) && steps == UINT32_C(2)
        && output[0] == input[0] && output[1] == input[1]
        && output[2] == input[2] && output[3] == input[3])) return 3;
    return 0;
}
"""
        with tempfile.TemporaryDirectory() as directory:
            src = Path(directory) / "a32_runtime_state.c"
            exe = Path(directory) / ("a32_runtime_state.exe" if os.name == "nt" else "a32_runtime_state")
            src.write_text(harness, encoding="utf-8")
            result = subprocess.run([compiler, str(src), "-std=c11", "-Wall", "-Wextra", "-Werror", "-o", str(exe)], capture_output=True, text=True)
            self.assertEqual(0, result.returncode, msg=result.stdout + result.stderr)
            run = subprocess.run([str(exe)], capture_output=True, text=True)
            self.assertEqual(0, run.returncode, msg=f"runtime A32 input/output/flags/step check failed with {run.returncode}")

    def test_runtime_state_io_rejects_null_registers_and_invalid_nzcv(self):
        compiler = next((shutil.which(name) for name in (os.environ.get("CC", ""), "cc", "gcc", "clang") if name and shutil.which(name)), None)
        if not compiler:
            self.skipTest("no C compiler found; A32 runtime-state validation requires cc, gcc, or clang")
        source = poc.translate(
            [0xE2800001, 0xE12FFF1E],
            max_execution_steps=2,
            runtime_state_io=True,
        ).replace("uint32_t synthetic_entry_bounded(", "uint32_t a32_runtime_validate(")
        harness = source + """
int main(void) {
    const uint32_t input[4] = {1U, 2U, 3U, 4U};
    uint32_t output[4] = {UINT32_C(0xAAAAAAAA), UINT32_C(0xAAAAAAAA),
                          UINT32_C(0xAAAAAAAA), UINT32_C(0xAAAAAAAA)};
    uint8_t flags = UINT8_C(0xAA), status = UINT8_C(0xAA);
    uint32_t steps = UINT32_C(99);
    if (a32_runtime_validate(0, UINT8_C(0), &flags, &steps, &status, output) != 0U) return 1;
    if (status != UINT8_C(2) || steps != 0U || flags != UINT8_C(0xAA)) return 2;
    for (unsigned i = 0; i < 4; ++i) if (output[i] != UINT32_C(0xAAAAAAAA)) return 3;
    flags = UINT8_C(0xAA); status = UINT8_C(0xAA); steps = UINT32_C(99);
    if (a32_runtime_validate(input, UINT8_C(16), &flags, &steps, &status, output) != 0U) return 4;
    if (status != UINT8_C(2) || steps != 0U || flags != UINT8_C(0xAA)) return 5;
    for (unsigned i = 0; i < 4; ++i) if (output[i] != UINT32_C(0xAAAAAAAA)) return 6;
    return 0;
}
"""
        with tempfile.TemporaryDirectory() as directory:
            src = Path(directory) / "a32_runtime_invalid.c"
            exe = Path(directory) / ("a32_runtime_invalid.exe" if os.name == "nt" else "a32_runtime_invalid")
            src.write_text(harness, encoding="utf-8")
            result = subprocess.run([compiler, str(src), "-std=c11", "-Wall", "-Wextra", "-Werror", "-o", str(exe)], capture_output=True, text=True)
            self.assertEqual(0, result.returncode, msg=result.stdout + result.stderr)
            run = subprocess.run([str(exe)], capture_output=True, text=True)
            self.assertEqual(0, run.returncode, msg=f"invalid A32 runtime input handling failed with {run.returncode}")

    def test_runtime_state_io_requires_boolean_option_and_execution_budget(self):
        words = [0xE2800001, 0xE12FFF1E]
        with self.assertRaisesRegex(poc.UnsupportedInstruction, "requires an explicit execution budget"):
            poc.translate(words, runtime_state_io=True)
        with self.assertRaisesRegex(poc.UnsupportedInstruction, "must be a bool"):
            poc.translate(words, max_execution_steps=2, runtime_state_io=1)

if __name__ == "__main__":
    unittest.main()
