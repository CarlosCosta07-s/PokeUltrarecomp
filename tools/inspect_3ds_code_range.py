#!/usr/bin/env python3
"""Decode a fixed, user-selected range in a local decompressed 3DS .code file."""
from __future__ import annotations
import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import arm_subset_poc as arm  # noqa: E402
import inspect_3ds_target as intake  # noqa: E402
import thumb_subset_poc as thumb  # noqa: E402


class TargetRangeError(ValueError):
    """The selected range is outside this tool's explicit scope."""


def parse_address(token: str) -> int:
    try:
        value = int(token, 0)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f"expected a numeric address, preferably hexadecimal with 0x prefix: {token!r}"
        ) from exc
    if not 0 <= value < (1 << 32):
        raise argparse.ArgumentTypeError("address must fit uint32")
    return value


def mnemonic_for(state: str, decoded: tuple[object, ...]) -> str:
    if decoded == ("return",):
        return "BX LR"
    if decoded[0] == "branch":
        cond = decoded[1]
        return "B" if cond == "al" else f"B{str(cond).upper()}"
    cond = None
    inst = decoded
    if decoded[0] == "predicated":
        _, cond, inst = decoded
    op = str(inst[0])
    names = {
        "mov": "MOV", "mvn": "MVN", "add": "ADD", "sub": "SUB",
        "and": "AND", "orr": "ORR", "eor": "EOR", "bic": "BIC",
        "adds": "ADDS", "subs": "SUBS", "cmp": "CMP", "cmn": "CMN",
        "movs": "MOVS",
    }
    name = names.get(op)
    if name is None:
        raise TargetRangeError(f"unsupported decoded operation {op!r}")
    if cond is not None:
        name += str(cond).upper()
    if op in ("mov", "mvn", "movs", "cmp", "cmn"):
        return f"{name} r{inst[1]}, #{inst[2]}"
    if state == "thumb" and op in ("adds", "subs"):
        return f"{name} r{inst[1]}, #{inst[2]}"
    if op in ("add", "sub", "and", "orr", "eor", "bic", "adds", "subs"):
        return f"{name} r{inst[1]}, r{inst[2]}, #{inst[3]}"
    raise TargetRangeError(f"could not format decoded operation {decoded!r}")


