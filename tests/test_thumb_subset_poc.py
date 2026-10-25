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


if __name__ == "__main__":
    unittest.main()
