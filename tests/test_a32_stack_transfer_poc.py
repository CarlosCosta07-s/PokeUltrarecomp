"""Synthetic tests for bounded A32 stack transfer and mixed ALU/stack translation."""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import a32_stack_transfer_poc as poc  # noqa: E402


def _find_c_compiler():
    return next((shutil.which(name) for name in ("cc", "gcc", "clang", "cl") if shutil.which(name)), None)


def _compile_c(compiler, source, executable, workdir):
    if Path(compiler).stem.casefold() == "cl":
        command = [compiler, "/nologo", "/std:c11", "/W4", "/WX", f"/Fe:{executable}", str(source)]
    else:
        command = [compiler, str(source), "-std=c11", "-Wall", "-Wextra", "-Werror", "-o", str(executable)]
    return subprocess.run(command, cwd=workdir, capture_output=True, text=True)


class A32StackDecodeTests(unittest.TestCase):
    def test_decodes_common_full_descending_push_and_empty_ascending_pop(self):
        self.assertEqual(("stmdb_sp", (4, 5, 14)), poc.decode_word(0xE92D4030))
        self.assertEqual(("ldmia_sp", (4, 5, 14)), poc.decode_word(0xE8BD4030))

    def test_rejects_empty_pc_sp_and_non_al_register_lists(self):
        for word, message in (
            (0xE92D0000, "must not be empty"),
            (0xE92D2000, "SP in a write-back"),
            (0xE92D8000, "PC in a register list"),
            (0x192D4010, "AL-condition"),
            (0xE92F4010, "only SP"),
            (0xE8BD2010, "SP in a write-back"),
            (0xE8BD8000, "PC in a register list"),
        ):
            with self.subTest(word=f"0x{word:08X}"), self.assertRaisesRegex(poc.UnsupportedA32StackInstruction, message):
                poc.decode_word(word)

    def test_rejects_bad_input_types_and_unsupported_instructions(self):
        for value in (-1, 0x100000000, True, "E92D4010"):
            with self.subTest(value=value), self.assertRaises(poc.UnsupportedA32StackInstruction):
                poc.decode_word(value)
        with self.assertRaisesRegex(poc.UnsupportedA32StackInstruction, "not an A32 multiple-transfer"):
            poc.decode_word(0xE3A00001)
        with self.assertRaisesRegex(poc.UnsupportedA32StackInstruction, "only SP"):
            poc.decode_word(0xE8A04030)  # LDMIA-like encoding with non-SP base is refused.


