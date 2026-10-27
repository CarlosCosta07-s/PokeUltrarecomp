#!/usr/bin/env python3
"""Remote 3DS image intake using a secret HTTPS source URL and ephemeral storage."""
from __future__ import annotations
import argparse
import ipaddress
import json
import os
import subprocess
import sys
import tempfile
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAX_BYTES = 8 * 1024**3
FORMATS = {"3ds": "ncsd", "cci": "ncsd", "cia": "cia"}


class IntakeError(ValueError):
    pass


def normalize_format(value: str) -> tuple[str, str]:
    fmt = value.strip().lower().lstrip(".")
    if fmt == "ccd":
        raise IntakeError(".ccd is not a Nintendo 3DS container; use .3ds/.cci or .cia")
    if fmt not in FORMATS:
        raise IntakeError("supported formats: .3ds, .cci, .cia")
    return fmt, FORMATS[fmt]


def validate_url(value: str) -> None:
    try:
        parsed = urllib.parse.urlsplit(value.strip())
        port = parsed.port
    except ValueError as exc:
        raise IntakeError("invalid source URL; the URL is never written to logs") from exc
    if parsed.scheme.lower() != "https" or not parsed.hostname:
        raise IntakeError("source must be an HTTPS direct-download URL")
    if parsed.username or parsed.password or port not in (None, 443):
        raise IntakeError("use HTTPS on the standard port without embedded credentials")
    host = parsed.hostname.rstrip(".").casefold()
    if host in {"localhost", "localhost.localdomain"} or host.endswith((".local", ".localhost")):
        raise IntakeError("local hostnames are not accepted")
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        ip = None
    if ip is not None and not ip.is_global:
        raise IntakeError("private/reserved IP addresses are not accepted")


class HTTPSRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if urllib.parse.urlsplit(newurl).scheme.lower() != "https":
            raise IntakeError("download redirected away from HTTPS")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def download(source_url: str, destination: Path) -> int:
    validate_url(source_url)
    opener = urllib.request.build_opener(HTTPSRedirect())
    request = urllib.request.Request(source_url, headers={"User-Agent": "PokeUltrarecomp/1.0"})
    size = 0
    try:
        with opener.open(request, timeout=60) as response:
            if urllib.parse.urlsplit(response.geturl()).scheme.lower() != "https":
                raise IntakeError("download redirected away from HTTPS")
            declared = response.headers.get("Content-Length")
            if declared and declared.isdigit() and int(declared) > MAX_BYTES:
                raise IntakeError("download exceeds 8 GiB limit")
            destination.parent.mkdir(parents=True, exist_ok=True)
            with destination.open("wb") as output:
                while True:
                    block = response.read(1024 * 1024)
                    if not block:
                        break
                    size += len(block)
                    if size > MAX_BYTES:
                        raise IntakeError("download exceeds 8 GiB limit")
                    output.write(block)
    except IntakeError:
        destination.unlink(missing_ok=True)
        raise
    except Exception as exc:
        destination.unlink(missing_ok=True)
        raise IntakeError("download failed; check that the secret is an accessible direct HTTPS link") from exc
    if size == 0:
        destination.unlink(missing_ok=True)
        raise IntakeError("downloaded image is empty")
    return size


def _locate_code_file(exefs: Path) -> Path:
    candidates = [
        p for p in exefs.rglob("*")
        if p.is_file() and p.name.lower().lstrip(".") in {"code", "code.bin"}
    ]
    if len(candidates) != 1:
        raise IntakeError("CTRTool did not produce exactly one ExeFS code file")
    return candidates[0]


