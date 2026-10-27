#!/usr/bin/env python3
"""Smoke-test the candidate body decoder with synthetic ARM and Thumb bytes."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import capstone  # noqa: E402
from summarize_arm_function_candidates import scan_bounded_return_bodies  # noqa: E402


def main() -> int:
    arm_start = 0x00100000
    arm = (0xE92D4010).to_bytes(4, "little") + (0xE12FFF1E).to_bytes(4, "little")
    arm_result = scan_bounded_return_bodies(
        arm, arm_start,
        [{"state": "arm", "pattern": "synthetic-arm-push", "virtual_address": arm_start}],
        capstone,
    )
    if arm_result["candidate_sites_with_linear_return"] != 1:
        raise SystemExit("ARM synthetic candidate did not reach BX LR")
    if arm_result["return_kinds"]["bx_lr"] != 1:
        raise SystemExit("ARM synthetic BX LR return was not classified")
    arm_candidate = arm_result["private_bounded_candidates"][0]
    if arm_candidate["span_bytes_to_return"] != 8 or arm_candidate["instruction_count_to_return"] != 2:
        raise SystemExit("ARM synthetic candidate span differs from expected 8 bytes / 2 instructions")

    thumb_start = 0x00200000
    thumb = (0xB510).to_bytes(2, "little") + (0x4770).to_bytes(2, "little")
    thumb_result = scan_bounded_return_bodies(
        thumb, thumb_start,
        [{"state": "thumb", "pattern": "synthetic-thumb-push", "virtual_address": thumb_start}],
        capstone,
    )
    if thumb_result["candidate_sites_with_linear_return"] != 1:
        raise SystemExit("Thumb synthetic candidate did not reach BX LR")
    if thumb_result["return_kinds"]["bx_lr"] != 1:
        raise SystemExit("Thumb synthetic BX LR return was not classified")
    thumb_candidate = thumb_result["private_bounded_candidates"][0]
    if thumb_candidate["span_bytes_to_return"] != 4 or thumb_candidate["instruction_count_to_return"] != 2:
        raise SystemExit("Thumb synthetic candidate span differs from expected 4 bytes / 2 instructions")

    print("Candidate body decoder smoke test: ARM and Thumb synthetic return patterns passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())