class A32StackTranslationTests(unittest.TestCase):
    def test_requires_exact_bx_lr_terminator_and_bounded_input(self):
        with self.assertRaisesRegex(poc.UnsupportedA32StackInstruction, "empty"):
            poc.translate_stack_sequence([])
        with self.assertRaisesRegex(poc.UnsupportedA32StackInstruction, "must end with exact BX LR"):
            poc.translate_stack_sequence([0xE92D4030])
        with self.assertRaisesRegex(poc.UnsupportedA32StackInstruction, "after BX LR"):
            poc.translate_stack_sequence([0xE12FFF1E, 0xE92D4030])
        with self.assertRaisesRegex(poc.UnsupportedA32StackInstruction, "exceeds 256"):
            poc.translate_stack_sequence([0xE92D4010] * 256 + [0xE12FFF1E])

    def test_emits_direct_c_for_selected_stack_transfers(self):
        source = poc.translate_stack_sequence([0xE92D4030, 0xE8BD4030, 0xE12FFF1E])
        self.assertIn("const uint32_t new_sp = old_sp - transfer_bytes;", source)
        self.assertIn("r[13] = (uint32_t)transfer_end;", source)
        self.assertIn("uint32_t loaded[15]", source)
        self.assertNotIn("switch (word)", source)
        self.assertIn("exact BX LR sequence terminator", source)

    def test_native_c_round_trip_preserves_registers_memory_contract_and_nzcv(self):
        compiler = _find_c_compiler()
        if not compiler:
            self.skipTest("no C compiler found; A32 stack-transfer proof requires cc, gcc, clang, or MSVC")
        generated = poc.translate_stack_sequence([0xE92D4030, 0xE8BD4030, 0xE12FFF1E])
        harness = generated + r'''
#include <string.h>
int main(void) {
    uint32_t in[15] = {0U};
    uint32_t out[15] = {0U};
    uint8_t memory[64];
    memset(memory, 0xEE, sizeof(memory));
    in[4] = UINT32_C(0x44444444);
    in[5] = UINT32_C(0x55555555);
    in[13] = UINT32_C(0x1020);
    in[14] = UINT32_C(0xDEADBEEF);
    uint8_t flags = 0U, status = UINT8_C(0xFF);
    uint32_t steps = 0U;
    uint32_t result = a32_stack_transfer_entry(in, UINT8_C(0xB), &flags,
        memory, UINT32_C(0x1000), UINT32_C(64), out, &steps, &status);
    return result == 0U && status == 0U && steps == 3U && flags == UINT8_C(0xB)
        && out[4] == in[4] && out[5] == in[5] && out[13] == in[13] && out[14] == in[14]
        && memory[20] == UINT8_C(0x44) && memory[23] == UINT8_C(0x44)
        && memory[24] == UINT8_C(0x55) && memory[27] == UINT8_C(0x55)
        && memory[28] == UINT8_C(0xEF) && memory[29] == UINT8_C(0xBE)
        && memory[30] == UINT8_C(0xAD) && memory[31] == UINT8_C(0xDE)
        ? 0 : 1;
}
'''
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "a32_stack_roundtrip.c"
            executable = Path(directory) / ("a32_stack_roundtrip.exe" if os.name == "nt" else "a32_stack_roundtrip")
            source.write_text(harness, encoding="utf-8")
            built = _compile_c(compiler, source, executable, directory)
            self.assertEqual(0, built.returncode, msg=built.stdout + built.stderr)
            run = subprocess.run([str(executable)], cwd=directory, capture_output=True, text=True)
            self.assertEqual(0, run.returncode, msg=run.stdout + run.stderr)

    def test_native_ldmia_loads_registers_in_ascending_register_order(self):
        compiler = _find_c_compiler()
        if not compiler:
            self.skipTest("no C compiler found; A32 stack-transfer proof requires a C compiler")
        generated = poc.translate_stack_sequence([0xE8BD4030, 0xE12FFF1E])
        harness = generated + r'''
int main(void) {
    uint32_t in[15] = {0U};
    uint32_t out[15] = {0U};
    uint8_t memory[32] = {0U};
    memory[4] = 0x44; memory[5] = 0x33; memory[6] = 0x22; memory[7] = 0x11;
    memory[8] = 0x88; memory[9] = 0x77; memory[10] = 0x66; memory[11] = 0x55;
    memory[12] = 0xCC; memory[13] = 0xBB; memory[14] = 0xAA; memory[15] = 0x99;
    in[13] = UINT32_C(0x2004);
    uint8_t flags = 0U, status = UINT8_C(0xFF);
    uint32_t steps = 0U;
    (void)a32_stack_transfer_entry(in, UINT8_C(0x6), &flags, memory,
        UINT32_C(0x2000), UINT32_C(32), out, &steps, &status);
    return status == 0U && steps == 2U && flags == UINT8_C(0x6)
        && out[4] == UINT32_C(0x11223344) && out[5] == UINT32_C(0x55667788)
        && out[14] == UINT32_C(0x99AABBCC) && out[13] == UINT32_C(0x2010)
        ? 0 : 1;
}
'''
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "a32_stack_ldmia.c"
            executable = Path(directory) / ("a32_stack_ldmia.exe" if os.name == "nt" else "a32_stack_ldmia")
            source.write_text(harness, encoding="utf-8")
            built = _compile_c(compiler, source, executable, directory)
            self.assertEqual(0, built.returncode, msg=built.stdout + built.stderr)
            run = subprocess.run([str(executable)], cwd=directory, capture_output=True, text=True)
            self.assertEqual(0, run.returncode, msg=run.stdout + run.stderr)

    def test_native_failed_transfer_is_atomic_and_preserves_flags(self):
        compiler = _find_c_compiler()
        if not compiler:
            self.skipTest("no C compiler found; A32 stack-transfer fault proof requires a C compiler")
        generated = poc.translate_stack_sequence([0xE92D4030, 0xE12FFF1E])
        harness = generated + r'''
#include <string.h>
int main(void) {
    uint32_t in[15] = {0U};
    uint32_t out[15] = {0U};
    uint8_t memory[16];
    uint8_t before[16];
    memset(memory, 0x5A, sizeof(memory));
    memcpy(before, memory, sizeof(memory));
    in[4] = UINT32_C(0x44444444); in[5] = UINT32_C(0x55555555);
    in[13] = UINT32_C(0x1004); in[14] = UINT32_C(0xEEEEEEEE);
    uint8_t flags = 0U, status = 0U;
    uint32_t steps = 0U;
    (void)a32_stack_transfer_entry(in, UINT8_C(0xD), &flags, memory,
        UINT32_C(0x1000), UINT32_C(16), out, &steps, &status);
    return status == 1U && steps == 1U && flags == UINT8_C(0xD)
        && out[4] == in[4] && out[5] == in[5] && out[13] == in[13] && out[14] == in[14]
        && memcmp(memory, before, sizeof(memory)) == 0 ? 0 : 1;
}
'''
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "a32_stack_fault.c"
            executable = Path(directory) / ("a32_stack_fault.exe" if os.name == "nt" else "a32_stack_fault")
            source.write_text(harness, encoding="utf-8")
            built = _compile_c(compiler, source, executable, directory)
            self.assertEqual(0, built.returncode, msg=built.stdout + built.stderr)
            run = subprocess.run([str(executable)], cwd=directory, capture_output=True, text=True)
            self.assertEqual(0, run.returncode, msg=run.stdout + run.stderr)

    def test_native_failed_ldmia_preserves_prior_stores_and_registers(self):
        compiler = _find_c_compiler()
        if not compiler:
            self.skipTest("no C compiler found; A32 stack-transfer fault proof requires a C compiler")
        generated = poc.translate_stack_sequence([0xE92D4030, 0xE8BD4070, 0xE12FFF1E])
        harness = generated + r'''
#include <string.h>
int main(void) {
    uint32_t in[15] = {0U}, out[15] = {0U};
    uint8_t memory[32];
    memset(memory, 0xEE, sizeof(memory));
    in[4] = UINT32_C(0x44444444); in[5] = UINT32_C(0x55555555);
    in[6] = UINT32_C(0x66666666); in[13] = UINT32_C(0x1020);
    in[14] = UINT32_C(0xDEADBEEF);
    uint8_t flags = 0U, status = UINT8_C(0xFF); uint32_t steps = 0U;
    (void)a32_stack_transfer_entry(in, UINT8_C(0x9), &flags, memory,
        UINT32_C(0x1000), UINT32_C(32), out, &steps, &status);
    return status == 1U && steps == 2U && flags == UINT8_C(0x9)
        && out[4] == in[4] && out[5] == in[5] && out[6] == in[6]
        && out[14] == in[14] && out[13] == UINT32_C(0x1014)
        && memory[20] == UINT8_C(0x44) && memory[24] == UINT8_C(0x55)
        && memory[28] == UINT8_C(0xEF) && memory[31] == UINT8_C(0xDE)
        ? 0 : 1;
}
'''
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "a32_stack_ldmia_fault.c"
            executable = Path(directory) / ("a32_stack_ldmia_fault.exe" if os.name == "nt" else "a32_stack_ldmia_fault")
            source.write_text(harness, encoding="utf-8")
            built = _compile_c(compiler, source, executable, directory)
            self.assertEqual(0, built.returncode, msg=built.stdout + built.stderr)
            run = subprocess.run([str(executable)], cwd=directory, capture_output=True, text=True)
            self.assertEqual(0, run.returncode, msg=run.stdout + run.stderr)

    def test_native_rejects_guest_address_range_overflow(self):
        compiler = _find_c_compiler()
        if not compiler:
            self.skipTest("no C compiler found; A32 stack-transfer argument proof requires a C compiler")
        generated = poc.translate_stack_sequence([0xE92D4030, 0xE12FFF1E])
        harness = generated + r'''
int main(void) {
    uint32_t in[15] = {0U}, out[15];
    uint8_t memory[32] = {0U};
    for (unsigned i = 0U; i < 15U; ++i) out[i] = UINT32_C(0xDEADBEEF);
    in[13] = UINT32_C(0xFFFFFFF0);
    uint8_t flags = 0U, status = 0U; uint32_t steps = UINT32_C(99);
    (void)a32_stack_transfer_entry(in, UINT8_C(0x4), &flags, memory,
        UINT32_C(0xFFFFFFF0), UINT32_C(32), out, &steps, &status);
    return status == 2U && steps == 0U && flags == UINT8_C(0x4)
        && out[13] == UINT32_C(0xDEADBEEF) ? 0 : 1;
}
'''
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "a32_stack_bad_region.c"
            executable = Path(directory) / ("a32_stack_bad_region.exe" if os.name == "nt" else "a32_stack_bad_region")
            source.write_text(harness, encoding="utf-8")
            built = _compile_c(compiler, source, executable, directory)
            self.assertEqual(0, built.returncode, msg=built.stdout + built.stderr)
            run = subprocess.run([str(executable)], cwd=directory, capture_output=True, text=True)
            self.assertEqual(0, run.returncode, msg=run.stdout + run.stderr)

    def test_native_misaligned_stack_fails_without_changing_state(self):
        compiler = _find_c_compiler()
        if not compiler:
            self.skipTest("no C compiler found; A32 stack-transfer alignment proof requires a C compiler")
        generated = poc.translate_stack_sequence([0xE92D4030, 0xE12FFF1E])
        harness = generated + r'''
#include <string.h>
int main(void) {
    uint32_t in[15] = {0U}, out[15] = {0U};
    uint8_t memory[32], before[32];
    memset(memory, 0xA5, sizeof(memory)); memcpy(before, memory, sizeof(memory));
    in[13] = UINT32_C(0x1002); in[4] = UINT32_C(0x12345678);
    uint8_t flags = 0U, status = 0U; uint32_t steps = 0U;
    (void)a32_stack_transfer_entry(in, UINT8_C(0x2), &flags, memory,
        UINT32_C(0x1000), UINT32_C(32), out, &steps, &status);
    return status == 3U && steps == 1U && flags == UINT8_C(0x2)
        && out[13] == in[13] && out[4] == in[4] && memcmp(memory, before, sizeof(memory)) == 0
        ? 0 : 1;
}
'''
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "a32_stack_alignment.c"
            executable = Path(directory) / ("a32_stack_alignment.exe" if os.name == "nt" else "a32_stack_alignment")
            source.write_text(harness, encoding="utf-8")
            built = _compile_c(compiler, source, executable, directory)
            self.assertEqual(0, built.returncode, msg=built.stdout + built.stderr)
            run = subprocess.run([str(executable)], cwd=directory, capture_output=True, text=True)
            self.assertEqual(0, run.returncode, msg=run.stdout + run.stderr)



