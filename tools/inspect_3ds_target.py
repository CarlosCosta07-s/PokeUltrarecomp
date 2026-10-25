#!/usr/bin/env python3
"""Local-only structural preflight for Nintendo 3DS game executable inputs.

Reads a user-supplied ExHeader and already-decompressed ExeFS/.code file. It
reports metadata and SHA-256 digests; it never writes/copies the game bytes.
This is not a disassembler or a recompiler.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
TARGET_DIR = ROOT / "targets"
PAGE_SIZE = 0x1000
SCI_MIN_SIZE = 0x200
U32_LIMIT = 1 << 32


class TargetInspectionError(ValueError):
    """Input does not satisfy the structural preflight contract."""


def load_profiles() -> dict[str, dict[str, Any]]:
    profiles: dict[str, dict[str, Any]] = {}
    for path in sorted(TARGET_DIR.glob("*.json")):
        try:
            profile = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise TargetInspectionError(f"cannot read target profile {path.name}: {exc}") from exc
        target_id = profile.get("target_id")
        if not isinstance(target_id, str) or not target_id:
            raise TargetInspectionError(f"target profile {path.name} has no target_id")
        if target_id in profiles:
            raise TargetInspectionError(f"duplicate target_id in profile registry: {target_id}")
        profiles[target_id] = profile
    if not profiles:
        raise TargetInspectionError(f"no target profiles found in {TARGET_DIR}")
    return profiles


def normalize_title_id(value: str) -> str:
    normalized = value.strip().lower()
    if normalized.startswith("0x"):
        normalized = normalized[2:]
    if len(normalized) != 16 or any(ch not in "0123456789abcdef" for ch in normalized):
        raise TargetInspectionError("title ID must be exactly 16 hexadecimal digits")
    return normalized


def _u32(data: bytes, offset: int) -> int:
    return int.from_bytes(data[offset:offset + 4], "little", signed=False)


def _u16(data: bytes, offset: int) -> int:
    return int.from_bytes(data[offset:offset + 2], "little", signed=False)


def _read_input(path: Path, label: str) -> bytes:
    try:
        return path.read_bytes()
    except OSError as exc:
        raise TargetInspectionError(f"cannot read {label} file {path.name!r}: {exc}") from exc


def inspect_target(
    target_id: str,
    exheader_path: Path,
    code_path: Path,
    title_id: str | None = None,
) -> dict[str, Any]:
    """Inspect local ExHeader and decompressed ExeFS/.code inputs."""
    profiles = load_profiles()
    if target_id not in profiles:
        raise TargetInspectionError(
            f"unknown target {target_id!r}; available targets: {', '.join(sorted(profiles))}"
        )
    profile = profiles[target_id]
    exheader = _read_input(exheader_path, "ExHeader")
    code = _read_input(code_path, "decompressed .code")

    if len(exheader) < SCI_MIN_SIZE:
        raise TargetInspectionError(
            f"ExHeader is too short ({len(exheader)} bytes); at least 0x{SCI_MIN_SIZE:X} bytes are required"
        )
    if not code:
        raise TargetInspectionError("decompressed .code input is empty")

    identity: dict[str, Any] = {
        "title_id_provided": title_id is not None,
        "title_id": None,
        "title_id_match": "not-supplied",
        "title_kind": None,
    }
    warnings: list[str] = []
    if title_id is not None:
        normalized_id = normalize_title_id(title_id)
        identity["title_id"] = normalized_id
        matched_kind = None
        for candidate_id, candidate in profiles.items():
            ids = candidate.get("title_ids", {})
            for kind in ("base", "update"):
                if normalized_id == ids.get(kind, "").lower():
                    if candidate_id != target_id:
                        raise TargetInspectionError(
                            f"title ID {normalized_id} belongs to {candidate['display_name']} "
                            f"({kind}), not {profile['display_name']}"
                        )
                    matched_kind = kind
        if matched_kind is None:
            identity["title_id_match"] = "unrecognized"
            warnings.append(
                "title ID is not in the known base/update ID list; target identity was not independently confirmed"
            )
        else:
            identity["title_id_match"] = "matched"
            identity["title_kind"] = matched_kind

    app_title = exheader[0:8].decode("ascii", errors="replace").rstrip("\x00 ")
    flags = exheader[0x0D]
    remaster_version = _u16(exheader, 0x0E)
    stack_size = _u32(exheader, 0x1C)
    bss_size = _u32(exheader, 0x3C)

    segment_specs = (("text", 0x10), ("rodata", 0x20), ("data", 0x30))
    segments: list[dict[str, int | str]] = []
    occupied: list[tuple[int, int, str]] = []
    minimum_declared_payload = 0
    allocated_capacity = 0
    for name, offset in segment_specs:
        address = _u32(exheader, offset)
        pages = _u32(exheader, offset + 4)
        size = _u32(exheader, offset + 8)
        allocated = pages * PAGE_SIZE
        if size > allocated:
            raise TargetInspectionError(
                f"{name} segment declares {size} bytes but reserves only {allocated} bytes ({pages} pages)"
            )
        if size > 0 and pages == 0:
            raise TargetInspectionError(f"{name} segment has data but reserves zero pages")
        if pages and address + allocated > U32_LIMIT:
            raise TargetInspectionError(f"{name} segment address range overflows the 32-bit address space")
        if pages and address % PAGE_SIZE:
            warnings.append(f"{name} segment address 0x{address:08X} is not page-aligned")
        if pages:
            start, end = address, address + allocated
            for other_start, other_end, other_name in occupied:
                if start < other_end and other_start < end:
                    raise TargetInspectionError(
                        f"{name} segment page range overlaps {other_name} "
                        f"(0x{start:08X}..0x{end:08X})"
                    )
            occupied.append((start, end, name))
        minimum_declared_payload += size
        allocated_capacity += allocated
        segments.append({
            "name": name,
            "virtual_address": address,
            "allocated_pages": pages,
            "allocated_bytes": allocated,
            "declared_size_bytes": size,
        })

    if len(code) < minimum_declared_payload:
        raise TargetInspectionError(
            f"decompressed .code is too short ({len(code)} bytes); "
            f"declared segment payload needs at least {minimum_declared_payload} bytes"
        )
    if len(code) > allocated_capacity:
        raise TargetInspectionError(
            f"decompressed .code is larger than the combined page allocation "
            f"({len(code)} > {allocated_capacity} bytes)"
        )
    if len(code) != allocated_capacity:
        warnings.append(
            "decompressed .code length fits the declared segment sizes but does not equal total page allocation; "
            "verify the extraction/layout before translation"
        )
    if not identity["title_id_provided"]:
        warnings.append("no title ID supplied; selected target is a user declaration, not an independently verified identity")
    if not app_title:
        warnings.append("ExHeader application title field is empty or non-ASCII")

    return {
        "schema_version": 1,
        "status": "pass-with-warnings" if warnings else "pass",
        "target": {
            "target_id": profile["target_id"],
            "display_name": profile["display_name"],
            "platform": profile["platform"],
            "executable_container": profile["executable_container"],
            "executable_section": profile["executable_section"],
            "processor_family": profile["processor_family"],
            "instruction_states": profile["instruction_states"],
            "implementation_status": profile["status"],
        },
        "identity": {
            **identity,
            "exheader_application_title": app_title,
            "remaster_version": remaster_version,
        },
        "inputs": {
            "exheader": {
                "filename": exheader_path.name,
                "size_bytes": len(exheader),
                "sha256": hashlib.sha256(exheader).hexdigest(),
            },
            "decompressed_code": {
                "filename": code_path.name,
                "size_bytes": len(code),
                "sha256": hashlib.sha256(code).hexdigest(),
            },
            "source_exefs_code_was_compressed": bool(flags & 0x01),
            "input_policy": "The .code input must already be decompressed; this tool does not decrypt or decompress game data.",
        },
        "memory": {
            "page_size_bytes": PAGE_SIZE,
            "stack_size_bytes": stack_size,
            "bss_size_bytes": bss_size,
            "minimum_declared_segment_payload_bytes": minimum_declared_payload,
            "combined_segment_page_capacity_bytes": allocated_capacity,
            "segments": segments,
        },
        "checks": {
            "exheader_sci_present": True,
            "segment_sizes_fit_allocations": True,
            "segment_page_ranges_do_not_overlap": True,
            "code_is_large_enough_for_declared_payload": True,
            "code_fits_combined_page_capacity": True,
            "title_id_match": identity["title_id_match"],
        },
        "warnings": warnings,
        "limitations": [
            "This is a metadata/size preflight, not a disassembler or recompiler.",
            "It does not prove authenticity, exact game revision, correct instruction boundaries, or runtime compatibility.",
            "No game bytes are copied into the repository; generated reports should also remain local unless explicitly redacted.",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    try:
        profiles = load_profiles()
        parser = argparse.ArgumentParser(
            description="Inspect local 3DS ExHeader metadata and an already-decompressed game .code file."
        )
        parser.add_argument("--target", required=True, choices=sorted(profiles), help="game target profile")
        parser.add_argument("--exheader", required=True, type=Path, help="local ExHeader file from the same executable")
        parser.add_argument("--code", required=True, type=Path, help="local, already-decompressed ExeFS/.code file")
        parser.add_argument("--title-id", help="optional 16-digit NCCH/title ID read from local metadata")
        parser.add_argument("--report", type=Path, help="optional JSON report destination; keep outside the repository")
        args = parser.parse_args(argv)
        report = inspect_target(args.target, args.exheader, args.code, args.title_id)
        rendered = json.dumps(report, indent=2, ensure_ascii=False) + "\n"
        if args.report:
            args.report.write_text(rendered, encoding="utf-8", newline="\n")
        else:
            sys.stdout.write(rendered)
        return 0
    except (TargetInspectionError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
