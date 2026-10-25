"""Synthetic tests for the candidate function contract checker; no game data is read."""
import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tests"))
import check_function_contract as fc  # noqa: E402
import inspect_3ds_code_range as ranges  # noqa: E402
from test_inspect_3ds_code_range import build_exheader, put_units  # noqa: E402

TITLE = "00040000001B5000"


def base_contract(**changes):
    contract = {
        "schema_version": 1,
        "contract_id": "synthetic-001",
        "target_id": "ultra-sun",
        "state": "thumb",
        "entry_address": "0x00100000",
        "inputs": {"registers": [], "flags": []},
        "outputs": {"registers": ["r0"], "flags": []},
        "clobbers": {"registers": [], "flags": ["n", "z"]},
        "preserved": ["r4"],
        "stack_delta_on_return": 0,
        "memory": "stack-only",
        "calls": "none",
        "oracle": {"kind": "synthetic-differential-planned", "reference": "independent reference trace, not yet run"},
    }
    contract.update(changes)
    return contract


class ContractCheckTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.exheader = self.root / "exheader.bin"
        self.code = self.root / "code.bin"
        self.exheader.write_bytes(build_exheader())

    def report(self, words, count=None, **kwargs):
        data = bytearray(0x3000)
        put_units(data, 0, words, 2)
        self.code.write_bytes(data)
        result = ranges.inspect_code_range(
            "ultra-sun", self.exheader, self.code, "thumb", 0x00100000,
            count or len(words), title_id=TITLE, **kwargs,
        )
        return json.loads(json.dumps(result))      # exactly what a saved local report would hold

    def codes(self, result, bucket="violations"):
        return sorted(item["code"] for item in result[bucket])

    # --- a well-formed function: PUSH {r4, lr}; MOVS r0,#1; POP {r4, pc}
    def test_consistent_function_is_never_called_validated(self):
        result = fc.check_contract(base_contract(), self.report([0xB510, 0x2001, 0xBD10]))
        self.assertEqual("consistent-with-observed-static-effects", result["status"])
        self.assertEqual([], result["violations"])
        self.assertEqual(0, result["observed"]["stack_delta_on_return"])
        self.assertEqual(["preserved-register-written", "stack-only-unproven"], self.codes(result, "needs_proof"))
        self.assertEqual("required-not-run", result["oracle"]["status"])
        self.assertNotIn("validated", result["status"])
        self.assertEqual(1, sum("not validation" in text for text in result["limitations"]))

    def test_declared_stack_delta_mismatch_is_a_violation(self):
        result = fc.check_contract(base_contract(stack_delta_on_return=-4), self.report([0xB510, 0x2001, 0xBD10]))
        self.assertEqual("contract-violations", result["status"])
        found = result["violations"][0]
        self.assertEqual("stack-delta-mismatch", found["code"])
        self.assertEqual({"observed": 0, "declared": -4}, found["detail"])

    def test_unbalanced_stack_is_caught(self):
        result = fc.check_contract(base_contract(), self.report([0xB510, 0x2001, 0xBC10, 0x4770]))
        self.assertEqual(["stack-delta-mismatch"], self.codes(result))
        self.assertEqual({"observed": -4, "declared": 0}, result["violations"][0]["detail"])   # -8 (push) + 4 (pop r4)
        self.assertEqual(-4, result["observed"]["stack_delta_on_return"])

    def test_undeclared_register_and_flag_writes(self):
        report = self.report([0xB510, 0x2001, 0xBD10])
        result = fc.check_contract(base_contract(outputs={"registers": [], "flags": []}), report)
        self.assertEqual(["undeclared-register-write"], self.codes(result))
        self.assertEqual("r0", result["violations"][0]["detail"]["register"])
        result = fc.check_contract(base_contract(clobbers={"registers": [], "flags": []}), report)
        self.assertEqual(["undeclared-flag-write", "undeclared-flag-write"], self.codes(result))
        self.assertEqual(["n", "z"], sorted(v["detail"]["flag"] for v in result["violations"]))

    def test_memory_none_flags_stack_traffic(self):
        result = fc.check_contract(base_contract(memory="none"), self.report([0xB510, 0x2001, 0xBD10]))
        self.assertEqual(["memory-access-observed"], self.codes(result))

    def test_undeclared_input_register_and_flag_reads(self):
        report = self.report([0x2900, 0x4770])            # CMP r1,#0; BX LR
        contract = base_contract(preserved=[], outputs={"registers": [], "flags": []},
                                 clobbers={"registers": [], "flags": ["n", "z", "c", "v"]}, memory="none")
        result = fc.check_contract(contract, report)
        self.assertEqual(["undeclared-input-read"], self.codes(result))
        self.assertEqual("r1", result["violations"][0]["detail"]["register"])
        contract["inputs"] = {"registers": ["r1"], "flags": []}
        self.assertEqual("consistent-with-observed-static-effects", fc.check_contract(contract, report)["status"])

        branchy = self.report([0xD000, 0x4770])             # BEQ +0; BX LR: Z is read and never written
        contract = base_contract(preserved=[], outputs={"registers": [], "flags": []},
                                 clobbers={"registers": [], "flags": []}, memory="none")
        result = fc.check_contract(contract, branchy)
        self.assertEqual(["undeclared-flag-input"], self.codes(result))
        self.assertEqual("z", result["violations"][0]["detail"]["flag"])
        contract["inputs"] = {"registers": [], "flags": ["z"]}
        result = fc.check_contract(contract, branchy)
        self.assertEqual("consistent-with-observed-static-effects", result["status"])
        self.assertEqual(["stack-delta-unverifiable"], self.codes(result, "unverifiable"))   # branches are path-dependent

    def test_a_flag_read_before_a_later_write_is_not_flagged_documented_limit(self):
        # BEQ reads Z, then MOVS writes it: the rule is deliberately not path/order sensitive.
        result = fc.check_contract(base_contract(preserved=[], memory="none"), self.report([0xD000, 0x2001, 0x4770]))
        self.assertEqual("consistent-with-observed-static-effects", result["status"])
        self.assertTrue(any("not flagged" in text for text in result["limitations"]))

    def test_calls_are_a_violation_unless_declared_and_then_assumed(self):
        report = self.report([0xB510, 0xF000, 0xF800, 0xBD10], count=3)     # PUSH; BL +0; POP {r4, pc}
        result = fc.check_contract(base_contract(clobbers={"registers": [], "flags": ["n", "z"]}), report)
        self.assertEqual(["call-observed"], self.codes(result))
        self.assertEqual("0x00100002", result["violations"][0]["detail"]["address"])
        allowed = fc.check_contract(base_contract(calls="allowed", outputs={"registers": [], "flags": []},
                                                  clobbers={"registers": ["r0", "r1", "r2", "r3", "r12"], "flags": []}), report)
        self.assertEqual("consistent-with-observed-static-effects", allowed["status"], allowed["violations"])
        self.assertEqual(1, len(allowed["assumptions"]))
        self.assertEqual(0, allowed["observed"]["stack_delta_on_return"])

    def test_missing_return_and_indirect_transfers_are_unverifiable_not_violations(self):
        result = fc.check_contract(base_contract(memory="none", preserved=[]), self.report([0x2001]))
        self.assertEqual("consistent-with-observed-static-effects", result["status"])
        self.assertEqual(["no-return-observed", "stack-delta-unverifiable"], self.codes(result, "unverifiable"))
        result = fc.check_contract(base_contract(memory="none", preserved=[]), self.report([0x2001, 0x4718]))
        self.assertIn("indirect-transfer-unresolved", self.codes(result, "unverifiable"))

    def test_fails_closed_when_the_range_is_incomplete(self):
        report = self.report([0xB510, 0x46C0, 0xBD10], include_unsupported=True)
        result = fc.check_contract(base_contract(), report)
        self.assertEqual("not-validatable", result["status"])
        self.assertIsNone(result["observed"])
        self.assertEqual([], result["violations"])
        self.assertTrue(any("unsupported or raw" in reason for reason in result["not_validatable_reasons"]))

    def test_identity_mismatches_are_not_validatable(self):
        report = self.report([0xB510, 0x2001, 0xBD10])
        for change, text in (
            ({"entry_address": "0x00100002"}, "explicit range start"),
            ({"state": "arm"}, "state"),
            ({"target_id": "ultra-moon"}, "target"),
        ):
            with self.subTest(change=change):
                result = fc.check_contract(base_contract(**change), report)
                self.assertEqual("not-validatable", result["status"])
                self.assertTrue(any(text in reason for reason in result["not_validatable_reasons"]))

    def test_unknown_or_non_call_partial_effects_fail_closed_but_calls_do_not(self):
        report = self.report([0xB510, 0xF000, 0xF800, 0xBD10], count=3)
        self.assertEqual("partial", report["dataflow"]["instructions"][1]["status"])      # BL: callee effects unknown
        self.assertNotEqual("not-validatable", fc.check_contract(base_contract(calls="allowed"), report)["status"])
        broken = copy.deepcopy(report)
        broken["dataflow"]["instructions"][2]["status"] = "unknown"
        result = fc.check_contract(base_contract(calls="allowed"), broken)
        self.assertEqual("not-validatable", result["status"])
        self.assertTrue(any("unknown or partial" in reason for reason in result["not_validatable_reasons"]))
        broken["dataflow"]["instructions"][2]["status"] = "partial"                      # non-call partial also fails closed
        self.assertEqual("not-validatable", fc.check_contract(base_contract(calls="allowed"), broken)["status"])

    def test_a_non_call_instruction_writing_lr_is_still_reported(self):
        report = self.report([0xB510, 0xF000, 0xF800, 0xBD10], count=3)
        report["dataflow"]["instructions"][0]["registers_written"].append("lr")           # e.g. a MOV lr, Rx
        result = fc.check_contract(base_contract(calls="allowed", outputs={"registers": [], "flags": []},
                                                 clobbers={"registers": [], "flags": []}), report)
        self.assertIn("lr", [v["detail"].get("register") for v in result["violations"]])

    def test_input_objects_are_not_modified(self):
        contract, report = base_contract(), self.report([0xB510, 0x2001, 0xBD10])
        before = copy.deepcopy((contract, report))
        fc.check_contract(contract, report)
        self.assertEqual(before, (contract, report))


