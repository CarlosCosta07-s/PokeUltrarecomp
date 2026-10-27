#!/usr/bin/env python3
"""Clean-room proof of concept: translate a tiny synthetic ARM A32 subset to C.

This demonstrator is not a general-purpose recompiler and does not load game files.
It supports a narrow immediate subset plus register Operand2 forms with immediate
LSL/LSR/ASR/ROR/RRX shifts and rotated-immediate logical S-bit operations, including
the corresponding shifter-carry rules. It also handles bounded pre-indexed immediate
word, byte and halfword transfers plus signed LDRSB/LDRSH loads without writeback.
Register-controlled shifts, unsupported opcodes, other memory modes and real game
runtime services remain outside its scope.
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
    """Decode register Operand2 with immediate LSL/LSR/ASR/ROR/RRX shift semantics."""
    # A32 register-specified shift amounts (bit 4=1) remain unsupported.
    if word & 0x00000010:
        raise UnsupportedInstruction(
            f"register-specified Operand2 shifts are unsupported in 0x{word:08X}"
        )
    shift_type_code = (word >> 5) & 0b11
    shift_amount = (word >> 7) & 0x1F
    shift_kind: str | None = None
    if shift_type_code == 0:
        if shift_amount:
            shift_kind = "lsl"
    elif shift_type_code == 1:
        shift_kind = "lsr"
        shift_amount = shift_amount or 32
    elif shift_type_code == 2:
        shift_kind = "asr"
        shift_amount = shift_amount or 32
    else:
        if shift_amount == 0:
            shift_kind = "rrx"
        else:
            shift_kind = "ror"

    def complete(operation: tuple[object, ...]) -> tuple[object, ...]:
        if shift_kind is not None:
            operation = ("shifted_operand", operation, shift_kind, shift_amount)
        return _apply_condition(condition, operation)

    opcode = (word >> 21) & 0xF
    set_flags = (word >> 20) & 1
    rn = (word >> 16) & 0xF
    rd = (word >> 12) & 0xF
    rm = word & 0xF

    flag_setting_opcodes = {
        0b0000, 0b0001, 0b0010, 0b0011, 0b0100, 0b0101, 0b0110, 0b0111,
        0b1000, 0b1001, 0b1010, 0b1011, 0b1100, 0b1101, 0b1110, 0b1111,
    }
    if set_flags and opcode not in flag_setting_opcodes:
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
        return complete((operation, rn, rm))

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
        base = "mov" if opcode == 0b1101 else "mvn"
        operation = (base + "s" if set_flags else base) + "_reg"
        return complete((operation, rd, rm))

    if opcode in (0b1000, 0b1001):  # TST/TEQ: update flags without writing Rd.
        operation = "tst_reg" if opcode == 0b1000 else "teq_reg"
        if not set_flags:
            raise UnsupportedInstruction(f"{operation[:-4].upper()} requires the S bit to be set")
        if rd != 0:
            raise UnsupportedInstruction(
                f"only canonical {operation[:-4].upper()} register encoding with Rd=0 is supported"
            )
        if rn > 3 or rm > 3:
            register = max(rn, rm)
            raise UnsupportedInstruction(f"source register r{register} is outside r0-r3 subset")
        return complete((operation, rn, rm))

    logical_operations = {
        0b0000: "and",
        0b1100: "orr",
        0b0001: "eor",
        0b1110: "bic",
    }
    if opcode in logical_operations:
        if rn > 3 or rm > 3:
            register = max(rn, rm)
            raise UnsupportedInstruction(f"source register r{register} is outside r0-r3 subset")
        base = logical_operations[opcode]
        operation = (base + "s" if set_flags else base) + "_reg"
        return complete((operation, rd, rn, rm))

    arithmetic_operations = {
        0b0100: "add", 0b0010: "sub", 0b0101: "adc",
        0b0110: "sbc", 0b0111: "rsc",
    }
    if opcode in arithmetic_operations:
        if rn > 3 or rm > 3:
            register = max(rn, rm)
            raise UnsupportedInstruction(f"source register r{register} is outside r0-r3 subset")
        base = arithmetic_operations[opcode]
        operation = (base + "s" if set_flags else base) + "_reg"
        return complete((operation, rd, rn, rm))

    raise UnsupportedInstruction(
        f"unsupported register data-processing opcode {opcode:04b} in 0x{word:08X}"
    )


def _decode_single_data_transfer(word: int, condition: int) -> tuple[object, ...]:
    """Decode conservative A32 pre-indexed immediate LDR/STR byte and word transfers."""
    if (word >> 25) & 1:  # I=1 means register-offset form, which needs Operand2 shifts.
        raise UnsupportedInstruction(f"register-offset memory access is unsupported: 0x{word:08X}")
    pre_index = (word >> 24) & 1
    up = (word >> 23) & 1
    byte_transfer = (word >> 22) & 1
    writeback = (word >> 21) & 1
    load = (word >> 20) & 1
    rn = (word >> 16) & 0xF
    rd = (word >> 12) & 0xF
    offset = word & 0xFFF

    if not pre_index or writeback:
        raise UnsupportedInstruction(
            f"post-indexed or writeback memory access is unsupported: 0x{word:08X}"
        )
    if rn > 3:
        raise UnsupportedInstruction(f"base register r{rn} is outside r0-r3 subset")
    if rd > 3:
        raise UnsupportedInstruction(f"destination register r{rd} is outside r0-r3 subset")
    if byte_transfer:
        operation = "ldrb_imm" if load else "strb_imm"
    else:
        operation = "ldr_imm" if load else "str_imm"
    return _apply_condition(condition, (operation, rd, rn, offset, bool(up)))


def _decode_halfword_data_transfer(word: int, condition: int) -> tuple[object, ...]:
    """Decode conservative A32 immediate LDRH/STRH/LDRSB/LDRSH memory forms."""
    transfer_kind = (word >> 5) & 0b11  # S:H in the A32 extra load/store encoding.
    if transfer_kind == 0b00:
        raise UnsupportedInstruction(
            f"reserved or doubleword A32 extra memory transfer is unsupported: 0x{word:08X}"
        )
    immediate_offset = (word >> 22) & 1
    if not immediate_offset:
        raise UnsupportedInstruction(
            f"register-offset halfword/signed memory access is unsupported: 0x{word:08X}"
        )
    pre_index = (word >> 24) & 1
    up = (word >> 23) & 1
    writeback = (word >> 21) & 1
    load = (word >> 20) & 1
    rn = (word >> 16) & 0xF
    rd = (word >> 12) & 0xF
    if not pre_index or writeback:
        raise UnsupportedInstruction(
            f"post-indexed or writeback halfword/signed memory access is unsupported: 0x{word:08X}"
        )
    if rn > 3:
        raise UnsupportedInstruction(f"base register r{rn} is outside r0-r3 subset")
    if rd > 3:
        raise UnsupportedInstruction(f"destination register r{rd} is outside r0-r3 subset")

    # S:H=01 denotes LDRH/STRH; S:H=10/11 denote signed loads only.
    if transfer_kind == 0b01:
        operation = "ldrh_imm" if load else "strh_imm"
    elif transfer_kind == 0b10:
        if not load:
            raise UnsupportedInstruction(
                f"signed-byte store encoding is reserved and unsupported: 0x{word:08X}"
            )
        operation = "ldrsb_imm"
    else:  # transfer_kind == 0b11
        if not load:
            raise UnsupportedInstruction(
                f"signed-halfword store encoding is reserved and unsupported: 0x{word:08X}"
            )
        operation = "ldrsh_imm"

    # A32 extra-load/store immediate offsets use imm4H:imm4L, unlike LDR/STR imm12.
    offset = ((word >> 4) & 0xF0) | (word & 0xF)
    return _apply_condition(condition, (operation, rd, rn, offset, bool(up)))


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

    # Extra load/store forms share some bit patterns with multiply instructions.
    # A nonzero S:H field or P/U/I addressing fields distinguishes this class.
    if (
        (word & 0x0E000090) == 0x00000090
        and (((word >> 5) & 0b11) != 0 or ((word >> 22) & 0b111) != 0)
    ):
        return _decode_halfword_data_transfer(word, condition)

    # Single data-transfer class (LDR/STR byte/word) is decoded separately from ALU forms.
    if ((word >> 26) & 0b11) == 0b01:
        return _decode_single_data_transfer(word, condition)

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
    # A rotated immediate updates shifter-carry only when rotate_imm is nonzero.
    # None means preserve the incoming C flag for rotate_imm == 0.
    shifter_carry = ((immediate >> 31) & 1) if rotate else None

    # Flag-setting forms accepted here have explicit NZCV and shifter-carry rules.
    flag_setting_opcodes = {
        0b0000, 0b0001, 0b0010, 0b0011, 0b0100, 0b0101, 0b0110, 0b0111,
        0b1000, 0b1001, 0b1010, 0b1011, 0b1100, 0b1101, 0b1110, 0b1111,
    }
    if set_flags and opcode not in flag_setting_opcodes:
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

    if opcode in (0b0101, 0b0110, 0b0111):  # ADC/SBC/RSC: consume C-in.
        if rd > 3:
            raise UnsupportedInstruction(f"destination register r{rd} is outside r0-r3 subset")
        if rn > 3:
            raise UnsupportedInstruction(f"source register r{rn} is outside r0-r3 subset")
        base = {0b0101: "adc", 0b0110: "sbc", 0b0111: "rsc"}[opcode]
        operation = base + "s" if set_flags else base
        return _apply_condition(condition, (operation, rd, rn, immediate))

    if opcode in (0b1000, 0b1001):  # TST/TEQ (immediate): logical flags only.
        operation = "tst_imm" if opcode == 0b1000 else "teq_imm"
        if not set_flags:
            raise UnsupportedInstruction(f"{operation[:-4].upper()} requires the S bit to be set")
        if rd != 0:
            raise UnsupportedInstruction(f"only canonical {operation[:-4].upper()} encoding with Rd=0 is supported")
        if rn > 3:
            raise UnsupportedInstruction(f"source register r{rn} is outside r0-r3 subset")
        return _apply_condition(condition, (operation, rn, immediate, shifter_carry))

    # Restrict this POC to r0-r3 so the generated C and tests stay auditable.
    if rd > 3:
        raise UnsupportedInstruction(f"destination register r{rd} is outside r0-r3 subset")

    if opcode == 0b1101:  # MOV/MOVS (immediate)
        if rn != 0:
            raise UnsupportedInstruction("only the canonical MOV immediate encoding with Rn=0 is supported")
        if set_flags:
            return _apply_condition(condition, ("movs_imm", rd, immediate, shifter_carry))
        return _apply_condition(condition, ("mov", rd, immediate))

    if opcode == 0b1111:  # MVN/MVNS (immediate)
        if rn != 0:
            raise UnsupportedInstruction("only the canonical MVN immediate encoding with Rn=0 is supported")
        if set_flags:
            return _apply_condition(condition, ("mvns_imm", rd, immediate, shifter_carry))
        return _apply_condition(condition, ("mvn", rd, immediate))

    if opcode == 0b0000:  # AND (immediate)
        if rn > 3:
            raise UnsupportedInstruction(f"source register r{rn} is outside r0-r3 subset")
        if set_flags:
            return _apply_condition(condition, ("ands_imm", rd, rn, immediate, shifter_carry))
        return _apply_condition(condition, ("and", rd, rn, immediate))

    if opcode == 0b1100:  # ORR (immediate)
        if rn > 3:
            raise UnsupportedInstruction(f"source register r{rn} is outside r0-r3 subset")
        if set_flags:
            return _apply_condition(condition, ("orrs_imm", rd, rn, immediate, shifter_carry))
        return _apply_condition(condition, ("orr", rd, rn, immediate))

    if opcode == 0b0001:  # EOR (immediate)
        if rn > 3:
            raise UnsupportedInstruction(f"source register r{rn} is outside r0-r3 subset")
        if set_flags:
            return _apply_condition(condition, ("eors_imm", rd, rn, immediate, shifter_carry))
        return _apply_condition(condition, ("eor", rd, rn, immediate))

    if opcode == 0b1110:  # BIC (immediate)
        if rn > 3:
            raise UnsupportedInstruction(f"source register r{rn} is outside r0-r3 subset")
        if set_flags:
            return _apply_condition(condition, ("bics_imm", rd, rn, immediate, shifter_carry))
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
    runtime_memory_io: bool = False,
) -> str:
    """Translate a synthetic A32 sequence to standalone C.

    By default, registers and NZCV are fixed at translation time, preserving the
    original synthetic POC API. With ``runtime_state_io=True``, bounded C accepts
    entry r0-r3 and NZCV at runtime and returns all four registers plus NZCV,
    step count and execution status. ``runtime_memory_io=True`` adds an explicit,
    bounded byte-region for pre-indexed immediate word, byte, halfword and signed-load forms.
    Unsupported addresses and misaligned word accesses fail explicitly; no interpreter
    or memory fallback is generated. This remains a synthetic candidate model, not
    the original ARM ABI or proof of equivalence.
    """
    if not isinstance(runtime_state_io, bool):
        raise UnsupportedInstruction("runtime_state_io must be a bool")
    if not isinstance(runtime_memory_io, bool):
        raise UnsupportedInstruction("runtime_memory_io must be a bool")
    if runtime_memory_io and not runtime_state_io:
        raise UnsupportedInstruction("runtime_memory_io requires runtime_state_io=True")
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

    def base_instruction(instruction: tuple[object, ...]) -> tuple[object, ...]:
        while instruction[0] in ("predicated", "shifted_operand"):
            instruction = instruction[2] if instruction[0] == "predicated" else instruction[1]
        return instruction

    contains_memory_access = any(
        base_instruction(instruction)[0] in ("ldr_imm", "str_imm", "ldrb_imm", "strb_imm", "ldrh_imm", "strh_imm", "ldrsb_imm", "ldrsh_imm")
        for instruction in decoded[:-1]
    )
    if contains_memory_access and not runtime_memory_io:
        raise UnsupportedInstruction(
            "memory access requires runtime_memory_io=True and an explicit bounded guest-memory region"
        )

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
        instruction = base_instruction(instruction)
        operation = str(instruction[0])
        if operation in ("mov", "mvn"):
            used_registers.add(instruction[1])
        elif operation in ("mov_reg", "mvn_reg", "movs_reg", "mvns_reg"):
            used_registers.update((instruction[1], instruction[2]))
        elif operation in ("movs_imm", "mvns_imm"):
            used_registers.add(instruction[1])
        elif operation in ("tst_imm", "teq_imm"):
            used_registers.add(instruction[1])
        elif operation in ("ands_imm", "orrs_imm", "eors_imm", "bics_imm"):
            used_registers.update((instruction[1], instruction[2]))
        elif operation in ("and", "orr", "eor", "bic", "add", "sub", "adds", "subs", "adc", "adcs", "sbc", "sbcs", "rsc", "rscs"):
            used_registers.add(instruction[1])
            used_registers.add(instruction[2])
        elif operation in (
            "and_reg", "orr_reg", "eor_reg", "bic_reg", "ands_reg", "orrs_reg",
            "eors_reg", "bics_reg", "add_reg", "sub_reg", "adds_reg", "subs_reg",
            "adc_reg", "adcs_reg", "sbc_reg", "sbcs_reg", "rsc_reg", "rscs_reg",
        ):
            used_registers.update((instruction[1], instruction[2], instruction[3]))
        elif operation in ("cmn", "cmp"):
            used_registers.add(instruction[1])
        elif operation in ("cmn_reg", "cmp_reg", "tst_reg", "teq_reg"):
            used_registers.update((instruction[1], instruction[2]))
        elif operation in ("ldr_imm", "str_imm", "ldrb_imm", "strb_imm", "ldrh_imm", "strh_imm", "ldrsb_imm", "ldrsh_imm"):
            used_registers.update((instruction[1], instruction[2]))

    if runtime_state_io:
        used_registers = set(range(4))
    bounded = max_execution_steps is not None
    function_signature = (
        "uint32_t synthetic_entry_bounded(const uint32_t *registers_in, "
        "uint8_t initial_nzcv, uint8_t *nzcv_out, uint32_t *steps_executed_out, "
        "uint8_t *execution_status_out, uint32_t *registers_out, "
        "uint8_t *memory, uint32_t memory_base, uint32_t memory_size)"
        if runtime_memory_io else (
            "uint32_t synthetic_entry_bounded(const uint32_t *registers_in, "
            "uint8_t initial_nzcv, uint8_t *nzcv_out, uint32_t *steps_executed_out, "
            "uint8_t *execution_status_out, uint32_t *registers_out)"
            if runtime_state_io else (
                "uint32_t synthetic_entry_bounded(uint8_t *nzcv_out, "
                "uint32_t *steps_executed_out, uint8_t *execution_status_out)"
                if bounded else "uint32_t synthetic_entry(uint8_t *nzcv_out)"
            )
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
    if runtime_memory_io:
        lines.extend((
            "    if (registers_in == 0 || initial_nzcv > UINT8_C(15) || memory == 0 || memory_size == 0U",
            "        || ((uint64_t)memory_base + (uint64_t)memory_size) > UINT64_C(0x100000000)) {",
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
        if runtime_memory_io:
            lines.append("    uint8_t execution_status = UINT8_C(0);")
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
        shifted_operand_expr: str | None = None
        shifted_carry_expr: str | None = None
        if instruction[0] == "shifted_operand":
            _, shifted_instruction, shift_kind, shift_amount = instruction
            instruction = shifted_instruction
            operation_name = str(instruction[0])
            rm_index = 2 if operation_name in (
                "mov_reg", "mvn_reg", "movs_reg", "mvns_reg",
                "cmn_reg", "cmp_reg", "tst_reg", "teq_reg",
            ) else 3
            rm = int(instruction[rm_index])
            suffix = f"{len(lines)}"
            shifted_operand_expr = f"shifted_operand_{suffix}"
            lines.append(f"    uint32_t {shifted_operand_expr};")
            needs_shift_carry = operation_name in (
                "movs_reg", "mvns_reg", "ands_reg", "orrs_reg",
                "eors_reg", "bics_reg", "tst_reg", "teq_reg",
            )
            if needs_shift_carry:
                shifted_carry_expr = f"shifted_carry_{suffix}"
                lines.append(f"    uint32_t {shifted_carry_expr};")
            source = f"r{rm}"
            if shift_kind == "lsl":
                lines.append(f"    {shifted_operand_expr} = (uint32_t)({source} << {shift_amount});")
                if shifted_carry_expr:
                    lines.append(f"    {shifted_carry_expr} = ({source} >> {32 - shift_amount}) & 1U;")
            elif shift_kind == "lsr":
                if shift_amount == 32:
                    lines.append(f"    {shifted_operand_expr} = UINT32_C(0);")
                    if shifted_carry_expr:
                        lines.append(f"    {shifted_carry_expr} = ({source} >> 31) & 1U;")
                else:
                    lines.append(f"    {shifted_operand_expr} = {source} >> {shift_amount};")
                    if shifted_carry_expr:
                        lines.append(f"    {shifted_carry_expr} = ({source} >> {shift_amount - 1}) & 1U;")
            elif shift_kind == "asr":
                if shift_amount == 32:
                    lines.append(
                        f"    {shifted_operand_expr} = (({source} & UINT32_C(0x80000000)) != 0U) ? UINT32_MAX : UINT32_C(0);"
                    )
                    if shifted_carry_expr:
                        lines.append(f"    {shifted_carry_expr} = ({source} >> 31) & 1U;")
                else:
                    lines.append(f"    {shifted_operand_expr} = {source} >> {shift_amount};")
                    lines.append(
                        f"    if (({source} & UINT32_C(0x80000000)) != 0U) "
                        f"{shifted_operand_expr} |= UINT32_MAX << {32 - shift_amount};"
                    )
                    if shifted_carry_expr:
                        lines.append(f"    {shifted_carry_expr} = ({source} >> {shift_amount - 1}) & 1U;")
            elif shift_kind == "ror":
                lines.append(
                    f"    {shifted_operand_expr} = (uint32_t)(({source} >> {shift_amount}) | ({source} << {32 - shift_amount}));"
                )
                if shifted_carry_expr:
                    lines.append(f"    {shifted_carry_expr} = ({shifted_operand_expr} >> 31) & 1U;")
            elif shift_kind == "rrx":
                lines.append(
                    f"    {shifted_operand_expr} = (uint32_t)((flag_c << 31) | ({source} >> 1));"
                )
                if shifted_carry_expr:
                    lines.append(f"    {shifted_carry_expr} = {source} & 1U;")
            else:
                raise UnsupportedInstruction(f"internal unknown Operand2 shift {shift_kind!r}")
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
        elif instruction[0] in ("movs_imm", "mvns_imm"):
            _, rd, immediate, carry_out = instruction
            expression = f"UINT32_C({immediate})" if instruction[0] == "movs_imm" else f"(uint32_t)~UINT32_C({immediate})"
            lines.append(f"    r{rd} = {expression};")
            lines.append(f"    flag_n = (r{rd} >> 31) & 1U;")
            lines.append(f"    flag_z = (uint32_t)(r{rd} == 0U);")
            if carry_out is not None:
                lines.append(f"    flag_c = UINT32_C({carry_out});")
        elif instruction[0] in ("mov_reg", "mvn_reg", "movs_reg", "mvns_reg"):
            _, rd, rm = instruction
            base = instruction[0].removesuffix("_reg").removesuffix("s")
            rm_expression = shifted_operand_expr or f"r{rm}"
            if base == "mov":
                expression = rm_expression
            elif shifted_operand_expr:
                expression = f"(uint32_t)~({rm_expression})"
            else:
                expression = f"(uint32_t)~r{rm}"
            lines.append(f"    r{rd} = {expression};")
            if instruction[0] in ("movs_reg", "mvns_reg"):
                lines.append(f"    flag_n = (r{rd} >> 31) & 1U;")
                lines.append(f"    flag_z = (uint32_t)(r{rd} == 0U);")
                if shifted_carry_expr:
                    lines.append(f"    flag_c = {shifted_carry_expr};")
        elif instruction[0] in (
            "and_reg", "orr_reg", "eor_reg", "bic_reg",
            "ands_reg", "orrs_reg", "eors_reg", "bics_reg",
        ):
            _, rd, rn, rm = instruction
            base = instruction[0].removesuffix("_reg").removesuffix("s")
            operator = {"and": "&", "orr": "|", "eor": "^", "bic": "& ~"}[base]
            rm_expression = shifted_operand_expr or f"r{rm}"
            if base == "bic":
                expression = f"r{rn} & ~({rm_expression})" if shifted_operand_expr else f"r{rn} & ~r{rm}"
            else:
                expression = f"r{rn} {operator} ({rm_expression})" if shifted_operand_expr else f"r{rn} {operator} r{rm}"
            if instruction[0] in ("ands_reg", "orrs_reg", "eors_reg", "bics_reg"):
                suffix = f"{len(lines)}"
                result = f"logical_result_{suffix}"
                lines.append(f"    uint32_t {result} = (uint32_t)({expression});")
                lines.append(f"    r{rd} = {result};")
                lines.append(f"    flag_n = ({result} >> 31) & 1U;")
                lines.append(f"    flag_z = (uint32_t)({result} == 0U);")
                if shifted_carry_expr:
                    lines.append(f"    flag_c = {shifted_carry_expr};")
            else:
                lines.append(f"    r{rd} = (uint32_t)({expression});")
        elif instruction[0] in ("tst_reg", "teq_reg"):
            _, rn, rm = instruction
            suffix = f"{len(lines)}"
            result = f"test_result_{suffix}"
            operator = "&" if instruction[0] == "tst_reg" else "^"
            rm_expression = shifted_operand_expr or f"r{rm}"
            expression = f"r{rn} {operator} ({rm_expression})" if shifted_operand_expr else f"r{rn} {operator} r{rm}"
            lines.append(f"    uint32_t {result} = (uint32_t)({expression});")
            lines.append(f"    flag_n = ({result} >> 31) & 1U;")
            lines.append(f"    flag_z = (uint32_t)({result} == 0U);")
            if shifted_carry_expr:
                lines.append(f"    flag_c = {shifted_carry_expr};")
        elif instruction[0] in ("ldr_imm", "str_imm", "ldrb_imm", "strb_imm", "ldrh_imm", "strh_imm", "ldrsb_imm", "ldrsh_imm"):
            _, rd, rn, immediate, add_offset = instruction
            byte_access = instruction[0] in ("ldrb_imm", "strb_imm", "ldrsb_imm")
            halfword_access = instruction[0] in ("ldrh_imm", "strh_imm", "ldrsh_imm")
            access_size = 1 if byte_access else (2 if halfword_access else 4)
            alignment_mask = 0 if byte_access else (1 if halfword_access else 3)
            suffix = f"{len(lines)}"
            address = f"memory_address_{suffix}"
            offset_in_region = f"memory_offset_{suffix}"
            if add_offset:
                wide_address = f"memory_wide_address_{suffix}"
                lines.append(f"    uint64_t {wide_address} = (uint64_t)r{rn} + UINT32_C({immediate});")
                lines.append(f"    if ({wide_address} > UINT64_C(0xFFFFFFFF)) {{ execution_status = UINT8_C(3); goto arm_exit; }}")
                lines.append(f"    uint32_t {address} = (uint32_t){wide_address};")
            else:
                lines.append(f"    if (r{rn} < UINT32_C({immediate})) {{ execution_status = UINT8_C(3); goto arm_exit; }}")
                lines.append(f"    uint32_t {address} = (uint32_t)(r{rn} - UINT32_C({immediate}));")
            if alignment_mask:
                lines.append(f"    if (({address} & UINT32_C({alignment_mask})) != 0U) {{ execution_status = UINT8_C(4); goto arm_exit; }}")
            lines.append(
                f"    if ({address} < memory_base || ((uint64_t){address} + UINT64_C({access_size})) > ((uint64_t)memory_base + (uint64_t)memory_size)) {{ execution_status = UINT8_C(3); goto arm_exit; }}"
            )
            lines.append(f"    uint32_t {offset_in_region} = {address} - memory_base;")
            if instruction[0] == "ldrb_imm":
                lines.append(f"    r{rd} = (uint32_t)memory[{offset_in_region}];")
            elif instruction[0] == "ldrsb_imm":
                lines.append(f"    r{rd} = (uint32_t)memory[{offset_in_region}];")
                lines.append(f"    if ((r{rd} & UINT32_C(0x80)) != 0U) r{rd} |= UINT32_C(0xFFFFFF00);")
            elif instruction[0] == "strb_imm":
                lines.append(f"    memory[{offset_in_region}] = (uint8_t)(r{rd} & UINT32_C(0xFF));")
            elif instruction[0] in ("ldrh_imm", "ldrsh_imm"):
                lines.append(
                    f"    r{rd} = (uint32_t)memory[{offset_in_region}] "
                    f"| ((uint32_t)memory[{offset_in_region} + 1U] << 8);"
                )
                if instruction[0] == "ldrsh_imm":
                    lines.append(f"    if ((r{rd} & UINT32_C(0x8000)) != 0U) r{rd} |= UINT32_C(0xFFFF0000);")
            elif instruction[0] == "strh_imm":
                lines.extend((
                    f"    memory[{offset_in_region}] = (uint8_t)(r{rd} & UINT32_C(0xFF));",
                    f"    memory[{offset_in_region} + 1U] = (uint8_t)((r{rd} >> 8) & UINT32_C(0xFF));",
                ))
            elif instruction[0] == "ldr_imm":
                lines.append(
                    f"    r{rd} = (uint32_t)memory[{offset_in_region}] "
                    f"| ((uint32_t)memory[{offset_in_region} + 1U] << 8) "
                    f"| ((uint32_t)memory[{offset_in_region} + 2U] << 16) "
                    f"| ((uint32_t)memory[{offset_in_region} + 3U] << 24);"
                )
            else:
                lines.extend((
                    f"    memory[{offset_in_region}] = (uint8_t)(r{rd} & UINT32_C(0xFF));",
                    f"    memory[{offset_in_region} + 1U] = (uint8_t)((r{rd} >> 8) & UINT32_C(0xFF));",
                    f"    memory[{offset_in_region} + 2U] = (uint8_t)((r{rd} >> 16) & UINT32_C(0xFF));",
                    f"    memory[{offset_in_region} + 3U] = (uint8_t)((r{rd} >> 24) & UINT32_C(0xFF));",
                ))
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
        elif instruction[0] in ("ands_imm", "orrs_imm", "eors_imm", "bics_imm"):
            _, rd, rn, immediate, carry_out = instruction
            base = {"ands_imm": "and", "orrs_imm": "orr", "eors_imm": "eor", "bics_imm": "bic"}[instruction[0]]
            operator = {"and": "&", "orr": "|", "eor": "^", "bic": "& ~"}[base]
            expression = f"r{rn} & ~UINT32_C({immediate})" if base == "bic" else f"r{rn} {operator} UINT32_C({immediate})"
            suffix = f"{len(lines)}"
            result = f"logical_imm_result_{suffix}"
            lines.append(f"    uint32_t {result} = (uint32_t)({expression});")
            lines.append(f"    r{rd} = {result};")
            lines.append(f"    flag_n = ({result} >> 31) & 1U;")
            lines.append(f"    flag_z = (uint32_t)({result} == 0U);")
            if carry_out is not None:
                lines.append(f"    flag_c = UINT32_C({carry_out});")
        elif instruction[0] in ("tst_imm", "teq_imm"):
            _, rn, immediate, carry_out = instruction
            suffix = f"{len(lines)}"
            result = f"logical_imm_test_{suffix}"
            operator = "&" if instruction[0] == "tst_imm" else "^"
            lines.append(f"    uint32_t {result} = (uint32_t)(r{rn} {operator} UINT32_C({immediate}));")
            lines.append(f"    flag_n = ({result} >> 31) & 1U;")
            lines.append(f"    flag_z = (uint32_t)({result} == 0U);")
            if carry_out is not None:
                lines.append(f"    flag_c = UINT32_C({carry_out});")
        elif instruction[0] == "add":
            _, rd, rn, immediate = instruction
            lines.append(f"    r{rd} = (uint32_t)(r{rn} + UINT32_C({immediate}));")
        elif instruction[0] == "sub":
            _, rd, rn, immediate = instruction
            lines.append(f"    r{rd} = (uint32_t)(r{rn} - UINT32_C({immediate}));")
        elif instruction[0] in ("add_reg", "sub_reg"):
            _, rd, rn, rm = instruction
            operator = "+" if instruction[0] == "add_reg" else "-"
            rm_expression = shifted_operand_expr or f"r{rm}"
            expression = f"r{rn} {operator} ({rm_expression})" if shifted_operand_expr else f"r{rn} {operator} r{rm}"
            lines.append(f"    r{rd} = (uint32_t)({expression});")
        elif instruction[0] in ("adc", "sbc", "rsc", "adc_reg", "sbc_reg", "rsc_reg"):
            register_operand = str(instruction[0]).endswith("_reg")
            operation_name = str(instruction[0]).removesuffix("_reg")
            if register_operand:
                _, rd, rn, rm = instruction
                rhs_expr = shifted_operand_expr or f"r{rm}"
            else:
                _, rd, rn, immediate = instruction
                rhs_expr = f"UINT32_C({immediate})"
            carry_in = f"flag_c"
            if operation_name == "adc":
                expression = f"(uint64_t)r{rn} + (uint64_t)({rhs_expr}) + (uint64_t){carry_in}"
            elif operation_name == "sbc":
                expression = f"(uint64_t)r{rn} - ((uint64_t)({rhs_expr}) + (uint64_t)(1U - {carry_in}))"
            else:
                expression = f"(uint64_t)({rhs_expr}) - ((uint64_t)r{rn} + (uint64_t)(1U - {carry_in}))"
            lines.append(f"    r{rd} = (uint32_t)({expression});")
        elif instruction[0] in ("adds", "subs", "cmn", "cmp", "adcs", "sbcs", "rscs", "adds_reg", "subs_reg", "cmn_reg", "cmp_reg", "adcs_reg", "sbcs_reg", "rscs_reg"):
            operation = str(instruction[0]).removesuffix("_reg")
            register_operand = str(instruction[0]).endswith("_reg")
            if operation in ("cmn", "cmp"):
                if register_operand:
                    _, rn, rm = instruction
                    rhs_expression = shifted_operand_expr or f"r{rm}"
                else:
                    _, rn, immediate = instruction
                    rhs_expression = f"UINT32_C({immediate})"
                rd = None
            else:
                if register_operand:
                    _, rd, rn, rm = instruction
                    rhs_expression = shifted_operand_expr or f"r{rm}"
                else:
                    _, rd, rn, immediate = instruction
                    rhs_expression = f"UINT32_C({immediate})"

            # RSC reverses the subtraction operands: Operand2 - Rn - (1-C).
            lhs_expression = f"r{rn}"
            rhs_expr = rhs_expression
            if operation == "rscs":
                lhs_expression, rhs_expr = rhs_expr, lhs_expression

            suffix = f"{len(lines)}"
            lhs = f"flag_lhs_{suffix}"
            result = f"flag_result_{suffix}"
            rhs = f"flag_rhs_{suffix}"
            lines.append(f"    uint32_t {lhs} = (uint32_t)({lhs_expression});")
            lines.append(f"    uint32_t {rhs} = (uint32_t)({rhs_expr});")
            if operation in ("adds", "cmn", "adcs"):
                carry_in = f"flag_carry_in_{suffix}"
                if operation == "adcs":
                    lines.append(f"    uint32_t {carry_in} = flag_c;")
                else:
                    lines.append(f"    uint32_t {carry_in} = UINT32_C(0);")
                wide = f"flag_wide_{suffix}"
                lines.append(f"    uint64_t {wide} = (uint64_t){lhs} + (uint64_t){rhs} + (uint64_t){carry_in};")
                lines.append(f"    uint32_t {result} = (uint32_t){wide};")
                lines.append(f"    flag_c = (uint32_t)(({wide} >> 32) & UINT64_C(1));")
                lines.append(f"    flag_v = (uint32_t)((~({lhs} ^ {rhs}) & ({lhs} ^ {result}) & UINT32_C(0x80000000)) != 0U);")
            else:
                if operation in ("sbcs", "rscs"):
                    carry_in = f"flag_carry_in_{suffix}"
                    lines.append(f"    uint32_t {carry_in} = flag_c;")
                    subtrahend = f"flag_subtrahend_{suffix}"
                    lines.append(f"    uint64_t {subtrahend} = (uint64_t){rhs} + (uint64_t)(1U - {carry_in});")
                    lines.append(f"    uint32_t {result} = (uint32_t)((uint64_t){lhs} - {subtrahend});")
                    lines.append(f"    flag_c = (uint32_t)((uint64_t){lhs} >= {subtrahend});")
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
    if runtime_memory_io:
        lines.extend((
            f"    if (execution_steps >= UINT32_C({max_execution_steps})) goto arm_budget_exhausted;",
            "    execution_steps++;",
            "    goto arm_exit;",
            "arm_budget_exhausted: ;",
            "    execution_status = UINT8_C(1);",
            "    goto arm_exit;",
            "arm_exit: ;",
            "    if (steps_executed_out != 0) *steps_executed_out = execution_steps;",
            "    if (execution_status_out != 0) *execution_status_out = execution_status;",
        ))
    elif bounded:
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
