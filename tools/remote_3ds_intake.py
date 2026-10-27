#!/usr/bin/env python3
"""Remote 3DS image intake using a secret HTTPS source URL and ephemeral storage."""
from __future__ import annotations
import argparse
import ipaddress
import json
import os
import re
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


def extract_container_title_id(
    image_path: Path, format_name: str, ncch_index: int,
) -> str | None:
    """Read the selected NCCH Program ID from an unencrypted NCSD header."""
    _fmt, kind = normalize_format(format_name)
    if kind != "ncsd":
        return None
    if not 0 <= ncch_index < 8:
        raise IntakeError("NCSD partition index must be from 0 to 7")
    try:
        file_size = image_path.stat().st_size
        with image_path.open("rb") as stream:
            if file_size < 0x200:
                raise IntakeError("NCSD container header is truncated")
            stream.seek(0x100)
            if stream.read(4) != b"NCSD":
                raise IntakeError("input does not contain the expected NCSD header")
            stream.seek(0x120 + ncch_index * 8)
            entry = stream.read(8)
            if len(entry) != 8:
                raise IntakeError("NCSD partition table is truncated")
            offset_units = int.from_bytes(entry[0:4], "little")
            size_units = int.from_bytes(entry[4:8], "little")
            if offset_units == 0 or size_units == 0:
                raise IntakeError("selected NCSD partition is absent")
            offset = offset_units * 0x200
            size = size_units * 0x200
            if offset < 0x200 or size < 0x200 or offset > file_size or size > file_size - offset:
                raise IntakeError("selected NCSD partition range is outside the image")
            stream.seek(offset)
            header = stream.read(0x200)
            if len(header) != 0x200 or header[0x100:0x104] != b"NCCH":
                raise IntakeError("selected NCSD partition does not contain an NCCH header")
            return f"{int.from_bytes(header[0x118:0x120], 'little'):016x}"
    except OSError as exc:
        raise IntakeError("could not read the NCSD container header") from exc

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


def google_drive_file_details(source_url: str) -> tuple[str, str] | None:
    """Extract a public Google Drive file ID and optional resource key from a share URL."""
    parsed = urllib.parse.urlsplit(source_url.strip())
    host = (parsed.hostname or "").casefold().rstrip(".")
    if host not in {"drive.google.com", "docs.google.com", "drive.usercontent.google.com"}:
        return None
    query = urllib.parse.parse_qs(parsed.query)
    file_id = query.get("id", [""])[0]
    if not file_id:
        match = re.search(r"/file/d/([A-Za-z0-9_-]+)", parsed.path)
        if match:
            file_id = match.group(1)
    if not re.fullmatch(r"[A-Za-z0-9_-]{10,200}", file_id or ""):
        return None
    resource_key = query.get("resourcekey", query.get("resourceKey", [""]))[0]
    if resource_key and not re.fullmatch(r"[A-Za-z0-9_-]{1,256}", resource_key):
        raise IntakeError("Google Drive resource key contains unsupported characters")
    return file_id, resource_key


def _download_google_drive(source_url: str, destination: Path) -> int:
    """Download a public Google Drive share link while handling large-file confirmation."""
    try:
        import gdown
    except ImportError as exc:
        raise IntakeError("Google Drive downloader dependency is unavailable") from exc

    def enforce_size_limit(bytes_so_far: int, bytes_total: int | None) -> None:
        if bytes_total is not None and bytes_total > MAX_BYTES:
            raise IntakeError("download exceeds 8 GiB limit")
        if bytes_so_far > MAX_BYTES:
            raise IntakeError("download exceeds 8 GiB limit")

    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        result = gdown.download(
            url=source_url.strip(),
            output=str(destination),
            quiet=True,
            use_cookies=False,
            resume=True,
            timeout=60,
            retries=3,
            progress=enforce_size_limit,
        )
        if not result or not destination.is_file():
            raise IntakeError(
                "Google Drive did not return a downloadable file; verify sharing permissions and download quota"
            )
        size = destination.stat().st_size
        if size == 0:
            raise IntakeError("downloaded image is empty")
        if size > MAX_BYTES:
            raise IntakeError("download exceeds 8 GiB limit")
        return size
    except IntakeError:
        destination.unlink(missing_ok=True)
        raise
    except Exception:
        # Deliberately suppress the underlying exception: third-party errors may
        # include the secret URL or other private request details.
        destination.unlink(missing_ok=True)
        raise IntakeError(
            "Google Drive download failed; set access to Anyone with the link and check whether Drive is blocking or quota-limiting downloads"
        ) from None


