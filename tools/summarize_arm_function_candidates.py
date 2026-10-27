#!/usr/bin/env python3
"""Inventory ARM/Thumb prologue-like sites in a local 3DS text segment.

This is a heuristic census, not a function-boundary detector. By default the
CLI prints aggregate counts only. Address-level results require an explicit
private report path outside the repository.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


class CandidateScanError(ValueError):
    """Candidate census input or output violates its contract."""


def _outside_project(path: Path) -> Path:
    resolved = path.expanduser().resolve()
    try:
        resolved.relative_to(ROOT.resolve())
    except ValueError:
        return resolved
    raise CandidateScanError(
        "private candidate report must be outside the repository because addresses are game-derived"
    )


def scan_candidates(
    target_id: str,
    exheader_path: Path,
    code_path: Path,
    *,
    preflight: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Count plausible prologue encodings in .text without emitting addresses."""
    from inspect_3ds_target import TargetInspectionError, inspect_target

    try:
        inspected = preflight or inspect_target(target_id, exheader_path, code_path)
    except TargetInspectionError as exc:
        raise CandidateScanError(f"target preflight failed: {exc}") from exc

    if inspected.get("identity", {}).get("program_id_match") != "matched":
        raise CandidateScanError(
            "candidate census requires an ExHeader ACI Program ID recognized for the selected target"
        )

    text_segment = next(
        (segment for segment in inspected.get("memory", {}).get("segments", [])
         if segment.get("name") == "text"),
        None,
    )
    if text_segment is None:
        raise CandidateScanError("target metadata has no text segment")

    try:
        code = code_path.expanduser().resolve().read_bytes()
    except OSError as exc:
        raise CandidateScanError("cannot read local .code file for candidate census") from exc

    text_offset = int(text_segment["code_file_offset"])
    text_size = int(text_segment["declared_size_bytes"])
    text_start = int(text_segment["virtual_address"])
    text_end_offset = text_offset + text_size
    if text_offset < 0 or text_size <= 0 or text_end_offset > len(code):
        raise CandidateScanError("declared .text range is not fully backed by the local .code file")

    text = code[text_offset:text_end_offset]
    candidates: list[dict[str, Any]] = []
    counts = {
        "arm_push_or_stmdb_sp": 0,
        "arm_sub_sp_immediate": 0,
        "thumb_push": 0,
        "thumb_sub_sp_immediate": 0,
    }

    # ARM PUSH is commonly encoded as STMDB SP!, {registers}. Ignore the
    # condition field and reject empty register lists.
    for offset in range(0, len(text) - 3, 4):
        word = int.from_bytes(text[offset:offset + 4], "little")
        register_list = word & 0xFFFF
        if (word & 0x0FFF0000) == 0x092D0000 and register_list:
            counts["arm_push_or_stmdb_sp"] += 1
            candidates.append({
                "state": "arm",
                "pattern": "arm_push_or_stmdb_sp",
                "virtual_address": text_start + offset,
            })
        elif (word & 0x0FFF0000) == 0x024D0000 and (word & 0xFFF):
            counts["arm_sub_sp_immediate"] += 1
            candidates.append({
                "state": "arm",
                "pattern": "arm_sub_sp_immediate",
                "virtual_address": text_start + offset,
            })

    # Thumb PUSH uses 1011 010L rrrrrrrr; SUB SP, #imm7*4 uses 1011 0000 1iiiiiii.
    for offset in range(0, len(text) - 1, 2):
        halfword = int.from_bytes(text[offset:offset + 2], "little")
        if (halfword & 0xFE00) == 0xB400 and (halfword & 0x01FF):
            counts["thumb_push"] += 1
            candidates.append({
                "state": "thumb",
                "pattern": "thumb_push",
                "virtual_address": text_start + offset,
            })
        elif (halfword & 0xFF80) == 0xB080 and (halfword & 0x007F):
            counts["thumb_sub_sp_immediate"] += 1
            candidates.append({
                "state": "thumb",
                "pattern": "thumb_sub_sp_immediate",
                "virtual_address": text_start + offset,
            })

    summary = {
        "schema_version": 1,
        "status": "pass",
        "target": target_id,
        "text_size_bytes": text_size,
        "candidate_sites_total": len(candidates),
        "candidate_sites_by_pattern": counts,
        "addresses_emitted": False,
        "function_boundaries_verified": False,
        "interpretation": (
            "Heuristic prologue-like instruction sites only. Code and data may share "
            "the text segment; these counts do not identify proven functions."
        ),
    }
    return {"summary": summary, "private_candidates": candidates}


def main(argv: list[str] | None = None) -> int:
    from inspect_3ds_target import load_profiles

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", required=True, choices=sorted(load_profiles()))
    parser.add_argument("--exheader", required=True, type=Path)
    parser.add_argument("--code", required=True, type=Path)
    parser.add_argument(
        "--private-report",
        type=Path,
        help="optional address-level JSON output; must be outside the repository",
    )
    args = parser.parse_args(argv)

    try:
        result = scan_candidates(args.target, args.exheader, args.code)
        if args.private_report:
            destination = _outside_project(args.private_report)
            if destination in (args.exheader.expanduser().resolve(), args.code.expanduser().resolve()):
                raise CandidateScanError("private report must not overwrite either input")
            destination.parent.mkdir(parents=True, exist_ok=True)
            private_report = {
                **result["summary"],
                "addresses_emitted": True,
                "candidates": result["private_candidates"],
            }
            destination.write_text(
                json.dumps(private_report, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
        # Never print candidate addresses or raw game-derived instructions to stdout.
        print(json.dumps(result["summary"], indent=2, ensure_ascii=False))
        return 0
    except (CandidateScanError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
