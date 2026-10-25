"""Synthetic clean-room tests for the narrow Thumb-16 translator."""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import thumb_subset_poc as poc  # noqa: E402


class ThumbDecodeTests(unittest.TestCase):
    def test_default_fixture_decodes(self):
        self.assertEqual(
            [
                ("movs", 0, 12),
                ("subs", 0, 8),
                ("adds", 0, 3),
                ("cmp", 0, 7),
                ("return",),
            ],
            [poc.decode_halfword(word) for word in poc.DEFAULT_HALFWORDS],
        )

    def test_decodes_movs_immediate(self):
        self.assertEqual(("movs", 2, 0xAB), poc.decode_halfword(0x22AB))

    def test_decodes_cmp_immediate(self):
        self.assertEqual(("cmp", 3, 0x7F), poc.decode_halfword(0x2B7F))

    def test_decodes_adds_immediate(self):
        self.assertEqual(("adds", 1, 0xFF), poc.decode_halfword(0x31FF))

    def test_decodes_subs_immediate(self):
        self.assertEqual(("subs", 4, 0x11), poc.decode_halfword(0x3C11))

    def test_decodes_selected_data_processing_register_forms(self):
        self.assertEqual(("ands_reg", 0, 1), poc.decode_halfword(0x4008))
        self.assertEqual(("eors_reg", 0, 1), poc.decode_halfword(0x4048))
        self.assertEqual(("tst_reg", 0, 1), poc.decode_halfword(0x4208))
        self.assertEqual(("orrs_reg", 0, 1), poc.decode_halfword(0x4308))
        self.assertEqual(("bics_reg", 0, 1), poc.decode_halfword(0x4388))
        self.assertEqual(("mvns_reg", 0, 1), poc.decode_halfword(0x43C8))

    def test_classifies_data_processing_register_space_conservatively(self):
        expected = {0x0: "ands_reg", 0x1: "eors_reg", 0x8: "tst_reg", 0xC: "orrs_reg", 0xE: "bics_reg", 0xF: "mvns_reg"}
        for word in range(0x4000, 0x4400):
            opcode = (word >> 6) & 0xF
            with self.subTest(word=f"0x{word:04X}"):
                if opcode in expected:
                    decoded = poc.decode_halfword(word)
                    self.assertEqual(expected[opcode], decoded[0])
                    self.assertEqual(word & 7, decoded[1])
                    self.assertEqual((word >> 3) & 7, decoded[2])
                else:
                    with self.assertRaisesRegex(poc.UnsupportedThumbInstruction, "data-processing register opcode"):
                        poc.decode_halfword(word)

    def test_decodes_immediate_shift_forms(self):
        self.assertEqual(("lsl_imm", 0, 1, 31), poc.decode_halfword(0x07C8))
        self.assertEqual(("lsr_imm", 3, 2, 4), poc.decode_halfword(0x0913))
        self.assertEqual(("asr_imm", 5, 4, 0), poc.decode_halfword(0x1025))

    def test_classifies_every_encoding_in_thumb_immediate_shift_spaces(self):
        expected = {0x0000: "lsl_imm", 0x0800: "lsr_imm", 0x1000: "asr_imm"}
        for word in range(0x0000, 0x1800):
            with self.subTest(word=f"0x{word:04X}"):
                decoded = poc.decode_halfword(word)
                opcode = word & 0xF800
                self.assertEqual(expected[opcode], decoded[0])
                self.assertEqual((word >> 6) & 0x1F, decoded[3])
                self.assertEqual((word >> 3) & 0x7, decoded[2])
                self.assertEqual(word & 0x7, decoded[1])

    def test_decodes_three_operand_add_sub_and_imm3_forms(self):
        self.assertEqual(("adds_reg", 0, 1, 2), poc.decode_halfword(0x1888))
        self.assertEqual(("subs_reg", 0, 1, 2), poc.decode_halfword(0x1A88))
        self.assertEqual(("adds_imm3", 0, 1, 3), poc.decode_halfword(0x1CC8))
        self.assertEqual(("subs_imm3", 0, 1, 3), poc.decode_halfword(0x1EC8))

    def test_classifies_every_encoding_in_three_operand_add_sub_space(self):
        for word in range(0x1800, 0x2000):
            with self.subTest(word=f"0x{word:04X}"):
                decoded = poc.decode_halfword(word)
                expected_op = "subs" if word & 0x0200 else "adds"
                suffix = "imm3" if word & 0x0400 else "reg"
                self.assertEqual(f"{expected_op}_{suffix}", decoded[0])
                self.assertEqual((word >> 3) & 7, decoded[2])

    def test_decodes_unconditional_forward_and_backward_branches(self):
        self.assertEqual(("branch", "al", 0), poc.decode_halfword(0xE000))
        self.assertEqual(("branch", "al", -1), poc.decode_halfword(0xE7FF))
        self.assertEqual(("branch", "al", -0x400), poc.decode_halfword(0xE400))

    def test_decodes_conditional_branch(self):
        self.assertEqual(("branch", "eq", 0), poc.decode_halfword(0xD000))
        self.assertEqual(("branch", "ne", -3), poc.decode_halfword(0xD1FD))

    def test_decodes_exact_bx_lr(self):
        self.assertEqual(("return",), poc.decode_halfword(0x4770))

    def test_rejects_reserved_conditional_branch_conditions(self):
        for word in (0xDE00, 0xDF00):
            with self.subTest(word=word), self.assertRaisesRegex(
                poc.UnsupportedThumbInstruction, "reserved|unsupported"
            ):
                poc.decode_halfword(word)

    def test_rejects_unsupported_instruction(self):
        with self.assertRaisesRegex(poc.UnsupportedThumbInstruction, "unsupported Thumb-16"):
            poc.decode_halfword(0x46C0)  # MOV r8,r8

    def test_rejects_halfword_outside_uint16_and_bool(self):
        for value in (-1, 0x10000, True):
            with self.subTest(value=value), self.assertRaises(poc.UnsupportedThumbInstruction):
                poc.decode_halfword(value)


