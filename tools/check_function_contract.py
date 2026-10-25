#!/usr/bin/env python3
"""Check a maintainer-declared candidate function contract against a local range report.

The contract is a *claim* made by the maintainer; nothing here infers it. The
checker only reports violations that the statically observed effects of the
explicitly selected range prove, and lists separately what it cannot decide.
It never executes code, never reads game files and never says a function is
validated: an independent oracle is always still required.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]

SCHEMA_VERSION = 1
TARGETS = ("ultra-sun", "ultra-moon")
STATES = ("arm", "thumb")
REGISTERS = tuple(f"r{n}" for n in range(13)) + ("sp", "lr", "pc")
FLAGS = ("n", "z", "c", "v")
MEMORY_MODES = ("none", "stack-only", "may-access")
CALL_MODES = ("none", "allowed")
IMPLICIT_READS = {"sp", "lr", "pc"}
IMPLICIT_WRITES = {"sp", "pc"}
RETURN_FLOWS = ("return", "return-or-indirect-branch")
BRANCH_FLOWS = ("branch", "conditional-branch", "indirect-branch")
CALL_FLOWS = ("call", "indirect-call")
CONTRACT_KEYS = {
    "schema_version", "contract_id", "target_id", "state", "entry_address", "inputs", "outputs",
    "clobbers", "preserved", "stack_delta_on_return", "memory", "calls", "oracle",
}
ID_PATTERN = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")
ADDRESS_PATTERN = re.compile(r"^0x[0-9A-Fa-f]{1,8}$")

LIMITATIONS = (
    "The contract is a maintainer claim; it is not inferred from, or proven against, the game.",
    "Violations are only those proven by statically observed effects of the selected range; the analysis is not path-sensitive.",
    "Register and flag reads are checked only against those never written in the range; a read before a later write is not flagged.",
    "Preservation of a register, memory addresses, callee behaviour and the real ABI are not proven; they need an independent oracle.",
    "A consistent result is not validation, equivalence, or permission to emit C; the oracle is always required-not-run here.",
)


class ContractError(ValueError):
    """The contract or the report is malformed or outside this checker's scope."""


def _address(value: object, field: str) -> int:
    if not isinstance(value, str) or not ADDRESS_PATTERN.match(value):
        raise ContractError(f"{field} must be a hexadecimal string like 0x00100000: {value!r}")
    return int(value, 16)


def _name_list(value: object, field: str, allowed: tuple[str, ...], *, forbid: tuple[str, ...] = ()) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ContractError(f"{field} must be a list of strings")
    if len(set(value)) != len(value):
        raise ContractError(f"{field} contains duplicates")
    for item in value:
        if item not in allowed:
            raise ContractError(f"{field} contains an unknown name: {item!r}")
        if item in forbid:
            raise ContractError(f"{field} may not name {item!r}; it is handled implicitly")
    return list(value)


def _group(contract: dict[str, Any], key: str) -> dict[str, list[str]]:
    group = contract.get(key)
    if not isinstance(group, dict) or set(group) != {"registers", "flags"}:
        raise ContractError(f"{key} must be an object with exactly 'registers' and 'flags'")
    return {
        "registers": _name_list(group["registers"], f"{key}.registers", REGISTERS, forbid=("pc",)),
        "flags": _name_list(group["flags"], f"{key}.flags", FLAGS),
    }