def download(source_url: str, destination: Path) -> int:
    validate_url(source_url)
    drive_details = google_drive_file_details(source_url)
    if drive_details is not None:
        return _download_google_drive(source_url, destination)

    opener = urllib.request.build_opener(HTTPSRedirect())
    request = urllib.request.Request(source_url.strip(), headers={"User-Agent": "PokeUltrarecomp/1.0"})
    size = 0
    try:
        with opener.open(request, timeout=60) as response:
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
        raise IntakeError("download failed; check that the secret is an accessible HTTPS download link") from exc
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
    candidate_decode_summary: bool = False,
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
    container_title_id = extract_container_title_id(image_path, fmt, ncch_index)
    try:
        from inspect_3ds_target import inspect_target
        report = inspect_target(target, exheader, code_path, title_id=container_title_id)
    except Exception as exc:
        raise IntakeError("target metadata/segment validation failed; check game version and decompression state") from exc
    from summarize_arm_function_candidates import scan_candidates

    candidate_census = scan_candidates(
        target, exheader, code_path, preflight=report,
        decode_summary=candidate_decode_summary,
    )["summary"]
    text_segment = next(s for s in report["memory"]["segments"] if s["name"] == "text")
    return {
        "status": "pass",
        "target": target,
        "format": "." + fmt,
        "text_size_bytes": int(text_segment["declared_size_bytes"]),
        "decompressed_code_size_bytes": int(report["inputs"]["decompressed_code"]["size_bytes"]),
        "container_title_id_supplied": container_title_id is not None,
        "container_title_id_match": report["identity"]["title_id_match"],
        "container_title_kind": report["identity"]["title_kind"],
        "candidate_census": candidate_census,
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
            work / "extract", ncch_index=index, candidate_decode_summary=True,
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
                f"- Container title identity: {result['container_title_id_match']}\\n"
                f"- Matched title kind: {result['container_title_kind'] or 'not confirmed'}\\n"
                "- ROM, extracted code, hashes, and disassembly uploaded: **no**\n"
                f"- Text segment: {result['text_size_bytes']} bytes\n"
                f"- Heuristic prologue-like sites: {result['candidate_census']['candidate_sites_total']}\n"
                f"  - ARM PUSH/ STMDB SP!: {result['candidate_census']['candidate_sites_by_pattern']['arm_push_or_stmdb_sp']}\n"
                f"  - ARM SUB SP immediate: {result['candidate_census']['candidate_sites_by_pattern']['arm_sub_sp_immediate']}\n"
                f"  - Thumb PUSH: {result['candidate_census']['candidate_sites_by_pattern']['thumb_push']}\n"
                f"  - Thumb SUB SP immediate: {result['candidate_census']['candidate_sites_by_pattern']['thumb_sub_sp_immediate']}\n"
                f"- Candidates whose bounded Capstone scan reaches a return-like instruction: {result['candidate_census']['bounded_return_scan']['candidate_sites_with_linear_return']}\n"
                f"  - ARM: {result['candidate_census']['bounded_return_scan']['candidate_sites_with_linear_return_by_state']['arm']}\n"
                f"  - Thumb: {result['candidate_census']['bounded_return_scan']['candidate_sites_with_linear_return_by_state']['thumb']}\n"
                f"  - Return within 16 instructions: {result['candidate_census']['bounded_return_scan']['candidate_sites_with_return_within_16_instructions']}\n\n"
                "**Caution:** these are heuristic instruction sites and bounded linear decodes, not verified function boundaries or reachability proofs. No candidate addresses or instruction bytes are published.\n\n"
                "This validates the container/layout and inventories candidate prologues; it does not prove recompilation or gameplay.\n",
                encoding="utf-8",
            )
        print(json.dumps({
            "status": result["status"], "target": result["target"],
            "format": result["format"], "container_and_layout_validated": True,
            "container_title_id_supplied": result["container_title_id_supplied"],
            "container_title_id_match": result["container_title_id_match"],
            "container_title_kind": result["container_title_kind"],
            "candidate_census": result["candidate_census"],
            "game_bytes_or_disassembly_uploaded": False,
        }, indent=2))
        return 0
    except IntakeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