class ThumbTranslationTests(unittest.TestCase):
    def test_emits_expected_operations(self):
        source = poc.translate(list(poc.DEFAULT_HALFWORDS))
        self.assertIn("r0 = UINT32_C(12);", source)
        self.assertIn("uint32_t thumb_lhs_1 = r0;", source)
        self.assertIn("thumb_wide_2", source)
        self.assertIn("flag_c = (uint32_t)(thumb_lhs_3 >= thumb_rhs_3);", source)
        self.assertIn("return r0;", source)

    def test_requires_bx_lr_as_final_instruction(self):
        with self.assertRaisesRegex(poc.UnsupportedThumbInstruction, "sequence must end with BX LR"):
            poc.translate([0x2003])
        with self.assertRaisesRegex(poc.UnsupportedThumbInstruction, "instructions after BX LR"):
            poc.translate([0x4770, 0x2003])

    def test_enforces_instruction_limit(self):
        with self.assertRaisesRegex(poc.UnsupportedThumbInstruction, "exceeds 256"):
            poc.translate([0x2001] * (poc.MAX_INSTRUCTIONS + 1))

    def test_rejects_empty_sequence(self):
        with self.assertRaisesRegex(poc.UnsupportedThumbInstruction, "empty Thumb"):
            poc.translate([])

    def test_rejects_out_of_range_branch_target(self):
        with self.assertRaisesRegex(poc.UnsupportedThumbInstruction, "out-of-range"):
            poc.translate([0xE001, 0x4770])

    def test_rejects_backward_branch_without_budget(self):
        with self.assertRaisesRegex(poc.UnsupportedThumbInstruction, "requires an execution budget"):
            poc.translate([0xE7FE, 0x4770])

    def test_rejects_invalid_initial_nzcv(self):
        for value in (-1, 16, True, "4", None):
            with self.subTest(value=value), self.assertRaisesRegex(poc.UnsupportedThumbInstruction, "initial NZCV"):
                poc.translate([0x4770], initial_nzcv=value)

    def test_rejects_invalid_execution_budget(self):
        for value in (0, -1, True, "8", 100001):
            with self.subTest(value=value), self.assertRaisesRegex(poc.UnsupportedThumbInstruction, "execution budget"):
                poc.translate([0x4770], max_execution_steps=value)

    def test_initial_nzcv_is_emitted_and_default_is_zero(self):
        words = [0x2001, 0x4770]
        self.assertEqual(poc.translate(words), poc.translate(words, initial_nzcv=0))
        source = poc.translate(words, initial_nzcv=0xA)
        self.assertIn("uint32_t flag_n = 1U;", source)
        self.assertIn("uint32_t flag_z = 0U;", source)
        self.assertIn("uint32_t flag_c = 1U;", source)
        self.assertIn("uint32_t flag_v = 0U;", source)

    def test_conditional_branch_uses_entry_nzcv(self):
        source = poc.translate([0xD000, 0x2001, 0x4770], initial_nzcv=0x4)
        self.assertIn("if (flag_z != 0U) goto thumb_label_2;", source)
        self.assertIn("thumb_label_2: ;", source)

    def test_cli_emits_c_for_default_fixture(self):
        script = str(ROOT / "tools" / "thumb_subset_poc.py")
        result = subprocess.run([sys.executable, script], capture_output=True, text=True, check=False)
        self.assertEqual(0, result.returncode, msg=result.stderr)
        self.assertIn("uint32_t thumb_entry(uint8_t *nzcv_out)", result.stdout)
        self.assertIn("UINT32_C(12)", result.stdout)
        self.assertIn("return r0;", result.stdout)

    def test_cli_accepts_execution_budget(self):
        script = str(ROOT / "tools" / "thumb_subset_poc.py")
        words = ["2003", "3801", "D1FD", "4770"]
        result = subprocess.run(
            [sys.executable, script, "--max-execution-steps", "8", *words],
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(0, result.returncode, msg=result.stderr)
        self.assertIn("thumb_entry_bounded", result.stdout)
        self.assertIn("execution_status_out", result.stdout)

    def test_native_three_operand_add_sub_updates_result_and_nzcv(self):
        compiler = next((shutil.which(name) for name in (os.environ.get("CC", ""), "cc", "gcc", "clang") if name and shutil.which(name)), None)
        if not compiler:
            self.skipTest("no C compiler found; Thumb arithmetic proof requires cc, gcc, or clang")
        # Function A: 7 + 3 - 5 = 5, with the final no-borrow flag set.
        add_imm3 = poc.translate([0x2107, 0x1CC8, 0x1F40, 0x4770]).replace(
            "uint32_t thumb_entry(", "uint32_t thumb_add_imm3("
        )
        # Function B: 0 - 1 = 0xFFFFFFFF; then x + x = 0xFFFFFFFE.
        # A final register subtraction sets N=1 and C=0 without changing r0.
        add_reg = poc.translate([0x2100, 0x1E4A, 0x1890, 0x1A83, 0x4770]).replace(
            "uint32_t thumb_entry(", "uint32_t thumb_add_reg("
        )
        harness = "\n".join((add_imm3, add_reg)) + """
int main(void) {
    uint8_t flags = 0;
    if (!(thumb_add_imm3(&flags) == UINT32_C(5) && flags == UINT8_C(2))) return 1;
    flags = 0;
    if (!(thumb_add_reg(&flags) == UINT32_C(0xFFFFFFFE) && flags == UINT8_C(8))) return 2;
    return 0;
}
"""
        with tempfile.TemporaryDirectory() as directory:
            src = Path(directory) / "thumb_add_sub.c"
            exe = Path(directory) / ("thumb_add_sub.exe" if os.name == "nt" else "thumb_add_sub")
            src.write_text(harness, encoding="utf-8")
            result = subprocess.run([compiler, str(src), "-std=c11", "-Wall", "-Wextra", "-Werror", "-o", str(exe)], capture_output=True, text=True)
            self.assertEqual(0, result.returncode, msg=result.stdout + result.stderr)
            run = subprocess.run([str(exe)], capture_output=True, text=True)
            self.assertEqual(0, run.returncode, msg=run.stdout + run.stderr)

    def test_native_immediate_shifts_cover_zero_special_cases_and_carry(self):
        compiler = next((shutil.which(name) for name in (os.environ.get("CC", ""), "cc", "gcc", "clang") if name and shutil.which(name)), None)
        if not compiler:
            self.skipTest("no C compiler found; Thumb shift proof requires cc, gcc, or clang")
        lsl_overflow = poc.translate([0x2101, 0x07C9, 0x0048, 0x4770]).replace(
            "uint32_t thumb_entry(", "uint32_t lsl_overflow("
        )
        lsr_32 = poc.translate([0x2101, 0x07C9, 0x0808, 0x4770]).replace(
            "uint32_t thumb_entry(", "uint32_t lsr_32("
        )
        asr_32 = poc.translate([0x2101, 0x07C9, 0x1008, 0x4770]).replace(
            "uint32_t thumb_entry(", "uint32_t asr_32("
        )
        lsr_one = poc.translate([0x2101, 0x07C9, 0x0848, 0x4770]).replace(
            "uint32_t thumb_entry(", "uint32_t lsr_one("
        )
        lsl_zero = poc.translate([0x2101, 0x0008, 0x4770], initial_nzcv=0x3).replace(
            "uint32_t thumb_entry(", "uint32_t lsl_zero("
        )
        asr_sign = poc.translate([0x2180, 0x0609, 0x1048, 0x4770]).replace(
            "uint32_t thumb_entry(", "uint32_t asr_sign("
        )
        harness = "\n".join((lsl_overflow, lsr_32, asr_32, lsr_one, lsl_zero, asr_sign)) + """
int main(void) {
    uint8_t flags = 0;
    if (!(lsl_overflow(&flags) == UINT32_C(0) && flags == UINT8_C(6))) return 1;
    flags = 0;
    if (!(lsr_32(&flags) == UINT32_C(0) && flags == UINT8_C(6))) return 2;
    flags = 0;
    if (!(asr_32(&flags) == UINT32_MAX && flags == UINT8_C(10))) return 3;
    flags = 0;
    if (!(lsr_one(&flags) == UINT32_C(0x40000000) && flags == UINT8_C(0))) return 4;
    flags = 0;
    if (!(lsl_zero(&flags) == UINT32_C(1) && flags == UINT8_C(3))) return 5;
    flags = 0;
    if (!(asr_sign(&flags) == UINT32_C(0xC0000000) && flags == UINT8_C(8))) return 6;
    return 0;
}
"""
        with tempfile.TemporaryDirectory() as directory:
            src = Path(directory) / "thumb_shift.c"
            exe = Path(directory) / ("thumb_shift.exe" if os.name == "nt" else "thumb_shift")
            src.write_text(harness, encoding="utf-8")
            result = subprocess.run([compiler, str(src), "-std=c11", "-Wall", "-Wextra", "-Werror", "-o", str(exe)], capture_output=True, text=True)
            self.assertEqual(0, result.returncode, msg=result.stdout + result.stderr)
            run = subprocess.run([str(exe)], capture_output=True, text=True)
            self.assertEqual(0, run.returncode, msg=run.stdout + run.stderr)

    def test_native_logical_register_ops_update_nz_and_preserve_cv(self):
        compiler = next((shutil.which(name) for name in (os.environ.get("CC", ""), "cc", "gcc", "clang") if name and shutil.which(name)), None)
        if not compiler:
            self.skipTest("no C compiler found; Thumb logical-operation proof requires cc, gcc, or clang")
        initial = 0x3  # C and V set; logical operations must preserve both.
        functions = (
            poc.translate([0x200F, 0x2103, 0x4008, 0x4770], initial_nzcv=initial).replace("uint32_t thumb_entry(", "uint32_t logical_ands("),
            poc.translate([0x200F, 0x2103, 0x4048, 0x4770], initial_nzcv=initial).replace("uint32_t thumb_entry(", "uint32_t logical_eors("),
            poc.translate([0x200F, 0x2103, 0x4308, 0x4770], initial_nzcv=initial).replace("uint32_t thumb_entry(", "uint32_t logical_orrs("),
            poc.translate([0x200F, 0x2103, 0x4388, 0x4770], initial_nzcv=initial).replace("uint32_t thumb_entry(", "uint32_t logical_bics("),
            poc.translate([0x200F, 0x2103, 0x43C8, 0x4770], initial_nzcv=initial).replace("uint32_t thumb_entry(", "uint32_t logical_mvns("),
            poc.translate([0x2008, 0x2103, 0x4208, 0x4770], initial_nzcv=initial).replace("uint32_t thumb_entry(", "uint32_t logical_tst("),
        )
        harness = "\n".join(functions) + """
int main(void) {
    uint8_t flags = 0;
    if (!(logical_ands(&flags) == UINT32_C(3) && flags == UINT8_C(3))) return 1;
    flags = 0;
    if (!(logical_eors(&flags) == UINT32_C(12) && flags == UINT8_C(3))) return 2;
    flags = 0;
    if (!(logical_orrs(&flags) == UINT32_C(15) && flags == UINT8_C(3))) return 3;
    flags = 0;
    if (!(logical_bics(&flags) == UINT32_C(12) && flags == UINT8_C(3))) return 4;
    flags = 0;
    if (!(logical_mvns(&flags) == UINT32_C(0xFFFFFFFC) && flags == UINT8_C(11))) return 5;
    flags = 0;
    if (!(logical_tst(&flags) == UINT32_C(8) && flags == UINT8_C(7))) return 6;
    return 0;
}
"""
        with tempfile.TemporaryDirectory() as directory:
            src = Path(directory) / "thumb_logic.c"
            exe = Path(directory) / ("thumb_logic.exe" if os.name == "nt" else "thumb_logic")
            src.write_text(harness, encoding="utf-8")
            result = subprocess.run([compiler, str(src), "-std=c11", "-Wall", "-Wextra", "-Werror", "-o", str(exe)], capture_output=True, text=True)
            self.assertEqual(0, result.returncode, msg=result.stdout + result.stderr)
            run = subprocess.run([str(exe)], capture_output=True, text=True)
            self.assertEqual(0, run.returncode, msg=run.stdout + run.stderr)

    def test_native_default_fixture_compiles_and_returns_seven(self):
        compiler = next((shutil.which(name) for name in (os.environ.get("CC", ""), "cc", "gcc", "clang") if name and shutil.which(name)), None)
        if not compiler:
            self.skipTest("no C compiler found; native Thumb proof requires cc, gcc, or clang")
        source = poc.translate(list(poc.DEFAULT_HALFWORDS))
        harness = source + "\nint main(void) { uint8_t flags = 0; return thumb_entry(&flags) == UINT32_C(7) && flags == UINT8_C(6) ? 0 : 1; }\n"
        with tempfile.TemporaryDirectory() as directory:
            src = Path(directory) / "thumb.c"
            exe = Path(directory) / ("thumb.exe" if os.name == "nt" else "thumb")
            src.write_text(harness, encoding="utf-8")
            result = subprocess.run([compiler, str(src), "-std=c11", "-Wall", "-Wextra", "-Werror", "-o", str(exe)], capture_output=True, text=True)
            self.assertEqual(0, result.returncode, msg=result.stdout + result.stderr)
            run = subprocess.run([str(exe)], capture_output=True, text=True)
            self.assertEqual(0, run.returncode, msg=run.stdout + run.stderr)

    def test_all_conditional_branch_conditions_against_independent_table_when_compiler_exists(self):
        compiler = next((shutil.which(name) for name in (os.environ.get("CC", ""), "cc", "gcc", "clang") if name and shutil.which(name)), None)
        if not compiler:
            self.skipTest("no C compiler found; native Thumb condition proof requires cc, gcc, or clang")
        spec = [
            lambda n, z, c, v: z,
            lambda n, z, c, v: not z,
            lambda n, z, c, v: c,
            lambda n, z, c, v: not c,
            lambda n, z, c, v: n,
            lambda n, z, c, v: not n,
            lambda n, z, c, v: v,
            lambda n, z, c, v: not v,
            lambda n, z, c, v: c and not z,
            lambda n, z, c, v: (not c) or z,
            lambda n, z, c, v: n == v,
            lambda n, z, c, v: n != v,
            lambda n, z, c, v: (not z) and n == v,
            lambda n, z, c, v: z or n != v,
        ]
        sources = []
        checks = []
        for code, condition in enumerate(spec):
            words = [0xD000 | (code << 8), 0x2001, 0x4770]
            for nzcv in range(16):
                name = f"thumb_cond_{code:X}_{nzcv:X}"
                sources.append(poc.translate(words, initial_nzcv=nzcv).replace(
                    "uint32_t thumb_entry(", f"uint32_t {name}("
                ))
                n, z, c, v = (bool(nzcv & 8), bool(nzcv & 4), bool(nzcv & 2), bool(nzcv & 1))
                taken = condition(n, z, c, v)
                expected_result = 0 if taken else 1
                expected_flags = nzcv if taken else (nzcv & 0x3)
                checks.append(
                    f"    {{ uint8_t f = 0; if (!({name}(&f) == UINT32_C({expected_result}) && f == UINT8_C({expected_flags}))) bad++; }}"
                )
        harness = "\n".join(sources) + "\nint main(void) { int bad = 0;\n" + "\n".join(checks) + "\nreturn bad; }\n"
        with tempfile.TemporaryDirectory() as directory:
            src = Path(directory) / "thumb_conditions.c"
            exe = Path(directory) / ("thumb_conditions.exe" if os.name == "nt" else "thumb_conditions")
            src.write_text(harness, encoding="utf-8")
            result = subprocess.run([compiler, str(src), "-std=c11", "-Wall", "-Wextra", "-Werror", "-o", str(exe)], capture_output=True, text=True)
            self.assertEqual(0, result.returncode, msg=result.stdout + result.stderr)
            run = subprocess.run([str(exe)], capture_output=True, text=True)
            self.assertEqual(0, run.returncode, msg=f"{run.returncode} of {len(checks)} Thumb condition cases mismatched")

    def test_bounded_loop_reports_return_or_budget_exhaustion_when_compiler_exists(self):
        compiler = next((shutil.which(name) for name in (os.environ.get("CC", ""), "cc", "gcc", "clang") if name and shutil.which(name)), None)
        if not compiler:
            self.skipTest("no C compiler found; bounded Thumb loop proof requires cc, gcc, or clang")
        words = [0x2003, 0x3801, 0xD1FD, 0x4770]
        success = poc.translate(words, max_execution_steps=8).replace(
            "uint32_t thumb_entry_bounded(", "uint32_t thumb_loop_success("
        )
        exhausted = poc.translate(words, max_execution_steps=2).replace(
            "uint32_t thumb_entry_bounded(", "uint32_t thumb_loop_exhausted("
        )
        harness = "\n".join((success, exhausted)) + """
int main(void) {
    uint8_t flags = 0, status = 255;
    uint32_t steps = 0;
    if (!(thumb_loop_success(&flags, &steps, &status) == UINT32_C(0)
        && flags == UINT8_C(6) && status == UINT8_C(0)
        && steps == UINT32_C(8))) return 1;
    flags = 0; status = 255; steps = 0;
    if (!(thumb_loop_exhausted(&flags, &steps, &status) == UINT32_C(2)
        && flags == UINT8_C(2) && status == UINT8_C(1)
        && steps == UINT32_C(2))) return 2;
    return 0;
}
"""
        with tempfile.TemporaryDirectory() as directory:
            src = Path(directory) / "thumb_loop.c"
            exe = Path(directory) / ("thumb_loop.exe" if os.name == "nt" else "thumb_loop")
            src.write_text(harness, encoding="utf-8")
            result = subprocess.run([compiler, str(src), "-std=c11", "-Wall", "-Wextra", "-Werror", "-o", str(exe)], capture_output=True, text=True)
            self.assertEqual(0, result.returncode, msg=result.stdout + result.stderr)
            run = subprocess.run([str(exe)], capture_output=True, text=True)
            self.assertEqual(0, run.returncode, msg=run.stdout + run.stderr)

    def test_conditional_branch_not_taken_consumes_budget_when_compiler_exists(self):
        compiler = next((shutil.which(name) for name in (os.environ.get("CC", ""), "cc", "gcc", "clang") if name and shutil.which(name)), None)
        if not compiler:
            self.skipTest("no C compiler found; branch-budget proof requires cc, gcc, or clang")
        source = poc.translate([0xD000, 0x2001, 0x4770], initial_nzcv=0, max_execution_steps=1).replace(
            "uint32_t thumb_entry_bounded(", "uint32_t thumb_false_branch_budget("
        )
        harness = source + """
int main(void) {
    uint8_t flags = 0, status = 255;
    uint32_t steps = 0;
    return thumb_false_branch_budget(&flags, &steps, &status) == UINT32_C(0)
        && flags == UINT8_C(0) && status == UINT8_C(1) && steps == UINT32_C(1) ? 0 : 1;
}
"""
        with tempfile.TemporaryDirectory() as directory:
            src = Path(directory) / "thumb_false_branch.c"
            exe = Path(directory) / ("thumb_false_branch.exe" if os.name == "nt" else "thumb_false_branch")
            src.write_text(harness, encoding="utf-8")
            result = subprocess.run([compiler, str(src), "-std=c11", "-Wall", "-Wextra", "-Werror", "-o", str(exe)], capture_output=True, text=True)
            self.assertEqual(0, result.returncode, msg=result.stdout + result.stderr)
            run = subprocess.run([str(exe)], capture_output=True, text=True)
            self.assertEqual(0, run.returncode, msg=run.stdout + run.stderr)


class ThumbCallPairTests(unittest.TestCase):
    """BL/BLX (immediate) pair; expected offsets are hand-derived, not recomputed."""

    def test_bl_offsets_including_limits(self):
        cases = {
            (0xF000, 0xF800): 0,
            (0xF000, 0xF801): 2,
            (0xF000, 0xFFFF): 4094,
            (0xF001, 0xF800): 4096,
            (0xF3FF, 0xFFFF): 0x3FFFFE,      # largest positive offset
            (0xF400, 0xF800): -0x400000,     # most negative offset
            (0xF7FF, 0xFFFE): -4,            # "bl ."
            (0xF7FF, 0xFFFF): -2,
        }
        for (first, second), offset in cases.items():
            with self.subTest(first=hex(first), second=hex(second)):
                self.assertEqual(("call", "bl", offset), poc.decode_call_pair(first, second))

    def test_blx_offsets_and_bit0_rule(self):
        cases = {(0xF000, 0xE800): 0, (0xF000, 0xE802): 4, (0xF7FF, 0xEFFE): -4, (0xF3FF, 0xEFFE): 0x3FFFFC}
        for (first, second), offset in cases.items():
            with self.subTest(first=hex(first), second=hex(second)):
                self.assertEqual(("call", "blx", offset), poc.decode_call_pair(first, second))
        with self.assertRaisesRegex(poc.UnsupportedThumbInstruction, "bit 0"):
            poc.decode_call_pair(0xF000, 0xE801)

    def test_every_prefix_value_and_every_non_suffix_is_classified(self):
        for first in range(0x10000):
            if (first & 0xF800) == 0xF000:
                continue
            with self.assertRaises(poc.UnsupportedThumbInstruction):
                poc.decode_call_pair(first, 0xF800)
        for second in range(0x10000):
            high = second & 0xF800
            if high == 0xF800 or (high == 0xE800 and not second & 1):
                continue
            with self.assertRaises(poc.UnsupportedThumbInstruction):
                poc.decode_call_pair(0xF000, second)

    def test_thumb2_j1_j2_and_other_pairs_stay_undecoded(self):
        for second in (0xF000, 0xD000, 0xE000, 0xC800, 0x0000, 0x4770):
            with self.subTest(second=hex(second)), self.assertRaises(poc.UnsupportedThumbInstruction):
                poc.decode_call_pair(0xF000, second)

    def test_rejects_non_uint16_inputs(self):
        for bad in (True, -1, 0x10000, "F000", None):
            with self.subTest(bad=bad):
                with self.assertRaises(poc.UnsupportedThumbInstruction):
                    poc.decode_call_pair(bad, 0xF800)
                with self.assertRaises(poc.UnsupportedThumbInstruction):
                    poc.decode_call_pair(0xF000, bad)

    def test_lone_prefix_is_still_not_a_16_bit_instruction(self):
        for word in (0xF000, 0xF800, 0xE800):
            with self.subTest(word=hex(word)), self.assertRaises(poc.UnsupportedThumbInstruction):
                poc.decode_halfword(word)

    def test_call_target_bl_stays_thumb(self):
        bl0 = ("call", "bl", 0)
        self.assertEqual((0x00100004, "thumb"), poc.call_target(0x00100000, bl0))
        self.assertEqual((0x00100006, "thumb"), poc.call_target(0x00100002, bl0))
        self.assertEqual((0x00100000, "thumb"), poc.call_target(0x00100000, poc.decode_call_pair(0xF7FF, 0xFFFE)))

    def test_call_target_blx_enters_arm_and_aligns_down(self):
        blx0 = ("call", "blx", 0)
        self.assertEqual((0x00100004, "arm"), poc.call_target(0x00100000, blx0))
        self.assertEqual((0x00100004, "arm"), poc.call_target(0x00100002, blx0))   # 0x100006 -> 0x100004
        self.assertEqual((0x00100008, "arm"), poc.call_target(0x00100002, ("call", "blx", 4)))  # 0x10000A -> 0x100008

    def test_call_target_address_space_limits(self):
        self.assertEqual((0xFFFFFFFE, "thumb"), poc.call_target(0xFFFFFFFA, ("call", "bl", 0)))
        self.assertEqual((0, "thumb"), poc.call_target(0, poc.decode_call_pair(0xF7FF, 0xFFFE)))
        for address, decoded in (
            (0xFFFFFFFC, ("call", "bl", 0)),                         # raw 2**32
            (0x00000000, poc.decode_call_pair(0xF7FF, 0xFFFD)),      # raw -2
            (0x00100000, poc.decode_call_pair(0xF400, 0xF800)),      # raw < 0
        ):
            with self.subTest(address=hex(address), decoded=decoded):
                with self.assertRaisesRegex(poc.UnsupportedThumbInstruction, "outside the 32-bit"):
                    poc.call_target(address, decoded)

    def test_call_target_rejects_bad_inputs(self):
        ok = ("call", "bl", 0)
        for address in (True, -2, 1 << 32, 0x00100001, "0x100000"):
            with self.subTest(address=address), self.assertRaises(poc.UnsupportedThumbInstruction):
                poc.call_target(address, ok)
        for decoded in (("return",), ("call", "bx", 0), ("call", "bl"), ("call", "bl", "0"), ("branch", "al", 0)):
            with self.subTest(decoded=decoded), self.assertRaises(poc.UnsupportedThumbInstruction):
                poc.call_target(0x00100000, decoded)


class ThumbIndirectFlowTests(unittest.TestCase):
    """BX Rm / BLX Rm / POP {..., PC}; expectations are written out by hand."""

    def test_bx_register_forms(self):
        for word, rm in ((0x4700, 0), (0x4708, 1), (0x4718, 3), (0x4768, 13)):
            with self.subTest(word=hex(word)):
                self.assertEqual(("bx", rm), poc.decode_halfword(word))
        self.assertEqual(("return",), poc.decode_halfword(0x4770))   # BX LR keeps its own IR

    def test_blx_register_forms(self):
        for word, rm in ((0x4780, 0), (0x4788, 1), (0x4790, 2), (0x47F0, 14)):
            with self.subTest(word=hex(word)):
                self.assertEqual(("blx_reg", rm), poc.decode_halfword(word))

    def test_pc_as_register_and_nonzero_sbz_bits_are_refused(self):
        for word in (0x4778, 0x47F8, 0x4701, 0x4707, 0x4771, 0x4781, 0x4787, 0x47F1):
            with self.subTest(word=hex(word)), self.assertRaises(poc.UnsupportedThumbInstruction):
                poc.decode_halfword(word)

    def test_pop_with_pc_only(self):
        self.assertEqual(("pop_pc", 0x00), poc.decode_halfword(0xBD00))
        self.assertEqual(("pop_pc", 0x10), poc.decode_halfword(0xBD10))
        self.assertEqual(("pop_pc", 0xFF), poc.decode_halfword(0xBDFF))
        for word in (0xBE00, 0xBEFF, 0xB600, 0xB300):   # BKPT, CPS/SETEND space, unrelated misc
            with self.subTest(word=hex(word)), self.assertRaises(poc.UnsupportedThumbInstruction):
                poc.decode_halfword(word)

    def test_exhaustive_classification_of_the_affected_space(self):
        for word in range(0x4700, 0x4800):
            if word == 0x4770:
                expected = ("return",)
            elif word & 7 == 0 and not word & 0x80 and ((word >> 3) & 0xF) != 15:
                expected = ("bx", (word >> 3) & 0xF)
            elif word & 7 == 0 and word & 0x80 and ((word >> 3) & 0xF) != 15:
                expected = ("blx_reg", (word >> 3) & 0xF)
            else:
                expected = None
            with self.subTest(word=hex(word)):
                if expected is None:
                    with self.assertRaises(poc.UnsupportedThumbInstruction):
                        poc.decode_halfword(word)
                else:
                    self.assertEqual(expected, poc.decode_halfword(word))
        for word in range(0xBD00, 0xBE00):
            self.assertEqual(("pop_pc", word & 0xFF), poc.decode_halfword(word))

    def test_synthetic_translator_refuses_indirect_flow(self):
        for words in ([0x4718, 0x4770], [0x4790, 0x4770], [0xBD10, 0x4770], [0x2001, 0xBD00]):
            with self.subTest(words=[hex(w) for w in words]):
                with self.assertRaisesRegex(poc.UnsupportedThumbInstruction, "register-indirect"):
                    poc.translate(words)


class ThumbStackTransferTests(unittest.TestCase):
    """PUSH {reglist[, LR]} / POP {reglist}; expectations are written out by hand."""

    def test_push_forms(self):
        cases = {0xB401: (0x01, False), 0xB4F0: (0xF0, False), 0xB510: (0x10, True),
                 0xB500: (0x00, True), 0xB5FF: (0xFF, True), 0xB4FF: (0xFF, False)}
        for word, (mask, lr) in cases.items():
            with self.subTest(word=hex(word)):
                self.assertEqual(("push", mask, lr), poc.decode_halfword(word))

    def test_pop_forms(self):
        for word, mask in ((0xBC01, 0x01), (0xBC10, 0x10), (0xBCFF, 0xFF)):
            with self.subTest(word=hex(word)):
                self.assertEqual(("pop", mask), poc.decode_halfword(word))
        self.assertEqual(("pop_pc", 0x00), poc.decode_halfword(0xBD00))   # POP {pc} unchanged

    def test_empty_register_lists_are_refused(self):
        for word in (0xB400, 0xBC00):
            with self.subTest(word=hex(word)), self.assertRaisesRegex(poc.UnsupportedThumbInstruction, "empty register list"):
                poc.decode_halfword(word)

    def test_exhaustive_push_pop_space(self):
        for word in range(0xB400, 0xB600):
            with self.subTest(word=hex(word)):
                if word == 0xB400:
                    with self.assertRaises(poc.UnsupportedThumbInstruction):
                        poc.decode_halfword(word)
                else:
                    self.assertEqual(("push", word & 0xFF, bool(word & 0x100)), poc.decode_halfword(word))
        for word in range(0xBC00, 0xBD00):
            with self.subTest(word=hex(word)):
                if word == 0xBC00:
                    with self.assertRaises(poc.UnsupportedThumbInstruction):
                        poc.decode_halfword(word)
                else:
                    self.assertEqual(("pop", word & 0xFF), poc.decode_halfword(word))

    def test_neighbouring_misc_encodings_stay_unknown(self):
        for word in (0xB3FF, 0xB600, 0xB6FF, 0xBA00, 0xBE00, 0xBF00):
            with self.subTest(word=hex(word)), self.assertRaises(poc.UnsupportedThumbInstruction):
                poc.decode_halfword(word)

    def test_synthetic_translator_refuses_stack_transfers(self):
        for words in ([0xB510, 0x4770], [0x2001, 0xBC10, 0x4770]):
            with self.subTest(words=[hex(w) for w in words]):
                with self.assertRaisesRegex(poc.UnsupportedThumbInstruction, "stack transfer"):
                    poc.translate(words)


class ThumbLiteralLoadTests(unittest.TestCase):
    """LDR Rd, [PC, #imm8*4]; expectations are written out by hand."""

    def test_decode_forms(self):
        cases = {0x4800: (0, 0), 0x4905: (1, 20), 0x4A01: (2, 4), 0x4FFF: (7, 1020), 0x4C80: (4, 512)}
        for word, (rd, offset) in cases.items():
            with self.subTest(word=hex(word)):
                self.assertEqual(("ldr_literal", rd, offset), poc.decode_halfword(word))

    def test_exhaustive_decode_space_and_neighbours(self):
        for word in range(0x4800, 0x5000):
            self.assertEqual(("ldr_literal", (word >> 8) & 7, (word & 0xFF) * 4), poc.decode_halfword(word))
        for word in (0x47FF, 0x5000, 0x5800, 0x4000, 0x4400):   # BLX-range edge, register-offset loads, ALU/hi-reg space
            with self.subTest(word=hex(word)), self.assertRaises(poc.UnsupportedThumbInstruction):
                poc.decode_halfword(word)

    def test_literal_address_alignment_and_limits(self):
        zero, max_offset = ("ldr_literal", 0, 0), ("ldr_literal", 7, 1020)
        self.assertEqual(0x00100004, poc.literal_address(0x00100000, zero))
        self.assertEqual(0x00100004, poc.literal_address(0x00100002, zero))     # PC 0x100006 aligns down
        self.assertEqual(0x00100008, poc.literal_address(0x00100002, ("ldr_literal", 1, 4)))
        self.assertEqual(0x00100400, poc.literal_address(0x00100000, max_offset))
        self.assertEqual(0xFFFFFFFC, poc.literal_address(0xFFFFFFF8, zero))     # last whole word
        self.assertEqual(0xFFFFFFFC, poc.literal_address(0xFFFFFFFA, zero))

    def test_literal_address_refuses_what_does_not_fit_or_is_malformed(self):
        for address, decoded in (
            (0xFFFFFFFC, ("ldr_literal", 0, 0)),        # PC alone is 2**32
            (0xFFFFFFF8, ("ldr_literal", 0, 4)),        # literal at 2**32
            (0xFFFFFFF0, ("ldr_literal", 0, 1020)),
        ):
            with self.subTest(address=hex(address), decoded=decoded):
                with self.assertRaisesRegex(poc.UnsupportedThumbInstruction, "outside the 32-bit"):
                    poc.literal_address(address, decoded)
        for address in (True, -2, 1 << 32, 0x00100001, "0x100000"):
            with self.subTest(address=address), self.assertRaises(poc.UnsupportedThumbInstruction):
                poc.literal_address(address, ("ldr_literal", 0, 0))
        for decoded in (("return",), ("ldr_literal", 0), ("ldr_literal", 0, 1024), ("ldr_literal", 0, 2),
                        ("ldr_literal", 0, -4), ("ldr_literal", 0, True), ("call", "bl", 0)):
            with self.subTest(decoded=decoded), self.assertRaises(poc.UnsupportedThumbInstruction):
                poc.literal_address(0x00100000, decoded)

    def test_synthetic_translator_refuses_literal_loads(self):
        for words in ([0x4800, 0x4770], [0x2001, 0x4FFF, 0x4770]):
            with self.subTest(words=[hex(w) for w in words]):
                with self.assertRaisesRegex(poc.UnsupportedThumbInstruction, "literal load"):
                    poc.translate(words)


if __name__ == "__main__":
    unittest.main()
