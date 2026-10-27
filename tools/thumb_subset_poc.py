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
MEMORY_OPS = ("str_reg", "strh_reg", "strb_reg", "ldrsb_reg", "ldr_reg", "ldrh_reg", "ldrb_reg", "ldrsh_reg", "str_imm", "ldr_imm", "strb_imm", "ldrb_imm", "strh_imm", "ldrh_imm", "str_sp", "ldr_sp", "stmia", "ldmia")
SUPPORTED_NATIVE_MEMORY_OPS = frozenset((
    "str_reg", "strh_reg", "strb_reg", "ldrsb_reg", "ldr_reg", "ldrh_reg",
    "ldrb_reg", "ldrsh_reg", "str_imm", "ldr_imm", "strb_imm", "ldrb_imm",
    "strh_imm", "ldrh_imm",
))
MEMORY_ACCESS_WIDTHS = {
    "str_reg": 4, "ldr_reg": 4, "str_imm": 4, "ldr_imm": 4,
    "strh_reg": 2, "ldrh_reg": 2, "strh_imm": 2, "ldrh_imm": 2,
    "strb_reg": 1, "ldrsb_reg": 1, "ldrb_reg": 1, "ldrsh_reg": 2,
    "strb_imm": 1, "ldrb_imm": 1,
}
MEMORY_STORE_OPS = frozenset(("str_reg", "strh_reg", "strb_reg", "str_imm", "strb_imm", "strh_imm"))
ADDRESS_OPS = ("adr", "add_sp_imm", "add_sp", "sub_sp")


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

    # Complete Thumb-1 data-processing register group, using low registers only.
    if (word & 0xFC00) == 0x4000:
        opcode = (word >> 6) & 0xF
        rm = (word >> 3) & 0x7
        rd = word & 0x7
        supported_ops = {
            0x0: "ands_reg",
            0x1: "eors_reg",
            0x2: "lsls_reg",
            0x3: "lsrs_reg",
            0x4: "asrs_reg",
            0x5: "adcs_reg",
            0x6: "sbcs_reg",
            0x7: "rors_reg",
            0x8: "tst_reg",
            0x9: "rsbs_zero",
            0xA: "cmp_reg",
            0xB: "cmn_reg",
            0xC: "orrs_reg",
            0xD: "muls_reg",
            0xE: "bics_reg",
            0xF: "mvns_reg",
        }
        if opcode not in supported_ops:
            raise UnsupportedThumbInstruction(
                f"unsupported Thumb data-processing register opcode {opcode:04b} in 0x{word:04X}"
            )
        return (supported_ops[opcode], rd, rm)

    # Thumb-1 register-offset load/store group: 0101 op Rm Rn Rt.
    # Decoded for inspection only; the synthetic translator has no memory model.
    if (word & 0xF000) == 0x5000:
        opcode = (word >> 9) & 0x7
        rm = (word >> 6) & 0x7
        rn = (word >> 3) & 0x7
        rt = word & 0x7
        memory_ops = {
            0x0: "str_reg", 0x1: "strh_reg", 0x2: "strb_reg", 0x3: "ldrsb_reg",
            0x4: "ldr_reg", 0x5: "ldrh_reg", 0x6: "ldrb_reg", 0x7: "ldrsh_reg",
        }
        return (memory_ops[opcode], rt, rn, rm)

    # Thumb-1 immediate-offset transfers scale imm5 by access width.
    immediate_op = word & 0xF800
    if immediate_op in (0x6000, 0x6800, 0x7000, 0x7800, 0x8000, 0x8800):
        rt = word & 0x7
        rn = (word >> 3) & 0x7
        imm5 = (word >> 6) & 0x1F
        forms = {
            0x6000: ("str_imm", 4), 0x6800: ("ldr_imm", 4),
            0x7000: ("strb_imm", 1), 0x7800: ("ldrb_imm", 1),
            0x8000: ("strh_imm", 2), 0x8800: ("ldrh_imm", 2),
        }
        operation, scale = forms[immediate_op]
        return (operation, rt, rn, imm5 * scale)

    # Thumb-1 SP-relative word transfers use imm8 scaled by four bytes.
    if immediate_op in (0x9000, 0x9800):
        rt = (word >> 8) & 0x7
        imm8 = word & 0xFF
        operation = "str_sp" if immediate_op == 0x9000 else "ldr_sp"
        return (operation, rt, imm8 * 4)

    # Thumb-1 Load/Store Multiple: 1100 L Rn register_list.
    if (word & 0xF000) == 0xC000:
        load = bool(word & 0x0800)
        rn = (word >> 8) & 0x7
        register_list = word & 0xFF
        if register_list == 0:
            raise UnsupportedThumbInstruction(
                f"empty LDM/STM register list is unpredictable (0x{word:04X})"
            )
        return ("ldmia" if load else "stmia", rn, register_list)

    # Thumb-1 PC/SP address-generation instructions.
    if (word & 0xF800) in (0xA000, 0xA800):
        rd = (word >> 8) & 0x7
        offset = (word & 0xFF) * 4
        operation = "adr" if (word & 0xF800) == 0xA000 else "add_sp_imm"
        return (operation, rd, offset)

    # Thumb-1 adjusts SP directly by imm7 * 4 without changing NZCV.
    if (word & 0xFF00) == 0xB000:
        subtract = bool(word & 0x0080)
        offset = (word & 0x7F) * 4
        return ("sub_sp" if subtract else "add_sp", offset)

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
    runtime_state_io: bool = False,
    runtime_memory_io: bool = False,
) -> str:
    """Translate a bounded Thumb-16 sequence to host C.

    ``runtime_state_io=True`` exposes r0-r7 and NZCV at runtime.
    ``runtime_memory_io=True`` adds a bounded guest-memory byte region and
    emits native C loads/stores for a conservative Thumb-1 subset. Unsupported
    memory forms, invalid addresses, misaligned multi-byte accesses and invalid
    entry state fail explicitly; no interpreter or fallback exists.
    This is a synthetic candidate model, not a general ARM ABI proof.
    """
    if not isinstance(runtime_state_io, bool):
        raise UnsupportedThumbInstruction("runtime_state_io must be a bool")
    if not isinstance(runtime_memory_io, bool):
        raise UnsupportedThumbInstruction("runtime_memory_io must be a bool")
    if runtime_memory_io and not runtime_state_io:
        raise UnsupportedThumbInstruction("runtime_memory_io requires runtime_state_io=True")
    if runtime_state_io and max_execution_steps is None:
        raise UnsupportedThumbInstruction("runtime_state_io requires an explicit execution budget")
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
    supported_memory_found = False
    for inst in decoded:
        if inst[0] in LITERAL_OPS:
            raise UnsupportedThumbInstruction(
                "PC-relative literal load is decoded for inspection only; "
                "the limited native memory model does not model PC-relative literals"
            )
        if inst[0] in MEMORY_OPS:
            if not runtime_memory_io:
                raise UnsupportedThumbInstruction(
                    f"memory access ({inst[0]}) is decoded for inspection only; "
                    "the synthetic translator has no memory model"
                )
            if inst[0] not in SUPPORTED_NATIVE_MEMORY_OPS:
                raise UnsupportedThumbInstruction(
                    f"memory access ({inst[0]}) is outside the limited native memory model"
                )
            supported_memory_found = True
        if inst[0] in ADDRESS_OPS:
            raise UnsupportedThumbInstruction(
                f"PC/SP address arithmetic ({inst[0]}) is decoded for inspection only; "
                "the synthetic translator does not model PC or SP"
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
    if runtime_memory_io and not supported_memory_found:
        raise UnsupportedThumbInstruction("runtime_memory_io requires at least one supported memory instruction")

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
        elif inst[0] in ("ands_reg", "eors_reg", "lsls_reg", "lsrs_reg", "asrs_reg", "adcs_reg", "sbcs_reg", "rors_reg", "orrs_reg", "muls_reg", "bics_reg", "mvns_reg", "tst_reg", "cmp_reg", "cmn_reg", "rsbs_zero"):
            used_registers.update((inst[1], inst[2]))
        elif inst[0] == "cmp":
            used_registers.add(inst[1])

    if runtime_state_io:
        used_registers = set(range(8))
    bounded = max_execution_steps is not None
    if runtime_memory_io:
        signature = (
            "uint32_t thumb_entry_memory_bounded(const uint32_t *registers_in, "
            "uint8_t initial_nzcv, uint8_t *nzcv_out, uint32_t *steps_executed_out, "
            "uint8_t *execution_status_out, uint32_t *registers_out, uint8_t *memory_bytes, "
            "uint32_t guest_memory_base, uint32_t guest_memory_size)"
        )
    elif runtime_state_io:
        signature = (
            "uint32_t thumb_entry_bounded(const uint32_t *registers_in, "
            "uint8_t initial_nzcv, uint8_t *nzcv_out, uint32_t *steps_executed_out, "
            "uint8_t *execution_status_out, uint32_t *registers_out)"
        )
    elif bounded:
        signature = "uint32_t thumb_entry_bounded(uint8_t *nzcv_out, uint32_t *steps_executed_out, uint8_t *execution_status_out)"
    else:
        signature = "uint32_t thumb_entry(uint8_t *nzcv_out)"
    flag_initializers = (
        [
            "    uint32_t flag_n = (uint32_t)((initial_nzcv >> 3) & 1U);",
            "    uint32_t flag_z = (uint32_t)((initial_nzcv >> 2) & 1U);",
            "    uint32_t flag_c = (uint32_t)((initial_nzcv >> 1) & 1U);",
            "    uint32_t flag_v = (uint32_t)(initial_nzcv & 1U);",
        ] if runtime_state_io else [
            f"    uint32_t flag_n = {(initial_nzcv >> 3) & 1}U;",
            f"    uint32_t flag_z = {(initial_nzcv >> 2) & 1}U;",
            f"    uint32_t flag_c = {(initial_nzcv >> 1) & 1}U;",
            f"    uint32_t flag_v = {initial_nzcv & 1}U;",
        ]
    )
    lines = [
        "#include <stdint.h>",
        "",
        "/* Generated C remains a candidate model; independent semantic validation is required. */"
        if runtime_state_io else
        "/* Generated only from synthetic Thumb halfwords supplied by the caller. */",
        signature,
        "{",
    ]
    if runtime_memory_io:
        lines.extend((
            "    if (registers_in == 0 || initial_nzcv > UINT8_C(15) || memory_bytes == 0 || guest_memory_size == 0U || "
            "((uint64_t)guest_memory_base + (uint64_t)guest_memory_size > UINT64_C(0x100000000))) {",
            "        if (steps_executed_out != 0) *steps_executed_out = 0U;",
            "        if (execution_status_out != 0) *execution_status_out = UINT8_C(2);",
            "        return 0U;",
            "    }",
        ))
    elif runtime_state_io:
        lines.extend((
            "    if (registers_in == 0 || initial_nzcv > UINT8_C(15)) {",
            "        if (steps_executed_out != 0) *steps_executed_out = 0U;",
            "        if (execution_status_out != 0) *execution_status_out = UINT8_C(2);",
            "        return 0U;",
            "    }",
        ))
    lines.extend(flag_initializers)
    if bounded:
        lines.append("    uint32_t execution_steps = 0U;")
    if runtime_state_io:
        lines.extend(f"    uint32_t r{reg} = registers_in[{reg}];" for reg in sorted(used_registers))
    else:
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
        elif op in ("adcs_reg", "sbcs_reg"):
            _, rd, rm = inst
            suffix = str(index)
            lhs = f"thumb_carry_lhs_{suffix}"
            rhs = f"thumb_carry_rhs_{suffix}"
            result = f"thumb_carry_result_{suffix}"
            lines.append(f"    uint32_t {lhs} = r{rd};")
            lines.append(f"    uint32_t {rhs} = r{rm};")
            if op == "adcs_reg":
                carry_in = f"thumb_carry_in_{suffix}"
                wide = f"thumb_adc_wide_{suffix}"
                lines.append(f"    uint32_t {carry_in} = flag_c;")
                lines.append(f"    uint64_t {wide} = (uint64_t){lhs} + (uint64_t){rhs} + (uint64_t){carry_in};")
                lines.append(f"    uint32_t {result} = (uint32_t){wide};")
                lines.append(f"    flag_c = (uint32_t)(({wide} >> 32) & UINT64_C(1));")
                lines.append(f"    flag_v = (uint32_t)((~({lhs} ^ {rhs}) & ({lhs} ^ {result}) & UINT32_C(0x80000000)) != 0U);")
            else:
                borrow_in = f"thumb_sbc_borrow_{suffix}"
                subtrahend = f"thumb_sbc_subtrahend_{suffix}"
                lines.append(f"    uint32_t {borrow_in} = (uint32_t)(flag_c == 0U);")
                lines.append(f"    uint64_t {subtrahend} = (uint64_t){rhs} + (uint64_t){borrow_in};")
                lines.append(f"    uint32_t {result} = (uint32_t)((uint64_t){lhs} - {subtrahend});")
                lines.append(f"    flag_c = (uint32_t)((uint64_t){lhs} >= {subtrahend});")
                lines.append(f"    flag_v = (uint32_t)((({lhs} ^ {rhs}) & ({lhs} ^ {result}) & UINT32_C(0x80000000)) != 0U);")
            lines.append(f"    r{rd} = {result};")
            lines.append(f"    flag_n = ({result} >> 31) & 1U;")
            lines.append(f"    flag_z = (uint32_t)({result} == 0U);")
        elif op == "muls_reg":
            _, rd, rm = inst
            suffix = str(index)
            lhs = f"thumb_muls_lhs_{suffix}"
            rhs = f"thumb_muls_rhs_{suffix}"
            wide = f"thumb_muls_wide_{suffix}"
            result = f"thumb_muls_result_{suffix}"
            lines.append(f"    uint32_t {lhs} = r{rd};")
            lines.append(f"    uint32_t {rhs} = r{rm};")
            lines.append(f"    uint64_t {wide} = (uint64_t){lhs} * (uint64_t){rhs};")
            lines.append(f"    uint32_t {result} = (uint32_t){wide};")
            lines.append(f"    r{rd} = {result};")
            lines.append(f"    flag_n = ({result} >> 31) & 1U;")
            lines.append(f"    flag_z = (uint32_t)({result} == 0U);")
            # Thumb-1 MULS updates N/Z; C/V remain unchanged.
        elif op in ("lsls_reg", "lsrs_reg", "asrs_reg", "rors_reg"):
            _, rd, rm = inst
            suffix = str(index)
            source = f"thumb_regshift_source_{suffix}"
            amount_source = f"thumb_regshift_amount_source_{suffix}"
            amount = f"thumb_regshift_amount_{suffix}"
            result = f"thumb_regshift_result_{suffix}"
            rotation = f"thumb_regshift_rotation_{suffix}"
            if op == "rors_reg":
                lines.append(f"    uint32_t {rotation} = 0U;")
            lines.append(f"    uint32_t {source} = r{rd};")
            lines.append(f"    uint32_t {amount_source} = r{rm};")
            lines.append(f"    uint32_t {amount} = {amount_source} & UINT32_C(0xFF);")
            lines.append(f"    uint32_t {result} = {source};")
            if op == "lsls_reg":
                lines.append(f"    if ({amount} != 0U) {{")
                lines.append(f"        if ({amount} < 32U) {{")
                lines.append(f"            {result} = (uint32_t)({source} << {amount});")
                lines.append(f"            flag_c = ({source} >> (32U - {amount})) & 1U;")
                lines.append(f"        }} else if ({amount} == 32U) {{")
                lines.append(f"            {result} = UINT32_C(0);")
                lines.append(f"            flag_c = {source} & 1U;")
                lines.append("        } else {")
                lines.append(f"            {result} = UINT32_C(0);")
                lines.append("            flag_c = 0U;")
                lines.append("        }")
                lines.append("    }")
            elif op == "lsrs_reg":
                lines.append(f"    if ({amount} != 0U) {{")
                lines.append(f"        if ({amount} < 32U) {{")
                lines.append(f"            {result} = {source} >> {amount};")
                lines.append(f"            flag_c = ({source} >> ({amount} - 1U)) & 1U;")
                lines.append(f"        }} else if ({amount} == 32U) {{")
                lines.append(f"            {result} = UINT32_C(0);")
                lines.append(f"            flag_c = ({source} >> 31) & 1U;")
                lines.append("        } else {")
                lines.append(f"            {result} = UINT32_C(0);")
                lines.append("            flag_c = 0U;")
                lines.append("        }")
                lines.append("    }")
            elif op == "asrs_reg":
                lines.append(f"    if ({amount} != 0U) {{")
                lines.append(f"        if ({amount} < 32U) {{")
                lines.append(f"            {result} = ({source} >> {amount}) | ")
                lines.append(f"                (({source} & UINT32_C(0x80000000)) ? (UINT32_MAX << (32U - {amount})) : UINT32_C(0));")
                lines.append(f"            flag_c = ({source} >> ({amount} - 1U)) & 1U;")
                lines.append("        } else {")
                lines.append(f"            {result} = ({source} & UINT32_C(0x80000000)) ? UINT32_MAX : UINT32_C(0);")
                lines.append(f"            flag_c = ({source} >> 31) & 1U;")
                lines.append("        }")
                lines.append("    }")
            else:  # ROR by register; a nonzero multiple of 32 preserves value but updates C.
                lines.append(f"    if ({amount} != 0U) {{")
                lines.append(f"        {rotation} = {amount} & UINT32_C(31);")
                lines.append(f"        if ({rotation} != 0U) {{")
                lines.append(f"            {result} = ({source} >> {rotation}) | ({source} << (32U - {rotation}));")
                lines.append(f"            flag_c = ({result} >> 31) & 1U;")
                lines.append("        } else {")
                lines.append(f"            {result} = {source};")
                lines.append(f"            flag_c = ({source} >> 31) & 1U;")
                lines.append("        }")
                lines.append("    }")
            lines.append(f"    r{rd} = {result};")
            lines.append(f"    flag_n = ({result} >> 31) & 1U;")
            lines.append(f"    flag_z = (uint32_t)({result} == 0U);")
        elif op == "rsbs_zero":
            _, rd, rm = inst
            suffix = str(index)
            operand = f"thumb_rsb_operand_{suffix}"
            result = f"thumb_rsb_result_{suffix}"
            lines.append(f"    uint32_t {operand} = r{rm};")
            lines.append(f"    uint32_t {result} = (uint32_t)(UINT32_C(0) - {operand});")
            lines.append(f"    flag_c = (uint32_t)(UINT32_C(0) >= {operand});")
            lines.append(f"    flag_v = (uint32_t)(({operand} & {result} & UINT32_C(0x80000000)) != 0U);")
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
        elif op in SUPPORTED_NATIVE_MEMORY_OPS:
            if op.endswith("_reg"):
                _, rd, rn, rm = inst
                address_expression = f"(uint32_t)(r{rn} + r{rm})"
            else:
                _, rd, rn, immediate_offset = inst
                address_expression = f"(uint32_t)(r{rn} + UINT32_C({immediate_offset}))"

            width = MEMORY_ACCESS_WIDTHS[op]
            suffix = str(index)
            address = f"thumb_memory_address_{suffix}"
            memory_offset = f"thumb_memory_offset_{suffix}"
            if op in MEMORY_STORE_OPS:
                value = f"thumb_memory_store_value_{suffix}"
                lines.append("    {")
                lines.append(f"        const uint32_t {address} = {address_expression};")
                if width > 1:
                    lines.append(f"        if (({address} & UINT32_C({width - 1})) != 0U) goto thumb_alignment_fault;")
                lines.append(f"        if ({address} < guest_memory_base) goto thumb_memory_fault;")
                lines.append(f"        const uint32_t {memory_offset} = {address} - guest_memory_base;")
                lines.append(
                    f"        if ({memory_offset} > guest_memory_size || UINT32_C({width}) > guest_memory_size - {memory_offset}) goto thumb_memory_fault;"
                )
                lines.append(f"        const uint32_t {value} = r{rd};")
                for byte_index in range(width):
                    shift = byte_index * 8
                    lines.append(
                        f"        memory_bytes[{memory_offset} + UINT32_C({byte_index})] = "
                        f"(uint8_t)(({value} >> {shift}) & UINT32_C(0xFF));"
                    )
                lines.append("    }")
            else:
                loaded = f"thumb_memory_loaded_{suffix}"
                lines.append("    {")
                lines.append(f"        const uint32_t {address} = {address_expression};")
                if width > 1:
                    lines.append(f"        if (({address} & UINT32_C({width - 1})) != 0U) goto thumb_alignment_fault;")
                lines.append(f"        if ({address} < guest_memory_base) goto thumb_memory_fault;")
                lines.append(f"        const uint32_t {memory_offset} = {address} - guest_memory_base;")
                lines.append(
                    f"        if ({memory_offset} > guest_memory_size || UINT32_C({width}) > guest_memory_size - {memory_offset}) goto thumb_memory_fault;"
                )
                if width == 1:
                    lines.append(f"        uint32_t {loaded} = (uint32_t)memory_bytes[{memory_offset}];")
                elif width == 2:
                    lines.append(
                        f"        uint32_t {loaded} = (uint32_t)memory_bytes[{memory_offset}] | "
                        f"((uint32_t)memory_bytes[{memory_offset} + UINT32_C(1)] << 8);"
                    )
                else:
                    lines.append(
                        f"        uint32_t {loaded} = (uint32_t)memory_bytes[{memory_offset}] | "
                        f"((uint32_t)memory_bytes[{memory_offset} + UINT32_C(1)] << 8) | "
                        f"((uint32_t)memory_bytes[{memory_offset} + UINT32_C(2)] << 16) | "
                        f"((uint32_t)memory_bytes[{memory_offset} + UINT32_C(3)] << 24);"
                    )
                if op == "ldrsb_reg":
                    lines.append(
                        f"        r{rd} = ({loaded} & UINT32_C(0x80)) != 0U ? "
                        f"({loaded} | UINT32_C(0xFFFFFF00)) : {loaded};"
                    )
                elif op == "ldrsh_reg":
                    lines.append(
                        f"        r{rd} = ({loaded} & UINT32_C(0x8000)) != 0U ? "
                        f"({loaded} | UINT32_C(0xFFFF0000)) : {loaded};"
                    )
                else:
                    lines.append(f"        r{rd} = {loaded};")
                lines.append("    }")
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
        ))
        if runtime_memory_io:
            lines.extend((
                "    goto thumb_exit;",
                "thumb_memory_fault: ;",
                "    if (steps_executed_out != 0) *steps_executed_out = execution_steps;",
                "    if (execution_status_out != 0) *execution_status_out = UINT8_C(3);",
                "    goto thumb_exit;",
                "thumb_alignment_fault: ;",
                "    if (steps_executed_out != 0) *steps_executed_out = execution_steps;",
                "    if (execution_status_out != 0) *execution_status_out = UINT8_C(4);",
            ))
        lines.append("thumb_exit: ;")
    # Read each guest register in the epilogue so strict C compilers do not
    # reject valid fixtures that write a register whose value is not returned.
    lines.extend(f"    (void)r{reg};" for reg in sorted(used_registers))
    lines.extend((
        "    if (nzcv_out != 0) {",
        "        *nzcv_out = (uint8_t)((flag_n << 3) | (flag_z << 2) | (flag_c << 1) | flag_v);",
        "    }",
    ))
    if runtime_state_io:
        lines.append("    if (registers_out != 0) {")
        lines.extend(f"        registers_out[{reg}] = r{reg};" for reg in range(8))
        lines.append("    }")
    lines.extend((
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
