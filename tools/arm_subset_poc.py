#!/usr/bin/env python3
"""Clean-room proof of concept: translate a tiny synthetic ARM A32 subset to C.

This deliberately tiny demonstrator is not a general-purpose recompiler, does not
load game files, and supports a bounded immediate subset: MOV/ADD/SUB/AND/ORR/EOR/BIC/MVN,
flag-setting ADDS/SUBS, CMN/CMP, and BX LR. Logical S-bit forms remain unsupported.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

DEFAULT_WORDS = (0xE3A0000C, 0xE2400008, 0xE2800003, 0xE2000007, 0xE3800008, 0xE2200001, 0xE3C00002, 0xE3E01000, 0xE201000C, 0xE12FFF1E)
MAX_INSTRUCTIONS = 256


class UnsupportedInstruction(ValueError):
    """The input is outside this demonstrator's intentionally small subset."""


def ror32(value: int, amount: int) -> int:
    amount %= 32
    value &= 0xFFFFFFFF
    if amount == 0:
        return value
    return ((value >> amount) | (value << (32 - amount))) & 0xFFFFFFFF


def decode_word(word: int) -> tuple[object, ...]:
    """Decode one supported ARM A32 word into a small, explicit instruction tuple."""
    if not isinstance(word, int) or word < 0 or word > 0xFFFFFFFF:
        raise UnsupportedInstruction(f"instruction word outside uint32: {word!r}")

    # The only supported return/terminator is BX LR, with its exact encoding.
    if word == 0xE12FFF1E:
        return ("return",)

    condition = (word >> 28) & 0xF
    if condition != 0xE:
        raise UnsupportedInstruction(f"condition code is not AL in 0x{word:08X}")

    # Only ARM data-processing instructions with an immediate operand.
    if ((word >> 25) & 0b111) != 0b001:
        raise UnsupportedInstruction(f"not a supported immediate data-processing instruction: 0x{word:08X}")

    opcode = (word >> 21) & 0xF
    set_flags = (word >> 20) & 1
    rn = (word >> 16) & 0xF
    rd = (word >> 12) & 0xF
    rotate = ((word >> 8) & 0xF) * 2
    imm8 = word & 0xFF
    immediate = ror32(imm8, rotate)

    # This integration stage deliberately enables only flag-setting ADD/SUB and
    # canonical CMN. Logical S-bit forms require shifter-carry semantics and stay
    # unsupported until that behavior is modeled end-to-end.
    if set_flags and opcode not in (0b0100, 0b0010, 0b1011, 0b1010):
        raise UnsupportedInstruction(f"flag-setting form is unsupported: 0x{word:08X}")

    if opcode == 0b1011:  # CMN (immediate): arithmetic flags, no destination write
        if not set_flags:
            raise UnsupportedInstruction("CMN requires the S bit to be set")
        if rd != 0:
            raise UnsupportedInstruction("only canonical CMN encoding with Rd=0 is supported")
        if rn > 3:
            raise UnsupportedInstruction(f"source register r{rn} is outside r0-r3 subset")
        return ("cmn", rn, immediate)

    if opcode == 0b1010:  # CMP (immediate): subtract for flags, no destination write
        if not set_flags:
            raise UnsupportedInstruction("CMP requires the S bit to be set")
        if rd != 0:
            raise UnsupportedInstruction("only canonical CMP encoding with Rd=0 is supported")
        if rn > 3:
            raise UnsupportedInstruction(f"source register r{rn} is outside r0-r3 subset")
        return ("cmp", rn, immediate)

    # Restrict this POC to r0-r3 so the generated C and tests stay auditable.
    if rd > 3:
        raise UnsupportedInstruction(f"destination register r{rd} is outside r0-r3 subset")

    if opcode == 0b1101:  # MOV (immediate)
        if rn != 0:
            raise UnsupportedInstruction("only the canonical MOV immediate encoding with Rn=0 is supported")
        return ("mov", rd, immediate)

    if opcode == 0b1111:  # MVN (immediate)
        if rn != 0:
            raise UnsupportedInstruction("only the canonical MVN immediate encoding with Rn=0 is supported")
        return ("mvn", rd, immediate)

    if opcode == 0b0000:  # AND (immediate)
        if rn > 3:
            raise UnsupportedInstruction(f"source register r{rn} is outside r0-r3 subset")
        return ("and", rd, rn, immediate)

    if opcode == 0b1100:  # ORR (immediate)
        if rn > 3:
            raise UnsupportedInstruction(f"source register r{rn} is outside r0-r3 subset")
        return ("orr", rd, rn, immediate)

    if opcode == 0b0001:  # EOR (immediate)
        if rn > 3:
            raise UnsupportedInstruction(f"source register r{rn} is outside r0-r3 subset")
        return ("eor", rd, rn, immediate)

    if opcode == 0b1110:  # BIC (immediate)
        if rn > 3:
            raise UnsupportedInstruction(f"source register r{rn} is outside r0-r3 subset")
        return ("bic", rd, rn, immediate)

    if opcode == 0b0100:  # ADD (immediate)
        if rn > 3:
            raise UnsupportedInstruction(f"source register r{rn} is outside r0-r3 subset")
        return ("adds" if set_flags else "add", rd, rn, immediate)

    if opcode == 0b0010:  # SUB (immediate)
        if rn > 3:
            raise UnsupportedInstruction(f"source register r{rn} is outside r0-r3 subset")
        return ("subs" if set_flags else "sub", rd, rn, immediate)

    raise UnsupportedInstruction(f"unsupported data-processing opcode {opcode:04b} in 0x{word:08X}")


