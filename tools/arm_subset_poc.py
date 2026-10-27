#!/usr/bin/env python3
"""Clean-room proof of concept: translate a tiny synthetic ARM A32 subset to C.

This demonstrator is not a general-purpose recompiler and does not load game files.
It supports a bounded immediate data-processing subset, NZCV for ADDS/SUBS/CMN/CMP,
and B with standard condition codes. Logical S-bit forms, memory and game runtime
services remain outside the scope of this proof of concept.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

DEFAULT_WORDS = (0xE3A0000C, 0xE2400008, 0xE2800003, 0xE2000007, 0xE3800008, 0xE2200001, 0xE3C00002, 0xE3E01000, 0xE201000C, 0xE12FFF1E)
MAX_INSTRUCTIONS = 256
MAX_EXECUTION_STEPS = 100000

# ARM condition field (bits 31:28) -> supported predicate name for B and data ops.
# 0xF selects the unconditional/BLX-immediate space and is rejected by this POC.
BRANCH_CONDITION_NAMES = {
    0x0: "eq", 0x1: "ne", 0x2: "cs", 0x3: "cc", 0x4: "mi", 0x5: "pl", 0x6: "vs",
    0x7: "vc", 0x8: "hi", 0x9: "ls", 0xA: "ge", 0xB: "lt", 0xC: "gt", 0xD: "le",
    0xE: "al",
}
# C expressions over the 0/1-valued flag_n/flag_z/flag_c/flag_v of the generated function.
BRANCH_CONDITION_C = {
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


class UnsupportedInstruction(ValueError):
    """The input is outside this demonstrator's intentionally small subset."""


def _apply_condition(condition: int, instruction: tuple[object, ...]) -> tuple[object, ...]:
    """Wrap a supported non-AL data-processing instruction with its A32 predicate."""
    if condition == 0xE:
        return instruction
    mnemonic = BRANCH_CONDITION_NAMES.get(condition)
    if mnemonic is None or mnemonic == "al":
        raise UnsupportedInstruction(f"unsupported data-processing condition 0x{condition:X}")
    return ("predicated", mnemonic, instruction)


def ror32(value: int, amount: int) -> int:
    amount %= 32
    value &= 0xFFFFFFFF
    if amount == 0:
        return value
    return ((value >> amount) | (value << (32 - amount))) & 0xFFFFFFFF


def _decode_register_data_processing(word: int, condition: int) -> tuple[object, ...]:
    """Decode a register Operand2 with the only accepted shift form: no shift."""
    if word & 0x00000FF0:
        raise UnsupportedInstruction(
            f"register Operand2 shifts are unsupported in 0x{word:08X}"
        )
    opcode = (word >> 21) & 0xF
    set_flags = (word >> 20) & 1
    rn = (word >> 16) & 0xF
    rd = (word >> 12) & 0xF
    rm = word & 0xF

    if set_flags and opcode not in (0b0100, 0b0010, 0b1011, 0b1010):
        raise UnsupportedInstruction(
            f"flag-setting form is unsupported for register Operand2: 0x{word:08X}"
        )

    # All values remain in a tiny, explicit r0-r3 model. PC/SP/LR operands
    # and PC writes are excluded rather than approximated.
    if opcode in (0b1011, 0b1010):  # CMN/CMP register: update flags only.
        operation = "cmn_reg" if opcode == 0b1011 else "cmp_reg"
        if not set_flags:
            raise UnsupportedInstruction(f"{operation[:-4].upper()} requires the S bit to be set")
        if rd != 0:
            raise UnsupportedInstruction(
                f"only canonical {operation[:-4].upper()} register encoding with Rd=0 is supported"
            )
        if rn > 3 or rm > 3:
            register = max(rn, rm)
            raise UnsupportedInstruction(f"source register r{register} is outside r0-r3 subset")
        return _apply_condition(condition, (operation, rn, rm))

    if rd > 3:
        raise UnsupportedInstruction(f"destination register r{rd} is outside r0-r3 subset")

    if opcode in (0b1101, 0b1111):  # MOV/MVN register.
        if rn != 0:
            operation = "MOV" if opcode == 0b1101 else "MVN"
            raise UnsupportedInstruction(
                f"only the canonical {operation} register encoding with Rn=0 is supported"
            )
        if rm > 3:
            raise UnsupportedInstruction(f"source register r{rm} is outside r0-r3 subset")
        operation = "mov_reg" if opcode == 0b1101 else "mvn_reg"
        return _apply_condition(condition, (operation, rd, rm))

    logical_operations = {
        0b0000: "and_reg",
        0b1100: "orr_reg",
        0b0001: "eor_reg",
        0b1110: "bic_reg",
    }
    if opcode in logical_operations:
        if rn > 3 or rm > 3:
            register = max(rn, rm)
            raise UnsupportedInstruction(f"source register r{register} is outside r0-r3 subset")
        return _apply_condition(condition, (logical_operations[opcode], rd, rn, rm))

    if opcode in (0b0100, 0b0010):  # ADD/SUB, optionally setting arithmetic flags.
        if rn > 3 or rm > 3:
            register = max(rn, rm)
            raise UnsupportedInstruction(f"source register r{register} is outside r0-r3 subset")
        base = "add" if opcode == 0b0100 else "sub"
        operation = (base + "s" if set_flags else base) + "_reg"
        return _apply_condition(condition, (operation, rd, rn, rm))

    raise UnsupportedInstruction(
        f"unsupported register data-processing opcode {opcode:04b} in 0x{word:08X}"
    )


