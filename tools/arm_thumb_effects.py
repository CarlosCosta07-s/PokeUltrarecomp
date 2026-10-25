"""Conservative register/flag effect summaries for explicit ARM/Thumb decode records.

This is static bookkeeping, not symbolic execution or an ABI inference engine.
Unknown encodings and call side effects remain explicitly incomplete.
"""
from __future__ import annotations

from typing import Any

CONDITION_FLAGS = {"n", "z", "c", "v"}


def _reg(number: int) -> str:
    return "sp" if number == 13 else "lr" if number == 14 else "pc" if number == 15 else f"r{number}"


def instruction_effects(item: dict[str, Any], state: str) -> dict[str, Any]:
    """Summarize register/flag effects for one inspected instruction."""
    address = item.get("virtual_address")
    decoded = item.get("decoded_ir")
    base = {
        "instruction_address": address,
        "mnemonic": item.get("mnemonic"),
        "status": "known",
        "registers_read": [],
        "registers_written": [],
        "flags_read": [],
        "flags_written": [],
        "memory": "none",
        "control_flow": "fallthrough",
        "conditional": False,
        "notes": [],
    }
    if item.get("decode_status", "decoded") != "decoded" or not isinstance(decoded, (list, tuple)) or not decoded:
        base["status"] = "unknown"
        base["memory"] = "unknown"
        base["control_flow"] = "unknown"
        base["notes"].append("unsupported encoding: register, flag, memory and control-flow effects are not inferred")
        return base

    op_ir = tuple(decoded)
    if op_ir[0] == "predicated":
        _, condition, inner = op_ir
        inner_item = dict(item, decoded_ir=inner)
        effect = instruction_effects(inner_item, state)
        effect["conditional"] = True
        effect["flags_read"] = sorted(set(effect["flags_read"]) | CONDITION_FLAGS)
        effect["notes"].append(f"execution is predicated on condition {condition}")
        return effect

    op = op_ir[0]
    reads: set[str] = set()
    writes: set[str] = set()
    flags_read: set[str] = set()
    flags_written: set[str] = set()
    memory = "none"
    flow = "fallthrough"
    notes: list[str] = []
    conditional = False

    if op == "branch":
        condition = str(op_ir[1])
        if condition != "al":
            flags_read |= CONDITION_FLAGS
            conditional = True
        writes.add("pc")
        flow = "conditional-branch" if conditional else "branch"
    elif op == "return":
        reads.add("lr")
        writes.add("pc")
        flow = "return"
    elif op in ("bx", "blx_reg"):
        reads.add(_reg(int(op_ir[1])))
        writes.add("pc")
        flow = "indirect-call" if op == "blx_reg" else "indirect-branch"
        if op == "blx_reg":
            writes.add("lr")
            notes.append("callee and caller-saved register effects are unknown")
            base["status"] = "partial"
    elif op == "call":
        writes.update(("lr", "pc"))
        flow = "call"
        base["status"] = "partial"
        notes.append("call target's effects and ABI clobbers are unknown")
    elif op in ("mov", "mvn", "movs"):
        writes.add(_reg(int(op_ir[1])))
        if op == "movs":
            flags_written |= {"n", "z"}
    elif op in ("adds", "subs"):
        reads.add(_reg(int(op_ir[1])))
        writes.add(_reg(int(op_ir[1])))
        flags_written |= CONDITION_FLAGS
    elif op in ("add", "sub", "and", "orr", "eor", "bic"):
        writes.add(_reg(int(op_ir[1])))
        reads.add(_reg(int(op_ir[2])))
        if op in ("add", "sub"):
            pass
    elif op in ("cmp", "cmn"):
        reads.add(_reg(int(op_ir[1])))
        flags_written |= CONDITION_FLAGS
    elif op in ("lsl_imm", "lsr_imm", "asr_imm"):
        writes.add(_reg(int(op_ir[1])))
        reads.add(_reg(int(op_ir[2])))
        flags_written |= {"n", "z", "c"}
        notes.append("carry behavior depends on shift amount; V is preserved")
    elif op in ("adds_imm3", "subs_imm3"):
        writes.add(_reg(int(op_ir[1])))
        reads.add(_reg(int(op_ir[2])))
        flags_written |= CONDITION_FLAGS
    elif op in {
        "ands_reg", "eors_reg", "lsls_reg", "lsrs_reg", "asrs_reg",
        "adcs_reg", "sbcs_reg", "rors_reg", "tst_reg", "rsbs_zero",
        "cmp_reg", "cmn_reg", "orrs_reg", "muls_reg", "bics_reg", "mvns_reg",
    }:
        dest, source = int(op_ir[1]), int(op_ir[2])
        reads.add(_reg(source))
        if op not in ("rsbs_zero",):
            reads.add(_reg(dest))
        if op in ("cmp_reg", "cmn_reg", "tst_reg"):
            pass
        else:
            writes.add(_reg(dest))
        if op in ("adcs_reg", "sbcs_reg"):
            flags_read.add("c")
            flags_written |= CONDITION_FLAGS
        elif op in ("cmp_reg", "cmn_reg", "rsbs_zero"):
            flags_written |= CONDITION_FLAGS
        elif op == "muls_reg":
            flags_written |= {"n", "z"}
            notes.append("C and V are preserved")
        else:
            flags_written |= {"n", "z", "c"}
            notes.append("V is preserved; C follows the operation's shifter semantics")
    elif op == "ldr_literal":
        reads.add("pc")
        writes.add(_reg(int(op_ir[1])))
        memory = "read"
    elif op in ("push", "pop", "pop_pc"):
        mask = int(op_ir[1])
        regs = {_reg(n) for n in range(8) if (mask >> n) & 1}
        reads.add("sp")
        writes.add("sp")
        if op == "push":
            regs |= {"lr"} if bool(op_ir[2]) else set()
            reads |= regs
            memory = "write"
        else:
            writes |= regs
            memory = "read"
            if op == "pop_pc":
                writes.add("pc")
                flow = "return-or-indirect-branch"
    elif op in ("str_reg", "strh_reg", "strb_reg", "ldrsb_reg", "ldr_reg", "ldrh_reg", "ldrb_reg", "ldrsh_reg"):
        rt, rn, rm = map(int, op_ir[1:4])
        reads |= {_reg(rn), _reg(rm)}
        if op.startswith("str"):
            reads.add(_reg(rt))
            memory = "write"
        else:
            writes.add(_reg(rt))
            memory = "read"
    elif op in ("str_imm", "ldr_imm", "strb_imm", "ldrb_imm", "strh_imm", "ldrh_imm"):
        rt, rn = map(int, op_ir[1:3])
        reads.add(_reg(rn))
        if op.startswith("str"):
            reads.add(_reg(rt))
            memory = "write"
        else:
            writes.add(_reg(rt))
            memory = "read"
    elif op in ("str_sp", "ldr_sp"):
        rt = int(op_ir[1])
        reads.add("sp")
        if op == "str_sp":
            reads.add(_reg(rt))
            memory = "write"
        else:
            writes.add(_reg(rt))
            memory = "read"
    elif op in ("stmia", "ldmia"):
        rn, mask = int(op_ir[1]), int(op_ir[2])
        base_reg = _reg(rn)
        regs = {_reg(n) for n in range(8) if (mask >> n) & 1}
        reads.add(base_reg)
        memory = "write" if op == "stmia" else "read"
        if op == "stmia":
            reads |= regs
            writes.add(base_reg)
        else:
            writes |= regs
            if base_reg not in regs:
                writes.add(base_reg)
    elif op == "adr":
        reads.add("pc")
        writes.add(_reg(int(op_ir[1])))
    elif op == "add_sp_imm":
        reads.add("sp")
        writes.add(_reg(int(op_ir[1])))
    elif op in ("add_sp", "sub_sp"):
        reads.add("sp")
        writes.add("sp")
    else:
        base["status"] = "unknown"
        base["memory"] = "unknown"
        base["control_flow"] = "unknown"
        base["notes"].append(f"no effect rule for decoded operation {op!r}")
        return base

    base.update({
        "registers_read": sorted(reads),
        "registers_written": sorted(writes),
        "flags_read": sorted(flags_read),
        "flags_written": sorted(flags_written),
        "memory": memory,
        "control_flow": flow,
        "conditional": conditional,
        "notes": notes,
    })
    return base


