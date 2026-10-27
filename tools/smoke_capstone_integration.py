#!/usr/bin/env python3
"""Smoke-test the real Capstone Python package using only synthetic Thumb bytes."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import capstone  # noqa: E402
from disassemble_retail_range import disassemble_retail_range  # noqa: E402


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="pokeultra-capstone-smoke-") as temporary:
        work = Path(temporary)
        exheader_path = work / "synthetic.exheader"
        code_path = work / "synthetic.code"
        report_path = work / "synthetic-report.json"

        exheader = bytearray(0x208)
        exheader[0:8] = b"TestGame"
        exheader[0x200:0x208] = int("00040000001B5000", 16).to_bytes(8, "little")
        for (address, pages, size), offset in zip(
            ((0x00100000, 1, 0x80), (0x00200000, 1, 0x40), (0x00300000, 1, 0x20)),
            (0x10, 0x20, 0x30),
        ):
            exheader[offset:offset + 4] = address.to_bytes(4, "little")
            exheader[offset + 4:offset + 8] = pages.to_bytes(4, "little")
            exheader[offset + 8:offset + 12] = size.to_bytes(4, "little")
        exheader_path.write_bytes(exheader)

        # Thumb NOP encoding is 00 BF in little-endian byte order.
        code = (b"\x00\xbf" * 0x40) + (b"\x00" * (0x3000 - 0x80))
        code_path.write_bytes(code)
        report = disassemble_retail_range(
            "ultra-sun",
            exheader_path,
            code_path,
            "thumb",
            0x00100000,
            4,
            report_path,
        )
        instructions = report["instructions"]
        if [item["mnemonic"] for item in instructions] != ["nop", "nop"]:
            raise RuntimeError(f"unexpected Capstone output: {instructions!r}")
        if [item["bytes_hex"] for item in instructions] != ["00bf", "00bf"]:
            raise RuntimeError(f"incorrect decoded instruction bytes: {instructions!r}")
        if not report_path.is_file():
            raise RuntimeError("private JSON report was not written")
        print(
            f"PASS: Capstone {capstone.__version__} decoded two synthetic Thumb NOPs "
            "with exact byte coverage; no retail data was used"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
