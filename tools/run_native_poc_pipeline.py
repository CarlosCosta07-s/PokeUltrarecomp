#!/usr/bin/env python3
"""End-to-end native-code smoke test for the synthetic A32 and Thumb translators.

This tool only feeds synthetic instructions to the project's own narrow
translators, compiles generated C with a host C compiler, and executes the
resulting native binaries. It never reads game files, interprets ARM/Thumb at
runtime, or uses an emulator as a test oracle.
"""
from __future__ import annotations

import argparse
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Sequence

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import arm_subset_poc  # noqa: E402
import thumb_subset_poc  # noqa: E402


ARM_WORDS = (
    0xE3A0000C,  # MOV r0, #12
    0xE2400008,  # SUB r0, r0, #8
    0xE2800003,  # ADD r0, r0, #3
    0xE2000007,  # AND r0, r0, #7
    0xE3800008,  # ORR r0, r0, #8
    0xE2200001,  # EOR r0, r0, #1
    0xE3C00002,  # BIC r0, r0, #2
    0xE3E01000,  # MVN r1, #0
    0xE201000C,  # AND r0, r1, #12
    0xE12FFF1E,  # BX lr
)
THUMB_HALFWORDS = (0x200C, 0x3808, 0x3003, 0x2807, 0x4770)
MEMORY_HALFWORDS = (
    0x5042,  # STR r2, [r0, r1]
    0x5843,  # LDR r3, [r0, r1]
    0x8102,  # STRH r2, [r0, #8]
    0x8904,  # LDRH r4, [r0, #8]
    0x7282,  # STRB r2, [r0, #10]
    0x5645,  # LDRSB r5, [r0, r1]
    0x7A86,  # LDRB r6, [r0, #10]
    0x4770,  # BX lr
)


class PipelineError(RuntimeError):
    """A native pipeline step did not meet its acceptance condition."""


def _compiler_command(requested: str | None) -> tuple[list[str], bool]:
    """Find a C compiler and report whether it uses MSVC command-line flags."""
    raw = requested or os.environ.get("CC", "").strip()
    candidates: list[list[str]] = []
    if raw:
        # CMake may pass an absolute compiler path containing spaces as a single
        # argument. Prefer that exact file before splitting shell-style commands
        # such as "ccache gcc".
        path_candidate = raw.strip().strip('"')
        if Path(path_candidate).is_file():
            parsed = [path_candidate]
        else:
            parsed = [token.strip('"') for token in shlex.split(raw, posix=(os.name != "nt"))]
        if not parsed:
            raise PipelineError("CC/--cc was provided but contains no compiler command")
        candidates.append(parsed)
    else:
        defaults = ("cl", "clang-cl", "cc", "gcc", "clang") if os.name == "nt" else ("cc", "gcc", "clang")
        candidates.extend([[name] for name in defaults])

    for command in candidates:
        resolved = shutil.which(command[0])
        if resolved is None and Path(command[0]).is_file():
            resolved = str(Path(command[0]).resolve())
        if resolved is None:
            if raw:
                raise PipelineError(
                    f"compiler {command[0]!r} was not found on PATH; initialize the compiler environment "
                    "or set CC/--cc to a valid command"
                )
            continue
        command[0] = resolved
        name = Path(resolved).name.lower()
        is_msvc = name in {"cl", "cl.exe", "clang-cl", "clang-cl.exe"}
        return command, is_msvc

    raise PipelineError(
        "no supported C compiler found; install GCC/Clang or initialize the MSVC developer environment "
        "and set CC=cl"
    )


