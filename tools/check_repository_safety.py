#!/usr/bin/env python3
"""Dependency-free pre-commit checks for PokeUltrarecomp.

This is a conservative guardrail, not a legal review, malware scanner, or proof
that the entire Git history is clean. It checks the current index plus files
that Git would normally show as untracked and not ignored.
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import unquote, urlsplit

REQUIRED_FILES = (
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
)

# These extensions commonly contain title images, executable modules, or
# extracted resources. Generic .bin/.dat extensions are intentionally omitted.
PROHIBITED_EXTENSIONS = {
    ".3ds", ".3dsx", ".cia", ".cxi", ".cci", ".tik", ".tmd",
    ".firm", ".firmware", ".rom", ".nds", ".gba", ".bcsar",
    ".bclim", ".bflim", ".bcres", ".bflyt", ".sarc", ".narc",
    ".szs", ".cetk", ".exefs", ".romfs", ".ncch", ".ncsd",
    ".exheader", ".cro",
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


def git_candidate_paths(root: Path) -> list[str]:
    """Return indexed/tracked paths plus non-ignored untracked paths."""
    completed = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=root,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return sorted({item.decode("utf-8", errors="surrogateescape")
                   for item in completed.stdout.split(b"\0") if item})


def strip_fenced_blocks(text: str) -> str:
    return FENCED_BLOCK_RE.sub("", text)


def local_markdown_link_errors(root: Path, markdown_path: Path, text: str) -> list[str]:
    """Validate relative Markdown targets, ignoring anchors and external URLs."""
    errors: list[str] = []
    clean_text = strip_fenced_blocks(text)
    for match in INLINE_LINK_RE.finditer(clean_text):
        target = match.group(1).strip()
        # Remove an optional Markdown title after an angle-bracket target only
        # when the whole target is already a simple <path>.
        if target.startswith("<") and ">" in target:
            target = target[1:target.index(">")]
        else:
            # A space may introduce a Markdown link title. Keep simple targets;
            # do not attempt to parse complex quoted titles.
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
        resolved_root = root.resolve()
        destination = (resolved_root / markdown_path.parent / raw_path).resolve()
        try:
            destination.relative_to(resolved_root)
        except ValueError:
            errors.append(f"{markdown_path.as_posix()}: local link escapes repository root: {raw_path!r}")
            continue
        if not destination.exists():
            errors.append(f"{markdown_path.as_posix()}: broken local link target {raw_path!r}")
    return errors


def check_repository(root: Path) -> tuple[list[str], list[str]]:
    """Return (errors, notes) for the checked working tree/index."""
    errors: list[str] = []
    notes: list[str] = []
    root = root.resolve()

    if not (root / ".git").exists():
        errors.append(f"not a Git working tree: {root}")
        return errors, notes

    for required in REQUIRED_FILES:
        if not (root / required).is_file():
            errors.append(f"required project document missing: {required}")

    try:
        paths = git_candidate_paths(root)
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        errors.append(f"could not enumerate Git files: {exc}")
        return errors, notes

    for relative in paths:
        reason = prohibited_path_reason(relative)
        if reason:
            errors.append(f"{relative}: {reason}")

        candidate = root / relative
        if candidate.is_file() and not candidate.is_symlink() and candidate.suffix.casefold() == ".md":
            try:
                content = candidate.read_text(encoding="utf-8")
            except (OSError, UnicodeError):
                notes.append(f"skipped Markdown link scan for unreadable/non-UTF-8 file: {relative}")
                continue
            errors.extend(local_markdown_link_errors(root, Path(relative), content))

    notes.append(f"checked {len(paths)} indexed/tracked or non-ignored untracked paths")
    notes.append("ignored files that are not tracked are not scanned; a forced git add -f can bypass .gitignore")
    notes.append("this checker does not inspect Git history, content licensing, or the legality of any input")
    return errors, notes


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="Git working-tree root (default: current directory)")
    args = parser.parse_args(argv)

    try:
        subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=args.root, check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
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
    print("PASS: repository path and local Markdown-link checks completed.")
    print("This PASS does not certify licensing, source provenance, clean history, or game compatibility.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