def extract_and_inspect(
    image_path: Path, target: str, format_name: str, ctrtool_command: list[str],
    work_directory: Path, *, ncch_index: int = 0,
) -> dict:
    fmt, kind = normalize_format(format_name)
    if not 0 <= ncch_index <= 65535:
        raise IntakeError("partition/content index must be from 0 to 65535")
    work = work_directory.resolve()
    if not work.is_relative_to(Path(tempfile.gettempdir()).resolve()) or work.is_relative_to(ROOT.resolve()):
        raise IntakeError("working directory must be outside the repository and inside system temporary storage")
    if not image_path.is_file():
        raise IntakeError("input image does not exist")
    work.mkdir(parents=True, exist_ok=True)
    exefs = work / "exefs"
    exefs.mkdir(exist_ok=True)
    exheader = work / "exheader.bin"
    try:
        run = subprocess.run(
            [*ctrtool_command, f"--intype={kind}", f"--ncch={ncch_index}",
             f"--exheader={exheader}", f"--exefsdir={exefs}", str(image_path)],
            cwd=work, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            timeout=600, check=False,
        )
    except Exception as exc:
        raise IntakeError("CTRTool failed or timed out; no files were published") from exc
    if run.returncode != 0:
        raise IntakeError(
            "CTRTool could not extract this partition; it may be encrypted, malformed, or require keys not provided by this workflow"
        )
    code_path = _locate_code_file(exefs)
    try:
        from inspect_3ds_target import inspect_target
        report = inspect_target(target, exheader, code_path)
    except Exception as exc:
        raise IntakeError("target metadata/segment validation failed; check game version and decompression state") from exc
    text_segment = next(s for s in report["memory"]["segments"] if s["name"] == "text")
    return {
        "status": "pass",
        "target": target,
        "format": "." + fmt,
        "text_size_bytes": int(text_segment["declared_size_bytes"]),
        "decompressed_code_size_bytes": int(report["inputs"]["decompressed_code"]["size_bytes"]),
        "no_game_bytes_or_disassembly_uploaded": True,
    }


def process(source_url: str, target: str, format_name: str, ctrtool: Path, index: int) -> dict:
    fmt, _ = normalize_format(format_name)
    if index < 0 or index > 65535:
        raise IntakeError("partition/content index must be from 0 to 65535")
    with tempfile.TemporaryDirectory(prefix="pokeultra-intake-") as tmp:
        work = Path(tmp).resolve()
        source = work / ("input." + fmt)
        size = download(source_url, source)
        result = extract_and_inspect(
            source, target, fmt, [str(ctrtool.resolve())],
            work / "extract", ncch_index=index,
        )
        result["downloaded_bytes"] = size
        return result


def main() -> int:
    from inspect_3ds_target import load_profiles
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", choices=sorted(load_profiles()), required=True)
    parser.add_argument("--format", choices=sorted(FORMATS), required=True)
    parser.add_argument("--ctrtool", type=Path, required=True)
    parser.add_argument("--ncch-index", type=int, default=0)
    args = parser.parse_args()
    source = os.environ.get("POKEULTRARECOMP_SOURCE_URL", "")
    if not source:
        print("ERROR: configure the Actions secret POKEULTRARECOMP_SOURCE_URL", file=sys.stderr)
        return 2
    try:
        result = process(source, args.target, args.format, args.ctrtool, args.ncch_index)
        summary = os.environ.get("GITHUB_STEP_SUMMARY")
        if summary:
            Path(summary).write_text(
                "# Remote 3DS intake\n\n"
                f"- Status: **{result['status']}**\n"
                f"- Target: {result['target']}\n"
                f"- Format: {result['format']}\n"
                "- Container extraction and metadata preflight: **passed**\n"
                "- ROM, extracted code, hashes, and disassembly uploaded: **no**\n\n"
                "This validates the container/layout only; it does not prove recompilation or gameplay.\n",
                encoding="utf-8",
            )
        print(json.dumps({
            "status": result["status"], "target": result["target"],
            "format": result["format"], "container_and_layout_validated": True,
            "game_bytes_or_disassembly_uploaded": False,
        }, indent=2))
        return 0
    except IntakeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
