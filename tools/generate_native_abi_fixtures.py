#!/usr/bin/env python3
"""Generate synthetic ARM/Thumb C fixtures with a stable C ABI adapter.

This is build-time code generation only. It does not read game assets or produce
an interpreter, JIT, emulator, or fallback path for unsupported instructions.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import arm_subset_poc  # noqa: E402
import thumb_subset_poc  # noqa: E402

A32_WORDS = (
    0xE3A0000C, 0xE2400008, 0xE2800003, 0xE2000007, 0xE3800008,
    0xE2200001, 0xE3C00002, 0xE3E01000, 0xE201000C, 0xE12FFF1E,
)
THUMB_HALFWORDS = (0x200C, 0x3808, 0x3003, 0x2807, 0x4770)
THUMB_MEMORY_HALFWORDS = (
    0x5042, 0x5843, 0x5242, 0x5A44, 0x5442, 0x5645, 0x5C46, 0x5E47,
    0x60C2, 0x68C3, 0x7402, 0x7C06, 0x8242, 0x8A44, 0x4770,
)
THUMB_MULTIPLE_MEMORY_HALFWORDS = (0xC006, 0xCB30, 0x4770)
THUMB_LDMIA_BASE_LIST_HALFWORDS = (0xC801, 0x4770)
THUMB_LITERAL_MEMORY_HALFWORDS = (0x2000, 0x4901, 0x4770)

A32_ADAPTER = r"""
#include <stddef.h>
#include <stdint.h>
#include "pokeultrarecomp/native_abi.h"

int poke_native_execute_a32(const PokeNativeCall *call, PokeNativeResult *result)
{
    uint32_t registers_out[4] = {0U, 0U, 0U, 0U};
    uint8_t nzcv_out = UINT8_C(0xAA);
    uint8_t execution_status = UINT8_C(0xAA);
    uint32_t steps_executed = 0U;
    PokeNativeResult completed = {0};

    if (call == NULL || result == NULL) {
        return POKE_NATIVE_ABI_INVALID_ARGUMENT;
    }
    if (call->abi_version != POKE_NATIVE_ABI_VERSION) {
        return POKE_NATIVE_ABI_VERSION_MISMATCH;
    }
    if (call->initial_nzcv > UINT8_C(15)) {
        return POKE_NATIVE_ABI_INVALID_ARGUMENT;
    }

    const uint32_t return_value = poke_a32_generated_entry(
        call->registers, call->initial_nzcv, &nzcv_out, &steps_executed,
        &execution_status, registers_out
    );
    if (execution_status != UINT8_C(0)) {
        return POKE_NATIVE_ABI_EXECUTION_FAILED;
    }

    completed.abi_version = POKE_NATIVE_ABI_VERSION;
    for (unsigned int index = 0U; index < POKE_NATIVE_REGISTER_COUNT; ++index) {
        completed.registers[index] = call->registers[index];
    }
    for (unsigned int index = 0U; index < 4U; ++index) {
        completed.registers[index] = registers_out[index];
    }
    completed.return_value = return_value;
    completed.steps_executed = steps_executed;
    completed.nzcv = nzcv_out;
    completed.execution_status = execution_status;
    *result = completed;
    return POKE_NATIVE_ABI_OK;
}
"""

THUMB_ADAPTER = r"""
#include <stddef.h>
#include <stdint.h>
#include "pokeultrarecomp/native_abi.h"

