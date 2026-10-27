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


def _return_kind(instruction: Any) -> str | None:
    """Classify only common return-like encodings; this is not a CFG proof."""
    mnemonic = str(getattr(instruction, "mnemonic", "")).casefold().split(".", 1)[0]
    operands = str(getattr(instruction, "op_str", "")).casefold().replace(" ", "")
    if mnemonic == "bx" and operands == "lr":
        return "bx_lr"
    if mnemonic == "mov" and operands == "pc,lr":
        return "mov_pc_lr"
    if mnemonic == "pop" and "pc" in operands:
        return "pop_pc"
    if mnemonic.startswith("ldm") and "sp" in operands and "pc" in operands:
        return "ldm_sp_pc"
    return None


def scan_bounded_return_bodies(
    text: bytes,
    text_start: int,
    candidates: list[dict[str, Any]],
    capstone_module: Any,
    *,
    max_window_bytes: int = 512,
    max_instructions: int = 96,
) -> dict[str, Any]:
    """Count candidates that linearly decode to a return-like instruction."""
    if max_window_bytes <= 0 or max_instructions <= 0:
        raise CandidateScanError("bounded decode limits must be positive")
    engines: dict[str, Any] = {}
    for state, mode in (
        ("arm", capstone_module.CS_MODE_ARM),
        ("thumb", capstone_module.CS_MODE_THUMB),
    ):
        engine = capstone_module.Cs(
            capstone_module.CS_ARCH_ARM,
            mode | capstone_module.CS_MODE_LITTLE_ENDIAN,
        )
        engine.detail = False
        engines[state] = engine

    bounded: list[dict[str, Any]] = []
    terminators = {"bx_lr": 0, "mov_pc_lr": 0, "pop_pc": 0, "ldm_sp_pc": 0}
    for candidate in candidates:
        state = str(candidate["state"])
        address = int(candidate["virtual_address"])
        offset = address - text_start
        if state not in engines or offset < 0 or offset >= len(text):
            continue
        window = text[offset:offset + max_window_bytes]
        engine = engines[state]
        try:
            instructions = engine.disasm(window, address, count=max_instructions)
            cursor = address
            count = 0
            return_kind = None
            for instruction in instructions:
                if int(instruction.size) <= 0 or int(instruction.address) != cursor:
                    break
                cursor += int(instruction.size)
                count += 1
                return_kind = _return_kind(instruction)
                if return_kind:
                    break
                mnemonic = str(getattr(instruction, "mnemonic", "")).casefold().split(".", 1)[0]
                # Do not pretend a linear scan can follow an unconditional branch
                # to a distant epilogue or prove reachability across control flow.
                if mnemonic == "b":
                    break
        except Exception as exc:
            raise CandidateScanError("Capstone failed during bounded candidate decode") from exc
        if return_kind:
            terminators[return_kind] += 1
            bounded.append({
                "state": state,
                "pattern": candidate["pattern"],
                "virtual_address": address,
                "span_bytes_to_return": cursor - address,
                "instruction_count_to_return": count,
                "return_kind": return_kind,
            })

    return {
        "max_window_bytes": max_window_bytes,
        "max_instructions": max_instructions,
        "candidate_sites_with_linear_return": len(bounded),
        "candidate_sites_with_linear_return_by_state": {
            "arm": sum(item["state"] == "arm" for item in bounded),
            "thumb": sum(item["state"] == "thumb" for item in bounded),
        },
        "candidate_sites_with_return_within_16_instructions": sum(
            item["instruction_count_to_return"] <= 16 for item in bounded
        ),
        "return_kinds": terminators,
        "function_boundaries_verified": False,
        "addresses_emitted": False,
    } | {"private_bounded_candidates": bounded}


def scan_candidates(
    target_id: str,
    exheader_path: Path,
    code_path: Path,
    *,
    preflight: dict[str, Any] | None = None,
    decode_summary: bool = False,
    capstone_module: Any | None = None,
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

    bounded_body_scan = None
    if decode_summary:
        if capstone_module is None:
            try:
                import capstone as capstone_module
            except ImportError as exc:
                raise CandidateScanError(
                    "Capstone is required for bounded return scanning; install tools/requirements-analysis.txt"
                ) from exc
        bounded_body_scan = scan_bounded_return_bodies(
            text, text_start, candidates, capstone_module
        )

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
    if bounded_body_scan is not None:
        summary["bounded_return_scan"] = {
            key: value for key, value in bounded_body_scan.items()
            if key != "private_bounded_candidates"
        }
    return {
        "summary": summary,
        "private_candidates": candidates,
        "private_bounded_candidates": (
            bounded_body_scan["private_bounded_candidates"]
            if bounded_body_scan is not None else []
        ),
    }


def main(argv: list[str] | None = None) -> int:
    from inspect_3ds_target import load_profiles

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", required=True, choices=sorted(load_profiles()))
    parser.add_argument("--exheader", required=True, type=Path)
    parser.add_argument("--code", required=True, type=Path)
    parser.add_argument(
        "--decode-summary",
        action="store_true",
        help="use Capstone to count heuristic candidates that linearly reach a return-like instruction",
    )
    parser.add_argument(
        "--private-report",
        type=Path,
        help="optional address-level JSON output; must be outside the repository",
    )
    args = parser.parse_args(argv)

    try:
        result = scan_candidates(
            args.target, args.exheader, args.code,
            decode_summary=args.decode_summary,
        )
        if args.private_report:
            destination = _outside_project(args.private_report)
            if destination in (args.exheader.expanduser().resolve(), args.code.expanduser().resolve()):
                raise CandidateScanError("private report must not overwrite either input")
            destination.parent.mkdir(parents=True, exist_ok=True)
            private_report = {
                **result["summary"],
                "addresses_emitted": True,
                "candidates": result["private_candidates"],
                "bounded_return_candidates": result["private_bounded_candidates"],
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
