#!/usr/bin/env python3
"""Clean-room POC for a deliberately small 16-bit Thumb-to-C subset."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

MAX_INSTRUCTIONS = 256
MAX_EXECUTION_STEPS = 100000
DEFAULT_HALFWORDS = (0x200C, 0x3808, 0x3003, 0x2807, 0x4770)

CONDITION_NAMES = {
    0x0: "eq", 0x1: "ne", 0x2: "cs", 0x3: "cc", 0x4: "mi", 0x5: "pl",
    0x6: "vs", 0x7: "vc", 0x8: "hi", 0x9: "ls", 0xA: "ge", 0xB: "lt",
    0xC: "gt", 0xD: "le",
}
CONDITION_C = {
    "eq": "flag_z != 0U",
    "ne": "flag_z == 0U",
    "cs": "flag_c != 0U",
    "cc": "flag_c == 0U",
    "mi": "flag_n != 0U",
    "pl": "flag_n == 0U",
    "vs": "flag_v != 0U",
    "vc": "flag_v == 0U",
    "hi": "flag_c != 0U && flag_z == 0U",
    "ls": "flag_c == 0U || flag_z != 0U",
    "ge": "flag_n == flag_v",
    "lt": "flag_n != flag_v",
    "gt": "flag_z == 0U && flag_n == flag_v",
    "le": "flag_z != 0U || flag_n != flag_v",
}


INDIRECT_FLOW_OPS = ("bx", "blx_reg", "pop_pc")
STACK_OPS = ("push", "pop")
LITERAL_OPS = ("ldr_literal",)


class UnsupportedThumbInstruction(ValueError):
    """Input is outside this intentionally narrow Thumb-16 demonstrator."""


def _sign_extend(value: int, bits: int) -> int:
    sign = 1 << (bits - 1)
    return value - (1 << bits) if value & sign else value


def decode_halfword(word: int) -> tuple[object, ...]:
    """Decode one 16-bit Thumb instruction into a closed, small IR."""
    if isinstance(word, bool) or not isinstance(word, int) or not 0 <= word <= 0xFFFF:
        raise UnsupportedThumbInstruction(f"instruction halfword outside uint16: {word!r}")

    if word == 0x4770:  # BX LR; exact encoding only
        return ("return",)

    # Register-indirect control flow. Bits 2:0 are should-be-zero; PC as Rm is refused.
    if (word & 0xFF87) == 0x4700:  # BX Rm (0x4770 = BX LR handled above)
        rm = (word >> 3) & 0xF
        if rm == 15:
            raise UnsupportedThumbInstruction(f"BX PC (0x{word:04X}) is not decoded")
        return ("bx", rm)
    if (word & 0xFF87) == 0x4780:  # BLX Rm
        rm = (word >> 3) & 0xF
        if rm == 15:
            raise UnsupportedThumbInstruction(f"BLX PC (0x{word:04X}) is unpredictable and not decoded")
        return ("blx_reg", rm)
    if (word & 0xFF00) == 0xBD00:  # POP {reglist, PC}
        return ("pop_pc", word & 0xFF)
    if (word & 0xF800) == 0x4800:  # LDR Rd, [PC, #imm8*4]
        return ("ldr_literal", (word >> 8) & 0x7, (word & 0xFF) * 4)
    # Stack transfers. An empty list without LR/PC is unpredictable and refused.
    if (word & 0xFE00) == 0xB400:  # PUSH {reglist[, LR]}
        mask, lr = word & 0xFF, bool(word & 0x100)
        if mask == 0 and not lr:
            raise UnsupportedThumbInstruction(f"PUSH with an empty register list (0x{word:04X}) is unpredictable")
        return ("push", mask, lr)
    if (word & 0xFF00) == 0xBC00:  # POP {reglist} (no PC)
        mask = word & 0xFF
        if mask == 0:
            raise UnsupportedThumbInstruction(f"POP with an empty register list (0x{word:04X}) is unpredictable")
        return ("pop", mask)

    # Thumb-1 immediate shifts: LSL, LSR and ASR (imm5=0 has per-op semantics).
    shift_opcode = word & 0xF800
    if shift_opcode in (0x0000, 0x0800, 0x1000):
        shift_names = {0x0000: "lsl_imm", 0x0800: "lsr_imm", 0x1000: "asr_imm"}
        amount = (word >> 6) & 0x1F
        rm = (word >> 3) & 0x7
        rd = word & 0x7
        return (shift_names[shift_opcode], rd, rm, amount)

    # Thumb-1 data-processing register group (low registers only).
    # Unimplemented ALU opcodes remain explicit failures.
    if (word & 0xFC00) == 0x4000:
        opcode = (word >> 6) & 0xF
        rm = (word >> 3) & 0x7
        rd = word & 0x7
        supported_ops = {
            0x0: "ands_reg",
            0x1: "eors_reg",
            0x8: "tst_reg",
            0x9: "rsbs_zero",
            0xA: "cmp_reg",
            0xB: "cmn_reg",
            0xC: "orrs_reg",
            0xE: "bics_reg",
            0xF: "mvns_reg",
        }
        if opcode not in supported_ops:
            raise UnsupportedThumbInstruction(
                f"unsupported Thumb data-processing register opcode {opcode:04b} in 0x{word:04X}"
            )
        return (supported_ops[opcode], rd, rm)

    # Thumb-1 three-operand ADD/SUB: register Rm or imm3.
    if (word & 0xF800) == 0x1800:
        immediate_form = (word >> 10) & 1
        subtract = (word >> 9) & 1
        operand = (word >> 6) & 0x7
        rn = (word >> 3) & 0x7
        rd = word & 0x7
        operation = "subs" if subtract else "adds"
        if immediate_form:
            return (f"{operation}_imm3", rd, rn, operand)
        return (f"{operation}_reg", rd, rn, operand)

    op = word & 0xF800
    rd_or_rn = (word >> 8) & 0x7
    immediate = word & 0xFF
    if op == 0x2000:  # MOVS Rd, #imm8
        return ("movs", rd_or_rn, immediate)
    if op == 0x2800:  # CMP Rn, #imm8
        return ("cmp", rd_or_rn, immediate)
    if op == 0x3000:  # ADDS Rd, #imm8
        return ("adds", rd_or_rn, immediate)
    if op == 0x3800:  # SUBS Rd, #imm8
        return ("subs", rd_or_rn, immediate)

    # Thumb PC = instruction address + 4; offsets are in halfword units.
    if (word & 0xF800) == 0xE000:  # unconditional B, signed imm11
        return ("branch", "al", _sign_extend(word & 0x7FF, 11))

    if (word & 0xF000) == 0xD000:  # conditional B, signed imm8
        condition_code = (word >> 8) & 0xF
        if condition_code not in CONDITION_NAMES:
            raise UnsupportedThumbInstruction(
                f"unsupported or reserved Thumb conditional branch condition 0x{condition_code:X}"
            )
        return ("branch", CONDITION_NAMES[condition_code], _sign_extend(word & 0xFF, 8))

    raise UnsupportedThumbInstruction(f"unsupported Thumb-16 instruction 0x{word:04X}")


def _check_uint16(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 0xFFFF:
        raise UnsupportedThumbInstruction(f"{label} outside uint16: {value!r}")
    return value


def decode_call_pair(first: int, second: int) -> tuple[object, ...]:
    """Decode a Thumb BL/BLX (immediate) halfword pair as one logical call.

    Only the ARMv6K prefix/suffix form is accepted (the 3DS ARM11 has no
    Thumb-2): first = 11110 imm11, second = 11111 imm11 (BL) or
    11101 imm11 with bit 0 clear (BLX, switches to ARM). The Thumb-2
    J1/J2 forms and every other 32-bit pair are left undecoded.
    Returns ("call", "bl"|"blx", byte_offset) with the offset relative to PC,
    where PC = instruction address + 4.
    """
    first = _check_uint16(first, "first Thumb halfword")
    second = _check_uint16(second, "second Thumb halfword")
    if (first & 0xF800) != 0xF000:
        raise UnsupportedThumbInstruction(f"0x{first:04X} is not a Thumb BL/BLX prefix")
    suffix = second & 0xF800
    if suffix == 0xF800:
        kind = "bl"
    elif suffix == 0xE800:
        if second & 1:
            raise UnsupportedThumbInstruction(
                f"BLX suffix 0x{second:04X} has bit 0 set; refusing an undefined encoding"
            )
        kind = "blx"
    else:
        raise UnsupportedThumbInstruction(
            f"0x{first:04X} 0x{second:04X} is not an ARMv6K Thumb BL/BLX pair"
        )
    offset = (_sign_extend(first & 0x7FF, 11) << 12) + ((second & 0x7FF) << 1)
    return ("call", kind, offset)


def call_target(address: int, decoded: tuple[object, ...]) -> tuple[int, str]:
    """Return (target address, target state) for a decoded Thumb call.

    BL stays in Thumb at PC + offset; BLX enters ARM at Align(PC + offset, 4).
    Targets outside uint32 are refused rather than wrapped.
    """
    if isinstance(address, bool) or not isinstance(address, int) or not 0 <= address < (1 << 32):
        raise UnsupportedThumbInstruction(f"call address must fit uint32: {address!r}")
    if address & 1:
        raise UnsupportedThumbInstruction(f"Thumb call address must be halfword aligned: 0x{address:08X}")
    if len(decoded) != 3 or decoded[0] != "call" or decoded[1] not in ("bl", "blx") or not isinstance(decoded[2], int):
        raise UnsupportedThumbInstruction(f"not a decoded Thumb call: {decoded!r}")
    raw = address + 4 + decoded[2]
    if not 0 <= raw < (1 << 32):
        raise UnsupportedThumbInstruction(
            f"call at 0x{address:08X} targets 0x{raw & 0xFFFFFFFF:08X} outside the 32-bit address space (raw {raw})"
        )
    if decoded[1] == "bl":
        return raw, "thumb"
    return raw & ~3, "arm"


def literal_address(address: int, decoded: tuple[object, ...]) -> int:
    """Return the address of the 32-bit literal named by a decoded Thumb LDR (literal).

    Align(address + 4, 4) + offset. The value is never read; a literal whose
    four bytes do not fit the 32-bit address space is refused, not wrapped.
    """
    if isinstance(address, bool) or not isinstance(address, int) or not 0 <= address < (1 << 32):
        raise UnsupportedThumbInstruction(f"literal-load address must fit uint32: {address!r}")
    if address & 1:
        raise UnsupportedThumbInstruction(f"Thumb address must be halfword aligned: 0x{address:08X}")
    if (
        len(decoded) != 3 or decoded[0] != "ldr_literal"
        or not isinstance(decoded[2], int) or isinstance(decoded[2], bool)
        or not 0 <= decoded[2] <= 1020 or decoded[2] % 4
    ):
        raise UnsupportedThumbInstruction(f"not a decoded Thumb literal load: {decoded!r}")
    literal = ((address + 4) & ~3) + decoded[2]
    if literal + 4 > (1 << 32):
        raise UnsupportedThumbInstruction(
            f"literal load at 0x{address:08X} names a literal at 0x{literal:X} outside the 32-bit address space"
        )
    return literal


def translate(
    halfwords: tuple[int, ...] | list[int],
    initial_nzcv: int = 0,
    max_execution_steps: int | None = None,
) -> str:
    """Translate a list of synthetic Thumb-16 halfwords to host C.

    Without a budget, backward/self-targeting branches are refused. A supplied
    budget counts every visited guest instruction, including branches not taken
    and the final BX LR.
    """
    if isinstance(initial_nzcv, bool) or not isinstance(initial_nzcv, int) or not 0 <= initial_nzcv <= 0xF:
        raise UnsupportedThumbInstruction(f"initial NZCV must be a 4-bit value (0..15): {initial_nzcv!r}")
    if max_execution_steps is not None and (
        isinstance(max_execution_steps, bool)
        or not isinstance(max_execution_steps, int)
        or not 1 <= max_execution_steps <= MAX_EXECUTION_STEPS
    ):
        raise UnsupportedThumbInstruction(
            f"execution budget must be an integer in 1..{MAX_EXECUTION_STEPS}: {max_execution_steps!r}"
        )
    if not halfwords:
        raise UnsupportedThumbInstruction("empty Thumb instruction sequence")
    if len(halfwords) > MAX_INSTRUCTIONS:
        raise UnsupportedThumbInstruction(f"sequence exceeds {MAX_INSTRUCTIONS} halfwords")

    decoded = [decode_halfword(word) for word in halfwords]
    for inst in decoded:
        if inst[0] in LITERAL_OPS:
            raise UnsupportedThumbInstruction(
                "PC-relative literal load is decoded for inspection only; "
                "the synthetic translator has no memory model"
            )
        if inst[0] in STACK_OPS:
            raise UnsupportedThumbInstruction(
                f"stack transfer ({inst[0]}) is decoded for inspection only; "
                "the synthetic translator has no memory model"
            )
        if inst[0] in INDIRECT_FLOW_OPS:
            raise UnsupportedThumbInstruction(
                f"register-indirect control flow ({inst[0]}) is decoded for inspection only; "
                "the synthetic translator does not model it"
            )
    if any(inst == ("return",) for inst in decoded[:-1]):
        raise UnsupportedThumbInstruction("instructions after BX LR are unsupported")
    if decoded[-1] != ("return",):
        raise UnsupportedThumbInstruction("sequence must end with BX LR")

    branch_targets: dict[int, int] = {}
    for index, inst in enumerate(decoded):
        if inst[0] != "branch":
            continue
        target = index + 2 + inst[2]
        if not 0 <= target < len(decoded):
            raise UnsupportedThumbInstruction(
                f"branch at halfword {index} targets out-of-range halfword {target}"
            )
        if target <= index and max_execution_steps is None:
            raise UnsupportedThumbInstruction(
                f"backward or self-targeting branch at halfword {index} requires an execution budget"
            )
        branch_targets[index] = target

    used_registers = {0}
    for inst in decoded[:-1]:
        if inst[0] in ("movs", "adds", "subs"):
            used_registers.add(inst[1])
        elif inst[0] in ("adds_imm3", "subs_imm3"):
            used_registers.update((inst[1], inst[2]))
        elif inst[0] in ("adds_reg", "subs_reg"):
            used_registers.update((inst[1], inst[2], inst[3]))
        elif inst[0] in ("lsl_imm", "lsr_imm", "asr_imm"):
            used_registers.update((inst[1], inst[2]))
        elif inst[0] in ("ands_reg", "eors_reg", "orrs_reg", "bics_reg", "mvns_reg", "tst_reg", "cmp_reg", "cmn_reg", "rsbs_zero"):
            used_registers.update((inst[1], inst[2]))
        elif inst[0] == "cmp":
            used_registers.add(inst[1])

    bounded = max_execution_steps is not None
    signature = (
        "uint32_t thumb_entry_bounded(uint8_t *nzcv_out, "
        "uint32_t *steps_executed_out, uint8_t *execution_status_out)"
        if bounded else "uint32_t thumb_entry(uint8_t *nzcv_out)"
    )
    lines = [
        "#include <stdint.h>",
        "",
        "/* Generated only from synthetic Thumb halfwords supplied by the caller. */",
        signature,
        "{",
        f"    uint32_t flag_n = {(initial_nzcv >> 3) & 1}U;",
        f"    uint32_t flag_z = {(initial_nzcv >> 2) & 1}U;",
        f"    uint32_t flag_c = {(initial_nzcv >> 1) & 1}U;",
        f"    uint32_t flag_v = {initial_nzcv & 1}U;",
    ]
    if bounded:
        lines.append("    uint32_t execution_steps = 0U;")
    lines.extend(f"    uint32_t r{reg} = 0U;" for reg in sorted(used_registers))

    branch_target_indices = set(branch_targets.values())
    for index, inst in enumerate(decoded[:-1]):
        if index in branch_target_indices:
            lines.append(f"thumb_label_{index}: ;")
        if bounded:
            lines.append(f"    if (execution_steps >= UINT32_C({max_execution_steps})) goto thumb_budget_exhausted;")
            lines.append("    execution_steps++;")

        op = inst[0]
        if op == "movs":
            _, rd, immediate = inst
            lines.append(f"    r{rd} = UINT32_C({immediate});")
            lines.append(f"    flag_n = (r{rd} >> 31) & 1U;")
            lines.append(f"    flag_z = (uint32_t)(r{rd} == 0U);")
        elif op == "rsbs_zero":
            _, rd, rm = inst
            suffix = str(index)
            operand = f"thumb_rsb_operand_{suffix}"
            result = f"thumb_rsb_result_{suffix}"
            lines.append(f"    uint32_t {operand} = r{rm};")
            lines.append(f"    uint32_t {result} = (uint32_t)(UINT32_C(0) - {operand});")
            lines.append(f"    flag_c = (uint32_t)(UINT32_C(0) >= {operand});")
            lines.append(f"    flag_v = (uint32_t)((({operand} ^ UINT32_C(0)) & ({operand} ^ {result}) & UINT32_C(0x80000000)) != 0U);")
            lines.append(f"    r{rd} = {result};")
            lines.append(f"    flag_n = ({result} >> 31) & 1U;")
            lines.append(f"    flag_z = (uint32_t)({result} == 0U);")
        elif op in ("ands_reg", "eors_reg", "orrs_reg", "bics_reg", "mvns_reg", "tst_reg"):
            _, rd, rm = inst
            suffix = str(index)
            lhs = f"thumb_dp_lhs_{suffix}"
            rhs = f"thumb_dp_rhs_{suffix}"
            result = f"thumb_dp_result_{suffix}"
            lines.append(f"    uint32_t {rhs} = r{rm};")
            if op == "mvns_reg":
                lines.append(f"    uint32_t {result} = (uint32_t)~{rhs};")
            else:
                lines.append(f"    uint32_t {lhs} = r{rd};")
                expression = {
                    "ands_reg": f"({lhs} & {rhs})",
                    "eors_reg": f"({lhs} ^ {rhs})",
                    "orrs_reg": f"({lhs} | {rhs})",
                    "bics_reg": f"({lhs} & ~{rhs})",
                    "tst_reg": f"({lhs} & {rhs})",
                }[op]
                lines.append(f"    uint32_t {result} = (uint32_t){expression};")
            if op != "tst_reg":
                lines.append(f"    r{rd} = {result};")
            # Unshifted logical ALU forms update N/Z and preserve C/V.
            lines.append(f"    flag_n = ({result} >> 31) & 1U;")
            lines.append(f"    flag_z = (uint32_t)({result} == 0U);")
        elif op in ("lsl_imm", "lsr_imm", "asr_imm"):
            _, rd, rm, amount = inst
            suffix = str(index)
            source = f"thumb_shift_source_{suffix}"
            result = f"thumb_shift_result_{suffix}"
            lines.append(f"    uint32_t {source} = r{rm};")
            if op == "lsl_imm":
                if amount == 0:
                    lines.append(f"    uint32_t {result} = {source};")
                else:
                    lines.append(f"    uint32_t {result} = (uint32_t)({source} << {amount});")
                    lines.append(f"    flag_c = ({source} >> {32 - amount}) & 1U;")
            elif op == "lsr_imm":
                if amount == 0:
                    lines.append(f"    uint32_t {result} = UINT32_C(0);")
                    lines.append(f"    flag_c = ({source} >> 31) & 1U;")
                else:
                    lines.append(f"    uint32_t {result} = {source} >> {amount};")
                    lines.append(f"    flag_c = ({source} >> {amount - 1}) & 1U;")
            else:  # ASR immediate; avoid implementation-defined signed right shift in C.
                if amount == 0:
                    lines.append(f"    uint32_t {result} = ({source} & UINT32_C(0x80000000)) ? UINT32_MAX : UINT32_C(0);")
                    lines.append(f"    flag_c = ({source} >> 31) & 1U;")
                else:
                    lines.append(
                        f"    uint32_t {result} = ({source} >> {amount}) | "
                        f"(({source} & UINT32_C(0x80000000)) ? (UINT32_MAX << {32 - amount}) : UINT32_C(0));"
                    )
                    lines.append(f"    flag_c = ({source} >> {amount - 1}) & 1U;")
            lines.append(f"    r{rd} = {result};")
            lines.append(f"    flag_n = ({result} >> 31) & 1U;")
            lines.append(f"    flag_z = (uint32_t)({result} == 0U);")
        elif op in ("adds", "subs", "cmp", "cmp_reg", "cmn_reg", "adds_imm3", "subs_imm3", "adds_reg", "subs_reg"):
            if op == "cmp":
                _, rn, immediate = inst
                rd = None
                rhs_register = None
            elif op in ("cmp_reg", "cmn_reg"):
                _, rn, rm = inst
                rd = None
                immediate = None
                rhs_register = rm
            elif op in ("adds", "subs"):
                _, rd, immediate = inst
                rn = rd
                rhs_register = None
            elif op in ("adds_imm3", "subs_imm3"):
                _, rd, rn, immediate = inst
                rhs_register = None
            else:
                _, rd, rn, rm = inst
                immediate = None
                rhs_register = rm
            suffix = str(index)
            lhs = f"thumb_lhs_{suffix}"
            rhs = f"thumb_rhs_{suffix}"
            result = f"thumb_result_{suffix}"
            operation = "adds" if op.startswith("adds") or op == "cmn_reg" else "subs"
            lines.append(f"    uint32_t {lhs} = r{rn};")
            if rhs_register is not None:
                lines.append(f"    uint32_t {rhs} = r{rhs_register};")
            else:
                lines.append(f"    uint32_t {rhs} = UINT32_C({immediate});")
            if operation == "adds":
                wide = f"thumb_wide_{suffix}"
                lines.append(f"    uint64_t {wide} = (uint64_t){lhs} + (uint64_t){rhs};")
                lines.append(f"    uint32_t {result} = (uint32_t){wide};")
                lines.append(f"    flag_c = (uint32_t)(({wide} >> 32) & UINT64_C(1));")
                lines.append(f"    flag_v = (uint32_t)((~({lhs} ^ {rhs}) & ({lhs} ^ {result}) & UINT32_C(0x80000000)) != 0U);")
            else:
                lines.append(f"    uint32_t {result} = (uint32_t)({lhs} - {rhs});")
                lines.append(f"    flag_c = (uint32_t)({lhs} >= {rhs});")
                lines.append(f"    flag_v = (uint32_t)((({lhs} ^ {rhs}) & ({lhs} ^ {result}) & UINT32_C(0x80000000)) != 0U);")
            if rd is not None:
                lines.append(f"    r{rd} = {result};")
            lines.append(f"    flag_n = ({result} >> 31) & 1U;")
            lines.append(f"    flag_z = (uint32_t)({result} == 0U);")
        elif op == "branch":
            condition = inst[1]
            target = branch_targets[index]
            if condition == "al":
                lines.append(f"    goto thumb_label_{target};")
            else:
                lines.append(f"    if ({CONDITION_C[condition]}) goto thumb_label_{target};")
        else:
            raise UnsupportedThumbInstruction(f"internal unsupported IR tuple: {inst!r}")

    if len(decoded) - 1 in branch_target_indices:
        lines.append(f"thumb_label_{len(decoded) - 1}: ;")
    if bounded:
        lines.extend((
            f"    if (execution_steps >= UINT32_C({max_execution_steps})) goto thumb_budget_exhausted;",
            "    execution_steps++;",
            "    if (steps_executed_out != 0) *steps_executed_out = execution_steps;",
            "    if (execution_status_out != 0) *execution_status_out = UINT8_C(0);",
            "    goto thumb_exit;",
            "thumb_budget_exhausted: ;",
            "    if (steps_executed_out != 0) *steps_executed_out = execution_steps;",
            "    if (execution_status_out != 0) *execution_status_out = UINT8_C(1);",
            "thumb_exit: ;",
        ))
    # Read each guest register in the epilogue so strict C compilers do not
    # reject valid fixtures that write a register whose value is not returned.
    lines.extend(f"    (void)r{reg};" for reg in sorted(used_registers))
    lines.extend((
        "    if (nzcv_out != 0) {",
        "        *nzcv_out = (uint8_t)((flag_n << 3) | (flag_z << 2) | (flag_c << 1) | flag_v);",
        "    }",
        "    return r0;",
        "}",
        "",
    ))
    return "\n".join(lines)


def parse_halfword(token: str) -> int:
    try:
        value = int(token, 16)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"expected a hexadecimal Thumb halfword, got {token!r}") from exc
    if not 0 <= value <= 0xFFFF:
        raise argparse.ArgumentTypeError(f"Thumb halfword is outside uint16: {token!r}")
    return value


def parse_nzcv(token: str) -> int:
    try:
        value = int(token, 0)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"expected an integer 0..15 for NZCV, got {token!r}") from exc
    if not 0 <= value <= 0xF:
        raise argparse.ArgumentTypeError(f"NZCV must be a 4-bit value (0..15): {token!r}")
    return value


def parse_execution_budget(token: str) -> int:
    try:
        value = int(token, 0)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f"expected an execution budget in 1..{MAX_EXECUTION_STEPS}, got {token!r}"
        ) from exc
    if not 1 <= value <= MAX_EXECUTION_STEPS:
        raise argparse.ArgumentTypeError(
            f"execution budget must be in 1..{MAX_EXECUTION_STEPS}: {token!r}"
        )
    return value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Translate a tiny, synthetic 16-bit Thumb instruction subset into C; no game files are read."
    )
    parser.add_argument(
        "halfwords", nargs="*", type=parse_halfword,
        help="hex halfwords (default: MOVS r0,#12; SUBS r0,#8; ADDS r0,#3; CMP r0,#7; BX LR)",
    )
    parser.add_argument("--output", type=Path, help="write generated C to a file instead of stdout")
    parser.add_argument(
        "--initial-nzcv", type=parse_nzcv, default=0,
        help="entry flag state as a 4-bit nibble N:bit3 Z:bit2 C:bit1 V:bit0 (default: 0)",
    )
    parser.add_argument(
        "--max-execution-steps", type=parse_execution_budget, default=None,
        help=f"maximum guest instructions executed (1..{MAX_EXECUTION_STEPS}); required for backward/self-targeting branches",
    )
    args = parser.parse_args(argv)
    try:
        source = translate(
            args.halfwords or list(DEFAULT_HALFWORDS),
            initial_nzcv=args.initial_nzcv,
            max_execution_steps=args.max_execution_steps,
        )
        if args.output:
            args.output.write_text(source, encoding="utf-8", newline="\n")
        else:
            sys.stdout.write(source)
    except (UnsupportedThumbInstruction, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
