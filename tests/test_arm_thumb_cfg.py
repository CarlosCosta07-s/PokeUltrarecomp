"""Unit tests for conservative candidate ARM/Thumb control-flow graphs."""
import unittest

from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import arm_thumb_cfg as cfg  # noqa: E402


def ins(index, address, ir, mnemonic, *, size=2, status="decoded", **extra):
    return {
        "index": index,
        "virtual_address": f"0x{address:08X}",
        "instruction_size_bytes": size,
        "decoded_ir": ir,
        "mnemonic": mnemonic,
        "decode_status": status,
        **extra,
    }


class CandidateControlFlowTests(unittest.TestCase):
    def analyze(self, instructions, state="thumb", start=0x1000, end=0x1100):
        return cfg.analyze_control_flow(instructions, state, start, end)

    def test_linear_sequence_is_one_candidate_block_ending_at_return(self):
        report = self.analyze([
            ins(0, 0x1000, ["movs", 0, 1], "MOVS r0, #1"),
            ins(1, 0x1002, ["adds", 0, 1], "ADDS r0, #1"),
            ins(2, 0x1004, ["return"], "BX LR"),
        ], end=0x1006)
        self.assertEqual("candidate-cfg", report["status"])
        self.assertEqual(1, report["basic_block_count"])
        self.assertEqual([0, 1, 2], report["basic_blocks"][0]["instruction_indices"])
        self.assertEqual([], report["edges"])

    def test_conditional_branch_has_taken_and_not_taken_edges(self):
        report = self.analyze([
            ins(0, 0x1000, ["branch", "ne", 0], "BNE", branch_target_virtual_address="0x00001004"),
            ins(1, 0x1002, ["movs", 0, 1], "MOVS r0, #1"),
            ins(2, 0x1004, ["return"], "BX LR"),
        ], end=0x1006)
        self.assertEqual(3, report["basic_block_count"])
        branch_edges = [edge for edge in report["edges"] if edge["from_block"] == "B0"]
        self.assertEqual({"conditional-taken", "conditional-not-taken"}, {edge["kind"] for edge in branch_edges})
        taken = next(edge for edge in branch_edges if edge["kind"] == "conditional-taken")
        fallthrough = next(edge for edge in branch_edges if edge["kind"] == "conditional-not-taken")
        self.assertEqual("B2", taken["to_block"])
        self.assertEqual("B1", fallthrough["to_block"])
        self.assertEqual("resolved", taken["resolution"])

    def test_unconditional_branch_has_no_fallthrough_edge(self):
        report = self.analyze([
            ins(0, 0x1000, ["branch", "al", 0], "B", branch_target_virtual_address="0x00001004"),
            ins(1, 0x1002, ["movs", 0, 1], "MOVS r0, #1"),
            ins(2, 0x1004, ["return"], "BX LR"),
        ], end=0x1006)
        edges = [edge for edge in report["edges"] if edge["from_block"] == "B0"]
        self.assertEqual(1, len(edges))
        self.assertEqual("unconditional-branch", edges[0]["kind"])
        self.assertEqual("B2", edges[0]["to_block"])

    def test_loop_back_edge_is_preserved_without_claiming_execution(self):
        report = self.analyze([
            ins(0, 0x1000, ["movs", 0, 2], "MOVS r0, #2"),
            ins(1, 0x1002, ["branch", "ne", -2], "BNE", branch_target_virtual_address="0x00001000"),
            ins(2, 0x1004, ["return"], "BX LR"),
        ], end=0x1006)
        back = next(edge for edge in report["edges"] if edge["kind"] == "conditional-taken")
        self.assertEqual("B0", back["to_block"])
        self.assertEqual("resolved", back["resolution"])

    def test_target_inside_range_but_not_instruction_start_is_not_guessed(self):
        report = self.analyze([
            ins(0, 0x1000, ["branch", "al", 0], "B", branch_target_virtual_address="0x00001001"),
            ins(1, 0x1002, ["return"], "BX LR"),
        ], end=0x1004)
        edge = report["edges"][0]
        self.assertEqual("not-an-instruction-start", edge["resolution"])
        self.assertEqual("candidate-cfg-with-warnings", report["status"])

    def test_branch_outside_selected_range_is_reported_as_boundary_edge(self):
        report = self.analyze([
            ins(0, 0x1000, ["branch", "al", 10], "B", branch_target_virtual_address="0x00001020"),
        ], end=0x1002)
        self.assertEqual("outside-selected-range", report["edges"][0]["resolution"])
        self.assertIsNone(report["edges"][0]["to_block"])

    def test_direct_call_records_target_and_possible_return_continuation(self):
        report = self.analyze([
            ins(0, 0x1000, ["call", "bl", 4], "BL", size=4, branch_target_virtual_address="0x00002000", branch_target_state="thumb"),
            ins(1, 0x1004, ["return"], "BX LR"),
        ], end=0x1006)
        self.assertEqual(1, len(report["unresolved_transfers"]))
        self.assertEqual("BL", report["unresolved_transfers"][0]["kind"])
        edge = report["edges"][0]
        self.assertEqual("call-return-continuation", edge["kind"])
        self.assertEqual("B1", edge["to_block"])

    def test_indirect_branch_is_an_unresolved_terminator(self):
        report = self.analyze([
            ins(0, 0x1000, ["bx", 3], "BX r3", indirect_branch=True),
            ins(1, 0x1002, ["return"], "BX LR"),
        ], end=0x1004)
        self.assertEqual("candidate-cfg-with-warnings", report["status"])
        self.assertEqual("BX", report["unresolved_transfers"][0]["kind"])
        self.assertEqual([], report["edges"])

    def test_indirect_call_has_only_a_possible_return_continuation(self):
        report = self.analyze([
            ins(0, 0x1000, ["blx_reg", 3], "BLX r3", indirect_branch=True, branch_target_virtual_address=None),
            ins(1, 0x1002, ["return"], "BX LR"),
        ], end=0x1004)
        self.assertEqual("indirect-call-return-continuation", report["edges"][0]["kind"])
        self.assertEqual("0x00001002", report["edges"][0]["target_address"])
        self.assertEqual("resolved", report["edges"][0]["resolution"])
        self.assertIsNone(report["unresolved_transfers"][0]["target_address"])
        self.assertEqual("BLX_REG", report["unresolved_transfers"][0]["kind"])

    def test_unknown_instruction_blocks_known_flow_to_following_range(self):
        report = self.analyze([
            ins(0, 0x1000, None, None, status="unsupported", reason="unknown opcode"),
            ins(1, 0x1002, ["return"], "BX LR"),
        ], end=0x1004)
        self.assertEqual(2, report["basic_block_count"])
        self.assertEqual("candidate-cfg-with-warnings", report["status"])
        self.assertEqual([], report["edges"])
        self.assertEqual("unknown-instruction", report["unresolved_transfers"][0]["kind"])

    def test_literal_overlap_is_exposed_as_potential_data(self):
        report = self.analyze([
            ins(0, 0x1000, ["ldr_literal", 0, 4], "LDR r0, [pc, #4]",
                literal_pool_virtual_address="0x00001006",
                literal_overlaps_selected_range=True,
                literal_is_scanned_instruction_start=True),
            ins(1, 0x1002, ["movs", 0, 1], "MOVS r0, #1"),
            ins(2, 0x1004, ["return"], "BX LR"),
        ], end=0x1006)
        self.assertEqual("candidate-cfg-with-warnings", report["status"])
        self.assertTrue(report["potential_data_references"][0]["overlaps_selected_range"])
        self.assertFalse(report["potential_data_references"][0]["literal_value_read"])
        self.assertTrue(any("may be data" in w for w in report["warnings"]))

    def test_rejects_malformed_range_and_duplicate_addresses(self):
        with self.assertRaisesRegex(ValueError, "non-empty uint32"):
            cfg.analyze_control_flow([], "thumb", 0x1000, 0x1000)
        with self.assertRaisesRegex(ValueError, "duplicate instruction address"):
            self.analyze([
                ins(0, 0x1000, ["return"], "BX LR"),
                ins(1, 0x1000, ["return"], "BX LR"),
            ], end=0x1002)


if __name__ == "__main__":
    unittest.main()
