#!/usr/bin/env python3
"""Build a local-only ELF32 ARM analysis container from a user's decompressed 3DS code."""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
PAGE_SIZE = 0x1000
ELF_HEADER_SIZE = 52
ELF_PROGRAM_HEADER_SIZE = 32
ELF_PAYLOAD_OFFSET = PAGE_SIZE
U32_LIMIT = 1 << 32
ELF_MACHINE_ARM = 40
ELF_PT_LOAD = 1
ELF_ET_EXEC = 2
ELF_EABI5_FLAGS = 0x05000000


class RetailCodeWrapError(ValueError):
    """Input or output violates the local-only analysis-container contract."""


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _read_bytes(path: Path, label: str) -> bytes:
    try:
        return path.read_bytes()
    except OSError as exc:
        raise RetailCodeWrapError(f"cannot read {label} file {path.name!r}: {exc}") from exc


def _outside_project(path: Path, label: str) -> Path:
    resolved = path.expanduser().resolve()
    try:
        resolved.relative_to(ROOT.resolve())
    except ValueError:
        return resolved
    raise RetailCodeWrapError(f"{label} must be outside the repository because it contains or describes local game data")


def _u32(data: bytes, offset: int) -> int:
    return int.from_bytes(data[offset:offset + 4], "little", signed=False)


def _elf_header(entry_address: int, program_header_count: int) -> bytes:
    ident = b"\x7fELF" + bytes((1, 1, 1, 0)) + bytes(8)
    return struct.pack(
        "<16sHHIIIIIHHHHHH",
        ident, ELF_ET_EXEC, ELF_MACHINE_ARM, 1, entry_address,
        ELF_HEADER_SIZE, 0, ELF_EABI5_FLAGS,
        ELF_HEADER_SIZE, ELF_PROGRAM_HEADER_SIZE, program_header_count, 0, 0, 0,
    )