class ContractSchemaTests(unittest.TestCase):
    def rejects(self, **changes):
        with self.assertRaises(fc.ContractError, msg=repr(changes)):
            fc.parse_contract(base_contract(**changes))

    def test_accepts_the_reference_contract(self):
        parsed = fc.parse_contract(base_contract())
        self.assertEqual(0x00100000, parsed["entry_address"])

    def test_rejects_malformed_fields(self):
        self.rejects(schema_version=2)
        self.rejects(schema_version=True)
        self.rejects(contract_id="has space")
        self.rejects(contract_id="x" * 65)
        self.rejects(target_id="ultra-star")
        self.rejects(state="thumb2")
        self.rejects(entry_address="0x00100001")                 # unaligned for Thumb
        self.rejects(entry_address="0x1FFFFFFFF")                # wider than uint32
        self.rejects(entry_address="1048576")
        self.rejects(state="arm", entry_address="0x00100002")    # unaligned for ARM
        self.rejects(memory="maybe")
        self.rejects(calls="sometimes")
        self.rejects(stack_delta_on_return=2)
        self.rejects(stack_delta_on_return=True)
        self.rejects(stack_delta_on_return=0x10004)
        self.rejects(stack_delta_on_return="0")

    def test_rejects_bad_register_and_flag_lists(self):
        self.rejects(inputs={"registers": ["r16"], "flags": []})
        self.rejects(inputs={"registers": ["R0"], "flags": []})
        self.rejects(inputs={"registers": ["r0", "r0"], "flags": []})
        self.rejects(inputs={"registers": [], "flags": ["x"]})
        self.rejects(inputs={"registers": ["pc"], "flags": []})
        self.rejects(inputs={"registers": []})
        self.rejects(inputs={"registers": [], "flags": [], "extra": []})
        self.rejects(preserved=["pc"])
        self.rejects(preserved="r4")
        self.rejects(preserved=["r0"])                            # r0 is also an output
        self.rejects(clobbers={"registers": ["r4"], "flags": []})  # r4 is also preserved
        self.rejects(outputs={"registers": [], "flags": ["n"]})    # n is also clobbered

    def test_rejects_unknown_missing_keys_and_weak_oracle(self):
        with self.assertRaises(fc.ContractError):
            fc.parse_contract({**base_contract(), "typo": 1})
        missing = base_contract()
        del missing["memory"]
        with self.assertRaises(fc.ContractError):
            fc.parse_contract(missing)
        self.rejects(oracle={"kind": "x"})
        self.rejects(oracle={"kind": "x", "reference": "  "})
        self.rejects(oracle={"kind": "x", "reference": "y", "status": "passed"})
        self.rejects(oracle="independent reference")
        for bad in (None, [], "contract", 1):
            with self.assertRaises(fc.ContractError):
                fc.parse_contract(bad)

    def test_rejects_reports_with_missing_parts(self):
        for broken in ({}, {"target": {"target_id": "ultra-sun"}}, {"instructions": []}):
            with self.assertRaises(fc.ContractError):
                fc.check_contract(base_contract(), broken)


class ContractCliTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        exheader, code = self.root / "exheader.bin", self.root / "code.bin"
        exheader.write_bytes(build_exheader())
        data = bytearray(0x3000)
        put_units(data, 0, [0xB510, 0x2001, 0xBD10], 2)
        code.write_bytes(data)
        self.report = ranges.inspect_code_range("ultra-sun", exheader, code, "thumb", 0x00100000, 3, title_id=TITLE)
        self.report_path = self.root / "report.json"
        self.report_path.write_text(json.dumps(self.report), encoding="utf-8")

    def run_cli(self, contract, *extra):
        path = self.root / "contract.json"
        path.write_text(json.dumps(contract), encoding="utf-8")
        return subprocess.run(
            [sys.executable, str(ROOT / "tools" / "check_function_contract.py"),
             "--contract", str(path), "--report", str(self.report_path), *extra],
            capture_output=True, text=True,
        )

    def test_exit_codes_follow_the_verdict(self):
        ok = self.run_cli(base_contract())
        self.assertEqual(0, ok.returncode, msg=ok.stderr)
        self.assertEqual("consistent-with-observed-static-effects", json.loads(ok.stdout)["status"])
        bad = self.run_cli(base_contract(stack_delta_on_return=-4))
        self.assertEqual(1, bad.returncode)
        unknown = self.run_cli(base_contract(target_id="ultra-moon"))
        self.assertEqual(2, unknown.returncode)
        self.assertEqual("not-validatable", json.loads(unknown.stdout)["status"])

    def test_malformed_inputs_exit_two_with_a_clear_message(self):
        run = self.run_cli(base_contract(memory="maybe"))
        self.assertEqual(2, run.returncode)
        self.assertIn("memory must be one of", run.stderr)
        self.assertEqual("", run.stdout)
        run = subprocess.run(
            [sys.executable, str(ROOT / "tools" / "check_function_contract.py"),
             "--contract", str(self.root / "missing.json"), "--report", str(self.report_path)],
            capture_output=True, text=True,
        )
        self.assertEqual(2, run.returncode)
        self.assertIn("cannot read contract JSON", run.stderr)

    def test_output_inside_the_repository_is_refused(self):
        run = self.run_cli(base_contract(), "--output", str(ROOT / "contract-result.json"))
        self.assertEqual(2, run.returncode)
        self.assertIn("outside the repository", run.stderr)
        self.assertFalse((ROOT / "contract-result.json").exists())
        outside = self.root / "result.json"
        self.assertEqual(0, self.run_cli(base_contract(), "--output", str(outside)).returncode)
        self.assertEqual("synthetic-001", json.loads(outside.read_text(encoding="utf-8"))["contract_id"])


if __name__ == "__main__":
    unittest.main()
