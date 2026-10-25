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

    def test_rejects_conditional_instruction(self):
        with self.assertRaises(poc.UnsupportedInstruction):
            poc.decode_word(0x13A00003)  # MOVNE r0, #3

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
            poc.decode_word(0xCA000000)  # BGT

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

if __name__ == "__main__":
    unittest.main()
