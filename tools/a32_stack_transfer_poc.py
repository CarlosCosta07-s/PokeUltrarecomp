#!/usr/bin/env python3
"""Translate a deliberately small A32 stack-transfer subset to native C.

The stack-only entry translates STMDB SP!, {registers}, LDMIA SP!, {registers},
and a final exact BX LR terminator. A separate mixed proof also permits a tiny
AL-condition MOV/ADD/SUB-immediate subset on r0-r3, sharing the same r0-r14
state with stack transfers. Both emit fixed C and reject unsupported encodings;
the bounded memory region is synthetic, not the Nintendo 3DS map.
"""
from __future__ import annotations

import arm_subset_poc

MAX_INSTRUCTIONS = 256
REGISTER_COUNT = 15  # r0-r14; r15/PC is deliberately not part of this model.
STATUS_RETURNED = 0
STATUS_MEMORY_FAULT = 1
STATUS_INVALID_ARGUMENT = 2
STATUS_ALIGNMENT_FAULT = 3


class UnsupportedA32StackInstruction(ValueError):
    """The input is outside this explicitly bounded translator subset."""


def decode_word(word: int) -> tuple[object, ...]:
    """Decode supported AL-condition stack transfers, terminal LDMIA-to-PC, or BX LR."""
    if isinstance(word, bool) or not isinstance(word, int) or not 0 <= word <= 0xFFFFFFFF:
        raise UnsupportedA32StackInstruction(f"instruction word outside uint32: {word!r}")
    if word == 0xE12FFF1E:
        return ("return",)

    condition = (word >> 28) & 0xF
    if condition != 0xE:
        raise UnsupportedA32StackInstruction("only unconditional AL-condition stack transfers are supported")
    if ((word >> 25) & 0b111) != 0b100:
        raise UnsupportedA32StackInstruction(f"not an A32 multiple-transfer encoding: 0x{word:08X}")

    pre_index = (word >> 24) & 1
    increment = (word >> 23) & 1
    s_bit = (word >> 22) & 1
    writeback = (word >> 21) & 1
    load = (word >> 20) & 1
    base = (word >> 16) & 0xF
    register_mask = word & 0xFFFF

    if s_bit:
        raise UnsupportedA32StackInstruction("S-bit/user-bank multiple transfers are unsupported")
    if base != 13:
        raise UnsupportedA32StackInstruction("only SP (r13) may be the multiple-transfer base register")
    if not writeback:
        raise UnsupportedA32StackInstruction("stack multiple transfers must request SP write-back")

    # The initial model covers common full-descending pushes and empty-ascending
    # pops only. Other addressing modes need separate proof and tests.
    if (pre_index, increment, load) == (1, 0, 0):
        operation = "stmdb_sp"
    elif (pre_index, increment, load) == (0, 1, 1):
        operation = "ldmia_sp"
    else:
        raise UnsupportedA32StackInstruction("only STMDB SP! and LDMIA SP! are supported")

    if register_mask == 0:
        raise UnsupportedA32StackInstruction("multiple-transfer register list must not be empty")
    if register_mask & (1 << 13):
        raise UnsupportedA32StackInstruction("SP in a write-back register list is unsupported")

    pc_in_list = bool(register_mask & (1 << 15))
    if pc_in_list and operation != "ldmia_sp":
        raise UnsupportedA32StackInstruction("PC in a register list is unsupported except for terminal LDMIA SP! return epilogues")

    registers = tuple(index for index in range(REGISTER_COUNT) if register_mask & (1 << index))
    if pc_in_list:
        return ("ldmia_sp_pc", registers)
    return (operation, registers)