def translate(words: tuple[int, ...] | list[int]) -> str:
    """Translate a bounded instruction sequence to a standalone C function."""
    if not words:
        raise UnsupportedInstruction("empty instruction sequence")
    if len(words) > MAX_INSTRUCTIONS:
        raise UnsupportedInstruction(f"sequence exceeds {MAX_INSTRUCTIONS} instructions")

    decoded = [decode_word(word) for word in words]
    if decoded[-1] != ("return",):
        raise UnsupportedInstruction("sequence must end with BX LR")
    if any(instruction == ("return",) for instruction in decoded[:-1]):
        raise UnsupportedInstruction("instructions after BX LR are unsupported")

    used_registers = {0}  # r0 is the return register, even if not written.
    for instruction in decoded[:-1]:
        if instruction[0] in ("mov", "mvn"):
            used_registers.add(instruction[1])
        elif instruction[0] in ("and", "orr", "eor", "bic", "add", "sub", "adds", "subs"):
            used_registers.add(instruction[1])
            used_registers.add(instruction[2])
        elif instruction[0] in ("cmn", "cmp"):
            used_registers.add(instruction[1])

    lines = [
        "#include <stdint.h>",
        "",
        "/* Generated only from the synthetic instruction sequence supplied. */",
        "uint32_t synthetic_entry(uint8_t *nzcv_out)",
        "{",
        "    uint32_t flag_n = 0;",
        "    uint32_t flag_z = 0;",
        "    uint32_t flag_c = 0;",
        "    uint32_t flag_v = 0;",
    ]
    lines.extend(f"    uint32_t r{register} = 0;" for register in sorted(used_registers))
    for instruction in decoded[:-1]:
        if instruction[0] == "mov":
            _, rd, immediate = instruction
            lines.append(f"    r{rd} = UINT32_C({immediate});")
        elif instruction[0] == "mvn":
            _, rd, immediate = instruction
            lines.append(f"    r{rd} = (uint32_t)~UINT32_C({immediate});")
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
        elif instruction[0] in ("adds", "subs", "cmn", "cmp"):
            operation = instruction[0]
            if operation in ("cmn", "cmp"):
                _, rn, immediate = instruction
                rd = None
            else:
                _, rd, rn, immediate = instruction
            suffix = f"{len(lines)}"
            lhs = f"flag_lhs_{suffix}"
            result = f"flag_result_{suffix}"
            rhs = f"flag_rhs_{suffix}"
            lines.append(f"    uint32_t {lhs} = r{rn};")
            lines.append(f"    uint32_t {rhs} = UINT32_C({immediate});")
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
    lines.extend((
        "    if (nzcv_out != 0) {",
        "        *nzcv_out = (uint8_t)((flag_n << 3) | (flag_z << 2) | (flag_c << 1) | flag_v);",
        "    }",
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Translate a tiny, synthetic ARM A32 instruction subset into C; no game files are read."
    )
    parser.add_argument(
        "words", nargs="*", type=parse_word,
        help="hex instruction words (default: MOV r0,#12; SUB r0,r0,#8; ADD r0,r0,#3; AND r0,r0,#7; ORR r0,r0,#8; EOR r0,r0,#1; BIC r0,r0,#2; MVN r1,#0; AND r0,r1,#12; BX LR)",
    )
    parser.add_argument("--output", type=Path, help="write generated C to a file instead of stdout")
    args = parser.parse_args(argv)

    try:
        source = translate(args.words or list(DEFAULT_WORDS))
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