class A32MixedSequenceTests(unittest.TestCase):
    def test_decodes_only_non_flag_setting_alu_ops_for_shared_state(self):
        self.assertEqual(("mov", 0, 3), poc.decode_mixed_word(0xE3A00003))
        self.assertEqual(("add", 0, 0, 2), poc.decode_mixed_word(0xE2800002))
        self.assertEqual(("sub", 1, 1, 1), poc.decode_mixed_word(0xE2411001))
        for word in (0xE3B00001, 0x13A00001, 0xE3A04001, 0xE0810002):
            with self.subTest(word=f"0x{word:08X}"), self.assertRaises(poc.UnsupportedA32StackInstruction):
                poc.decode_mixed_word(word)

    def test_generates_shared_register_state_for_alu_and_stack(self):
        source = poc.translate_mixed_sequence([
            0xE3A00003, 0xE92D4030, 0xE2800002, 0xE8BD4030, 0xE12FFF1E
        ])
        self.assertIn("r[0] = UINT32_C(0x00000003);", source)
        self.assertIn("r[0] = r[0] + UINT32_C(0x00000002);", source)
        self.assertIn("r[13] = new_sp;", source)
        self.assertNotIn("switch (word)", source)

    def test_native_mixed_alu_stack_roundtrip_and_fault(self):
        compiler = _find_c_compiler()
        if not compiler:
            self.skipTest("no C compiler found; mixed A32 proof requires a native C compiler")
        words = [0xE3A00003, 0xE92D4030, 0xE2800002, 0xE8BD4030, 0xE12FFF1E]
        generated = poc.translate_mixed_sequence(words)
        fault_generated = poc.translate_mixed_sequence([0xE3A00003, 0xE92D4030, 0xE12FFF1E])
        harness = generated.replace(
            "uint32_t a32_stack_transfer_entry(", "uint32_t mixed_roundtrip(", 1
        ) + fault_generated.replace(
            "uint32_t a32_stack_transfer_entry(", "uint32_t mixed_fault(", 1
        ) + r'''
#include <string.h>
int main(void) {
    uint32_t in[15] = {0U}, out[15] = {0U};
    uint8_t memory[64]; memset(memory, 0xEE, sizeof(memory));
    in[4] = UINT32_C(0x44444444); in[5] = UINT32_C(0x55555555);
    in[13] = UINT32_C(0x1020); in[14] = UINT32_C(0xDEADBEEF);
    uint8_t flags = 0U, status = UINT8_C(0xFF); uint32_t steps = 0U;
    uint32_t returned = mixed_roundtrip(in, UINT8_C(0xB), &flags, memory,
        UINT32_C(0x1000), UINT32_C(64), out, &steps, &status);
    if (returned != 5U || status != 0U || steps != 5U || flags != UINT8_C(0xB)
        || out[0] != 5U || out[4] != in[4] || out[5] != in[5]
        || out[13] != in[13] || out[14] != in[14]) return 1;
    if (memory[20] != UINT8_C(0x44) || memory[24] != UINT8_C(0x55)
        || memory[28] != UINT8_C(0xEF) || memory[31] != UINT8_C(0xDE)) return 2;
    uint8_t before[64]; memcpy(before, memory, sizeof(memory));
    in[13] = UINT32_C(0x1004); flags = UINT8_C(0xFF); status = UINT8_C(0xFF); steps = 0U;
    returned = mixed_fault(in, UINT8_C(0x6), &flags, memory, UINT32_C(0x1000),
        UINT32_C(64), out, &steps, &status);
    if (returned != 3U || status != UINT8_C(1) || steps != UINT32_C(2)
        || flags != UINT8_C(0x6) || out[0] != 3U || out[13] != UINT32_C(0x1004)
        || memcmp(before, memory, sizeof(memory)) != 0) return 3;
    return 0;
}
'''
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "a32_mixed_sequence.c"
            executable = Path(directory) / ("a32_mixed_sequence.exe" if os.name == "nt" else "a32_mixed_sequence")
            source.write_text(harness, encoding="utf-8", newline="\n")
            built = _compile_c(compiler, source, executable, directory)
            self.assertEqual(0, built.returncode, msg=built.stdout + built.stderr)
            run = subprocess.run([str(executable)], cwd=directory, capture_output=True, text=True)
            self.assertEqual(0, run.returncode, msg=run.stdout + run.stderr)

if __name__ == "__main__":
    unittest.main()