def _compile_and_run(
    compiler: Sequence[str],
    is_msvc: bool,
    case_name: str,
    generated_c: str,
    harness_c: str,
    work_dir: Path,
) -> None:
    source_path = work_dir / f"{case_name}.c"
    executable_path = work_dir / (f"{case_name}.exe" if os.name == "nt" else case_name)
    source_path.write_text(generated_c + "\n" + harness_c, encoding="utf-8", newline="\n")

    if is_msvc:
        compile_command = [
            *compiler,
            "/nologo",
            "/std:c11",
            "/W4",
            "/WX",
            f"/Fe{executable_path.name}",
            source_path.name,
        ]
    else:
        compile_command = [
            *compiler,
            "-std=c11",
            "-Wall",
            "-Wextra",
            "-Werror",
            "-o",
            str(executable_path),
            str(source_path),
        ]

    try:
        compiled = subprocess.run(
            compile_command,
            cwd=work_dir,
            capture_output=True,
            text=True,
            timeout=90,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise PipelineError(f"{case_name}: C compilation exceeded 90 seconds") from exc

    if compiled.returncode != 0:
        raise PipelineError(
            f"{case_name}: native C compilation failed (exit {compiled.returncode})\n"
            f"command: {compile_command!r}\n{compiled.stdout}{compiled.stderr}"
        )
    if not executable_path.is_file():
        raise PipelineError(f"{case_name}: compiler succeeded but did not produce {executable_path.name}")

    try:
        executed = subprocess.run(
            [str(executable_path)],
            cwd=work_dir,
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise PipelineError(f"{case_name}: native executable exceeded 15 seconds") from exc

    if executed.returncode != 0:
        raise PipelineError(
            f"{case_name}: native executable returned {executed.returncode}\n"
            f"stdout: {executed.stdout}\nstderr: {executed.stderr}"
        )


def _assert_fail_closed() -> None:
    """Guarantee that this pipeline has no interpreter/fallback for unsupported input."""
    try:
        arm_subset_poc.translate([0xE3A04003, 0xE12FFF1E])  # MOV r4,#3 is outside the POC subset.
    except arm_subset_poc.UnsupportedInstruction:
        pass
    else:
        raise PipelineError("A32 negative case was accepted; unsupported register r4 must be rejected")

    try:
        thumb_subset_poc.translate([0x6000, 0x4770])  # STR immediate is inspected but not translated.
    except thumb_subset_poc.UnsupportedThumbInstruction:
        pass
    else:
        raise PipelineError("Thumb negative case was accepted; memory access must be rejected without a model")


def _a32_source() -> str:
    generated = arm_subset_poc.translate(
        list(ARM_WORDS),
        max_execution_steps=len(ARM_WORDS),
        initial_nzcv=0xB,
        runtime_state_io=True,
    )
    old_signature = "uint32_t synthetic_entry_bounded("
    if old_signature not in generated:
        raise PipelineError("A32 translator output no longer matches its documented bounded runtime interface")
    return generated.replace(old_signature, "uint32_t native_a32_smoke(", 1)


def _thumb_source() -> str:
    generated = thumb_subset_poc.translate(
        list(THUMB_HALFWORDS),
        max_execution_steps=len(THUMB_HALFWORDS),
        initial_nzcv=0x9,
        runtime_state_io=True,
    )
    old_signature = "uint32_t thumb_entry_bounded("
    if old_signature not in generated:
        raise PipelineError("Thumb translator output no longer matches its documented bounded runtime interface")
    return generated.replace(old_signature, "uint32_t native_thumb_smoke(", 1)


def _thumb_memory_source() -> str:
    generated = thumb_subset_poc.translate(
        list(MEMORY_HALFWORDS),
        max_execution_steps=len(MEMORY_HALFWORDS),
        runtime_state_io=True,
        runtime_memory_io=True,
    )
    old_signature = "uint32_t thumb_entry_memory_bounded("
    if old_signature not in generated:
        raise PipelineError("Thumb memory translator output does not match its bounded memory interface")
    return generated.replace(old_signature, "uint32_t native_thumb_memory_smoke(", 1)


A32_HARNESS = r"""
int main(void) {
    const uint32_t input[4] = {
        UINT32_C(37), UINT32_C(0x12345678), UINT32_C(0x80000000), UINT32_C(0xDEADBEEF)
    };
    uint32_t output[4] = {0U, 0U, 0U, 0U};
    uint8_t flags = UINT8_C(0xFF), status = UINT8_C(0xFF);
    uint32_t steps = 0U;
    const uint32_t result = native_a32_smoke(
        input, UINT8_C(0xB), &flags, &steps, &status, output
    );
    if (result != UINT32_C(12)) return 1;
    if (flags != UINT8_C(0xB) || status != UINT8_C(0)) return 2;
    if (steps != UINT32_C(10)) return 3;
    if (output[0] != UINT32_C(12) || output[1] != UINT32_MAX) return 4;
    if (output[2] != input[2] || output[3] != input[3]) return 5;
    if (input[0] != UINT32_C(37) || input[1] != UINT32_C(0x12345678)) return 6;
    return 0;
}
"""

THUMB_HARNESS = r"""
int main(void) {
    const uint32_t input[8] = {
        UINT32_C(99), UINT32_C(0x12345678), UINT32_C(0x80000000), UINT32_C(0xDEADBEEF),
        UINT32_C(4), UINT32_C(5), UINT32_C(6), UINT32_C(7)
    };
    uint32_t output[8] = {0U, 0U, 0U, 0U, 0U, 0U, 0U, 0U};
    uint8_t flags = UINT8_C(0xFF), status = UINT8_C(0xFF);
    uint32_t steps = 0U;
    const uint32_t result = native_thumb_smoke(
        input, UINT8_C(0x9), &flags, &steps, &status, output
    );
    if (result != UINT32_C(7)) return 1;
    if (flags != UINT8_C(6) || status != UINT8_C(0)) return 2;
    if (steps != UINT32_C(5)) return 3;
    if (output[0] != UINT32_C(7)) return 4;
    for (unsigned int index = 1U; index < 8U; ++index) {
        if (output[index] != input[index]) return 5;
    }
    return 0;
}
"""

MEMORY_HARNESS = r"""
#include <string.h>
int main(void) {
    const uint32_t input[8] = {
        UINT32_C(0x1000), UINT32_C(4), UINT32_C(0xA1B2C380), UINT32_C(0xAAAAAAAA),
        UINT32_C(0xAAAAAAAA), UINT32_C(0xAAAAAAAA), UINT32_C(0xAAAAAAAA), UINT32_C(0xAAAAAAAA)
    };
    uint32_t registers_out[8] = {0U, 0U, 0U, 0U, 0U, 0U, 0U, 0U};
    uint8_t memory[16];
    for (unsigned int i = 0U; i < sizeof(memory); ++i) memory[i] = UINT8_C(0xEE);
    uint8_t nzcv = UINT8_C(0xAA), status = UINT8_C(0xAA);
    uint32_t steps = 0U;
    const uint32_t returned = native_thumb_memory_smoke(
        input, UINT8_C(0x9), &nzcv, &steps, &status, registers_out,
        memory, UINT32_C(0x1000), UINT32_C(16)
    );
    if (returned != UINT32_C(0x1000) || status != UINT8_C(0) || steps != UINT32_C(8) || nzcv != UINT8_C(0x9)) return 1;
    if (registers_out[0] != UINT32_C(0x1000) || registers_out[1] != UINT32_C(4)
        || registers_out[2] != UINT32_C(0xA1B2C380) || registers_out[3] != UINT32_C(0xA1B2C380)
        || registers_out[4] != UINT32_C(0xC380) || registers_out[5] != UINT32_C(0xFFFFFF80)
        || registers_out[6] != UINT32_C(0x80) || registers_out[7] != UINT32_C(0xAAAAAAAA)) return 2;
    if (memory[4] != UINT8_C(0x80) || memory[5] != UINT8_C(0xC3)
        || memory[6] != UINT8_C(0xB2) || memory[7] != UINT8_C(0xA1)
        || memory[8] != UINT8_C(0x80) || memory[9] != UINT8_C(0xC3)
        || memory[10] != UINT8_C(0x80) || memory[11] != UINT8_C(0xEE)) return 3;

    uint8_t before[sizeof(memory)];
    memcpy(before, memory, sizeof(memory));
    const uint32_t out_of_range[8] = {
        UINT32_C(0x100C), UINT32_C(4), UINT32_C(0x11223344), 0U, 0U, 0U, 0U, 0U
    };
    for (unsigned int i = 0U; i < 8U; ++i) registers_out[i] = UINT32_C(0xAAAAAAAA);
    nzcv = UINT8_C(0xAA); status = UINT8_C(0xAA); steps = 99U;
    (void)native_thumb_memory_smoke(
        out_of_range, UINT8_C(0x6), &nzcv, &steps, &status, registers_out,
        memory, UINT32_C(0x1000), UINT32_C(16)
    );
    if (status != UINT8_C(3) || steps != UINT32_C(1) || nzcv != UINT8_C(0x6)) return 4;
    if (memcmp(before, memory, sizeof(memory)) != 0) return 5;

    const uint32_t misaligned[8] = {
        UINT32_C(0x1002), 0U, UINT32_C(0x11223344), 0U, 0U, 0U, 0U, 0U
    };
    nzcv = UINT8_C(0xAA); status = UINT8_C(0xAA); steps = 99U;
    (void)native_thumb_memory_smoke(
        misaligned, UINT8_C(0x6), &nzcv, &steps, &status, registers_out,
        memory, UINT32_C(0x1000), UINT32_C(16)
    );
    if (status != UINT8_C(4) || steps != UINT32_C(1)) return 6;
    if (memcmp(before, memory, sizeof(memory)) != 0) return 7;

    nzcv = UINT8_C(0xAA); status = UINT8_C(0xAA); steps = 99U;
    (void)native_thumb_memory_smoke(
        input, UINT8_C(0x9), &nzcv, &steps, &status, registers_out,
        0, UINT32_C(0x1000), UINT32_C(16)
    );
    if (status != UINT8_C(2) || steps != 0U || nzcv != UINT8_C(0xAA)) return 8;

    nzcv = UINT8_C(0xAA); status = UINT8_C(0xAA); steps = 99U;
    (void)native_thumb_memory_smoke(
        input, UINT8_C(0x9), &nzcv, &steps, &status, registers_out,
        memory, UINT32_C(0xFFFFFFF8), UINT32_C(16)
    );
    if (status != UINT8_C(2) || steps != 0U || nzcv != UINT8_C(0xAA)) return 9;
    return 0;
}


def run_pipeline(compiler_override: str | None = None) -> int:
    _assert_fail_closed()
    compiler, is_msvc = _compiler_command(compiler_override)
    print(f"Native compiler: {' '.join(compiler)} ({'MSVC-compatible' if is_msvc else 'GCC/Clang-compatible'})")
    print(f"Host: {sys.platform} / {os.name}")
    with tempfile.TemporaryDirectory(prefix="pokeultrarecomp-native-") as temporary:
        work_dir = Path(temporary)
        _compile_and_run(compiler, is_msvc, "native_a32_smoke", _a32_source(), A32_HARNESS, work_dir)
        print("PASS: synthetic ARM A32 -> C -> native executable (registers, NZCV, step budget)")
        _compile_and_run(compiler, is_msvc, "native_thumb_smoke", _thumb_source(), THUMB_HARNESS, work_dir)
        print("PASS: synthetic Thumb-16 -> C -> native executable (registers, NZCV, step budget)")
        _compile_and_run(compiler, is_msvc, "native_thumb_memory_smoke", _thumb_memory_source(), MEMORY_HARNESS, work_dir)
        print("PASS: native Thumb load/store widths, sign extension, bounds, alignment, and faults")
    print("PASS: unsupported A32/Thumb instructions fail closed; no interpreter or emulator is used")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Compile and execute synthetic ARM/Thumb-to-C fixtures as native host binaries."
    )
    parser.add_argument(
        "--cc",
        default=None,
        help="C compiler command (defaults to CC, then a supported compiler on PATH)",
    )
    args = parser.parse_args(argv)
    try:
        return run_pipeline(args.cc)
    except (OSError, PipelineError, arm_subset_poc.UnsupportedInstruction,
            thumb_subset_poc.UnsupportedThumbInstruction) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