def _translate_sequence(
    words: list[int] | tuple[int, ...], *, allow_basic_alu: bool
) -> str:
    """Emit C11 for a fixed A32 sequence ending in the exact BX LR terminator.

    The default subset is stack-only. The mixed proof additionally permits the
    existing A32 decoder's non-flag-setting AL-condition MOV/ADD/SUB immediates
    on r0-r3, all operating on the same r0-r14 state as the stack transfers.
    Input/output arrays use r0-r14 (SP=r13, LR=r14). Memory faults are
    transactional per transfer. Supported operations preserve NZCV. BX LR is a
    fixture terminator, not a native jump to the guest LR address.
    """
    if not isinstance(words, (list, tuple)) or not words:
        raise UnsupportedA32StackInstruction("empty A32 stack-transfer sequence")
    if len(words) > MAX_INSTRUCTIONS:
        raise UnsupportedA32StackInstruction(f"sequence exceeds {MAX_INSTRUCTIONS} instructions")

    decoder = decode_mixed_word if allow_basic_alu else decode_word
    decoded = [decoder(word) for word in words]
    if any(item == ("return",) for item in decoded[:-1]):
        raise UnsupportedA32StackInstruction("instructions after BX LR are unsupported")
    if any(item[0] == "ldmia_sp_pc" for item in decoded[:-1]):
        raise UnsupportedA32StackInstruction("instructions after terminal LDMIA SP!, {..., PC} are unsupported")
    terminal_pc_return = decoded[-1][0] == "ldmia_sp_pc"
    if not terminal_pc_return and decoded[-1] != ("return",):
        raise UnsupportedA32StackInstruction(
            "sequence must end with exact BX LR or terminal LDMIA SP!, {..., PC}"
        )
    sequence_instructions = decoded if terminal_pc_return else decoded[:-1]
    entry_name = "a32_stack_transfer_entry_with_pc" if terminal_pc_return else "a32_stack_transfer_entry"

    lines = [
        "#include <stdint.h>",
        "#include <stddef.h>",
        ("/* Fixed-sequence A32 ALU/stack proof; not a game runtime. */"
         if allow_basic_alu else "/* Fixed-sequence A32 stack-transfer proof; not a game runtime. */"),
        f"uint32_t {entry_name}(",
        "    const uint32_t *registers_in, uint8_t initial_nzcv, uint8_t *nzcv_out,",
        "    uint8_t *memory_bytes, uint32_t memory_base, uint32_t memory_size,",
        "    uint32_t *registers_out"
        + (", uint32_t *guest_pc_out" if terminal_pc_return else "")
        + ", uint32_t *steps_executed_out, uint8_t *execution_status_out)",
        "{",
        "    uint32_t r[15] = { 0U };",
        "    uint32_t steps = 0U;",
        "    uint8_t status = UINT8_C(0);",
        "    if (registers_in == NULL || registers_out == NULL || "
        + ("guest_pc_out == NULL || " if terminal_pc_return else "")
        + "memory_bytes == NULL ||",
        "        memory_size == 0U || initial_nzcv > UINT8_C(15) ||",
        "        ((uint64_t)memory_base + (uint64_t)memory_size) > UINT64_C(0x100000000)) {",
        "        if (steps_executed_out != NULL) *steps_executed_out = 0U;",
        "        if (execution_status_out != NULL) *execution_status_out = UINT8_C(2);",
        "        if (nzcv_out != NULL && initial_nzcv <= UINT8_C(15)) *nzcv_out = initial_nzcv;",
        "        return 0U;",
        "    }",
        "    for (uint32_t i = 0U; i < UINT32_C(15); ++i) r[i] = registers_in[i];",
    ]
    if terminal_pc_return:
        lines.append("    *guest_pc_out = UINT32_C(0);")

    for index, instruction in enumerate(sequence_instructions):
        operation = instruction[0]
        if operation in ("mov", "add", "sub"):
            if operation == "mov":
                _, rd, immediate = instruction
                expression = f"UINT32_C(0x{immediate:08X})"
            else:
                _, rd, rn, immediate = instruction
                operator = "+" if operation == "add" else "-"
                expression = f"r[{rn}] {operator} UINT32_C(0x{immediate:08X})"
            lines.extend((
                f"    /* Guest instruction {index + 1}: AL {operation.upper()} immediate. */",
                "    steps++;",
                f"    r[{rd}] = {expression};",
            ))
            continue

        operation, registers = instruction
        if operation not in ("stmdb_sp", "ldmia_sp", "ldmia_sp_pc"):
            raise UnsupportedA32StackInstruction(
                f"instruction {index + 1} is outside the selected sequence subset: {operation!r}"
            )
        count = len(registers) + (1 if operation == "ldmia_sp_pc" else 0)
        transfer_bytes = count * 4
        lines.extend((
            f"    /* Guest instruction {index + 1}: {operation.upper()} SP!, fixed register list. */",
            "    steps++;",
            "    {",
            f"        const uint32_t transfer_bytes = UINT32_C({transfer_bytes});",
            "        const uint32_t old_sp = r[13];",
            "        const uint64_t region_end = (uint64_t)memory_base + (uint64_t)memory_size;",
        ))
        if operation == "stmdb_sp":
            lines.extend((
                "        if ((old_sp & UINT32_C(3)) != 0U) { status = UINT8_C(3); goto a32_stack_exit; }",
                "        if ((uint64_t)old_sp < (uint64_t)transfer_bytes) { status = UINT8_C(1); goto a32_stack_exit; }",
                "        const uint32_t new_sp = old_sp - transfer_bytes;",
                "        const uint64_t transfer_end = (uint64_t)new_sp + (uint64_t)transfer_bytes;",
                "        if ((uint64_t)new_sp < (uint64_t)memory_base || transfer_end > region_end || transfer_end > UINT64_C(0x100000000)) {",
                "            status = UINT8_C(1); goto a32_stack_exit;",
                "        }",
            ))
            for position, register in enumerate(registers):
                offset = position * 4
                value = f"store_value_{index}_{register}"
                lines.extend((
                    f"        const uint32_t {value} = r[{register}];",
                    f"        memory_bytes[(new_sp - memory_base) + UINT32_C({offset})] = (uint8_t)({value} & UINT32_C(0xFF));",
                    f"        memory_bytes[(new_sp - memory_base) + UINT32_C({offset + 1})] = (uint8_t)(({value} >> 8) & UINT32_C(0xFF));",
                    f"        memory_bytes[(new_sp - memory_base) + UINT32_C({offset + 2})] = (uint8_t)(({value} >> 16) & UINT32_C(0xFF));",
                    f"        memory_bytes[(new_sp - memory_base) + UINT32_C({offset + 3})] = (uint8_t)(({value} >> 24) & UINT32_C(0xFF));",
                ))
            lines.append("        r[13] = new_sp;")
        else:
            lines.extend((
                "        if ((old_sp & UINT32_C(3)) != 0U) { status = UINT8_C(3); goto a32_stack_exit; }",
                "        const uint64_t transfer_end = (uint64_t)old_sp + (uint64_t)transfer_bytes;",
                "        if ((uint64_t)old_sp < (uint64_t)memory_base || transfer_end > region_end || transfer_end > UINT64_C(0x100000000)) {",
                "            status = UINT8_C(1); goto a32_stack_exit;",
                "        }",
                "        uint32_t loaded[15] = { 0U };",
            ))
            for position, register in enumerate(registers):
                offset = position * 4
                loaded = f"loaded_{index}_{register}"
                lines.extend((
                    f"        const uint32_t {loaded} = (uint32_t)memory_bytes[(old_sp - memory_base) + UINT32_C({offset})] |",
                    f"            ((uint32_t)memory_bytes[(old_sp - memory_base) + UINT32_C({offset + 1})] << 8) |",
                    f"            ((uint32_t)memory_bytes[(old_sp - memory_base) + UINT32_C({offset + 2})] << 16) |",
                    f"            ((uint32_t)memory_bytes[(old_sp - memory_base) + UINT32_C({offset + 3})] << 24);",
                    f"        loaded[{register}] = {loaded};",
                ))
            for register in registers:
                lines.append(f"        r[{register}] = loaded[{register}];")
            if operation == "ldmia_sp_pc":
                offset = len(registers) * 4
                loaded_pc = f"loaded_pc_{index}"
                lines.extend((
                    f"        const uint32_t {loaded_pc} = (uint32_t)memory_bytes[(old_sp - memory_base) + UINT32_C({offset})] |",
                    f"            ((uint32_t)memory_bytes[(old_sp - memory_base) + UINT32_C({offset + 1})] << 8) |",
                    f"            ((uint32_t)memory_bytes[(old_sp - memory_base) + UINT32_C({offset + 2})] << 16) |",
                    f"            ((uint32_t)memory_bytes[(old_sp - memory_base) + UINT32_C({offset + 3})] << 24);",
                ))
            lines.append("        r[13] = (uint32_t)transfer_end;")
            if operation == "ldmia_sp_pc":
                lines.append(f"        *guest_pc_out = {loaded_pc};")
        lines.append("    }")

    if not terminal_pc_return:
        lines.append("    steps++; /* exact BX LR sequence terminator */")
    lines.extend((
        "a32_stack_exit:",
        "    for (uint32_t i = 0U; i < UINT32_C(15); ++i) registers_out[i] = r[i];",
        "    if (nzcv_out != NULL) *nzcv_out = initial_nzcv;",
        "    if (steps_executed_out != NULL) *steps_executed_out = steps;",
        "    if (execution_status_out != NULL) *execution_status_out = status;",
        "    return r[0];",
        "}",
        "",
    ))
    return "\n".join(lines)


