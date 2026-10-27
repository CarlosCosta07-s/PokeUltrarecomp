#!/usr/bin/env python3
"""Disassemble an explicitly selected range from a local 3DS executable using Capstone."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
U32_LIMIT = 1 << 32


class RetailDisassemblyError(ValueError):
    """Input or output violates the explicit-range disassembly contract."""


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _outside_project(path: Path) -> Path:
    resolved = path.expanduser().resolve()
    try:
        resolved.relative_to(ROOT.resolve())
    except ValueError:
        return resolved
    raise RetailDisassemblyError(
        "disassembly report must be outside the repository because it contains game-derived instructions"
    )


def _read(path: Path, label: str) -> bytes:
    try:
        return path.read_bytes()
    except OSError as exc:
        raise RetailDisassemblyError(f"cannot read {label} file {path.name!r}: {exc}") from exc


def disassemble_retail_range(
    target_id: str,
    exheader_path: Path,
    code_path: Path,
    state: str,
    start_address: int,
    byte_count: int,
    report_path: Path,
    *,
    allow_unverified_target: bool = False,
    capstone_module: Any | None = None,
) -> dict[str, Any]:
    """Decode one explicit byte range and persist its private JSON report."""
    if state not in ("arm", "thumb"):
        raise RetailDisassemblyError("instruction state must be 'arm' or 'thumb'")
    if byte_count <= 0:
        raise RetailDisassemblyError("byte count must be positive")
    alignment = 4 if state == "arm" else 2
    if start_address % alignment:
        raise RetailDisassemblyError(f"{state.upper()} start address must be aligned to {alignment} bytes")
    if byte_count % alignment:
        raise RetailDisassemblyError(f"{state.upper()} byte count must be a multiple of {alignment}")
    if not 0 <= start_address < U32_LIMIT or byte_count > U32_LIMIT - start_address:
        raise RetailDisassemblyError("requested address range overflows the 32-bit address space")

    report_destination = _outside_project(report_path)
    exheader_resolved = exheader_path.expanduser().resolve()
    code_resolved = code_path.expanduser().resolve()
    if report_destination in (exheader_resolved, code_resolved):
        raise RetailDisassemblyError("report path must not overwrite either input file")

    from inspect_3ds_target import TargetInspectionError, inspect_target

    try:
        preflight = inspect_target(target_id, exheader_path, code_path)
    except TargetInspectionError as exc:
        raise RetailDisassemblyError(f"target preflight failed: {exc}") from exc
    if preflight["identity"]["program_id_match"] != "matched" and not allow_unverified_target:
        raise RetailDisassemblyError(
            "the ExHeader ACI Program ID is not recognized for the selected target; "
            "recheck the inputs or explicitly pass --allow-unverified-target"
        )

    code = _read(code_path, "decompressed .code")
    exheader = _read(exheader_path, "ExHeader")
    text_segment = next(
        (item for item in preflight["memory"]["segments"] if item["name"] == "text"),
        None,
    )
    if text_segment is None:
        raise RetailDisassemblyError("target metadata has no text segment")
    text_start = int(text_segment["virtual_address"])
    text_size = int(text_segment["declared_size_bytes"])
    requested_end = start_address + byte_count
    text_end = text_start + text_size
    if start_address < text_start or requested_end > text_end:
        raise RetailDisassemblyError(
            f"range 0x{start_address:08X}..0x{requested_end:08X} is outside declared text "
            f"0x{text_start:08X}..0x{text_end:08X}"
        )
    code_offset = int(text_segment["code_file_offset"]) + (start_address - text_start)
    selected = code[code_offset:code_offset + byte_count]
    if len(selected) != byte_count:
        raise RetailDisassemblyError("selected range is not fully backed by the local .code file")

    if capstone_module is None:
        try:
            import capstone as capstone_module
        except ImportError as exc:
            raise RetailDisassemblyError(
                "Capstone is required for this local analysis; install tools/requirements-analysis.txt "
                "in your local analysis environment"
            ) from exc

    capstone_mode = capstone_module.CS_MODE_ARM if state == "arm" else capstone_module.CS_MODE_THUMB
    capstone_mode |= capstone_module.CS_MODE_LITTLE_ENDIAN
    engine = capstone_module.Cs(capstone_module.CS_ARCH_ARM, capstone_mode)
    try:
        decoded = list(engine.disasm(selected, start_address))
    except Exception as exc:  # provider/API errors should be actionable, never a partial success
        raise RetailDisassemblyError(f"Capstone failed to decode the requested range: {exc}") from exc

    instructions: list[dict[str, Any]] = []
    cursor = start_address
    for instruction in decoded:
        if instruction.size <= 0 or instruction.address != cursor:
            raise RetailDisassemblyError(
                f"Capstone did not provide contiguous instruction coverage at 0x{cursor:08X}"
            )
        raw = bytes(instruction.bytes)
        if len(raw) != instruction.size or instruction.size > requested_end - cursor:
            raise RetailDisassemblyError("Capstone returned an instruction outside the requested range")
        instructions.append({
            "address": f"0x{instruction.address:08X}",
            "size_bytes": instruction.size,
            "bytes_hex": raw.hex(),
            "mnemonic": instruction.mnemonic,
            "operands": instruction.op_str,
        })
        cursor += instruction.size
    if cursor != requested_end:
        raise RetailDisassemblyError(
            f"decoder covered {cursor - start_address} of {byte_count} bytes; "
            "the range may contain an undecodable encoding or end mid-instruction"
        )
    if not instructions:
        raise RetailDisassemblyError("Capstone produced no instructions for the requested range")

    report = {
        "schema_version": 1,
        "status": "explicit-range-disassembled",
        "target": preflight["target"],
        "identity": preflight["identity"],
        "inputs": {
            "exheader": {"filename": exheader_path.name, "size_bytes": len(exheader), "sha256": _sha256(exheader)},
            "decompressed_code": {"filename": code_path.name, "size_bytes": len(code), "sha256": _sha256(code)},
        },
        "range": {
            "state": state,
            "start_address": f"0x{start_address:08X}",
            "byte_count": byte_count,
            "end_address_exclusive": f"0x{requested_end:08X}",
            "code_file_offset": code_offset,
            "raw_bytes_in_report": True,
        },
        "decoder": {
            "name": "Capstone",
            "version": str(getattr(capstone_module, "__version__", "unknown")),
            "architecture": "ARM",
            "little_endian": True,
            "state_was_supplied_by_caller": True,
        },
        "instructions": instructions,
        "verification": {
            "instruction_addresses_are_contiguous": True,
            "decoded_bytes_equal_requested_range": sum(i["size_bytes"] for i in instructions) == byte_count,
            "function_boundary_discovered_automatically": False,
            "instruction_set_version_validated_for_ARM11": False,
        },
        "warnings": list(preflight["warnings"]),
        "limitations": [
            "The report contains raw instruction bytes and disassembly; keep it local and outside the repository.",
            "The caller supplied the address, state, and byte count. This tool does not find function boundaries or switch ARM/Thumb state automatically.",
            "Capstone disassembly alone does not prove that every decoded word is an instruction rather than embedded data or a literal pool.",
            "The decoder is not configured here as an ARM11 instruction-version validator; verify target-specific legality separately.",
            "Disassembly is not recompilation and does not establish function equivalence or game execution.",
        ],
    }
    rendered = json.dumps(report, indent=2, ensure_ascii=False) + "\n"
    try:
        report_destination.parent.mkdir(parents=True, exist_ok=True)
        report_destination.write_text(rendered, encoding="utf-8", newline="\n")
    except OSError as exc:
        raise RetailDisassemblyError(f"cannot write report {report_destination.name!r}: {exc}") from exc
    return report


def main(argv: list[str] | None = None) -> int:
    from inspect_3ds_target import load_profiles

    profiles = load_profiles()
    parser = argparse.ArgumentParser(
        description="Disassemble a caller-selected range of local 3DS code with Capstone."
    )
    parser.add_argument("--target", choices=sorted(profiles), required=True)
    parser.add_argument("--exheader", type=Path, required=True)
    parser.add_argument("--code", type=Path, required=True, help="local, already-decompressed .code file")
    parser.add_argument("--state", choices=("arm", "thumb"), required=True)
    parser.add_argument("--start-address", type=lambda value: int(value, 0), required=True)
    parser.add_argument("--byte-count", type=lambda value: int(value, 0), required=True)
    parser.add_argument("--report", type=Path, required=True, help="JSON output path outside the repository")
    parser.add_argument("--allow-unverified-target", action="store_true")
    args = parser.parse_args(argv)
    try:
        report = disassemble_retail_range(
            args.target, args.exheader, args.code, args.state,
            args.start_address, args.byte_count, args.report,
            allow_unverified_target=args.allow_unverified_target,
        )
        sys.stdout.write(json.dumps({
            "status": report["status"],
            "instruction_count": len(report["instructions"]),
            "state": report["range"]["state"],
            "start_address": report["range"]["start_address"],
            "byte_count": report["range"]["byte_count"],
            "report_filename": args.report.name,
            "report_sha256": _sha256(args.report.read_bytes()),
        }, indent=2) + "\n")
        return 0
    except (RetailDisassemblyError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