int poke_native_execute_thumb(const PokeNativeCall *call, PokeNativeResult *result)
{
    uint32_t registers_out[POKE_NATIVE_REGISTER_COUNT] = {0U};
    uint8_t nzcv_out = UINT8_C(0xAA);
    uint8_t execution_status = UINT8_C(0xAA);
    uint32_t steps_executed = 0U;
    PokeNativeResult completed = {0};

    if (call == NULL || result == NULL) {
        return POKE_NATIVE_ABI_INVALID_ARGUMENT;
    }
    if (call->abi_version != POKE_NATIVE_ABI_VERSION) {
        return POKE_NATIVE_ABI_VERSION_MISMATCH;
    }
    if (call->initial_nzcv > UINT8_C(15)) {
        return POKE_NATIVE_ABI_INVALID_ARGUMENT;
    }

    const uint32_t return_value = poke_thumb_generated_entry(
        call->registers, call->initial_nzcv, &nzcv_out, &steps_executed,
        &execution_status, registers_out
    );
    if (execution_status != UINT8_C(0)) {
        return POKE_NATIVE_ABI_EXECUTION_FAILED;
    }

    completed.abi_version = POKE_NATIVE_ABI_VERSION;
    for (unsigned int index = 0U; index < POKE_NATIVE_REGISTER_COUNT; ++index) {
        completed.registers[index] = registers_out[index];
    }
    completed.return_value = return_value;
    completed.steps_executed = steps_executed;
    completed.nzcv = nzcv_out;
    completed.execution_status = execution_status;
    *result = completed;
    return POKE_NATIVE_ABI_OK;
}
"""


def generate_a32() -> str:
    source = arm_subset_poc.translate(
        list(A32_WORDS),
        initial_nzcv=0,
        max_execution_steps=len(A32_WORDS),
        runtime_state_io=True,
    )
    old_signature = "uint32_t synthetic_entry_bounded("
    if old_signature not in source:
        raise RuntimeError("A32 generated function signature changed; update the ABI adapter deliberately")
    source = source.replace(old_signature, "uint32_t poke_a32_generated_entry(", 1)
    return source + "\n" + A32_ADAPTER


def generate_thumb() -> str:
    source = thumb_subset_poc.translate(
        list(THUMB_HALFWORDS),
        initial_nzcv=0,
        max_execution_steps=len(THUMB_HALFWORDS),
        runtime_state_io=True,
    )
    old_signature = "uint32_t thumb_entry_bounded("
    if old_signature not in source:
        raise RuntimeError("Thumb generated function signature changed; update the ABI adapter deliberately")
    source = source.replace(old_signature, "uint32_t poke_thumb_generated_entry(", 1)
    return source + "\n" + THUMB_ADAPTER


THUMB_MEMORY_ADAPTER = r"""
#include <stddef.h>
#include <stdint.h>
#include "pokeultrarecomp/native_abi.h"

typedef uint32_t (*PokeNativeMemoryEntry)(
    const uint32_t *registers_in,
    uint8_t initial_nzcv,
    uint8_t *nzcv_out,
    uint32_t *steps_executed_out,
    uint8_t *execution_status_out,
    uint32_t *registers_out,
    uint8_t *memory_bytes,
    uint32_t guest_memory_base,
    uint32_t guest_memory_size,
    uint32_t guest_entry_address
);

static int poke_native_execute_thumb_memory_with_entry(
    const PokeNativeCall *call,
    const PokeNativeMemory *memory,
    PokeNativeResult *result,
    PokeNativeMemoryEntry entry
)
{
    uint32_t registers_out[POKE_NATIVE_REGISTER_COUNT] = {0U};
    uint8_t nzcv_out = UINT8_C(0xAA);
    uint8_t execution_status = UINT8_C(0xAA);
    uint32_t steps_executed = 0U;
    PokeNativeResult completed = {0};

    if (call == NULL || memory == NULL || result == NULL || memory->bytes == NULL) {
        return POKE_NATIVE_ABI_INVALID_ARGUMENT;
    }
    if (call->abi_version != POKE_NATIVE_ABI_VERSION
        || memory->abi_version != POKE_NATIVE_ABI_VERSION) {
        return POKE_NATIVE_ABI_VERSION_MISMATCH;
    }
    if (call->initial_nzcv > UINT8_C(15) || entry == NULL) {
        return POKE_NATIVE_ABI_INVALID_ARGUMENT;
    }

    const uint32_t return_value = entry(
        call->registers, call->initial_nzcv, &nzcv_out, &steps_executed,
        &execution_status, registers_out, memory->bytes,
        memory->guest_base, memory->size, call->entry_address
    );

    completed.abi_version = POKE_NATIVE_ABI_VERSION;
    for (unsigned int index = 0U; index < POKE_NATIVE_REGISTER_COUNT; ++index) {
        completed.registers[index] = registers_out[index];
    }
    completed.return_value = return_value;
    completed.steps_executed = steps_executed;
    completed.nzcv = nzcv_out;
    completed.execution_status = execution_status;
    *result = completed;
    return POKE_NATIVE_ABI_OK;
}

