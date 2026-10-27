#!/usr/bin/env python3
"""Remote 3DS image intake using a secret HTTPS source URL and ephemeral storage."""
from __future__ import annotations
import argparse
import ipaddress
import json
import os
import re
import shutil
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


def classify_google_drive_download_failure(exc: Exception) -> str:
    """Classify Google Drive failures safely, without returning raw response text or URLs."""
    message = str(exc).casefold()
    quota_markers = (
        "too many users", "many accesses", "download quota", "quota exceeded",
        "quota has been exceeded", "rate limit", "rate-limited", "too many requests",
        "download limit", "try again later",
    )
    if any(marker in message for marker in quota_markers):
        return (
            "Google Drive appears to be rate-limiting this file's download; "
            "wait before retrying or use another authorized download host"
        )
    if any(marker in message for marker in (
        "cannot retrieve the public link", "permission", "request access",
        "not accessible", "file not found", "404",
    )):
        return (
            "Google Drive did not provide a public download link; verify that "
            "sharing allows anyone with the link and that any resource key is included"
        )
    exception_type = type(exc).__name__.casefold()
    if "timeout" in exception_type or "timed out" in message or "connection reset" in message:
        return "Google Drive download timed out or hit a network error; retry when the connection is stable"
    return (
        "Google Drive download failed; verify link access and check for temporary download "
        "quotas or provider/network restrictions"
    )


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
    except Exception as exc:
        # Third-party error text may contain the secret URL or private response details.
        destination.unlink(missing_ok=True)
        raise IntakeError(classify_google_drive_download_failure(exc)) from None


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


GHIDRA_SUMMARY_COUNTERS = (
    "functions_with_entry_inside_text",
    "functions_le_32_bytes",
    "functions_le_64_bytes",
    "functions_le_128_bytes",
    "leaf_functions",
    "leaf_functions_le_32_bytes",
    "leaf_functions_le_64_bytes",
    "leaf_functions_le_128_bytes",
    "functions_with_return_like_instruction",
    "leaf_functions_le_64_bytes_with_return_like_instruction",
    "instructions_in_leaf_functions_le_64_bytes",
    "excluded_bodies_crossing_text_bounds",
)
GHIDRA_MNEMONIC_RE = re.compile(r"^[a-z][a-z0-9.]{0,15}$")