def decode_mixed_word(word: int) -> tuple[object, ...]:
    """Decode stack operations plus a tiny AL MOV/ADD/SUB-immediate subset."""
    try:
        return decode_word(word)
    except UnsupportedA32StackInstruction:
        try:
            instruction = arm_subset_poc.decode_word(word)
        except arm_subset_poc.UnsupportedInstruction as exc:
            raise UnsupportedA32StackInstruction(str(exc)) from exc

    if instruction == ("return",):
        return instruction
    if not instruction or instruction[0] not in ("mov", "add", "sub"):
        raise UnsupportedA32StackInstruction(
            "mixed sequence only permits STMDB/LDMIA SP!, AL MOV/ADD/SUB immediates, and BX LR"
        )
    if instruction[0] == "mov":
        if len(instruction) != 3:
            raise UnsupportedA32StackInstruction("MOV must be an AL non-flag-setting immediate form")
        _, rd, immediate = instruction
        if not (0 <= rd <= 3 and 0 <= immediate <= 0xFFFFFFFF):
            raise UnsupportedA32StackInstruction("MOV operands are outside the mixed proof's r0-r3 subset")
    else:
        if len(instruction) != 4:
            raise UnsupportedA32StackInstruction("ADD/SUB must be AL non-flag-setting immediate forms")
        _, rd, rn, immediate = instruction
        if not (0 <= rd <= 3 and 0 <= rn <= 3 and 0 <= immediate <= 0xFFFFFFFF):
            raise UnsupportedA32StackInstruction("ADD/SUB operands are outside the mixed proof's r0-r3 subset")
    return instruction


def translate_stack_sequence(words: list[int] | tuple[int, ...]) -> str:
    """Translate only the bounded stack-transfer subset and exact BX LR terminator."""
    return _translate_sequence(words, allow_basic_alu=False)


def translate_mixed_sequence(words: list[int] | tuple[int, ...]) -> str:
    """Translate stack transfers interleaved with AL MOV/ADD/SUB immediates.

    The data-processing operations and stack transfers use a single 15-register
    state. The mixed proof remains experimental and deliberately rejects all
    other A32 instructions.
    """
    return _translate_sequence(words, allow_basic_alu=True)