int poke_native_execute_thumb_memory(
    const PokeNativeCall *call,
    const PokeNativeMemory *memory,
    PokeNativeResult *result
)
{
    return poke_native_execute_thumb_memory_with_entry(
        call, memory, result, poke_thumb_memory_generated_entry
    );
}

int poke_native_execute_thumb_multiple_memory(
    const PokeNativeCall *call,
    const PokeNativeMemory *memory,
    PokeNativeResult *result
)
{
    return poke_native_execute_thumb_memory_with_entry(
        call, memory, result, poke_thumb_multiple_memory_generated_entry
    );
}

int poke_native_execute_thumb_ldmia_base_list(
    const PokeNativeCall *call,
    const PokeNativeMemory *memory,
    PokeNativeResult *result
)
{
    return poke_native_execute_thumb_memory_with_entry(
        call, memory, result, poke_thumb_ldmia_base_list_generated_entry
    );
}

int poke_native_execute_thumb_literal_memory(
    const PokeNativeCall *call,
    const PokeNativeMemory *memory,
    PokeNativeResult *result
)
{
    return poke_native_execute_thumb_memory_with_entry(
        call, memory, result, poke_thumb_literal_memory_generated_entry
    );
}
"""


def _generate_memory_entry(halfwords: tuple[int, ...], symbol: str) -> str:
    source = thumb_subset_poc.translate(
        list(halfwords),
        initial_nzcv=0,
        max_execution_steps=len(halfwords),
        runtime_state_io=True,
        runtime_memory_io=True,
    )
    old_signature = "uint32_t thumb_entry_memory_bounded("
    if old_signature not in source:
        raise RuntimeError("Thumb memory signature changed; update the ABI adapter deliberately")
    return source.replace(old_signature, f"uint32_t {symbol}(", 1)


def generate_thumb_memory() -> str:
    sources = (
        _generate_memory_entry(THUMB_MEMORY_HALFWORDS, "poke_thumb_memory_generated_entry"),
        _generate_memory_entry(THUMB_MULTIPLE_MEMORY_HALFWORDS, "poke_thumb_multiple_memory_generated_entry"),
        _generate_memory_entry(THUMB_LDMIA_BASE_LIST_HALFWORDS, "poke_thumb_ldmia_base_list_generated_entry"),
        _generate_memory_entry(THUMB_LITERAL_MEMORY_HALFWORDS, "poke_thumb_literal_memory_generated_entry"),
        THUMB_MEMORY_ADAPTER,
    )
    return "\n".join(sources)
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        args.output_dir.mkdir(parents=True, exist_ok=True)
        outputs = {
            args.output_dir / "native_a32_generated.c": generate_a32(),
            args.output_dir / "native_thumb_generated.c": generate_thumb(),
            args.output_dir / "native_thumb_memory_generated.c": generate_thumb_memory(),
        }
        for path, source in outputs.items():
            path.write_text(source, encoding="utf-8", newline="\n")
            print(f"Generated synthetic native ABI fixture: {path.name}")
    except (OSError, RuntimeError, arm_subset_poc.UnsupportedInstruction,
            thumb_subset_poc.UnsupportedThumbInstruction) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