def decode_word(word: int) -> tuple[object, ...]:
    """Decode one supported ARM A32 word into a small, explicit instruction tuple."""
    if not isinstance(word, int) or word < 0 or word > 0xFFFFFFFF:
        raise UnsupportedInstruction(f"instruction word outside uint32: {word!r}")

    # The only supported return/terminator is BX LR, with its exact encoding.
    if word == 0xE12FFF1E:
        return ("return",)

    condition = (word >> 28) & 0xF

    # B (not BL) supports AL and the fourteen standard conditions (EQ..LE) in this POC.
    # ARM A32 computes the destination from PC+8 plus sign-extended imm24<<2.
    # Since this fixture is word-indexed, target = index + 2 + sign_extend(imm24).
    if ((word >> 25) & 0b111) == 0b101:
        if (word >> 24) & 1:
            raise UnsupportedInstruction(f"branch-with-link is unsupported: 0x{word:08X}")
        if condition not in BRANCH_CONDITION_NAMES:
            raise UnsupportedInstruction(f"branch condition is unsupported in 0x{word:08X}")
        offset = word & 0x00FFFFFF
        if offset & 0x00800000:
            offset -= 0x01000000
        branch_condition = BRANCH_CONDITION_NAMES[condition]
        return ("branch", branch_condition, offset)

    if condition == 0xF:
        raise UnsupportedInstruction(f"condition code 0xF is unsupported in 0x{word:08X}")

    # A32 data-processing instructions with a plain register operand (no
    # shifter) are a separate narrow subset. Other register-shift forms remain
    # rejected because they require exact Operand2 carry/shift semantics.
    operand_format = (word >> 25) & 0b111
    if operand_format == 0b000:
        return _decode_register_data_processing(word, condition)
    if operand_format != 0b001:
        raise UnsupportedInstruction(
            f"not a supported data-processing operand form: 0x{word:08X}"
        )

    opcode = (word >> 21) & 0xF
    set_flags = (word >> 20) & 1
    rn = (word >> 16) & 0xF
    rd = (word >> 12) & 0xF
    rotate = ((word >> 8) & 0xF) * 2
    imm8 = word & 0xFF
    immediate = ror32(imm8, rotate)

    # This integration stage deliberately enables only flag-setting ADD/SUB and
    # canonical CMN/CMP. Logical S-bit forms require shifter-carry semantics and
    # stay unsupported until that behavior is modeled end-to-end.
    if set_flags and opcode not in (0b0100, 0b0010, 0b1011, 0b1010):
        raise UnsupportedInstruction(f"flag-setting form is unsupported: 0x{word:08X}")

    if opcode == 0b1011:  # CMN (immediate): arithmetic flags, no destination write
        if not set_flags:
            raise UnsupportedInstruction("CMN requires the S bit to be set")
        if rd != 0:
            raise UnsupportedInstruction("only canonical CMN encoding with Rd=0 is supported")
        if rn > 3:
            raise UnsupportedInstruction(f"source register r{rn} is outside r0-r3 subset")
        return _apply_condition(condition, ("cmn", rn, immediate))

    if opcode == 0b1010:  # CMP (immediate): subtract for flags, no destination write
        if not set_flags:
            raise UnsupportedInstruction("CMP requires the S bit to be set")
        if rd != 0:
            raise UnsupportedInstruction("only canonical CMP encoding with Rd=0 is supported")
        if rn > 3:
            raise UnsupportedInstruction(f"source register r{rn} is outside r0-r3 subset")
        return _apply_condition(condition, ("cmp", rn, immediate))

    # Restrict this POC to r0-r3 so the generated C and tests stay auditable.
    if rd > 3:
        raise UnsupportedInstruction(f"destination register r{rd} is outside r0-r3 subset")

    if opcode == 0b1101:  # MOV (immediate)
        if rn != 0:
            raise UnsupportedInstruction("only the canonical MOV immediate encoding with Rn=0 is supported")
        return _apply_condition(condition, ("mov", rd, immediate))

    if opcode == 0b1111:  # MVN (immediate)
        if rn != 0:
            raise UnsupportedInstruction("only the canonical MVN immediate encoding with Rn=0 is supported")
        return _apply_condition(condition, ("mvn", rd, immediate))

    if opcode == 0b0000:  # AND (immediate)
        if rn > 3:
            raise UnsupportedInstruction(f"source register r{rn} is outside r0-r3 subset")
        return _apply_condition(condition, ("and", rd, rn, immediate))

    if opcode == 0b1100:  # ORR (immediate)
        if rn > 3:
            raise UnsupportedInstruction(f"source register r{rn} is outside r0-r3 subset")
        return _apply_condition(condition, ("orr", rd, rn, immediate))

    if opcode == 0b0001:  # EOR (immediate)
        if rn > 3:
            raise UnsupportedInstruction(f"source register r{rn} is outside r0-r3 subset")
        return _apply_condition(condition, ("eor", rd, rn, immediate))

    if opcode == 0b1110:  # BIC (immediate)
        if rn > 3:
            raise UnsupportedInstruction(f"source register r{rn} is outside r0-r3 subset")
        return _apply_condition(condition, ("bic", rd, rn, immediate))

    if opcode == 0b0100:  # ADD (immediate)
        if rn > 3:
            raise UnsupportedInstruction(f"source register r{rn} is outside r0-r3 subset")
        return _apply_condition(condition, ("adds" if set_flags else "add", rd, rn, immediate))

    if opcode == 0b0010:  # SUB (immediate)
        if rn > 3:
            raise UnsupportedInstruction(f"source register r{rn} is outside r0-r3 subset")
        return _apply_condition(condition, ("subs" if set_flags else "sub", rd, rn, immediate))

    raise UnsupportedInstruction(f"unsupported data-processing opcode {opcode:04b} in 0x{word:08X}")


