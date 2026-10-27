#!/usr/bin/env python3
"""Remote 3DS image intake using a secret HTTPS source URL and ephemeral storage."""
from __future__ import annotations
import argparse
import http.cookiejar
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


def google_drive_download_url(file_id: str, resource_key: str = "", confirm: str = "") -> str:
    """Construct a Google Drive download endpoint without exposing its URL to logs."""
    params = {"export": "download", "id": file_id}
    if resource_key:
        params["resourcekey"] = resource_key
    if confirm:
        params["confirm"] = confirm
    return "https://drive.google.com/uc?" + urllib.parse.urlencode(params)


def google_drive_confirmation_token(html: str, cookies=()) -> str:
    """Read Drive's large-file confirmation token from a cookie or confirmation page."""
    for cookie in cookies:
        if str(getattr(cookie, "name", "")).startswith("download_warning"):
            value = str(getattr(cookie, "value", ""))
            if re.fullmatch(r"[A-Za-z0-9_-]{1,256}", value):
                return value
    patterns = (
        r'(?:[?&]confirm=)([A-Za-z0-9_-]{1,256})',
        r"""name=["']confirm["']\s+value=["']([A-Za-z0-9_-]{1,256})["']""",
    )
    for pattern in patterns:
        match = re.search(pattern, html, re.IGNORECASE)
        if match:
            return match.group(1)
    return ""


def _open_file_response(opener, url: str, drive_details: tuple[str, str] | None):
    request = urllib.request.Request(url, headers={"User-Agent": "PokeUltrarecomp/1.0"})
    response = opener.open(request, timeout=60)
    if urllib.parse.urlsplit(response.geturl()).scheme.lower() != "https":
        response.close()
        raise IntakeError("download redirected away from HTTPS")
    content_type = response.headers.get_content_type().casefold()
    if content_type not in {"text/html", "application/xhtml+xml"}:
        return response

    # A normal Google Drive share page is HTML; only follow a recognised
    # confirmation token. Never accidentally save the HTML page as a game image.
    html = response.read(512 * 1024).decode("utf-8", errors="replace")
    cookie_handler = next((h for h in opener.handlers if isinstance(h, urllib.request.HTTPCookieProcessor)), None)
    cookies = cookie_handler.cookiejar if cookie_handler else ()
    token = google_drive_confirmation_token(html, cookies)
    response.close()
    if drive_details and token:
        file_id, resource_key = drive_details
        retry_url = google_drive_download_url(file_id, resource_key, token)
        retry = opener.open(
            urllib.request.Request(retry_url, headers={"User-Agent": "PokeUltrarecomp/1.0"}),
            timeout=60,
        )
        if urllib.parse.urlsplit(retry.geturl()).scheme.lower() != "https":
            retry.close()
            raise IntakeError("download redirected away from HTTPS")
        retry_type = retry.headers.get_content_type().casefold()
        if retry_type in {"text/html", "application/xhtml+xml"}:
            retry.close()
            raise IntakeError(
                "Google Drive returned a web page instead of the file; verify link access and that the file can be downloaded"
            )
        return retry
    raise IntakeError(
        "source returned a web page instead of a file; for Google Drive, use a share link accessible to anyone with the link"
    )


def download(source_url: str, destination: Path) -> int:
    validate_url(source_url)
    drive_details = google_drive_file_details(source_url)
    effective_url = (
        google_drive_download_url(*drive_details) if drive_details else source_url.strip()
    )
    cookie_jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(
        HTTPSRedirect(), urllib.request.HTTPCookieProcessor(cookie_jar)
    )
    # Keep the cookie jar private to this request; do not print URLs or response bodies.
    opener.drive_cookie_jar = cookie_jar
    size = 0
    try:
        response = _open_file_response(opener, effective_url, drive_details)
        with response:
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
