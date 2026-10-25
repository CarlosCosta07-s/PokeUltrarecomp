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
    def test_default_fixture_decodes_to_mov_sub_add_return(self):
        decoded = [poc.decode_word(word) for word in poc.DEFAULT_WORDS]
        self.assertEqual(
            [("mov", 0, 12), ("sub", 0, 0, 8), ("add", 0, 0, 3), ("return",)],
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

    def test_rejects_flag_setting_instruction(self):
        with self.assertRaises(poc.UnsupportedInstruction):
            poc.decode_word(0xE2900001)  # ADDS r0, r0, #1

    def test_decodes_sub_immediate(self):
        self.assertEqual(("sub", 0, 0, 3), poc.decode_word(0xE2400003))

    def test_rejects_sub_with_source_outside_supported_registers(self):
        with self.assertRaisesRegex(poc.UnsupportedInstruction, "source register r4"):
            poc.decode_word(0xE2440001)  # SUB r0, r4, #1


class TranslationTests(unittest.TestCase):
    def test_emits_c_with_expected_operations(self):
        source = poc.translate(list(poc.DEFAULT_WORDS))
        self.assertIn("r0 = UINT32_C(12);", source)
        self.assertIn("r0 = (uint32_t)(r0 - UINT32_C(8));", source)
        self.assertIn("r0 = (uint32_t)(r0 + UINT32_C(3));", source)
        self.assertIn("return r0;", source)

    def test_requires_bx_lr_as_final_instruction(self):
        with self.assertRaises(poc.UnsupportedInstruction):
            poc.translate([0xE3A00003])
        with self.assertRaises(poc.UnsupportedInstruction):
            poc.translate([0xE12FFF1E, 0xE3A00003])

    def test_enforces_instruction_limit(self):
        with self.assertRaises(poc.UnsupportedInstruction):
            poc.translate([0xE3A00003] * (poc.MAX_INSTRUCTIONS + 1))

    def test_cli_emits_c_for_the_default_synthetic_fixture(self):
        result = subprocess.run(
            [sys.executable, str(ROOT / "tools" / "arm_subset_poc.py")],
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(0, result.returncode, msg=result.stderr)
        self.assertIn("uint32_t synthetic_entry(void)", result.stdout)
        self.assertIn("UINT32_C(12)", result.stdout)
        self.assertIn("UINT32_C(8)", result.stdout)
        self.assertIn("UINT32_C(3)", result.stdout)
        self.assertIn("return r0;", result.stdout)

    def test_cli_returns_nonzero_for_incomplete_sequence(self):
        result = subprocess.run(
            [sys.executable, str(ROOT / "tools" / "arm_subset_poc.py"), "E3A00003"],
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(2, result.returncode)
        self.assertIn("sequence must end with BX LR", result.stderr)

    def test_generated_c_compiles_and_returns_seven_when_compiler_exists(self):
        compiler = next((shutil.which(name) for name in (os.environ.get("CC", ""), "cc", "gcc", "clang") if name and shutil.which(name)), None)
        if not compiler:
            self.skipTest("no C compiler found; native-code proof must be run on a compiler-enabled host")
        source = poc.translate(list(poc.DEFAULT_WORDS))
        harness = source + "\nint main(void) { return synthetic_entry() == UINT32_C(7) ? 0 : 1; }\n"
        with tempfile.TemporaryDirectory() as directory:
            src = Path(directory) / "poc.c"
            exe = Path(directory) / ("poc.exe" if os.name == "nt" else "poc")
            src.write_text(harness, encoding="utf-8")
            result = subprocess.run([compiler, str(src), "-std=c11", "-Wall", "-Wextra", "-Werror", "-o", str(exe)], capture_output=True, text=True)
            self.assertEqual(0, result.returncode, msg=result.stdout + result.stderr)
            run = subprocess.run([str(exe)], capture_output=True, text=True)
            self.assertEqual(0, run.returncode, msg=run.stdout + run.stderr)


if __name__ == "__main__":
    unittest.main()
