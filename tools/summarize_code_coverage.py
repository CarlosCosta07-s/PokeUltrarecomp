#!/usr/bin/env python3
"""Aggregate decoder coverage over consecutive explicit windows of a local .code file.

The summary contains counts and coarse opcode classes only: no individual
encodings, no per-instruction addresses and no bytes from the executable. It
tells a maintainer which instruction families the decoder still lacks for a
region they chose, so the next implementation step is driven by evidence.
"""
from __future__ import annotations
import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import inspect_3ds_code_range as ranges  # noqa: E402

MAX_WINDOWS = 256
END_OF_TEXT_MARKERS = ("extends beyond declared .text", "outside declared .text", "crosses the declared .text boundary")


def _opcode_class(state: str, item: dict[str, Any]) -> str:
    """Coarse class of an unsupported encoding (never the encoding itself)."""
    parts = [int(token, 16) for token in str(item["encoding"]).split()]
    if state == "arm":
        return f"0x{(parts[0] >> 20) & 0xFF:02X}"
    if item["decode_status"] == "unsupported-thumb32":
        return f"0x{parts[0] & 0xF800:04X}/0x{parts[1] & 0xF800:04X}"
    return f"0x{parts[0] >> 8:02X}xx"


def summarize_coverage(
    target_id: str,
    exheader_path: Path,
    code_path: Path,
    state: str,
    start_address: int,
    instructions_per_window: int,
    windows: int,
    *,
    title_id: str | None = None,
    allow_unverified_target: bool = False,
    top: int = 16,
) -> dict[str, Any]:
    if isinstance(windows, bool) or not isinstance(windows, int) or not 1 <= windows <= MAX_WINDOWS:
        raise ranges.TargetRangeError(f"window count must be an integer in 1..{MAX_WINDOWS}")
    if isinstance(top, bool) or not isinstance(top, int) or not 1 <= top <= 256:
        raise ranges.TargetRangeError("top must be an integer in 1..256")

    totals: Counter[str] = Counter()
    decoded_kinds: Counter[str] = Counter()
    unsupported_classes: Counter[str] = Counter()
    flow: Counter[str] = Counter()
    first: dict[str, Any] | None = None
    cursor = start_address
    stopped_reason: str | None = None
    windows_done = 0

    for window in range(windows):
        try:
            report = ranges.inspect_code_range(
                target_id, exheader_path, code_path, state, cursor, instructions_per_window,
                title_id=title_id, allow_unverified_target=allow_unverified_target,
                include_unsupported=True,
            )
        except ranges.TargetRangeError as exc:
            if window > 0 and any(marker in str(exc) for marker in END_OF_TEXT_MARKERS):
                stopped_reason = "reached the end of declared .text; the last partial window is not counted"
                break
            raise
        first = first or report
        windows_done += 1
        for item in report["instructions"]:
            size = int(item["instruction_size_bytes"])
            totals["instructions"] += 1
            totals["bytes"] += size
            if item["decode_status"] == "decoded":
                totals["decoded"] += 1
                totals["decoded_bytes"] += size
                decoded_kinds[str(item["mnemonic"]).split()[0]] += 1
            else:
                totals["unsupported"] += 1
                totals["unsupported_bytes"] += size
                unsupported_classes[_opcode_class(state, item)] += 1
            ir = item.get("decoded_ir")
            kind = ir[0] if ir else None
            if kind == "branch":
                flow["direct_branches"] += 1
                if item.get("branch_target_within_declared_text") is False:
                    flow["branch_targets_outside_declared_text"] += 1
            elif kind == "call":
                flow["calls"] += 1
                if item.get("branch_target_within_declared_text") is False:
                    flow["branch_targets_outside_declared_text"] += 1
            elif item.get("indirect_branch"):
                flow["indirect_branches"] += 1
            elif kind == "return":
                flow["returns"] += 1
            elif kind == "ldr_literal":
                flow["literal_loads"] += 1
                if item.get("literal_within_declared_text") is False:
                    flow["literals_outside_declared_text"] += 1
                if item.get("literal_overlaps_selected_range"):
                    flow["literals_inside_their_own_window"] += 1
            elif kind == "push":
                flow["stack_pushes"] += 1
            elif kind in ("pop", "pop_pc"):
                flow["stack_pops"] += 1
        cursor = int(report["range"]["selected_range_end"], 16)

    assert first is not None
    decoded = totals["decoded"]
    total = totals["instructions"]
    return {
        "schema_version": 1,
        "status": "coverage-summary-explicit-range",
        "target": first["target"],
        "range": {
            "state": state,
            "start_address": f"0x{start_address:08X}",
            "end_address": f"0x{cursor:08X}",
            "windows_requested": windows,
            "windows_counted": windows_done,
            "instructions_per_window": instructions_per_window,
            "stopped_reason": stopped_reason,
        },
        "input": {
            "exheader_sha256": first["input"]["exheader_sha256"],
            "code_sha256": first["input"]["code_sha256"],
        },
        "coverage": {
            "instructions": total,
            "decoded": decoded,
            "unsupported": totals["unsupported"],
            "decoded_ratio": round(decoded / total, 4) if total else 0.0,
            "bytes": totals["bytes"],
            "decoded_bytes": totals["decoded_bytes"],
            "unsupported_bytes": totals["unsupported_bytes"],
        },
        "decoded_by_mnemonic": dict(sorted(decoded_kinds.items(), key=lambda kv: (-kv[1], kv[0]))),
        "unsupported_by_opcode_class": [
            {"opcode_class": name, "count": count}
            for name, count in sorted(unsupported_classes.items(), key=lambda kv: (-kv[1], kv[0]))[:top]
        ],
        "flow": dict(sorted(flow.items())),
        "limitations": [
            "Consecutive linear windows from one explicit start address; no function discovery and no ARM/Thumb state detection.",
            "Literal pools, jump tables and other data inside the range are counted as instructions or unsupported entries, so ratios are indicative only.",
            "Opcode classes are coarse (Thumb-16: high byte; Thumb-32: both top-five-bit prefixes; ARM: bits 27:20) and are for choosing the next family to implement.",
            "A high decoded ratio is not semantic validation and is not evidence of game compatibility.",
            "Keep the summary local unless it has been reviewed; it is derived from local game code.",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    profiles = ranges.intake.load_profiles()
    parser = argparse.ArgumentParser(
        description="Summarize decoder coverage over consecutive explicit windows of a local decompressed .code file."
    )
    parser.add_argument("--target", required=True, choices=sorted(profiles))
    parser.add_argument("--exheader", required=True, type=Path)
    parser.add_argument("--code", required=True, type=Path)
    parser.add_argument("--state", required=True, choices=("arm", "thumb"))
    parser.add_argument("--start-address", required=True, type=ranges.parse_address)
    parser.add_argument("--instructions-per-window", type=int, default=256)
    parser.add_argument("--windows", type=int, default=1, help=f"consecutive windows to scan (1..{MAX_WINDOWS})")
    parser.add_argument("--top", type=int, default=16, help="unsupported opcode classes to list (1..256)")
    parser.add_argument("--title-id")
    parser.add_argument("--allow-unverified-target", action="store_true")
    parser.add_argument("--report", type=Path, help="write the summary outside the repository")
    args = parser.parse_args(argv)
    try:
        summary = summarize_coverage(
            args.target, args.exheader, args.code, args.state, args.start_address,
            args.instructions_per_window, args.windows, title_id=args.title_id,
            allow_unverified_target=args.allow_unverified_target, top=args.top,
        )
        rendered = json.dumps(summary, indent=2, ensure_ascii=False) + "\n"
        if args.report:
            target_path = args.report.resolve()
            if target_path == ROOT or ROOT in target_path.parents:
                raise ranges.TargetRangeError("report output must be outside the repository")
            args.report.write_text(rendered, encoding="utf-8", newline="\n")
        else:
            sys.stdout.write(rendered)
        return 0
    except (ranges.TargetRangeError, OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