def inspect_code_range(
    target_id: str,
    exheader_path: Path,
    code_path: Path,
    state: str,
    start_address: int,
    instruction_count: int,
    *,
    title_id: str | None = None,
    allow_unverified_target: bool = False,
    include_unsupported: bool = False,
) -> dict[str, Any]:
    """Decode a user-selected instruction range inside declared .text.

    With include_unsupported=True, unknown instructions are recorded as raw
    encodings. Thumb-2 prefix halfwords consume two halfwords as one unknown
    32-bit instruction so the remainder of the range stays aligned.
    """
    if state not in ("arm", "thumb"):
        raise TargetRangeError("instruction state must be 'arm' or 'thumb'")
    if isinstance(instruction_count, bool) or not isinstance(instruction_count, int):
        raise TargetRangeError("instruction count must be an integer")
    if not 1 <= instruction_count <= 256:
        raise TargetRangeError("instruction count must be in 1..256")
    if isinstance(start_address, bool) or not isinstance(start_address, int) or not 0 <= start_address < (1 << 32):
        raise TargetRangeError("start address must fit uint32")
    unit = 4 if state == "arm" else 2
    if start_address % unit:
        raise TargetRangeError(f"start address 0x{start_address:08X} is not aligned for {state.upper()}")

    try:
        checked = intake.inspect_target(target_id, exheader_path, code_path, title_id=title_id)
    except intake.TargetInspectionError as exc:
        raise TargetRangeError(str(exc)) from exc
    program_match = checked["identity"]["program_id_match"]
    if program_match != "matched" and not allow_unverified_target:
        raise TargetRangeError(
            "ExHeader Program ID is unrecognized; use the matching executable or explicitly pass "
            "--allow-unverified-target after verifying the local input"
        )

    text = next(segment for segment in checked["memory"]["segments"] if segment["name"] == "text")
    text_start = int(text["virtual_address"])
    text_size = int(text["declared_size_bytes"])
    relative = start_address - text_start
    if relative < 0 or relative >= text_size:
        raise TargetRangeError(
            f"start address 0x{start_address:08X} lies outside declared .text "
            f"0x{text_start:08X}..0x{text_start + text_size:08X}"
        )
    if relative + unit > text_size:
        raise TargetRangeError(
            f"requested range extends beyond declared .text payload ({text_size} bytes); page padding is not code"
        )

    try:
        code = code_path.read_bytes()
    except OSError as exc:
        raise TargetRangeError(f"cannot read local .code file: {exc}") from exc
    if hashlib.sha256(code).hexdigest() != checked["inputs"]["decompressed_code"]["sha256"]:
        raise TargetRangeError(".code changed during inspection; retry with a stable local file")
    file_offset = int(text["code_file_offset"]) + relative

    instructions: list[dict[str, Any]] = []
    cursor = 0
    index = 0
    while index < instruction_count:
        if relative + cursor + unit > text_size:
            raise TargetRangeError(
                f"requested range extends beyond declared .text payload ({text_size} bytes); page padding is not code"
            )
        absolute_offset = file_offset + cursor
        unit_bytes = code[absolute_offset:absolute_offset + unit]
        if len(unit_bytes) != unit:
            raise TargetRangeError("selected range is truncated in .code")
        word = int.from_bytes(unit_bytes, "little")
        address = start_address + cursor
        instruction_size = unit
        unknown_reason: str | None = None
        thumb32_second: int | None = None
        is_thumb32 = state == "thumb" and (word & 0xF800) in (0xE800, 0xF000, 0xF800)
        if is_thumb32:
            instruction_size = 4
            if relative + cursor + instruction_size > text_size:
                raise TargetRangeError(
                    f"32-bit Thumb instruction prefix at 0x{address:08X} crosses the declared .text boundary"
                )
            second_offset = absolute_offset + 2
            second_bytes = code[second_offset:second_offset + 2]
            if len(second_bytes) != 2:
                raise TargetRangeError(f"truncated 32-bit Thumb instruction at 0x{address:08X}")
            thumb32_second = int.from_bytes(second_bytes, "little")
            unknown_reason = "Thumb-2 32-bit instruction decoding is not implemented"
        else:
            try:
                decoded = arm.decode_word(word) if state == "arm" else thumb.decode_halfword(word)
                mnemonic = mnemonic_for(state, decoded)
            except (arm.UnsupportedInstruction, thumb.UnsupportedThumbInstruction, TargetRangeError) as exc:
                unknown_reason = str(exc)
            else:
                item = {
                    "index": index,
                    "virtual_address": f"0x{address:08X}",
                    "decompressed_code_file_offset": absolute_offset,
                    "instruction_size_bytes": instruction_size,
                    "encoding": f"0x{word:0{unit * 2}X}",
                    "decode_status": "decoded",
                    "mnemonic": mnemonic,
                    "decoded_ir": decoded,
                }
                if decoded[0] == "branch":
                    target_address = address + (2 + int(decoded[2])) * unit
                    item["branch_target_virtual_address"] = f"0x{target_address:08X}"
                    item["branch_target_within_declared_text"] = text_start <= target_address < text_start + text_size
                instructions.append(item)
                cursor += instruction_size
                index += 1
                continue

        if not include_unsupported:
            if is_thumb32:
                message = (
                    f"unsupported 32-bit Thumb instruction at 0x{address:08X} "
                    f"(halfwords 0x{word:04X} 0x{thumb32_second:04X}): {unknown_reason}; "
                    "use --include-unsupported to record raw encodings without decoding them"
                )
            else:
                digits = unit * 2
                message = (
                    f"unsupported instruction at 0x{address:08X} (0x{word:0{digits}X}): "
                    f"{unknown_reason}; use --include-unsupported to continue with raw encodings"
                )
            raise TargetRangeError(message)

        item = {
            "index": index,
            "virtual_address": f"0x{address:08X}",
            "decompressed_code_file_offset": absolute_offset,
            "instruction_size_bytes": instruction_size,
            "encoding": (
                f"0x{word:04X} 0x{thumb32_second:04X}" if is_thumb32
                else f"0x{word:0{unit * 2}X}"
            ),
            "decode_status": "unsupported-thumb32" if is_thumb32 else "unsupported",
            "mnemonic": None,
            "decoded_ir": None,
            "reason": unknown_reason,
        }
        if is_thumb32:
            item["halfwords"] = [f"0x{word:04X}", f"0x{thumb32_second:04X}"]
        instructions.append(item)
        cursor += instruction_size
        index += 1

    selected_end = start_address + cursor
    scanned_starts = {int(item["virtual_address"], 16) for item in instructions}
    for item in instructions:
        target_text = item.get("branch_target_virtual_address")
        if target_text is not None:
            branch_address = int(target_text, 16)
            item["branch_target_within_selected_range"] = start_address <= branch_address < selected_end
            item["branch_target_is_scanned_instruction_start"] = branch_address in scanned_starts

    has_unknown = any(item["decode_status"] != "decoded" for item in instructions)
    return {
        "schema_version": 1,
        "status": "partially-decoded-explicit-range" if has_unknown else "decoded-explicit-range",
        "target": {
            "target_id": checked["target"]["target_id"],
            "display_name": checked["target"]["display_name"],
            "program_id": checked["identity"]["program_id"],
            "program_id_match": program_match,
            "revision_hint": checked["revision_hint"],
        },
        "range": {
            "state": state,
            "start_address": f"0x{start_address:08X}",
            "instruction_count": instruction_count,
            "unit_bytes": unit,
            "byte_count": cursor,
            "decompressed_code_file_offset": file_offset,
            "text_virtual_start": f"0x{text_start:08X}",
            "text_declared_size_bytes": text_size,
            "selected_range_end": f"0x{selected_end:08X}",
            "includes_unsupported_raw_encodings": include_unsupported and has_unknown,
            "semantic_warning": "This is syntax-only; register, flag, control-flow and ABI assumptions are not proven to match the game.",
        },
        "input": {
            "exheader_filename": exheader_path.name,
            "exheader_sha256": checked["inputs"]["exheader"]["sha256"],
            "code_filename": code_path.name,
            "code_sha256": checked["inputs"]["decompressed_code"]["sha256"],
        },
        "instructions": instructions,
        "limitations": [
            "Only the explicit fixed-width range is decoded; no function discovery or automatic ARM/Thumb state detection.",
            "Only the current narrow ARM A32 and Thumb-16 subsets are decoded.",
            "With --include-unsupported, unknown encodings are recorded as raw bytes; they are not disassembled or semantically analyzed.",
            "Thumb-2 32-bit instructions are detected and kept together as two halfwords, but are not decoded.",
            "Literal pools, embedded data, relocations, calls, memory effects, ABI and control-flow context are not resolved.",
            "Reports contain instruction encodings derived from local game code; keep them local unless reviewed and redacted.",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    profiles = intake.load_profiles()
    parser = argparse.ArgumentParser(
        description="Decode an explicitly selected range in a local decompressed 3DS .code file."
    )
    parser.add_argument("--target", required=True, choices=sorted(profiles))
    parser.add_argument("--exheader", required=True, type=Path)
    parser.add_argument("--code", required=True, type=Path)
    parser.add_argument("--state", required=True, choices=("arm", "thumb"))
    parser.add_argument("--start-address", required=True, type=parse_address)
    parser.add_argument("--instruction-count", required=True, type=int)
    parser.add_argument("--title-id", help="optional NCCH/container ID, separate from the ExHeader Program ID")
    parser.add_argument("--allow-unverified-target", action="store_true")
    parser.add_argument(
        "--include-unsupported", action="store_true",
        help="record unknown encodings as raw data and continue; 32-bit Thumb instructions stay grouped",
    )
    parser.add_argument("--report", type=Path, help="write a local JSON report outside the repository")
    args = parser.parse_args(argv)
    try:
        report = inspect_code_range(
            args.target, args.exheader, args.code, args.state,
            args.start_address, args.instruction_count, title_id=args.title_id,
            allow_unverified_target=args.allow_unverified_target,
            include_unsupported=args.include_unsupported,
        )
        rendered = json.dumps(report, indent=2, ensure_ascii=False) + "\n"
        if args.report:
            target_path = args.report.resolve()
            if target_path == ROOT or ROOT in target_path.parents:
                raise TargetRangeError("report output must be outside the repository")
            args.report.write_text(rendered, encoding="utf-8", newline="\n")
        else:
            sys.stdout.write(rendered)
        return 0
    except (TargetRangeError, OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
