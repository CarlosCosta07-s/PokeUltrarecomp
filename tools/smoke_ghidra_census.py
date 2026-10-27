#!/usr/bin/env python3
"""Run the Ghidra census script on a tiny synthetic ARM ELF; no game file is used."""
from __future__ import annotations

import argparse
import json
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEXT_ADDRESS = 0x00100000
SYNTHETIC_WORDS = (0xE3A00001, 0xE12FFF1E)  # MOV r0,#1 ; BX LR


def write_synthetic_arm_elf(destination: Path) -> None:
    """Write a minimal 32-bit little-endian ARM executable with one RX load segment."""
    ident = bytearray(16)
    ident[:4] = b"\x7fELF"
    ident[4] = 1  # ELFCLASS32
    ident[5] = 1  # ELFDATA2LSB
    ident[6] = 1  # EV_CURRENT
    elf_header = struct.pack(
        "<HHIIIIIHHHHHH",
        2,              # ET_EXEC
        40,             # EM_ARM
        1,              # EV_CURRENT
        TEXT_ADDRESS,   # e_entry
        52,             # e_phoff
        0,              # e_shoff
        0x05000000,     # e_flags (EABI5)
        52,             # e_ehsize
        32,             # e_phentsize
        1,              # e_phnum
        40,             # e_shentsize
        0,              # e_shnum
        0,              # e_shstrndx
    )
    segment_offset = 52 + 32
    code = struct.pack("<II", *SYNTHETIC_WORDS)
    program_header = struct.pack(
        "<IIIIIIII",
        1,              # PT_LOAD
        segment_offset,
        TEXT_ADDRESS,
        TEXT_ADDRESS,
        len(code),
        len(code),
        5,              # PF_R | PF_X
        4,              # p_align
    )
    destination.write_bytes(bytes(ident) + elf_header + program_header + code)


def validate_sidecars(summary_path: Path, candidates_path: Path) -> int:
    try:
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        candidates = json.loads(candidates_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise RuntimeError("Ghidra did not write both census sidecars") from None

    if not isinstance(summary, dict):
        raise RuntimeError("Ghidra summary is not a JSON object")
    if summary.get("schema_version") != 1 or summary.get("status") != "pass":
        raise RuntimeError("Ghidra summary schema/status is invalid")
    if summary.get("text_size_bytes") != len(SYNTHETIC_WORDS) * 4:
        raise RuntimeError("Ghidra summary text-size does not match the synthetic ELF")
    if summary.get("addresses_emitted") is not False or summary.get("disassembly_emitted") is not False:
        raise RuntimeError("Ghidra summary violated the aggregate-only output policy")
    if summary.get("function_boundaries_verified") is not False:
        raise RuntimeError("Ghidra summary overstates function-boundary verification")

    if not isinstance(candidates, dict) or set(candidates) != {
        "schema_version", "omitted_candidate_count", "candidates"
    }:
        raise RuntimeError("private candidate sidecar schema is invalid")
    if candidates.get("schema_version") != 1:
        raise RuntimeError("private candidate sidecar version is invalid")
    omitted = candidates.get("omitted_candidate_count")
    records = candidates.get("candidates")
    if isinstance(omitted, bool) or not isinstance(omitted, int) or omitted < 0:
        raise RuntimeError("private candidate sidecar omission counter is invalid")
    if not isinstance(records, list) or len(records) > 10000:
        raise RuntimeError("private candidate sidecar list is invalid")
    for item in records:
        if not isinstance(item, dict) or set(item) != {
            "entry_address", "body_size_bytes", "instruction_count", "words"
        }:
            raise RuntimeError("private candidate record schema is invalid")
        words = item.get("words")
        if not isinstance(words, list) or not all(isinstance(word, str) for word in words):
            raise RuntimeError("private candidate record words are invalid")

    # Ghidra should identify the synthetic entry function and sidecar it for the
    # current ARM subset. Do not print the entry address or raw instruction words.
    if not any(item.get("words") == [f"0x{word:08X}" for word in SYNTHETIC_WORDS] for item in records):
        raise RuntimeError("Ghidra did not recover the expected synthetic leaf candidate")
    return len(records)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ghidra-headless", required=True, type=Path)
    args = parser.parse_args(argv)
    headless = args.ghidra_headless.expanduser().resolve()
    if not headless.is_file():
        print("ERROR: configured Ghidra headless executable is unavailable", file=sys.stderr)
        return 2

    try:
        with tempfile.TemporaryDirectory(prefix="pokeultra-ghidra-smoke-") as tmp:
            work = Path(tmp).resolve()
            project = work / "project"
            project.mkdir()
            elf_path = work / "synthetic-arm.elf"
            summary_path = work / "summary.json"
            candidates_path = work / "private-candidates.json"
            log_path = work / "headless.log"
            script_log = work / "script.log"
            app_log = work / "application.log"
            write_synthetic_arm_elf(elf_path)
            command = [
                str(headless), str(project), "synthetic-arm-census",
                "-import", str(elf_path), "-overwrite",
                "-scriptPath", str(ROOT / "tools" / "ghidra_scripts"),
                "-log", str(app_log), "-scriptlog", str(script_log),
                "-deleteProject",
                "-postScript", "FunctionCensusSummary.java",
                str(summary_path), str(candidates_path),
                f"0x{TEXT_ADDRESS:08X}", str(len(SYNTHETIC_WORDS) * 4),
            ]
            with log_path.open("wb") as log:
                completed = subprocess.run(
                    command, cwd=work, stdout=log, stderr=subprocess.STDOUT,
                    timeout=300, check=False,
                )
            if completed.returncode != 0:
                # Never print Ghidra's private path-rich logs into public CI output.
                raise RuntimeError(f"Ghidra headless exited with code {completed.returncode}")
            candidate_records = validate_sidecars(summary_path, candidates_path)
    except (OSError, RuntimeError, subprocess.TimeoutExpired) as exc:
        message = str(exc)
        message = message.replace(str(ROOT), "<repository>")
        print(f"ERROR: synthetic Ghidra census smoke failed: {message[:200]}", file=sys.stderr)
        return 1

    print(json.dumps({
        "status": "pass",
        "synthetic_arm_elf_used": True,
        "ghidra_script_executed": True,
        "aggregate_summary_validated": True,
        "private_candidate_sidecar_validated": True,
        "synthetic_candidate_records": candidate_records,
        "game_bytes_or_addresses_uploaded": False,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
