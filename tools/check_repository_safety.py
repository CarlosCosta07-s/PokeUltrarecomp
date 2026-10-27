#!/usr/bin/env python3
"""Dependency-free pre-commit checks for PokeUltrarecomp.

This is a conservative guardrail, not a legal review, malware scanner, or proof
that the entire Git history is clean. It inspects both staged Git-index blobs
and current working-tree files (including non-ignored untracked files).
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import unquote, urlsplit

REQUIRED_FILES = (
    ".gitignore",
    "README.md",
    "LICENSE",
    "CONTRIBUTING.md",
    "SECURITY.md",
    "THIRD_PARTY_NOTICES.md",
    "docs/ROADMAP.md",
    "docs/AUDIT.md",
    "docs/ARCHITECTURE.md",
    "docs/BUILD_NOTES.md",
    "docs/LEGAL_AND_IP.md",
    "docs/REFERENCE_TEST_001.md",
    "docs/POC_001_SPEC.md",
    "docs/CODEBASE_RESEARCH.md",
    "tools/arm_subset_poc.py",
    "tests/test_arm_subset_poc.py",
    "tools/inspect_3ds_target.py",
    "tests/test_inspect_3ds_target.py",
    "tools/thumb_subset_poc.py",
    "tools/inspect_3ds_code_range.py",
    "tools/arm_thumb_effects.py",
    "tests/test_arm_thumb_effects.py",
    "tools/arm_thumb_cfg.py",
    "tests/test_arm_thumb_cfg.py",
    "tests/test_inspect_3ds_code_range.py",
    "docs/CODE_RANGE_INSPECTION.md",
    "tests/test_thumb_subset_poc.py",
    "docs/THUMB_POC_002.md",
    "targets/pokemon_ultra_sun.json",
    "targets/pokemon_ultra_moon.json",
    "docs/GAME_TARGET_INTAKE.md",
    "tools/arm_flags.py",
    "tests/test_arm_flags.py",
    "tools/arm_differential_poc.py",
    "tests/test_arm_differential_poc.py",
    "CMakeLists.txt",
    ".github/workflows/native-pipeline.yml",
    "tools/run_native_poc_pipeline.py",
    "tools/generate_native_abi_fixtures.py",
    "include/pokeultrarecomp/native_abi.h",
    "tests/native_runtime_host.cpp",
    "tools/wrap_retail_code.py",
    "tests/test_wrap_retail_code.py",
    "tools/disassemble_retail_range.py",
    "tools/requirements-analysis.txt",
    "tools/smoke_capstone_integration.py",
    ".github/workflows/analysis-tools.yml",
    "tests/test_disassemble_retail_range.py",
    "docs/REAL_GAME_CODE_WORKFLOW.md",
)

# These extensions commonly contain title images, executable modules, or
# extracted resources. Generic .bin/.dat extensions are intentionally omitted.
PROHIBITED_EXTENSIONS = {
    ".3ds", ".3dsx", ".cia", ".cxi", ".cci", ".tik", ".tmd",
    ".firm", ".firmware", ".rom", ".nds", ".gba", ".bcsar",
    ".bcseq", ".bcstm", ".bcwav", ".bfres", ".bclim", ".bflim",
    ".bcres", ".bflyt", ".sarc", ".narc", ".szs", ".cetk",
    ".exefs", ".romfs", ".ncch", ".ncsd", ".exheader", ".cro",
    ".code", ".sav", ".garc",
}

PROHIBITED_FILENAMES = {
    "boot9.bin", "boot11.bin", "seeddb.bin", "movable.sed", "otp.bin",
    "aes_keys.txt", "prod.keys", "title.keys",
}
PROHIBITED_DIRS = {
    "roms", "dumps", "firmware", "keys", "extracted",
    "resources-extracted", "romfs", "analysis-private", "data-local",
    "runtime-local", "saves-local", "profiles-local",
}

# Deliberately simple inline Markdown link matcher; it is not a full CommonMark
# parser. Link targets with whitespace or nested parentheses should be reviewed
# manually if this checker cannot interpret them.
INLINE_LINK_RE = re.compile(r"(?<!!)\[[^\]]*\]\(([^)]+)\)")
FENCED_BLOCK_RE = re.compile(r"\x60\x60\x60.*?\x60\x60\x60|~~~.*?~~~", re.DOTALL)


def prohibited_path_reason(path_text: str) -> str | None:
    """Return a human-readable policy failure for a suspicious path, if any."""
    path = Path(path_text.replace("\\", "/"))
    parts = [part.casefold() for part in path.parts]
    basename = parts[-1] if parts else ""

    if basename in PROHIBITED_FILENAMES:
        return f"sensitive Nintendo 3DS key/system filename: {basename}"
    if basename == ".env" or (basename.startswith(".env.") and basename != ".env.example"):
        return "environment file may contain secrets"
    bad_dirs = sorted(set(parts[:-1]) & PROHIBITED_DIRS)
    if bad_dirs:
        return f"local/proprietary-data directory: {bad_dirs[0]}"
    suffix = Path(basename).suffix.casefold()
    if suffix in PROHIBITED_EXTENSIONS:
        return f"potential game image/module/resource extension: {suffix}"
    return None


def git_index_entries(root: Path) -> list[tuple[str, str, int]]:
    """Return (path, object id, stage) for every Git index entry."""
    completed = subprocess.run(
        ["git", "ls-files", "--stage", "-z"],
        cwd=root,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    entries: list[tuple[str, str, int]] = []
    for item in completed.stdout.split(b"\0"):
        if not item:
            continue
        metadata, raw_path = item.split(b"\t", 1)
        _mode, object_id, stage_text = metadata.decode("ascii").split()
        path = raw_path.decode("utf-8", errors="surrogateescape")
        entries.append((path, object_id, int(stage_text)))
    return entries


def git_untracked_paths(root: Path) -> list[str]:
    """Return untracked paths not excluded by .gitignore or Git excludes."""
    completed = subprocess.run(
        ["git", "ls-files", "--others", "--exclude-standard", "-z"],
        cwd=root,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return sorted({
        item.decode("utf-8", errors="surrogateescape")
        for item in completed.stdout.split(b"\0") if item
    })


def read_git_blob(root: Path, object_id: str) -> bytes:
    """Read the exact staged/index blob, without applying checkout filters."""
    completed = subprocess.run(
        ["git", "cat-file", "blob", object_id],
        cwd=root,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return completed.stdout


def strip_fenced_blocks(text: str) -> str:
    return FENCED_BLOCK_RE.sub("", text)


def local_markdown_link_errors(
    root: Path,
    markdown_path: Path,
    text: str,
    *,
    source_label: str = "working tree",
    available_paths: set[str] | None = None,
) -> list[str]:
    """Validate relative Markdown targets, ignoring anchors and external URLs."""
    errors: list[str] = []
    clean_text = strip_fenced_blocks(text)
    resolved_root = root.resolve()
    paths = available_paths or set()

    for match in INLINE_LINK_RE.finditer(clean_text):
        target = match.group(1).strip()
        if target.startswith("<") and ">" in target:
            target = target[1:target.index(">")]
        else:
            target = target.split("\t", 1)[0]
            if " " in target and not target.startswith(("http://", "https://", "mailto:")):
                target = target.split(" ", 1)[0]
        if not target or target.startswith("#"):
            continue
        parsed = urlsplit(target)
        if parsed.scheme or parsed.netloc:
            continue
        raw_path = unquote(parsed.path)
        if not raw_path:
            continue

        destination = (resolved_root / markdown_path.parent / raw_path).resolve()
        try:
            relative_target = destination.relative_to(resolved_root).as_posix()
        except ValueError:
            errors.append(
                f"{source_label}: {markdown_path.as_posix()}: "
                f"local link escapes repository root: {raw_path!r}"
            )
            continue

        exists_in_index = (
            relative_target in paths
            or any(path.startswith(relative_target.rstrip("/") + "/") for path in paths)
        )
        if not destination.exists() and not exists_in_index:
            errors.append(
                f"{source_label}: {markdown_path.as_posix()}: "
                f"broken local link target {raw_path!r}"
            )
    return errors


def check_repository(root: Path) -> tuple[list[str], list[str]]:
    """Return (errors, notes) for the staged index and working tree."""
    errors: list[str] = []
    notes: list[str] = []
    root = root.resolve()

    if not (root / ".git").exists():
        errors.append(f"not a Git working tree: {root}")
        return errors, notes

    try:
        index_entries = git_index_entries(root)
        untracked_paths = git_untracked_paths(root)
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        errors.append(f"could not enumerate Git index/worktree files: {exc}")
        return errors, notes

    index_stages: dict[str, set[int]] = {}
    index_paths: set[str] = set()
    stage_zero_paths: set[str] = set()
    for relative, _object_id, stage in index_entries:
        index_paths.add(relative)
        index_stages.setdefault(relative, set()).add(stage)
        if stage == 0:
            stage_zero_paths.add(relative)

    for required in REQUIRED_FILES:
        if required not in stage_zero_paths:
            errors.append(f"required project document missing or conflicted in Git index: {required}")

    candidate_paths = sorted(index_paths | set(untracked_paths))
    for relative in candidate_paths:
        reason = prohibited_path_reason(relative)
        if reason:
            errors.append(f"{relative}: {reason}")

    # Check staged Markdown blobs as committed, not merely their current
    # working-tree replacements. This catches staged/unstaged divergence.
    index_markdown: dict[str, bytes] = {}
    for relative, object_id, stage in index_entries:
        if stage != 0:
            errors.append(f"{relative}: unresolved merge conflict in Git index (stage {stage})")
            continue
        if Path(relative).suffix.casefold() != ".md":
            continue
        try:
            content_bytes = read_git_blob(root, object_id)
            index_markdown[relative] = content_bytes
            content = content_bytes.decode("utf-8")
        except (subprocess.CalledProcessError, UnicodeError):
            notes.append(f"skipped staged Markdown link scan for unreadable/non-UTF-8 blob: {relative}")
            continue
        errors.extend(local_markdown_link_errors(
            root,
            Path(relative),
            content,
            source_label="Git index",
            available_paths=stage_zero_paths,
        ))

    # Check working-tree replacements and non-ignored untracked files too.
    # If a Markdown file is byte-for-byte identical to its indexed blob, skip
    # the duplicate scan; staged versions have already been checked above.
    for relative in candidate_paths:
        candidate = root / relative
        if candidate.is_symlink() or not candidate.is_file():
            continue
        try:
            resolved_candidate = candidate.resolve()
            resolved_candidate.relative_to(root)
        except ValueError:
            errors.append(f"{relative}: working-tree path resolves outside repository root")
            continue
        if candidate.suffix.casefold() != ".md":
            continue
        try:
            content_bytes = candidate.read_bytes()
            if index_markdown.get(relative) == content_bytes:
                continue
            content = content_bytes.decode("utf-8")
        except (OSError, UnicodeError):
            notes.append(f"skipped working-tree Markdown link scan for unreadable/non-UTF-8 file: {relative}")
            continue
        errors.extend(local_markdown_link_errors(
            root,
            Path(relative),
            content,
            source_label="working tree",
            available_paths=stage_zero_paths,
        ))

    notes.append(
        f"checked {len(index_paths)} indexed paths and "
        f"{len(untracked_paths)} non-ignored untracked paths"
    )
    notes.append(
        "ignored files that are not tracked are not scanned; a forced git add -f can bypass .gitignore"
    )
    notes.append(
        "this checker does not inspect Git history, content licensing, or the legality of any input"
    )
    return errors, notes


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=Path.cwd(),
        help="Git working-tree root (default: current directory)",
    )
    args = parser.parse_args(argv)

    try:
        subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=args.root,
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        print(f"FAIL: cannot find a Git working tree or Git executable: {exc}", file=sys.stderr)
        return 2

    errors, notes = check_repository(args.root)
    for note in notes:
        print(f"NOTE: {note}")
    if errors:
        for error in errors:
            print(f"FAIL: {error}", file=sys.stderr)
        print(f"Repository safety check failed with {len(errors)} issue(s).", file=sys.stderr)
        return 1
    print("PASS: repository path and Markdown-link checks completed.")
    print("This PASS does not certify licensing, source provenance, clean history, or game compatibility.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
