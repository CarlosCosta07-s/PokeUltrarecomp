#!/usr/bin/env python3
"""Run the 3DS container intake locally without uploading game data or using a URL."""

from __future__ import annotations

import argparse
import json
import re
import sys
import tempfile
from pathlib import Path

import remote_3ds_intake as intake


ROOT = Path(__file__).resolve().parents[1]
MAX_IMAGE_BYTES = 8 * 1024**3
ARCHIVE_SUFFIXES = (".7z", ".zip", ".rar", ".tar", ".gz", ".xz")


def validate_local_image(image_path: Path, format_name: str) -> Path:
    """Validate a user-supplied local image and keep it outside the repository."""
    fmt, _ = intake.normalize_format(format_name)
    try:
        resolved = image_path.expanduser().resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise intake.IntakeError("local input image does not exist or cannot be resolved") from exc

    if not resolved.is_file():
        raise intake.IntakeError("local input must be a regular image file")

    try:
        resolved.relative_to(ROOT.resolve())
    except ValueError:
        pass
    else:
        raise intake.IntakeError(
            "keep the game image outside the repository; do not add it to Git"
        )

    lowered_name = resolved.name.casefold()
    if lowered_name.endswith(ARCHIVE_SUFFIXES) or re.search(r"\.\d{3}$", lowered_name):
        raise intake.IntakeError(
            "input appears to be a compressed archive or split archive part; "
            "extract it locally first and point to the resulting .3ds, .cci, or .cia file"
        )

    expected_suffix = "." + fmt
    if resolved.suffix.casefold() in {".3ds", ".cci", ".cia"} and resolved.suffix.casefold() != expected_suffix:
        raise intake.IntakeError(
            f"format mismatch: the file extension is {resolved.suffix}, but --format selected {expected_suffix}"
        )

    try:
        size = resolved.stat().st_size
    except OSError as exc:
        raise intake.IntakeError("cannot read local image metadata") from exc
    if size <= 0:
        raise intake.IntakeError("local input image is empty")
    if size > MAX_IMAGE_BYTES:
        raise intake.IntakeError("input image exceeds the 8 GiB safety limit")

    return resolved


def process_local(
    image_path: Path,
    target: str,
    format_name: str,
    ctrtool_path: Path,
    index: int = 0,
    ghidra_headless_path: Path | None = None,
) -> dict:
    """Analyze a local image with temporary extraction; never download or upload it."""
    if not 0 <= index <= 65535:
        raise intake.IntakeError("partition/content index must be from 0 to 65535")

    image = validate_local_image(image_path, format_name)
    try:
        ctrtool = ctrtool_path.expanduser().resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise intake.IntakeError("CTRTool executable does not exist") from exc
    if not ctrtool.is_file():
        raise intake.IntakeError("CTRTool path must identify a file")

    ghidra = None
    if ghidra_headless_path is not None:
        try:
            ghidra = ghidra_headless_path.expanduser().resolve(strict=True)
        except (OSError, RuntimeError) as exc:
            raise intake.IntakeError("Ghidra analyzeHeadless executable does not exist") from exc
        if not ghidra.is_file():
            raise intake.IntakeError("Ghidra path must identify a file")

    with tempfile.TemporaryDirectory(prefix="pokeultra-local-intake-") as temporary:
        result = intake.extract_and_inspect(
            image,
            target,
            format_name,
            [str(ctrtool)],
            Path(temporary) / "extract",
            ncch_index=index,
            candidate_decode_summary=True,
            ghidra_headless_path=ghidra,
        )

    # This record is intentionally aggregate-only: no input path, bytes, hashes,
    # function addresses, instruction words, or disassembly are emitted.
    return {
        "status": result["status"],
        "source_mode": "local",
        "source_uploaded": False,
        "source_path_emitted": False,
        "target": result["target"],
        "format": result["format"],
        "text_size_bytes": result["text_size_bytes"],
        "decompressed_code_size_bytes": result["decompressed_code_size_bytes"],
        "container_title_id_supplied": result["container_title_id_supplied"],
        "container_title_id_match": result["container_title_id_match"],
        "container_title_kind": result["container_title_kind"],
        "candidate_census": result["candidate_census"],
        "ghidra_function_census": result["ghidra_function_census"],
        "native_semantic_equivalence_verified": False,
        "game_started": False,
    }


def main(argv: list[str] | None = None) -> int:
    from inspect_3ds_target import load_profiles

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", required=True, type=Path, help="local .3ds, .cci, or .cia file; never uploaded")
    parser.add_argument("--target", choices=sorted(load_profiles()), required=True)
    parser.add_argument("--format", choices=sorted(intake.FORMATS), required=True)
    parser.add_argument("--ctrtool", required=True, type=Path, help="path to the locally installed CTRTool executable")
    parser.add_argument("--ncch-index", type=int, default=0)
    parser.add_argument(
        "--ghidra-headless",
        type=Path,
        help="optional local Ghidra analyzeHeadless executable; only aggregate results are emitted",
    )
    args = parser.parse_args(argv)

    try:
        result = process_local(
            args.image,
            args.target,
            args.format,
            args.ctrtool,
            args.ncch_index,
            ghidra_headless_path=args.ghidra_headless,
        )
    except intake.IntakeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    except OSError:
        print("ERROR: local intake failed due to an operating-system error", file=sys.stderr)
        return 2

    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