def parse_contract(contract: object) -> dict[str, Any]:
    """Validate the contract's shape and internal consistency, returning a normalized copy."""
    if not isinstance(contract, dict):
        raise ContractError("contract must be a JSON object")
    unknown = sorted(set(contract) - CONTRACT_KEYS)
    missing = sorted(CONTRACT_KEYS - set(contract))
    if unknown:
        raise ContractError(f"contract has unknown keys: {unknown}")
    if missing:
        raise ContractError(f"contract is missing keys: {missing}")
    if contract["schema_version"] != SCHEMA_VERSION or isinstance(contract["schema_version"], bool):
        raise ContractError(f"schema_version must be {SCHEMA_VERSION}")
    if not isinstance(contract["contract_id"], str) or not ID_PATTERN.match(contract["contract_id"]):
        raise ContractError("contract_id must be 1..64 characters of [A-Za-z0-9_.-]")
    if contract["target_id"] not in TARGETS:
        raise ContractError(f"target_id must be one of {TARGETS}")
    if contract["state"] not in STATES:
        raise ContractError(f"state must be one of {STATES}")
    entry = _address(contract["entry_address"], "entry_address")
    unit = 4 if contract["state"] == "arm" else 2
    if entry % unit:
        raise ContractError(f"entry_address 0x{entry:08X} is not aligned for {contract['state']}")

    inputs, outputs, clobbers = (_group(contract, key) for key in ("inputs", "outputs", "clobbers"))
    preserved = _name_list(contract["preserved"], "preserved", REGISTERS, forbid=("pc",))
    overlap = sorted(set(preserved) & (set(outputs["registers"]) | set(clobbers["registers"])))
    if overlap:
        raise ContractError(f"registers cannot be both preserved and output/clobbered: {overlap}")
    flag_overlap = sorted(set(outputs["flags"]) & set(clobbers["flags"]))
    if flag_overlap:
        raise ContractError(f"flags cannot be both output and clobbered: {flag_overlap}")

    delta = contract["stack_delta_on_return"]
    if isinstance(delta, bool) or not isinstance(delta, int) or delta % 4 or not -0x10000 <= delta <= 0x10000:
        raise ContractError("stack_delta_on_return must be a multiple of 4 within +/-65536")
    if contract["memory"] not in MEMORY_MODES:
        raise ContractError(f"memory must be one of {MEMORY_MODES}")
    if contract["calls"] not in CALL_MODES:
        raise ContractError(f"calls must be one of {CALL_MODES}")
    oracle = contract["oracle"]
    if (
        not isinstance(oracle, dict) or set(oracle) != {"kind", "reference"}
        or any(not isinstance(oracle[k], str) or not oracle[k].strip() for k in oracle)
    ):
        raise ContractError("oracle must name a non-empty 'kind' and 'reference' for the independent comparison")

    return {
        **{key: contract[key] for key in ("schema_version", "contract_id", "target_id", "state", "memory", "calls")},
        "entry_address": entry, "inputs": inputs, "outputs": outputs, "clobbers": clobbers,
        "preserved": preserved, "stack_delta_on_return": delta, "oracle": dict(oracle),
    }


def _need(mapping: object, key: str, where: str) -> Any:
    if not isinstance(mapping, dict) or key not in mapping:
        raise ContractError(f"report is missing {where}.{key}" if where else f"report is missing {key}")
    return mapping[key]


def _report_parts(report: object) -> dict[str, Any]:
    target = _need(_need(report, "target", ""), "target_id", "target")
    range_info = _need(report, "range", "")
    dataflow = _need(report, "dataflow", "")
    flow = _need(report, "control_flow", "")
    instructions = _need(report, "instructions", "")
    if not isinstance(instructions, list) or not instructions:
        raise ContractError("report.instructions must be a non-empty list")
    effects = _need(dataflow, "instructions", "dataflow")
    if not isinstance(effects, list) or len(effects) != len(instructions):
        raise ContractError("report.dataflow.instructions must match report.instructions")
    return {
        "target_id": target,
        "state": _need(range_info, "state", "range"),
        "start": _address(_need(range_info, "start_address", "range"), "range.start_address"),
        "raw": bool(range_info.get("includes_unsupported_raw_encodings")),
        "cfg_entry": _address(_need(flow, "entry_address", "control_flow"), "control_flow.entry_address"),
        "dataflow": dataflow,
        "instructions": instructions,
        "effects": effects,
    }


def _finding(code: str, message: str, **detail: Any) -> dict[str, Any]:
    return {"code": code, "message": message, "detail": detail}