def sanitize_ghidra_summary(summary_path: Path, expected_text_size: int) -> dict:
    """Accept an aggregate-only Ghidra result and strip all non-allowlisted fields."""
    try:
        raw = json.loads(summary_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise IntakeError("Ghidra census did not produce a readable summary") from exc
    if not isinstance(raw, dict):
        raise IntakeError("Ghidra census summary must be a JSON object")
    expected_keys = {
        "schema_version", "status", "text_size_bytes", *GHIDRA_SUMMARY_COUNTERS,
        "top_mnemonics_in_leaf_functions_le_64_bytes",
        "function_boundaries_verified", "addresses_emitted", "disassembly_emitted",
        "interpretation",
    }
    if set(raw) != expected_keys:
        raise IntakeError("Ghidra census summary has unexpected or missing fields")
    if raw.get("schema_version") != 1 or isinstance(raw.get("schema_version"), bool):
        raise IntakeError("Ghidra census summary schema version is unsupported")
    if raw.get("status") != "pass":
        raise IntakeError("Ghidra census did not report success")
    if raw.get("text_size_bytes") != expected_text_size:
        raise IntakeError("Ghidra census text-size does not match the validated executable")
    if any(raw.get(key) is not False for key in (
        "function_boundaries_verified", "addresses_emitted", "disassembly_emitted"
    )):
        raise IntakeError("Ghidra census does not satisfy the aggregate-only output policy")
    if not isinstance(raw.get("interpretation"), str):
        raise IntakeError("Ghidra census interpretation field is malformed")

    safe: dict[str, object] = {"schema_version": 1, "status": "pass", "text_size_bytes": expected_text_size}
    for key in GHIDRA_SUMMARY_COUNTERS:
        value = raw.get(key)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise IntakeError(f"Ghidra census counter {key} is invalid")
        safe[key] = value

    ordering = (
        ("functions_le_32_bytes", "functions_le_64_bytes"),
        ("functions_le_64_bytes", "functions_le_128_bytes"),
        ("functions_le_128_bytes", "functions_with_entry_inside_text"),
        ("leaf_functions_le_32_bytes", "leaf_functions_le_64_bytes"),
        ("leaf_functions_le_64_bytes", "leaf_functions_le_128_bytes"),
        ("leaf_functions_le_128_bytes", "leaf_functions"),
        ("leaf_functions", "functions_with_entry_inside_text"),
        ("leaf_functions_le_64_bytes_with_return_like_instruction", "leaf_functions_le_64_bytes"),
        ("functions_with_return_like_instruction", "functions_with_entry_inside_text"),
    )
    for smaller, larger in ordering:
        if int(safe[smaller]) > int(safe[larger]):
            raise IntakeError(f"Ghidra census counters violate ordering: {smaller} > {larger}")

    top = raw.get("top_mnemonics_in_leaf_functions_le_64_bytes")
    if not isinstance(top, list) or len(top) > 20:
        raise IntakeError("Ghidra census mnemonic histogram is malformed")
    cleaned_top: list[dict[str, object]] = []
    seen: set[str] = set()
    for item in top:
        if not isinstance(item, dict) or set(item) != {"mnemonic", "count"}:
            raise IntakeError("Ghidra census mnemonic item contains unexpected fields")
        mnemonic, count = item.get("mnemonic"), item.get("count")
        if not isinstance(mnemonic, str) or not GHIDRA_MNEMONIC_RE.fullmatch(mnemonic):
            raise IntakeError("Ghidra census contains a non-mnemonic value")
        if mnemonic in seen:
            raise IntakeError("Ghidra census repeats a mnemonic")
        if isinstance(count, bool) or not isinstance(count, int) or count <= 0:
            raise IntakeError("Ghidra census mnemonic count is invalid")
        seen.add(mnemonic)
        cleaned_top.append({"mnemonic": mnemonic, "count": count})
    safe["top_mnemonics_in_leaf_functions_le_64_bytes"] = cleaned_top
    safe["function_boundaries_verified"] = False
    safe["addresses_emitted"] = False
    safe["disassembly_emitted"] = False
    return safe


def classify_ghidra_failure(log_path: Path) -> str:
    """Return a bounded diagnostic category without exposing private logs."""
    try:
        diagnostic = log_path.read_text(encoding="utf-8", errors="replace").casefold()
    except OSError:
        return "private-log-unavailable"

    if any(token in diagnostic for token in (
        "error: cannot find symbol", "compilation failed", "failed to compile",
        "script compilation error", "javac:", "compilation errors",
    )) or re.search(r"(?m)^.*\.java:\d+:\s*error:", diagnostic):
        return "script-compilation"
    if any(token in diagnostic for token in (
        "unrecognized option", "unknown option", "invalid option", "usage:",
        "unexpected argument", "too many arguments",
    )):
        return "headless-command-line"
    if "script not found" in diagnostic or "could not find script" in diagnostic:
        return "script-discovery"
    if any(token in diagnostic for token in (
        "no language", "language id", "language not found", "processor not found",
    )):
        return "processor-language-selection"
    if "could not open project" in diagnostic or "failed to create project" in diagnostic:
        return "project-setup"
    if any(token in diagnostic for token in (
        "failed to load", "could not load", "import failed", "loader failed",
    )):
        return "elf-import"
    if "out of memory" in diagnostic or "java heap space" in diagnostic:
        return "memory-pressure"

    if any(token in diagnostic for token in (
        "script terminated with an exception", "script execution failed",
        "error while running script", "error running post script",
    )):
        return "script-execution"

    # Exception type names are safe to report; raw messages and stack traces may not be.
    exception_match = re.search(
        r"\b([a-z_$][a-z0-9_$]*(?:exception|error))\b",
        diagnostic,
        re.IGNORECASE,
    )
    if exception_match:
        name = exception_match.group(1).casefold()
        safe_names = {
            "illegalargumentexception": "illegal-argument",
            "nullpointerexception": "null-pointer",
            "nosuchmethoderror": "missing-method",
            "noclassdeffounderror": "missing-class",
            "classnotfoundexception": "missing-class",
            "nosuchfileexception": "missing-file",
            "filenotfoundexception": "missing-file",
            "ioexception": "io-error",
            "outofmemoryerror": "memory-pressure",
            "stackoverflowerror": "stack-overflow",
            "headlessscriptexception": "script-exception",
            "ghidraexception": "ghidra-exception",
        }
        return "java-" + safe_names.get(name, "exception")
    if "script" in diagnostic and "error" in diagnostic:
        return "script-error"
    if "analysis failed" in diagnostic or "analysis error" in diagnostic:
        return "analysis-error"
    return "headless-analysis"



def sanitized_ghidra_failure_hint(log_path: Path) -> str:
    """Select and redact one diagnostic line; never expose raw private logs."""
    try:
        lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return "private-log-unavailable"
    # Prefer actual compiler diagnostics over the later ClassNotFoundException
    # emitted when Ghidra tries to load a script whose compilation failed.
    compiler_errors = [
        line for line in lines
        if re.search(
            r"(?:\.java:\d+:\s*error:|error:\s*cannot find symbol|"
            r"cannot find symbol|script compilation error|failed to compile|"
            r"compilation failed|javac:)",
            line, re.IGNORECASE,
        )
    ]
    candidates = compiler_errors or [
        line for line in lines
        if re.search(r"(error|exception|failed|cannot|unable|invalid|not found)", line, re.IGNORECASE)
    ]
    if not candidates:
        return "no-matching-diagnostic"
    line = candidates[0]
    # Redact addresses, long hexadecimal values, file paths, and filenames from
    # the private import before allowing a short diagnostic through.
    line = re.sub(r"(?i)0x[0-9a-f]{1,16}", "<address>", line)
    line = re.sub(r"\b[a-f0-9]{8,}\b", "<hex>", line, flags=re.IGNORECASE)
    line = re.sub(r"(?:(?:[A-Za-z]:)?[\\/])[^\s:]+", "<path>", line)
    line = re.sub(r"(?i)[A-Za-z0-9_.-]+\.(?:elf|cci|cia|3ds|code|bin)", "<private-file>", line)
    line = re.sub(r"\s+", " ", line).strip()
    line = re.sub(r"[^A-Za-z0-9 _.,:;()\[\]<>/'=+?-]", "?", line)
    return line[:180] or "diagnostic-redacted"


ARM_DECODE_REJECTION_FAMILIES = (
    "branch-with-link",
    "unsupported-branch-condition",
    "unsupported-condition-code",
    "non-immediate-data-processing",
    "unsupported-operand-class",
    "register-shifted-operand",
    "unsupported-flag-setting-form",
    "noncanonical-cmn-cmp",
    "register-outside-r0-r3",
    "noncanonical-mov-mvn",
    "unsupported-data-processing-opcode",
    "other-decode-rejection",
)


def classify_arm_decode_rejection(message: str) -> str:
    """Map private translator errors into fixed safe categories, never emit raw words."""
    lowered = message.casefold()
    if "branch-with-link" in lowered or "branch with link" in lowered:
        return "branch-with-link"
    if "branch condition is unsupported" in lowered:
        return "unsupported-branch-condition"
    if "condition code" in lowered and "unsupported" in lowered:
        return "unsupported-condition-code"
    if (
        "not a supported immediate data-processing instruction" in lowered
        or "register operand is unsupported" in lowered
    ):
        return "non-immediate-data-processing"
    if "not a supported data-processing operand form" in lowered:
        return "unsupported-operand-class"
    if any(
        phrase in lowered
        for phrase in (
            "byte memory access is unsupported",
            "register-offset memory access is unsupported",
            "post-indexed or writeback memory access is unsupported",
        )
    ):
        return "unsupported-operand-class"
    if "register operand2 shifts are unsupported" in lowered:
        return "register-shifted-operand"
    if "flag-setting form is unsupported" in lowered:
        return "unsupported-flag-setting-form"
    if "canonical cmn" in lowered or "canonical cmp" in lowered or "cmn requires" in lowered or "cmp requires" in lowered:
        return "noncanonical-cmn-cmp"
    if "register r" in lowered and "outside r0-r3 subset" in lowered:
        return "register-outside-r0-r3"
    if "canonical mov" in lowered or "canonical mvn" in lowered:
        return "noncanonical-mov-mvn"
    if "unsupported data-processing opcode" in lowered:
        return "unsupported-data-processing-opcode"
    return "other-decode-rejection"


def screen_private_ghidra_candidates(sidecar_path: Path) -> dict:
    """Screen private Ghidra candidates with the current narrow ARM-to-C subset.

    Candidate addresses, instruction words, generated C, and compiler diagnostics
    stay in the temporary directory. Only aggregate counts and boolean statuses
    are returned to the workflow summary.
    """
    try:
        sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise IntakeError("private Ghidra candidate sidecar is missing or unreadable") from None
    if not isinstance(sidecar, dict) or set(sidecar) != {
        "schema_version", "omitted_candidate_count", "candidates"
    }:
        raise IntakeError("private Ghidra candidate sidecar has an invalid schema")
    if sidecar.get("schema_version") != 1 or isinstance(sidecar.get("schema_version"), bool):
        raise IntakeError("private Ghidra candidate sidecar schema version is unsupported")
    omitted = sidecar.get("omitted_candidate_count")
    candidates = sidecar.get("candidates")
    if isinstance(omitted, bool) or not isinstance(omitted, int) or omitted < 0:
        raise IntakeError("private Ghidra candidate omission count is invalid")
    if not isinstance(candidates, list) or len(candidates) > 10000:
        raise IntakeError("private Ghidra candidate list exceeds its allowed bound")

    try:
        import arm_subset_poc
    except ImportError:
        raise IntakeError("current ARM subset translator is unavailable for candidate screening") from None

    address_pattern = re.compile(r"^0x[0-9A-Fa-f]{8}$")
    word_pattern = re.compile(r"^0x[0-9A-Fa-f]{8}$")
    seen_addresses: set[str] = set()
    compatible_count = 0
    rejected_candidate_sequences = 0
    candidates_with_instruction_decode_rejections = 0
    sequence_level_rejections = 0
    rejection_family_counts: dict[str, int] = {}
    syntax_sample: list[str] = []
    max_syntax_sample = 128

    for candidate in candidates:
        if not isinstance(candidate, dict) or set(candidate) != {
            "entry_address", "body_size_bytes", "instruction_count", "words"
        }:
            raise IntakeError("private Ghidra candidate has unexpected or missing fields")
        address_text = candidate.get("entry_address")
        if not isinstance(address_text, str) or not address_pattern.fullmatch(address_text):
            raise IntakeError("private Ghidra candidate entry address is malformed")
        address_value = int(address_text, 16)
        if address_value % 4:
            raise IntakeError("private Ghidra candidate entry address is not ARM-aligned")
        normalized_address = address_text.upper()
        if normalized_address in seen_addresses:
            raise IntakeError("private Ghidra candidate sidecar repeats an entry address")
        seen_addresses.add(normalized_address)

        size = candidate.get("body_size_bytes")
        instruction_count = candidate.get("instruction_count")
        words_raw = candidate.get("words")
        if isinstance(size, bool) or not isinstance(size, int) or size < 8 or size > 64 or size % 4:
            raise IntakeError("private Ghidra candidate body size is invalid")
        if (
            isinstance(instruction_count, bool)
            or not isinstance(instruction_count, int)
            or instruction_count != size // 4
            or instruction_count < 2
            or instruction_count > 16
        ):
            raise IntakeError("private Ghidra candidate instruction count is invalid")
        if not isinstance(words_raw, list) or len(words_raw) != instruction_count:
            raise IntakeError("private Ghidra candidate instruction array has the wrong length")

        words: list[int] = []
        for item in words_raw:
            if not isinstance(item, str) or not word_pattern.fullmatch(item):
                raise IntakeError("private Ghidra candidate contains a malformed instruction word")
            words.append(int(item, 16))
        if words[-1] != 0xE12FFF1E:
            raise IntakeError("private Ghidra candidate does not end with exact BX LR")
        if size != len(words) * 4:
            raise IntakeError("private Ghidra candidate size does not match its word array")

        memory_model_needed = False
        for word in words[:-1]:
            try:
                decoded_word = arm_subset_poc.decode_word(word)
                if decoded_word[0] == "predicated":
                    decoded_word = decoded_word[2]
                if decoded_word[0] in ("ldr_imm", "str_imm", "ldrb_imm", "strb_imm", "ldrh_imm", "strh_imm", "ldrsb_imm", "ldrsh_imm"):
                    memory_model_needed = True
            except ValueError:
                # The translation attempt below records fixed, sanitized failure categories.
                pass

        try:
            generated = arm_subset_poc.translate(
                words,
                max_execution_steps=len(words),
                runtime_state_io=True,
                runtime_memory_io=memory_model_needed,
            )
        except ValueError as exc:
            # Count only fixed, sanitized decode families for diagnosis. Never
            # write the candidate address, word, exception text, or C source to logs.
            rejected_candidate_sequences += 1
            found_instruction_rejection = False
            for word in words[:-1]:
                try:
                    arm_subset_poc.decode_word(word)
                except ValueError as exc:
                    family = classify_arm_decode_rejection(str(exc))
                    rejection_family_counts[family] = rejection_family_counts.get(family, 0) + 1
                    found_instruction_rejection = True
            if found_instruction_rejection:
                candidates_with_instruction_decode_rejections += 1
            else:
                sequence_level_rejections += 1
            continue

        compatible_count += 1
        if len(syntax_sample) < max_syntax_sample:
            function_name = f"private_candidate_screen_{len(syntax_sample)}"
            signature = "uint32_t synthetic_entry_bounded("
            if signature not in generated:
                raise IntakeError("ARM translator emitted an unexpected runtime interface")
            syntax_sample.append(generated.replace(signature, f"uint32_t {function_name}(", 1))

    syntax_status = "not-run-no-compatible-candidates"
    if syntax_sample:
        compiler = None
        for name in (os.environ.get("CC", "").strip(), "cc", "gcc", "clang"):
            if name and (resolved := shutil.which(name)):
                compiler = resolved
                break
        if compiler is None:
            syntax_status = "not-run-no-c-compiler"
        else:
            try:
                compiled = subprocess.run(
                    [compiler, "-std=c11", "-Wall", "-Wextra", "-Werror",
                     "-fsyntax-only", "-x", "c", "-"],
                    input="\n\n".join(syntax_sample),
                    capture_output=True, text=True, timeout=120, check=False,
                )
                syntax_status = "passed" if compiled.returncode == 0 else "failed"
            except (OSError, subprocess.TimeoutExpired):
                syntax_status = "timed-out-or-unavailable"

    return {
        "status": "pass",
        "private_candidates_screened": len(candidates),
        "private_candidates_omitted_by_ghidra_cap": omitted,
        "sequences_accepted_by_current_arm_subset_translator": compatible_count,
        "candidate_sequences_rejected_by_current_arm_subset_translator": rejected_candidate_sequences,
        "candidate_sequences_with_instruction_decode_rejections": candidates_with_instruction_decode_rejections,
        "candidate_sequences_rejected_by_sequence_constraints": sequence_level_rejections,
        "unsupported_instruction_encodings_by_family": {
            family: rejection_family_counts[family]
            for family in ARM_DECODE_REJECTION_FAMILIES
            if rejection_family_counts.get(family, 0) > 0
        },
        "native_c_syntax_check": syntax_status,
        "native_c_syntax_sample_count": len(syntax_sample),
        "native_semantic_equivalence_verified": False,
        "function_boundaries_independently_verified": False,
        "addresses_or_instruction_words_emitted": False,
        "interpretation": (
            "Compatibility screening only. Ghidra boundaries can be heuristic; successful translation "
            "and host-C syntax checking do not prove ARM equivalence or gameplay."
        ),
    }


def run_ghidra_function_census(
    ghidra_headless_path: Path, target: str, exheader_path: Path,
    code_path: Path, text_segment: dict, work_directory: Path,
) -> dict:
    """Run Ghidra headless into private temporary files and return only safe aggregates."""
    executable = ghidra_headless_path.expanduser().resolve()
    if not executable.is_file():
        raise IntakeError("configured Ghidra headless executable does not exist")
    work = work_directory.resolve()
    if not work.is_relative_to(Path(tempfile.gettempdir()).resolve()) or work.is_relative_to(ROOT.resolve()):
        raise IntakeError("Ghidra working directory must be in temporary storage outside the repository")

    from wrap_retail_code import build_analysis_elf, RetailCodeWrapError
    elf_path = work / "private-analysis.elf"
    project_path = work / "ghidra-project"
    project_path.mkdir(parents=True, exist_ok=True)
    summary_path = work / "private-ghidra-summary.json"
    candidate_sidecar_path = work / "private-ghidra-candidates.json"
    log_path = work / "private-ghidra.log"
    script_log_path = work / "private-ghidra-script.log"
    app_log_path = work / "private-ghidra-app.log"
    try:
        build_analysis_elf(target, exheader_path, code_path, elf_path, confirm_decompressed=True)
    except (RetailCodeWrapError, OSError) as exc:
        raise IntakeError("could not prepare the private static-analysis container") from exc

    text_start = int(text_segment["virtual_address"])
    text_size = int(text_segment["declared_size_bytes"])
    # Permit a Python-script headless shim for cross-platform tests while
    # keeping real Ghidra binaries launched directly in production.
    launcher = [sys.executable, str(executable)] if executable.suffix.casefold() == ".py" else [str(executable)]
    command = [
        *launcher, str(project_path),
        "ultra-sun-private-census" if target == "ultra-sun" else "ultra-moon-private-census",
        "-import", str(elf_path), "-overwrite",
        "-scriptPath", str(ROOT / "tools" / "ghidra_scripts"),
        "-log", str(app_log_path),
        "-scriptlog", str(script_log_path),
        "-deleteProject",
        "-postScript", "FunctionCensusSummary.java",
        str(summary_path), str(candidate_sidecar_path),
        f"0x{text_start:08X}", str(text_size),
    ]
    try:
        with log_path.open("wb") as log:
            completed = subprocess.run(
                command, cwd=work, stdout=log, stderr=subprocess.STDOUT,
                timeout=3600, check=False,
            )
    except subprocess.TimeoutExpired as exc:
        raise IntakeError("Ghidra headless census timed out; private output was discarded") from exc
    except Exception as exc:
        raise IntakeError("Ghidra headless census could not be launched; private output was discarded") from exc

    # Ghidra writes important compiler and script exceptions to separated logs;
    # combine them only in private temporary storage for classification/redaction.
    try:
        with log_path.open("ab") as combined:
            for extra_log in (app_log_path, script_log_path):
                if extra_log.is_file():
                    combined.write(b"\n--- private Ghidra diagnostic log ---\n")
                    combined.write(extra_log.read_bytes())
    except OSError:
        pass

    if completed.returncode != 0:
        category = classify_ghidra_failure(log_path)
        hint = sanitized_ghidra_failure_hint(log_path)
        raise IntakeError(
            f"Ghidra headless census failed (category: {category}; diagnostic: {hint}); raw diagnostics were discarded"
        )
    try:
        safe_summary = sanitize_ghidra_summary(summary_path, text_size)
    except IntakeError as exc:
        if "did not produce a readable summary" not in str(exc):
            raise
        # A zero process exit code is not sufficient: Ghidra may finish without
        # executing the post-script. Report only an allowlisted, redacted hint.
        category = classify_ghidra_failure(log_path)
        hint = sanitized_ghidra_failure_hint(log_path)
        raise IntakeError(
            f"Ghidra headless census produced no readable summary "
            f"(category: {category}; diagnostic: {hint}); raw diagnostics were discarded"
        ) from None
    candidate_screen = screen_private_ghidra_candidates(candidate_sidecar_path)
    return {**safe_summary, "candidate_translation_screen": candidate_screen}


def extract_and_inspect(
    image_path: Path, target: str, format_name: str, ctrtool_command: list[str],
    work_directory: Path, *, ncch_index: int = 0,
    candidate_decode_summary: bool = False,
    ghidra_headless_path: Path | None = None,
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
    ghidra_census = None
    if ghidra_headless_path is not None:
        ghidra_census = run_ghidra_function_census(
            ghidra_headless_path, target, exheader, code_path,
            text_segment, work / "ghidra-private",
        )
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
        "ghidra_function_census": ghidra_census,
        "no_game_bytes_or_disassembly_uploaded": True,
    }


def process(
    source_url: str, target: str, format_name: str, ctrtool: Path, index: int,
    ghidra_headless_path: Path | None = None,
) -> dict:
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
            ghidra_headless_path=ghidra_headless_path,
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
    parser.add_argument(
        "--ghidra-headless", type=Path,
        help="optional Ghidra analyzeHeadless path; only aggregate results are emitted",
    )
    args = parser.parse_args()
    source = os.environ.get("POKEULTRARECOMP_SOURCE_URL", "")
    if not source:
        print("ERROR: configure the Actions secret POKEULTRARECOMP_SOURCE_URL", file=sys.stderr)
        return 2
    try:
        result = process(
            source, args.target, args.format, args.ctrtool, args.ncch_index,
            ghidra_headless_path=args.ghidra_headless,
        )
        summary = os.environ.get("GITHUB_STEP_SUMMARY")
        if summary:
            Path(summary).write_text(
                "# Remote 3DS intake\n\n"
                f"- Status: **{result['status']}**\n"
                f"- Target: {result['target']}\n"
                f"- Format: {result['format']}\n"
                "- Container extraction and metadata preflight: **passed**\n"
                f"- Container title identity: {result['container_title_id_match']}\n"
                f"- Matched title kind: {result['container_title_kind'] or 'not confirmed'}\n"
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
            if result["ghidra_function_census"] is not None:
                ghidra = result["ghidra_function_census"]
                screen = ghidra.get("candidate_translation_screen", {})
                ghidra_lines = [
                    "",
                    "## Ghidra aggregate-only function census",
                    "",
                    f"- Recognized function entries inside .text: {ghidra['functions_with_entry_inside_text']}",
                    f"- Leaf functions of at most 64 bytes: {ghidra['leaf_functions_le_64_bytes']}",
                    f"- Small leaf functions with a return-like instruction: {ghidra['leaf_functions_le_64_bytes_with_return_like_instruction']}",
                    f"- Private candidates screened against the current ARM subset: {screen.get('private_candidates_screened', 0)}",
                    f"- Sequences accepted by the ARM translator: {screen.get('sequences_accepted_by_current_arm_subset_translator', 0)}",
                    f"- Candidate sequences rejected by the ARM translator: {screen.get('candidate_sequences_rejected_by_current_arm_subset_translator', 0)}",
                    f"- Rejected sequences with unsupported instruction encodings: {screen.get('candidate_sequences_with_instruction_decode_rejections', 0)}",
                    f"- Rejected by sequence/runtime constraints: {screen.get('candidate_sequences_rejected_by_sequence_constraints', 0)}",
                    "- Unsupported instruction families (instruction-site counts in screened candidates): " + (
                        ", ".join(
                            f"{family} ({count})"
                            for family, count in screen.get("unsupported_instruction_encodings_by_family", {}).items()
                        ) or "none reported"
                    ),
                    f"- Sample host-C syntax check: {screen.get('native_c_syntax_check', 'not-run')}",
                    "- Native semantic equivalence independently verified: **no**",
                    "- Function boundaries independently verified: **no**",
                    "- Addresses, names, instruction bytes or disassembly published: **no**",
                    "",
                    "Top mnemonics in small leaf bodies: " + ", ".join(
                        f"{item['mnemonic']} ({item['count']})"
                        for item in ghidra["top_mnemonics_in_leaf_functions_le_64_bytes"]
                    ),
                    "",
                ]
                with Path(summary).open("a", encoding="utf-8") as output:
                    output.write("\n".join(ghidra_lines))
        print(json.dumps({
            "status": result["status"], "target": result["target"],
            "format": result["format"], "container_and_layout_validated": True,
            "container_title_id_supplied": result["container_title_id_supplied"],
            "container_title_id_match": result["container_title_id_match"],
            "container_title_kind": result["container_title_kind"],
            "candidate_census": result["candidate_census"],
            "ghidra_function_census": result["ghidra_function_census"],
            "game_bytes_or_disassembly_uploaded": False,
        }, indent=2))
        return 0
    except IntakeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
