"""Synthetic tests for conservative ARM/Thumb register and flag effects."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import arm_thumb_effects as effects  # noqa: E402


def ins(address, ir, mnemonic, **extra):
    return {
        "virtual_address": f"0x{address:08X}",
        "decode_status": "decoded",
        "decoded_ir": ir,
        "mnemonic": mnemonic,
        **extra,
    }


class InstructionEffectTests(unittest.TestCase):
    def test_thumb_adds_reads_and_writes_destination_and_updates_flags(self):
        report = effects.instruction_effects(ins(0x1000, ("adds", 2, 1), "ADDS r2, #1"), "thumb")
        self.assertEqual(["r2"], report["registers_read"])
        self.assertEqual(["r2"], report["registers_written"])
        self.assertEqual(["n", "z", "c", "v"], report["flags_written"])
        self.assertEqual("known", report["status"])

    def test_thumb_movs_immediate_only_writes_destination(self):
        report = effects.instruction_effects(ins(0x1000, ("movs", 3, 7), "MOVS r3, #7"), "thumb")
        self.assertEqual([], report["registers_read"])
        self.assertEqual(["r3"], report["registers_written"])
        self.assertEqual(["n", "z"], report["flags_written"])

    def test_conditional_branch_reads_nzcv_and_writes_pc(self):
        report = effects.instruction_effects(
            ins(0x1000, ("branch", "le", -2), "BLE", branch_target_virtual_address="0x00001000"),
            "thumb",
        )
        self.assertEqual(["n", "v", "z"], report["flags_read"])
        self.assertEqual(["pc"], report["registers_written"])
        self.assertEqual("conditional-branch", report["control_flow"])

    def test_predicated_arm_data_instruction_reads_condition_flags(self):
        report = effects.instruction_effects(
            ins(0x1000, ("predicated", "eq", ("add", 0, 1, 2)), "ADDEQ r0, r1, #2"),
            "arm",
        )
        self.assertEqual(["r1"], report["registers_read"])
        self.assertEqual(["r0"], report["registers_written"])
        self.assertEqual(["z"], report["flags_read"])
        self.assertTrue(report["conditional"])

    def test_thumb_adcs_reads_carry_and_updates_nzcv(self):
        report = effects.instruction_effects(ins(0x1000, ("adcs_reg", 0, 1), "ADCS r0, r1"), "thumb")
        self.assertEqual(["r0", "r1"], report["registers_read"])
        self.assertEqual(["c"], report["flags_read"])
        self.assertEqual(["c", "n", "v", "z"], report["flags_written"])

    def test_thumb_cmp_reads_operand_and_only_writes_flags(self):
        report = effects.instruction_effects(ins(0x1000, ("cmp_reg", 0, 1), "CMP r0, r1"), "thumb")
        self.assertEqual(["r0", "r1"], report["registers_read"])
        self.assertEqual([], report["registers_written"])
        self.assertEqual(["c", "n", "v", "z"], report["flags_written"])

    def test_load_store_effects_distinguish_memory_direction(self):
        load = effects.instruction_effects(ins(0x1000, ("ldr_imm", 2, 3, 12), "LDR r2, [r3, #12]"), "thumb")
        store = effects.instruction_effects(ins(0x1002, ("str_reg", 2, 3, 4), "STR r2, [r3, r4]"), "thumb")
        self.assertEqual(["r3"], load["registers_read"])
        self.assertEqual(["r2"], load["registers_written"])
        self.assertEqual("read", load["memory"])
        self.assertEqual(["r2", "r3", "r4"], store["registers_read"])
        self.assertEqual("write", store["memory"])

    def test_push_pop_and_multiple_transfer_account_for_sp_and_writeback(self):
        push = effects.instruction_effects(ins(0x1000, ("push", 0b101, True), "PUSH {r0, r2, lr}"), "thumb")
        pop = effects.instruction_effects(ins(0x1002, ("pop", 0b101), "POP {r0, r2}"), "thumb")
        ldm = effects.instruction_effects(ins(0x1004, ("ldmia", 0, 0b0011), "LDMIA r0!, {r0, r1}"), "thumb")
        self.assertEqual(["lr", "r0", "r2", "sp"], push["registers_read"])
        self.assertEqual(["sp"], push["registers_written"])
        self.assertEqual(["r0", "r2", "sp"], pop["registers_written"])
        self.assertEqual(["r0", "r1"], ldm["registers_written"])
        self.assertNotIn("r0", ldm["registers_read"])
        self.assertEqual("read", ldm["memory"])

    def test_calls_are_marked_partial_not_complete(self):
        report = effects.instruction_effects(ins(0x1000, ("call", "bl", 8), "BL"), "thumb")
        self.assertEqual("partial", report["status"])
        self.assertEqual(["lr", "pc"], report["registers_written"])
        self.assertTrue(any("ABI" in note for note in report["notes"]))

    def test_unknown_encodings_make_aggregate_explicitly_incomplete(self):
        report = effects.summarize_range([
            ins(0x1000, ("movs", 0, 1), "MOVS"),
            ins(0x1002, None, None, decode_status="unsupported"),
        ], "thumb")
        self.assertEqual("observed-effects-with-uncertainty", report["status"])
        self.assertEqual(["0x00001002"], report["incomplete_instruction_addresses"])
        self.assertIn("r0", report["observed_registers_written"])

    def test_aggregate_is_observed_effects_not_function_abi(self):
        report = effects.summarize_range([
            ins(0x1000, ("movs", 0, 1), "MOVS"),
            ins(0x1002, ("return",), "BX LR"),
        ], "thumb")
        self.assertEqual("observed-effects", report["status"])
        self.assertEqual(["lr"], report["observed_registers_read"])
        self.assertEqual(["pc", "r0"], report["observed_registers_written"])
        self.assertTrue(any("not a complete function return contract" in x for x in report["limitations"]))


if __name__ == "__main__":
    unittest.main()