def _stack_delta(parts: dict[str, Any]) -> tuple[int | None, str | None]:
    """Net SP change up to the first return-like instruction, or (None, reason)."""
    paired = sorted(zip(parts["instructions"], parts["effects"]), key=lambda pair: _address(
        pair[0].get("virtual_address"), "instruction.virtual_address"))
    for _, effect in paired:
        if effect.get("control_flow") in BRANCH_FLOWS:
            return None, "the range contains branches, so the stack delta is path-dependent"
    total = 0
    for item, effect in paired:
        delta_keys = [key for key in ("stack_delta_bytes", "stack_pointer_delta_bytes") if key in item]
        writes_sp = "sp" in effect.get("registers_written", [])
        if writes_sp and not delta_keys:
            return None, f"instruction at {item.get('virtual_address')} writes SP without a reported delta"
        if delta_keys and effect.get("conditional"):
            return None, f"conditional SP change at {item.get('virtual_address')} is path-dependent"
        for key in delta_keys:
            value = item[key]
            if isinstance(value, bool) or not isinstance(value, int):
                raise ContractError(f"{key} must be an integer at {item.get('virtual_address')}")
            total += value
        if effect.get("control_flow") in RETURN_FLOWS:
            return total, None
    return None, "no return-like instruction was observed"


