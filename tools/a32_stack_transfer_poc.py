#!/usr/bin/env python3
"""Translate a deliberately small A32 stack-transfer subset to native C.

Supported guest operations are only STMDB SP!, {registers}, LDMIA SP!,
{registers}, and a final exact BX LR terminator. The translator emits C for
those fixed instructions; it does not interpret ARM words at runtime. The
bounded memory region is a synthetic test model, not the Nintendo 3DS map.
"""
from __future__ import annotations

MAX_INSTRUCTIONS = 256
REGISTER_COUNT = 15  # r0-r14; r15/PC is deliberately not part of this model.
STATUS_RETURNED = 0
STATUS_MEMORY_FAULT = 1
STATUS_INVALID_ARGUMENT = 2
STATUS_ALIGNMENT_FAULT = 3


class UnsupportedA32StackInstruction(ValueError):
    """The input is outside this explicitly bounded translator subset."""


def decode_word(word: int) -> tuple[object, ...]:
    """Decode exact AL-condition STMDB SP! / LDMIA SP! forms or BX LR."""
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
    if register_mask & (1 << 15):
        raise UnsupportedA32StackInstruction("PC in a register list is unsupported; control-flow return is not modeled")

    registers = tuple(index for index in range(REGISTER_COUNT) if register_mask & (1 << index))
    return (operation, registers)


def translate_stack_sequence(words: list[int] | tuple[int, ...]) -> str:
    """Emit C11 for a fixed sequence of supported stack transfers ending in BX LR.

    Input/output arrays use indices r0-r14 (so SP is r13 and LR is r14).
    Memory faults are transactional per transfer: a failing instruction leaves
    its registers, SP, and memory unchanged. Earlier completed instructions
    remain reflected in the returned state. NZCV is preserved by every supported
    instruction and copied to nzcv_out. BX LR is a sequence terminator here, not
    a model of a native branch to the guest LR address.
    """
    if not isinstance(words, (list, tuple)) or not words:
        raise UnsupportedA32StackInstruction("empty A32 stack-transfer sequence")
    if len(words) > MAX_INSTRUCTIONS:
        raise UnsupportedA32StackInstruction(f"sequence exceeds {MAX_INSTRUCTIONS} instructions")

    decoded = [decode_word(word) for word in words]
    if any(item == ("return",) for item in decoded[:-1]):
        raise UnsupportedA32StackInstruction("instructions after BX LR are unsupported")
    if decoded[-1] != ("return",):
        raise UnsupportedA32StackInstruction("sequence must end with exact BX LR")

    lines = [
        "#include <stdint.h>",
        "#include <stddef.h>",
        "/* Fixed-sequence A32 stack-transfer proof; not a game runtime. */",
        "uint32_t a32_stack_transfer_entry(",
        "    const uint32_t *registers_in, uint8_t initial_nzcv, uint8_t *nzcv_out,",
        "    uint8_t *memory_bytes, uint32_t memory_base, uint32_t memory_size,",
        "    uint32_t *registers_out, uint32_t *steps_executed_out, uint8_t *execution_status_out)",
        "{",
        "    uint32_t r[15] = { 0U };",
        "    uint32_t steps = 0U;",
        "    uint8_t status = UINT8_C(0);",
        "    if (registers_in == NULL || registers_out == NULL || memory_bytes == NULL ||",
        "        memory_size == 0U || initial_nzcv > UINT8_C(15) ||",
        "        ((uint64_t)memory_base + (uint64_t)memory_size) > UINT64_C(0x100000000)) {",
        "        if (steps_executed_out != NULL) *steps_executed_out = 0U;",
        "        if (execution_status_out != NULL) *execution_status_out = UINT8_C(2);",
        "        if (nzcv_out != NULL && initial_nzcv <= UINT8_C(15)) *nzcv_out = initial_nzcv;",
        "        return 0U;",
        "    }",
        "    for (uint32_t i = 0U; i < UINT32_C(15); ++i) r[i] = registers_in[i];",
    ]

    for index, instruction in enumerate(decoded[:-1]):
        operation, registers = instruction
        count = len(registers)
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
            lines.append("        r[13] = (uint32_t)transfer_end;")
        lines.append("    }")

    lines.extend((
        "    steps++; /* exact BX LR sequence terminator */",
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
