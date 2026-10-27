#!/usr/bin/env python3
"""Compare generated ARM A32 C fixtures against the separate NZCV reference model.

This bounded experiment exercises synthetic immediates and plain register
Operand2 forms of ADDS, SUBS, CMN and CMP. It is not an emulator comparison.
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import arm_flags  # noqa: E402
import arm_subset_poc as translator  # noqa: E402

RETURN_WORD = 0xE12FFF1E


@dataclass(frozen=True, slots=True)
class DifferentialCase:
    name: str
    words: tuple[int, ...]
    initial_value: int
    expected_result: int
    expected_nzcv: int


def _initial_register_prefixes() -> tuple[tuple[str, int, tuple[int, ...]], ...]:
    """Provide short synthetic sequences for values around important boundaries."""
    return (
        ("zero", 0x00000000, (0xE3A00000,)),
        ("one", 0x00000001, (0xE3A00001,)),
        ("two", 0x00000002, (0xE3A00002,)),
        ("max-positive", 0x7FFFFFFF, (0xE3A00102, 0xE2400001)),
        ("max-positive-minus-one", 0x7FFFFFFE, (0xE3A00102, 0xE2400002)),
        ("sign-bit", 0x80000000, (0xE3A00102,)),
        ("minus-two", 0xFFFFFFFE, (0xE3E00001,)),
        ("minus-one", 0xFFFFFFFF, (0xE3E00000,)),
    )


# Encodings are literal fixtures: 1, 2 and a rotated immediate for 0x80000000.
_IMMEDIATES = (
    ("one", 0x00000001, 0x0001),
    ("two", 0x00000002, 0x0002),
    ("sign-bit", 0x80000000, 0x0102),
)


def build_cases() -> tuple[DifferentialCase, ...]:
    """Build an arithmetic matrix whose oracle is tools/arm_flags.py."""
    cases: list[DifferentialCase] = []
    operations = (
        ("adds", arm_flags.add_with_flags, 0xE2900000, True),
        ("subs", arm_flags.sub_with_flags, 0xE2500000, True),
        ("cmn", arm_flags.add_with_flags, 0xE3700000, False),
        ("cmp", arm_flags.sub_with_flags, 0xE3500000, False),
    )
    for lhs_name, lhs, prefix in _initial_register_prefixes():
        for immediate_name, rhs, encoded_immediate in _IMMEDIATES:
            for operation_name, reference, base_word, writes_result in operations:
                expected_arithmetic_result, expected_flags = reference(lhs, rhs)
                expected_result = expected_arithmetic_result if writes_result else lhs
                words = (*prefix, base_word | encoded_immediate, RETURN_WORD)
                cases.append(DifferentialCase(
                    name=f"{operation_name}-{lhs_name}-{immediate_name}",
                    words=words,
                    initial_value=lhs,
                    expected_result=expected_result,
                    expected_nzcv=expected_flags.nibble,
                ))
    register_operations = (
        ("adds-reg", arm_flags.add_with_flags, 0xE0900000, True),
        ("subs-reg", arm_flags.sub_with_flags, 0xE0500000, True),
        ("cmn-reg", arm_flags.add_with_flags, 0xE1700000, False),
        ("cmp-reg", arm_flags.sub_with_flags, 0xE1500000, False),
    )
    for lhs_name, lhs, prefix in _initial_register_prefixes():
        for immediate_name, rhs, encoded_immediate in _IMMEDIATES:
            mov_r1 = 0xE3A01000 | encoded_immediate
            for operation_name, reference, base_word, writes_result in register_operations:
                expected_arithmetic_result, expected_flags = reference(lhs, rhs)
                expected_result = expected_arithmetic_result if writes_result else lhs
                words = (*prefix, mov_r1, base_word | 1, RETURN_WORD)
                cases.append(DifferentialCase(
                    name=f"{operation_name}-{lhs_name}-{immediate_name}",
                    words=words,
                    initial_value=lhs,
                    expected_result=expected_result,
                    expected_nzcv=expected_flags.nibble,
                ))
    return tuple(cases)


def _find_compiler() -> str | None:
    candidates = (os.environ.get("CC", ""), "cc", "gcc", "clang")
    for candidate in candidates:
        if candidate:
            resolved = shutil.which(candidate)
            if resolved:
                return resolved
    return None


def _native_source(cases: tuple[DifferentialCase, ...]) -> str:
    function_sources: list[str] = ["#include <stdio.h>", "#include <stdint.h>", ""]
    main_lines = ["int main(void)", "{"]
    for index, case in enumerate(cases):
        function_name = f"synthetic_case_{index}"
        generated = translator.translate(list(case.words))
        if "uint32_t synthetic_entry(uint8_t *nzcv_out)" not in generated:
            raise RuntimeError(f"unexpected generated-C function signature for {case.name}")
        function_sources.append(generated.replace("synthetic_entry", function_name))
        main_lines.extend((
            "    {",
            "        uint8_t nzcv = UINT8_C(255);",
            f"        uint32_t result = {function_name}(&nzcv);",
            f'        printf("{index} %u %u\\n", (unsigned)result, (unsigned)nzcv);',
            "    }",
        ))
    main_lines.extend(("    return 0;", "}", ""))
    # No runtime success is asserted by the generated C itself; Python checks every row.
    return "\n".join(function_sources + main_lines)


def run_differential(compiler: str | None = None) -> tuple[str, int]:
    """Compile one native harness and compare all observed rows with the oracle."""
    selected_compiler = compiler or _find_compiler()
    if not selected_compiler:
        raise RuntimeError("no C compiler found (tried CC, cc, gcc, clang)")

    cases = build_cases()
    source = _native_source(cases)
    with tempfile.TemporaryDirectory(prefix="pokeultra-arm-diff-") as directory:
        root = Path(directory)
        source_path = root / "arm_differential.c"
        executable = root / ("arm_differential.exe" if os.name == "nt" else "arm_differential")
        source_path.write_text(source, encoding="utf-8", newline="\n")
        compiled = subprocess.run(
            [selected_compiler, str(source_path), "-std=c11", "-Wall", "-Wextra", "-Werror", "-o", str(executable)],
            capture_output=True, text=True, check=False,
        )
        if compiled.returncode:
            raise RuntimeError(
                "native C harness compilation failed:\n" + compiled.stdout + compiled.stderr
            )
        executed = subprocess.run([str(executable)], capture_output=True, text=True, check=False)
        if executed.returncode:
            raise RuntimeError(
                f"native C harness exited with {executed.returncode}:\n" + executed.stdout + executed.stderr
            )

    observed_rows: dict[int, tuple[int, int]] = {}
    try:
        for raw_line in executed.stdout.splitlines():
            parts = raw_line.split()
            if len(parts) != 3:
                raise ValueError(f"unexpected output row: {raw_line!r}")
            index, result, nzcv = (int(part, 10) for part in parts)
            if index in observed_rows:
                raise ValueError(f"duplicate output index: {index}")
            observed_rows[index] = (result, nzcv)
    except ValueError as exc:
        raise RuntimeError(f"could not parse native output: {exc}") from exc

    if len(observed_rows) != len(cases):
        raise RuntimeError(f"expected {len(cases)} native rows, received {len(observed_rows)}")

    failures: list[str] = []
    for index, case in enumerate(cases):
        observed_result, observed_nzcv = observed_rows[index]
        expected = (case.expected_result, case.expected_nzcv)
        observed = (observed_result, observed_nzcv)
        if observed != expected:
            failures.append(
                f"{case.name}: expected result=0x{expected[0]:08X}, NZCV=0x{expected[1]:X}; "
                f"observed result=0x{observed[0]:08X}, NZCV=0x{observed[1]:X}"
            )
    if failures:
        raise RuntimeError("differential mismatches:\n" + "\n".join(failures))
    return selected_compiler, len(cases)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cc", help="C compiler executable (defaults to CC, cc, gcc, then clang)")
    args = parser.parse_args(argv)
    try:
        compiler, count = run_differential(args.cc)
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    print(f"PASS: {count} synthetic immediate/register ADDS/SUBS/CMN/CMP native results and NZCV values matched tools/arm_flags.py.")
    print(f"Compiler: {compiler}; C11; -Wall -Wextra -Werror.")
    print("Scope: generated C vs the project's separate NZCV model; not an external emulator or game test.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