def build_analysis_elf(
    target_id: str,
    exheader_path: Path,
    code_path: Path,
    output_path: Path,
    *,
    confirm_decompressed: bool,
    allow_unverified_target: bool = False,
) -> dict[str, Any]:
    """Validate local inputs, then create an ELF container for static analysis only."""
    if not confirm_decompressed:
        raise RetailCodeWrapError(
            "refusing to wrap ambiguous bytes: pass --confirm-decompressed only after confirming "
            "that the local .code input has already been decompressed"
        )

    destination = _outside_project(output_path, "ELF output")
    exheader_resolved = exheader_path.expanduser().resolve()
    code_resolved = code_path.expanduser().resolve()
    if destination in (exheader_resolved, code_resolved):
        raise RetailCodeWrapError("ELF output must not overwrite either input file")

    from inspect_3ds_target import TargetInspectionError, inspect_target

    try:
        preflight = inspect_target(target_id, exheader_path, code_path)
    except TargetInspectionError as exc:
        raise RetailCodeWrapError(f"target preflight failed: {exc}") from exc

    if preflight["identity"]["program_id_match"] != "matched" and not allow_unverified_target:
        raise RetailCodeWrapError(
            "the ExHeader ACI Program ID is not recognized for the selected target; "
            "recheck the inputs or explicitly pass --allow-unverified-target"
        )

    exheader = _read_bytes(exheader_path, "ExHeader")
    code = _read_bytes(code_path, "decompressed .code")
    if len(exheader) < 0x40:
        raise RetailCodeWrapError("ExHeader is too short to describe all executable segments")

    bss_size = _u32(exheader, 0x3C)
    permissions = {"text": 5, "rodata": 4, "data": 6}
    elf_segments: list[dict[str, int | str]] = []

    for item in preflight["memory"]["segments"]:
        name = str(item["name"])
        allocated = int(item["allocated_bytes"])
        bss = bss_size if name == "data" else 0
        memory_size = allocated + bss
        if allocated == 0 and memory_size == 0:
            continue
        address = int(item["virtual_address"])
        if not 0 <= address < U32_LIMIT:
            raise RetailCodeWrapError(f"{name} virtual address is outside uint32")
        if memory_size > U32_LIMIT - address:
            raise RetailCodeWrapError(f"{name} memory range exceeds the 32-bit address space")
        elf_segments.append({
            "name": name,
            "file_offset": ELF_PAYLOAD_OFFSET + int(item["code_file_offset"]),
            "virtual_address": address,
            "file_size": allocated,
            "memory_size": memory_size,
            "flags": permissions[name],
            "alignment": PAGE_SIZE if address % PAGE_SIZE == 0 else 1,
            "code_file_offset": int(item["code_file_offset"]),
            "allocated_pages": int(item["allocated_pages"]),
            "declared_size_bytes": int(item["declared_size_bytes"]),
            "bss_size_bytes": bss,
        })

    text = next((item for item in elf_segments if item["name"] == "text"), None)
    if text is None or int(text["file_size"]) == 0 or int(text["declared_size_bytes"]) == 0:
        raise RetailCodeWrapError("the selected target has no non-empty text segment to analyze")
    if len(elf_segments) > 0xFFFF:
        raise RetailCodeWrapError("too many ELF load segments")

    program_headers = [
        struct.pack(
            "<IIIIIIII",
            ELF_PT_LOAD,
            int(segment["file_offset"]),
            int(segment["virtual_address"]),
            int(segment["virtual_address"]),
            int(segment["file_size"]),
            int(segment["memory_size"]),
            int(segment["flags"]),
            int(segment["alignment"]),
        )
        for segment in elf_segments
    ]
    prefix = _elf_header(int(text["virtual_address"]), len(program_headers)) + b"".join(program_headers)
    if len(prefix) > ELF_PAYLOAD_OFFSET:
        raise RetailCodeWrapError("ELF program headers exceed the reserved payload offset")
    elf_bytes = prefix + bytes(ELF_PAYLOAD_OFFSET - len(prefix)) + code
    if len(elf_bytes) != ELF_PAYLOAD_OFFSET + len(code):
        raise RetailCodeWrapError("internal ELF size check failed")

    for segment in elf_segments:
        code_start = int(segment["code_file_offset"])
        size = int(segment["file_size"])
        elf_start = int(segment["file_offset"])
        if elf_bytes[elf_start:elf_start + size] != code[code_start:code_start + size]:
            raise RetailCodeWrapError(f"ELF byte verification failed for {segment['name']}")

    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(elf_bytes)
    except OSError as exc:
        raise RetailCodeWrapError(f"cannot write ELF output {destination.name!r}: {exc}") from exc

    compression_flag = bool(exheader[0x0D] & 0x01)
    warnings = list(preflight["warnings"])
    if compression_flag:
        warnings.append(
            "The ExHeader indicates the stored ExeFS code was compressed. The caller confirmed the supplied input "
            "is already decompressed, but this tool cannot independently prove that."
        )

    return {
        "schema_version": 1,
        "status": "analysis-container-created",
        "purpose": "local static analysis only; not a runnable game or a reconstructed executable",
        "target": preflight["target"],
        "identity": preflight["identity"],
        "inputs": {
            "exheader": {"filename": exheader_path.name, "size_bytes": len(exheader), "sha256": _sha256(exheader)},
            "decompressed_code": {"filename": code_path.name, "size_bytes": len(code), "sha256": _sha256(code)},
            "caller_confirmed_decompressed": True,
            "exheader_original_code_compressed_flag": compression_flag,
        },
        "output": {
            "filename": destination.name,
            "size_bytes": len(elf_bytes),
            "sha256": _sha256(elf_bytes),
            "format": "ELF32 little-endian ARM analysis container",
            "elf_entry_address": f"0x{int(text['virtual_address']):08X}",
            "elf_entry_is_game_entrypoint_proof": False,
        },
        "memory": {
            "page_size_bytes": PAGE_SIZE,
            "bss_size_bytes": bss_size,
            "code_payload_offset_in_elf": ELF_PAYLOAD_OFFSET,
            "segments": [
                {
                    **segment,
                    "file_offset_hex": f"0x{int(segment['file_offset']):X}",
                    "virtual_address_hex": f"0x{int(segment['virtual_address']):08X}",
                }
                for segment in elf_segments
            ],
        },
        "verification": {
            "source_exheader_and_code_preflight": preflight["status"],
            "all_file_backed_segment_bytes_match_input": True,
            "source_bytes_embedded_in_output": True,
            "runtime_execution_attempted": False,
        },
        "warnings": warnings,
        "limitations": [
            "The declared text base is an ELF analysis entry hint; the actual game startup entry was not discovered.",
            "This tool does not recover functions, symbols, relocations, compiler flags, ARM/Thumb boundaries, CRO modules, or system services.",
            "Input hashes identify the local inputs but do not authenticate the dump or prove its exact software revision.",
            "The output contains supplied game code and must remain local; never commit or upload it.",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    from inspect_3ds_target import load_profiles

    parser = argparse.ArgumentParser(
        description="Wrap a user-supplied, already-decompressed 3DS code.bin as a local-only ELF analysis container."
    )
    profiles = load_profiles()
    parser.add_argument("--target", required=True, choices=sorted(profiles))
    parser.add_argument("--exheader", required=True, type=Path, help="ExHeader from the same local executable")
    parser.add_argument("--code", required=True, type=Path, help="matching, already-decompressed .code payload")
    parser.add_argument("--output", required=True, type=Path, help="ELF path outside the repository")
    parser.add_argument(
        "--confirm-decompressed",
        action="store_true",
        help="confirm you independently verified the supplied .code file is decompressed",
    )
    parser.add_argument(
        "--allow-unverified-target",
        action="store_true",
        help="allow an unrecognized ACI Program ID after manually checking the selected target",
    )
    parser.add_argument("--report", type=Path, help="optional JSON report path outside the repository")
    args = parser.parse_args(argv)

    try:
        report_path = None
        if args.report is not None:
            report_path = _outside_project(args.report, "JSON report")
            reserved = {
                args.output.expanduser().resolve(),
                args.exheader.expanduser().resolve(),
                args.code.expanduser().resolve(),
            }
            if report_path in reserved:
                raise RetailCodeWrapError("report path must not overwrite the output or either input")
        report = build_analysis_elf(
            args.target,
            args.exheader,
            args.code,
            args.output,
            confirm_decompressed=args.confirm_decompressed,
            allow_unverified_target=args.allow_unverified_target,
        )
        rendered = json.dumps(report, indent=2, ensure_ascii=False) + "\n"
        if report_path is not None:
            report_path.parent.mkdir(parents=True, exist_ok=True)
            report_path.write_text(rendered, encoding="utf-8", newline="\n")
        sys.stdout.write(rendered)
        return 0
    except (RetailCodeWrapError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