def summarize_range(instructions: list[dict[str, Any]], state: str) -> dict[str, Any]:
    """Attach per-instruction effects and aggregate only the observed effects."""
    effects = [instruction_effects(item, state) for item in instructions]
    reads = sorted({reg for effect in effects for reg in effect["registers_read"]})
    writes = sorted({reg for effect in effects for reg in effect["registers_written"]})
    flags_read = sorted({flag for effect in effects for flag in effect["flags_read"]})
    flags_written = sorted({flag for effect in effects for flag in effect["flags_written"]})
    uncertain = [effect["instruction_address"] for effect in effects if effect["status"] != "known"]
    return {
        "status": "observed-effects-with-uncertainty" if uncertain else "observed-effects",
        "instruction_count": len(effects),
        "observed_registers_read": reads,
        "observed_registers_written": writes,
        "observed_flags_read": flags_read,
        "observed_flags_written": flags_written,
        "memory_effects_present": any(effect["memory"] in ("read", "write", "unknown") for effect in effects),
        "incomplete_instruction_addresses": uncertain,
        "instructions": effects,
        "limitations": [
            "These are syntactic effects for the decoded subset, not path-sensitive liveness or symbolic values.",
            "Observed writes are not a complete function return contract; register preservation and caller/callee ABI rules are not inferred.",
            "Calls and unknown instructions can have additional effects not represented by the explicit register sets.",
            "Memory addresses and values are not evaluated or read by this analysis.",
        ],
    }