def check_contract(contract: object, report: object) -> dict[str, Any]:
    """Compare a contract with a range report; see the module docstring for scope."""
    spec = parse_contract(contract)
    parts = _report_parts(report)
    dataflow = parts["dataflow"]

    reasons: list[str] = []
    if parts["target_id"] != spec["target_id"]:
        reasons.append(f"report target {parts['target_id']!r} differs from contract target {spec['target_id']!r}")
    if parts["state"] != spec["state"]:
        reasons.append(f"report state {parts['state']!r} differs from contract state {spec['state']!r}")
    if parts["start"] != spec["entry_address"] or parts["cfg_entry"] != spec["entry_address"]:
        reasons.append(
            f"contract entry 0x{spec['entry_address']:08X} is not the explicit range start 0x{parts['start']:08X}"
        )
    if parts["raw"] or any(item.get("decode_status") != "decoded" for item in parts["instructions"]):
        reasons.append("the range contains unsupported or raw encodings, so its effects are incomplete")
    incomplete = [
        effect.get("instruction_address") for effect in parts["effects"]
        if effect.get("status") == "unknown"
        or (effect.get("status") != "known" and effect.get("control_flow") not in CALL_FLOWS)
    ]
    if incomplete:
        reasons.append(f"the effects of {len(incomplete)} instruction(s) are unknown or partial: {incomplete}")

    base: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "contract_id": spec["contract_id"],
        "target_id": spec["target_id"],
        "entry_address": f"0x{spec['entry_address']:08X}",
        "oracle": {"declared": spec["oracle"], "status": "required-not-run"},
        "limitations": list(LIMITATIONS),
    }
    if reasons:
        return {**base, "status": "not-validatable", "not_validatable_reasons": reasons,
                "violations": [], "needs_proof": [], "unverifiable": [], "assumptions": [], "observed": None}

    reads = set(dataflow["observed_registers_read"])
    writes = set(dataflow["observed_registers_written"])
    flags_read = set(dataflow["observed_flags_read"])
    flags_written = set(dataflow["observed_flags_written"])
    declared_in = set(spec["inputs"]["registers"])
    declared_out = set(spec["outputs"]["registers"])
    declared_clobber = set(spec["clobbers"]["registers"])
    preserved = set(spec["preserved"])
    calls = [effect for effect in parts["effects"] if effect.get("control_flow") in CALL_FLOWS]

    violations: list[dict[str, Any]] = []
    needs_proof: list[dict[str, Any]] = []
    unverifiable: list[dict[str, Any]] = []
    assumptions: list[str] = []

    # A call's own register effects (link register, callee clobbers) are governed by the
    # contract's `calls` mode, so they are not also reported as undeclared writes.
    direct_writes = {
        register for effect in parts["effects"] if effect.get("control_flow") not in CALL_FLOWS
        for register in effect.get("registers_written", [])
    }
    allowed_writes = declared_out | declared_clobber | preserved | IMPLICIT_WRITES
    for register in sorted(direct_writes - allowed_writes):
        violations.append(_finding("undeclared-register-write",
                                   f"{register} is written but is not an output, clobber or preserved register",
                                   register=register))
    for register in sorted((direct_writes & preserved) - {"sp"}):
        needs_proof.append(_finding("preserved-register-written",
                                    f"{register} is declared preserved but written; restoration is not proven",
                                    register=register))
    undeclared_reads = reads - writes - declared_in - preserved - IMPLICIT_READS
    for register in sorted(undeclared_reads):
        violations.append(_finding("undeclared-input-read",
                                   f"{register} is read but never written in the range and is not a declared input",
                                   register=register))

    for flag in sorted(flags_read - flags_written - set(spec["inputs"]["flags"])):
        violations.append(_finding("undeclared-flag-input",
                                   f"flag {flag} is read but never written in the range and is not a declared input",
                                   flag=flag))
    for flag in sorted(flags_written - set(spec["outputs"]["flags"]) - set(spec["clobbers"]["flags"])):
        violations.append(_finding("undeclared-flag-write",
                                   f"flag {flag} is written but is neither an output nor a clobber", flag=flag))

    memory_present = bool(dataflow.get("memory_effects_present"))
    if spec["memory"] == "none" and memory_present:
        violations.append(_finding("memory-access-observed", "memory effects are present but the contract says none"))
    elif spec["memory"] == "stack-only" and memory_present:
        needs_proof.append(_finding("stack-only-unproven",
                                    "memory effects are present; addresses are unresolved, so stack-only is unproven"))

    if spec["calls"] == "none":
        for effect in calls:
            violations.append(_finding("call-observed", "a call is present but the contract says none",
                                       address=effect.get("instruction_address")))
    elif calls:
        assumptions.append("callees are assumed to preserve SP and not to alter the declared preserved registers")

    flows = [effect.get("control_flow") for effect in parts["effects"]]
    if not any(flow in RETURN_FLOWS for flow in flows):
        unverifiable.append(_finding("no-return-observed", "no return-like instruction was observed in the range"))
    if any(flow in ("indirect-branch", "return-or-indirect-branch") for flow in flows):
        unverifiable.append(_finding("indirect-transfer-unresolved",
                                     "an indirect transfer exists; whether it is a return is not resolved"))

    observed_delta, why = _stack_delta(parts)
    if observed_delta is None:
        unverifiable.append(_finding("stack-delta-unverifiable", why or "unknown"))
    elif observed_delta != spec["stack_delta_on_return"]:
        violations.append(_finding("stack-delta-mismatch",
                                   f"observed net SP change {observed_delta} differs from declared "
                                   f"{spec['stack_delta_on_return']}", observed=observed_delta,
                                   declared=spec["stack_delta_on_return"]))

    status = "contract-violations" if violations else "consistent-with-observed-static-effects"
    return {
        **base, "status": status, "violations": violations, "needs_proof": needs_proof,
        "unverifiable": unverifiable, "assumptions": assumptions,
        "observed": {
            "registers_read": sorted(reads), "registers_written": sorted(writes),
            "flags_read": sorted(flags_read), "flags_written": sorted(flags_written),
            "stack_delta_on_return": observed_delta,
        },
    }


def _load_json(path: Path, label: str) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ContractError(f"cannot read {label} JSON {path.name}: {exc}") from exc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Check a declared candidate function contract against a local range report; reads no game files."
    )
    parser.add_argument("--contract", required=True, type=Path, help="maintainer-written contract JSON")
    parser.add_argument("--report", required=True, type=Path, help="JSON report from inspect_3ds_code_range.py")
    parser.add_argument("--output", type=Path, help="write the result to a local file outside the repository")
    args = parser.parse_args(argv)
    try:
        result = check_contract(_load_json(args.contract, "contract"), _load_json(args.report, "report"))
        rendered = json.dumps(result, indent=2, ensure_ascii=False) + "\n"
        if args.output:
            target = args.output.resolve()
            if target == ROOT or ROOT in target.parents:
                raise ContractError("output must be outside the repository")
            args.output.write_text(rendered, encoding="utf-8", newline="\n")
        else:
            sys.stdout.write(rendered)
    except (ContractError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    return {"consistent-with-observed-static-effects": 0, "contract-violations": 1}.get(result["status"], 2)


if __name__ == "__main__":
    raise SystemExit(main())