def translate(
    words: tuple[int, ...] | list[int],
    initial_nzcv: int = 0,
    max_execution_steps: int | None = None,
    runtime_state_io: bool = False,
) -> str:
    """Translate a synthetic A32 sequence to standalone C.

    By default, registers and NZCV are fixed at translation time, preserving the
    original synthetic POC API. With ``runtime_state_io=True``, bounded C accepts
    entry r0-r3 and NZCV at runtime and returns all four registers plus NZCV,
    step count and execution status. This is a candidate-range test interface,
    not the original ARM ABI or proof of equivalence.
    """
    if not isinstance(runtime_state_io, bool):
        raise UnsupportedInstruction("runtime_state_io must be a bool")
    if runtime_state_io and max_execution_steps is None:
        raise UnsupportedInstruction("runtime_state_io requires an explicit execution budget")
    if isinstance(initial_nzcv, bool) or not isinstance(initial_nzcv, int) or not 0 <= initial_nzcv <= 0xF:
        raise UnsupportedInstruction(f"initial NZCV must be a 4-bit value (0..15): {initial_nzcv!r}")
    if max_execution_steps is not None and (
        isinstance(max_execution_steps, bool)
        or not isinstance(max_execution_steps, int)
        or not 1 <= max_execution_steps <= MAX_EXECUTION_STEPS
    ):
        raise UnsupportedInstruction(
            f"execution budget must be an integer in 1..{MAX_EXECUTION_STEPS}: {max_execution_steps!r}"
        )
    if not words:
        raise UnsupportedInstruction("empty instruction sequence")
    if len(words) > MAX_INSTRUCTIONS:
        raise UnsupportedInstruction(f"sequence exceeds {MAX_INSTRUCTIONS} instructions")

    decoded = [decode_word(word) for word in words]
    if decoded[-1] != ("return",):
        raise UnsupportedInstruction("sequence must end with BX LR")
    if any(instruction == ("return",) for instruction in decoded[:-1]):
        raise UnsupportedInstruction("instructions after BX LR are unsupported")

    branch_targets: dict[int, int] = {}
    for instruction_index, instruction in enumerate(decoded):
        if instruction[0] == "branch":
            target = instruction_index + 2 + instruction[2]
            if not 0 <= target < len(decoded):
                raise UnsupportedInstruction(
                    f"branch at instruction {instruction_index} targets out-of-range instruction {target}"
                )
            if target <= instruction_index and max_execution_steps is None:
                raise UnsupportedInstruction(
                    f"backward or self-targeting branch at instruction {instruction_index} is unsupported without an execution budget"
                )
            branch_targets[instruction_index] = target

    used_registers = {0}  # r0 is the return register, even if not written.
    for instruction in decoded[:-1]:
        if instruction[0] == "predicated":
            instruction = instruction[2]
        operation = str(instruction[0])
        if operation in ("mov", "mvn"):
            used_registers.add(instruction[1])
        elif operation in ("mov_reg", "mvn_reg"):
            used_registers.update((instruction[1], instruction[2]))
        elif operation in ("and", "orr", "eor", "bic", "add", "sub", "adds", "subs"):
            used_registers.add(instruction[1])
            used_registers.add(instruction[2])
        elif operation in ("and_reg", "orr_reg", "eor_reg", "bic_reg", "add_reg", "sub_reg", "adds_reg", "subs_reg"):
            used_registers.update((instruction[1], instruction[2], instruction[3]))
        elif operation in ("cmn", "cmp"):
            used_registers.add(instruction[1])
        elif operation in ("cmn_reg", "cmp_reg"):
            used_registers.update((instruction[1], instruction[2]))

    if runtime_state_io:
        used_registers = set(range(4))
    bounded = max_execution_steps is not None
    function_signature = (
        "uint32_t synthetic_entry_bounded(const uint32_t *registers_in, "
        "uint8_t initial_nzcv, uint8_t *nzcv_out, uint32_t *steps_executed_out, "
        "uint8_t *execution_status_out, uint32_t *registers_out)"
        if runtime_state_io else (
            "uint32_t synthetic_entry_bounded(uint8_t *nzcv_out, "
            "uint32_t *steps_executed_out, uint8_t *execution_status_out)"
            if bounded else "uint32_t synthetic_entry(uint8_t *nzcv_out)"
        )
    )
    flag_initializers = (
        [
            "    uint32_t flag_n = (uint32_t)((initial_nzcv >> 3) & 1U);",
            "    uint32_t flag_z = (uint32_t)((initial_nzcv >> 2) & 1U);",
            "    uint32_t flag_c = (uint32_t)((initial_nzcv >> 1) & 1U);",
            "    uint32_t flag_v = (uint32_t)(initial_nzcv & 1U);",
        ] if runtime_state_io else [
            f"    uint32_t flag_n = {(initial_nzcv >> 3) & 1};",
            f"    uint32_t flag_z = {(initial_nzcv >> 2) & 1};",
            f"    uint32_t flag_c = {(initial_nzcv >> 1) & 1};",
            f"    uint32_t flag_v = {initial_nzcv & 1};",
        ]
    )
    lines = [
        "#include <stdint.h>",
        "",
        "/* Generated C remains a candidate model; independent semantic validation is required. */"
        if runtime_state_io else
        "/* Generated only from the synthetic instruction sequence supplied. */",
        function_signature,
        "{",
    ]
    if runtime_state_io:
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
        lines.extend(f"    uint32_t r{register} = registers_in[{register}];" for register in sorted(used_registers))
    else:
        lines.extend(f"    uint32_t r{register} = 0;" for register in sorted(used_registers))
    branch_target_indices = set(branch_targets.values())
    for instruction_index, instruction in enumerate(decoded[:-1]):
        if instruction_index in branch_target_indices:
            lines.append(f"arm_label_{instruction_index}: ;")
        if bounded:
            lines.append(f"    if (execution_steps >= UINT32_C({max_execution_steps})) goto arm_budget_exhausted;")
            lines.append("    execution_steps++;")
        condition_name: str | None = None
        if instruction[0] == "predicated":
            _, condition_name, instruction = instruction
            lines.append(f"    if ({BRANCH_CONDITION_C[condition_name]}) {{")
        conditional_body_start = len(lines)
        if instruction[0] == "branch":
            condition, _offset = instruction[1], instruction[2]
            target = branch_targets[instruction_index]
            if condition == "al":
                lines.append(f"    goto arm_label_{target};")
            elif condition in BRANCH_CONDITION_C:
                lines.append(f"    if ({BRANCH_CONDITION_C[condition]}) goto arm_label_{target};")
            else:  # decoder closes the supported condition set.
                raise UnsupportedInstruction(f"internal unsupported branch condition: {condition!r}")
        elif instruction[0] == "mov":
            _, rd, immediate = instruction
            lines.append(f"    r{rd} = UINT32_C({immediate});")
        elif instruction[0] == "mvn":
            _, rd, immediate = instruction
            lines.append(f"    r{rd} = (uint32_t)~UINT32_C({immediate});")
        elif instruction[0] in ("mov_reg", "mvn_reg"):
            _, rd, rm = instruction
            expression = f"r{rm}" if instruction[0] == "mov_reg" else f"(uint32_t)~r{rm}"
            lines.append(f"    r{rd} = {expression};")
        elif instruction[0] in ("and_reg", "orr_reg", "eor_reg", "bic_reg"):
            _, rd, rn, rm = instruction
            operator = {"and_reg": "&", "orr_reg": "|", "eor_reg": "^", "bic_reg": "& ~"}[instruction[0]]
            expression = f"r{rn} {operator} r{rm}" if instruction[0] != "bic_reg" else f"r{rn} & ~r{rm}"
            lines.append(f"    r{rd} = (uint32_t)({expression});")
        elif instruction[0] == "and":
            _, rd, rn, immediate = instruction
            lines.append(f"    r{rd} = (uint32_t)(r{rn} & UINT32_C({immediate}));")
        elif instruction[0] == "orr":
            _, rd, rn, immediate = instruction
            lines.append(f"    r{rd} = (uint32_t)(r{rn} | UINT32_C({immediate}));")
        elif instruction[0] == "eor":
            _, rd, rn, immediate = instruction
            lines.append(f"    r{rd} = (uint32_t)(r{rn} ^ UINT32_C({immediate}));")
        elif instruction[0] == "bic":
            _, rd, rn, immediate = instruction
            lines.append(f"    r{rd} = (uint32_t)(r{rn} & ~UINT32_C({immediate}));")
        elif instruction[0] == "add":
            _, rd, rn, immediate = instruction
            lines.append(f"    r{rd} = (uint32_t)(r{rn} + UINT32_C({immediate}));")
        elif instruction[0] == "sub":
            _, rd, rn, immediate = instruction
            lines.append(f"    r{rd} = (uint32_t)(r{rn} - UINT32_C({immediate}));")
        elif instruction[0] in ("add_reg", "sub_reg"):
            _, rd, rn, rm = instruction
            operator = "+" if instruction[0] == "add_reg" else "-"
            lines.append(f"    r{rd} = (uint32_t)(r{rn} {operator} r{rm});")
        elif instruction[0] in ("adds", "subs", "cmn", "cmp", "adds_reg", "subs_reg", "cmn_reg", "cmp_reg"):
            operation = str(instruction[0]).removesuffix("_reg")
            register_operand = str(instruction[0]).endswith("_reg")
            if operation in ("cmn", "cmp"):
                if register_operand:
                    _, rn, rm = instruction
                    rhs_expression = f"r{rm}"
                else:
                    _, rn, immediate = instruction
                    rhs_expression = f"UINT32_C({immediate})"
                rd = None
            else:
                if register_operand:
                    _, rd, rn, rm = instruction
                    rhs_expression = f"r{rm}"
                else:
                    _, rd, rn, immediate = instruction
                    rhs_expression = f"UINT32_C({immediate})"
            suffix = f"{len(lines)}"
            lhs = f"flag_lhs_{suffix}"
            result = f"flag_result_{suffix}"
            rhs = f"flag_rhs_{suffix}"
            lines.append(f"    uint32_t {lhs} = r{rn};")
            lines.append(f"    uint32_t {rhs} = {rhs_expression};")
            if operation in ("adds", "cmn"):
                wide = f"flag_wide_{suffix}"
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
        else:  # defensive: decode/translation tuples are intentionally closed.
            raise UnsupportedInstruction(f"internal unsupported tuple: {instruction!r}")
        if condition_name is not None:
            for line_index in range(conditional_body_start, len(lines)):
                lines[line_index] = "    " + lines[line_index]
            lines.append("    }")
    if len(decoded) - 1 in branch_target_indices:
        # BX LR is represented by the common C epilogue, which is the target
        # associated with the final guest instruction index.
        lines.append(f"arm_label_{len(decoded) - 1}: ;")
    if bounded:
        lines.extend((
            f"    if (execution_steps >= UINT32_C({max_execution_steps})) goto arm_budget_exhausted;",
            "    execution_steps++;",
            "    if (steps_executed_out != 0) *steps_executed_out = execution_steps;",
            "    if (execution_status_out != 0) *execution_status_out = UINT8_C(0);",
            "    goto arm_exit;",
            "arm_budget_exhausted: ;",
            "    if (steps_executed_out != 0) *steps_executed_out = execution_steps;",
            "    if (execution_status_out != 0) *execution_status_out = UINT8_C(1);",
            "arm_exit: ;",
        ))
    lines.extend((
        "    if (nzcv_out != 0) {",
        "        *nzcv_out = (uint8_t)((flag_n << 3) | (flag_z << 2) | (flag_c << 1) | flag_v);",
        "    }",
    ))
    if runtime_state_io:
        lines.append("    if (registers_out != 0) {")
        lines.extend(f"        registers_out[{register}] = r{register};" for register in range(4))
        lines.append("    }")
    lines.extend((
        "    return r0;",
        "}",
        "",
    ))
    return "\n".join(lines)


def parse_word(token: str) -> int:
    try:
        value = int(token, 16)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"expected a hexadecimal ARM word, got {token!r}") from exc
    if value < 0 or value > 0xFFFFFFFF:
        raise argparse.ArgumentTypeError(f"ARM word is outside uint32: {token!r}")
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
        description="Translate a tiny, synthetic ARM A32 instruction subset into C; no game files are read."
    )
    parser.add_argument(
        "words", nargs="*", type=parse_word,
        help="hex instruction words (default: MOV r0,#12; SUB r0,r0,#8; ADD r0,r0,#3; AND r0,r0,#7; ORR r0,r0,#8; EOR r0,r0,#1; BIC r0,r0,#2; MVN r1,#0; AND r0,r1,#12; BX LR)",
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
            args.words or list(DEFAULT_WORDS),
            initial_nzcv=args.initial_nzcv,
            max_execution_steps=args.max_execution_steps,
        )
        if args.output:
            args.output.write_text(source, encoding="utf-8", newline="\n")
        else:
            sys.stdout.write(source)
    except (UnsupportedInstruction, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
