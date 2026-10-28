"""Tests for the remote 3DS intake helpers using synthetic data only."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import remote_3ds_intake as intake  # noqa: E402


class Remote3DSIntakeTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="remote-3ds-intake-")
        self.addCleanup(self.temporary.cleanup)
        self.work = Path(self.temporary.name)
        self.fake_ctrtool = self.work / "fake_ctrtool.py"
        self.image_path = self.work / "synthetic.3ds"
        synthetic_ncsd = bytearray(0x1000)
        synthetic_ncsd[0x100:0x104] = b"NCSD"
        synthetic_ncsd[0x120:0x124] = (2).to_bytes(4, "little")
        synthetic_ncsd[0x124:0x128] = (4).to_bytes(4, "little")
        ncch_offset = 2 * 0x200
        synthetic_ncsd[ncch_offset + 0x100:ncch_offset + 0x104] = b"NCCH"
        synthetic_ncsd[ncch_offset + 0x118:ncch_offset + 0x120] = int(
            "00040000001B5000", 16
        ).to_bytes(8, "little")
        self.image_path.write_bytes(synthetic_ncsd)
        self.work_directory = self.work / "processing"

        header = bytearray(0x208)
        header[0:8] = b"TestGame"
        header[0x200:0x208] = int("00040000001B5000", 16).to_bytes(8, "little")
        for (address, pages, size), offset in zip(
            ((0x00100000, 1, 0x80), (0x00200000, 1, 0x40), (0x00300000, 1, 0x20)),
            (0x10, 0x20, 0x30),
        ):
            header[offset:offset + 4] = address.to_bytes(4, "little")
            header[offset + 4:offset + 8] = pages.to_bytes(4, "little")
            header[offset + 8:offset + 12] = size.to_bytes(4, "little")
        self.code = bytes((i * 11 + 9) & 0xFF for i in range(0x3000))
        self.header_fixture = self.work / "fixture.exheader"
        self.code_fixture = self.work / "fixture.code"
        self.header_fixture.write_bytes(header)
        self.code_fixture.write_bytes(self.code)
        self.fake_ctrtool.write_text(
            "import sys\nfrom pathlib import Path\n"
            "args=sys.argv[1:]\n"
            "header=next(a.split('=',1)[1] for a in args if a.startswith('--exheader='))\n"
            "exefs=next(a.split('=',1)[1] for a in args if a.startswith('--exefsdir='))\n"
            f"Path(header).write_bytes(Path({str(self.header_fixture)!r}).read_bytes())\n"
            "out=Path(exefs); out.mkdir(parents=True, exist_ok=True)\n"
            f"(out/'code.bin').write_bytes(Path({str(self.code_fixture)!r}).read_bytes())\n",
            encoding="utf-8",
        )

    def _valid_ghidra_summary(self, **overrides):
        summary = {
            "schema_version": 1,
            "status": "pass",
            "text_size_bytes": 128,
            "functions_with_entry_inside_text": 10,
            "functions_le_32_bytes": 2,
            "functions_le_64_bytes": 4,
            "functions_le_128_bytes": 8,
            "leaf_functions": 5,
            "leaf_functions_le_32_bytes": 1,
            "leaf_functions_le_64_bytes": 3,
            "leaf_functions_le_128_bytes": 4,
            "functions_with_return_like_instruction": 7,
            "leaf_functions_le_64_bytes_with_return_like_instruction": 2,
            "instructions_in_leaf_functions_le_64_bytes": 31,
            "excluded_bodies_crossing_text_bounds": 1,
            "top_mnemonics_in_leaf_functions_le_64_bytes": [
                {"mnemonic": "mov", "count": 12},
                {"mnemonic": "adds", "count": 8},
            ],
            "function_boundaries_verified": False,
            "addresses_emitted": False,
            "disassembly_emitted": False,
            "interpretation": "synthetic test fixture only",
        }
        summary.update(overrides)
        return summary

    def test_redacts_paths_addresses_and_hex_from_ghidra_hint(self):
        log_path = self.work / "private-ghidra.log"
        log_path.write_text(
            "ERROR: Script error at /home/runner/private-analysis.elf 0x00101234 payload E92D4010",
            encoding="utf-8",
        )
        hint = intake.sanitized_ghidra_failure_hint(log_path)
        self.assertIn("<path>", hint)
        self.assertIn("<address>", hint)
        self.assertNotIn("/home/runner", hint)
        self.assertNotIn("0x00101234", hint)
        self.assertNotIn("E92D4010", hint)

    def test_ghidra_hint_prioritizes_java_compiler_error_over_class_not_found(self):
        log_path = self.work / "private-ghidra-compiler.log"
        log_path.write_text(
            "Caused by: java.lang.ClassNotFoundException: FunctionCensusSummary not found by <hex>\n"
            "FunctionCensusSummary.java:71: error: cannot find symbol\n"
            "  symbol: method getNumAddresses().signum()\n",
            encoding="utf-8",
        )
        hint = intake.sanitized_ghidra_failure_hint(log_path)
        self.assertIn("FunctionCensusSummary.java:71: error:", hint)
        self.assertNotIn("ClassNotFoundException", hint)

    def test_classifies_ghidra_errors_without_returning_raw_logs(self):
        log_path = self.work / "private-ghidra.log"
        log_path.write_text("ERROR: compilation failed at private-address 0x00101234", encoding="utf-8")
        self.assertEqual("script-compilation", intake.classify_ghidra_failure(log_path))
        log_path.write_text("FunctionCensusSummary.java:71: error: incompatible types", encoding="utf-8")
        self.assertEqual("script-compilation", intake.classify_ghidra_failure(log_path))
        log_path.write_text("Script terminated with an exception: private path and address", encoding="utf-8")
        self.assertEqual("script-execution", intake.classify_ghidra_failure(log_path))
        log_path.write_text("java.lang.IllegalArgumentException: private path and address", encoding="utf-8")
        self.assertEqual("java-illegal-argument", intake.classify_ghidra_failure(log_path))
        log_path.write_text("unexpected diagnostic", encoding="utf-8")
        self.assertEqual("headless-analysis", intake.classify_ghidra_failure(log_path))
        self.assertNotIn("0x00101234", intake.classify_ghidra_failure(log_path))

    def test_ghidra_missing_summary_emits_only_redacted_diagnostic(self):
        fake_headless = self.work / "fake_no_summary.py"
        fake_headless.write_text(
            "import sys\n"
            "print('Ghidra failed while reading /tmp/private-analysis.elf at 0x00123456')\n",
            encoding="utf-8",
        )
        text_segment = {"virtual_address": 0x00100000, "declared_size_bytes": 128}
        with self.assertRaises(intake.IntakeError) as raised:
            intake.run_ghidra_function_census(
                fake_headless, "ultra-sun", self.header_fixture, self.code_fixture,
                text_segment, self.work / "ghidra-no-summary",
            )
        message = str(raised.exception)
        self.assertIn("no readable summary", message)
        self.assertIn("diagnostic:", message)
        self.assertNotIn("0x00123456", message)
        self.assertNotIn("private-analysis.elf", message)
        self.assertNotIn("/tmp/", message)

    def test_runs_ghidra_in_precreated_private_project_directory(self):
        fake_headless = self.work / "fake_analyzeHeadless.py"
        safe_fixture = self._valid_ghidra_summary()
        candidate_fixture = {
            "schema_version": 1,
            "omitted_candidate_count": 0,
            "candidates": [
                {
                    "entry_address": "0x00101000",
                    "body_size_bytes": 8,
                    "instruction_count": 2,
                    "words": ["0xE3A00001", "0xE12FFF1E"],
                },
                {
                    "entry_address": "0x00102000",
                    "body_size_bytes": 8,
                    "instruction_count": 2,
                    "words": ["0xE7910000", "0xE12FFF1E"],  # unsupported register-offset LDR form
                },
                {
                    "entry_address": "0x00103000",
                    "body_size_bytes": 8,
                    "instruction_count": 2,
                    "words": ["0xE5D00000", "0xE12FFF1E"],  # supported LDRB byte with bounded model
                },
            ],
        }
        fake_headless.write_text(
            "#!/usr/bin/env python3\n"
            "import json, sys\nfrom pathlib import Path\n"
            "args=sys.argv[1:]\n"
            "project=Path(args[0])\n"
            "if not project.is_dir(): raise SystemExit(23)\n"
            "post=args.index('-postScript')\n"
            "summary=Path(args[post+2])\n"
            "candidate_sidecar=Path(args[post+3])\n"
            "size=int(args[post+5])\n"
            f"data={safe_fixture!r}\n"
            f"candidate_data={candidate_fixture!r}\n"
            "data['text_size_bytes']=size\n"
            "summary.write_text(json.dumps(data), encoding='utf-8')\n"
            "candidate_sidecar.write_text(json.dumps(candidate_data), encoding='utf-8')\n",
            encoding="utf-8",
        )
        text_segment = {"virtual_address": 0x00100000, "declared_size_bytes": 128}
        result = intake.run_ghidra_function_census(
            fake_headless, "ultra-sun", self.header_fixture, self.code_fixture,
            text_segment, self.work / "ghidra-run",
        )
        self.assertEqual("pass", result["status"])
        self.assertEqual(10, result["functions_with_entry_inside_text"])
        screen = result["candidate_translation_screen"]
        self.assertEqual(3, screen["private_candidates_screened"])
        self.assertEqual(2, screen["sequences_accepted_by_current_arm_subset_translator"])
        self.assertFalse(screen["native_semantic_equivalence_verified"])
        self.assertFalse(screen["addresses_or_instruction_words_emitted"])
        self.assertTrue((self.work / "ghidra-run" / "ghidra-project").is_dir())

    def test_sanitizes_aggregate_ghidra_summary(self):
        summary_path = self.work / "ghidra-summary.json"
        summary_path.write_text(json.dumps(self._valid_ghidra_summary()), encoding="utf-8")
        sanitized = intake.sanitize_ghidra_summary(summary_path, 128)
        self.assertEqual("pass", sanitized["status"])
        self.assertEqual(10, sanitized["functions_with_entry_inside_text"])
        self.assertEqual(
            [{"mnemonic": "mov", "count": 12}, {"mnemonic": "adds", "count": 8}],
            sanitized["top_mnemonics_in_leaf_functions_le_64_bytes"],
        )
        self.assertNotIn("interpretation", sanitized)
        self.assertFalse(sanitized["addresses_emitted"])
        self.assertFalse(sanitized["disassembly_emitted"])

    def test_ghidra_summary_rejects_unexpected_address_fields(self):
        summary = self._valid_ghidra_summary()
        summary["addresses"] = ["0x00100000"]
        summary_path = self.work / "ghidra-summary-addresses.json"
        summary_path.write_text(json.dumps(summary), encoding="utf-8")
        with self.assertRaisesRegex(intake.IntakeError, "unexpected or missing fields"):
            intake.sanitize_ghidra_summary(summary_path, 128)

    def test_ghidra_summary_rejects_verified_boundary_claim(self):
        summary = self._valid_ghidra_summary(function_boundaries_verified=True)
        summary_path = self.work / "ghidra-summary-boundary.json"
        summary_path.write_text(json.dumps(summary), encoding="utf-8")
        with self.assertRaisesRegex(intake.IntakeError, "aggregate-only"):
            intake.sanitize_ghidra_summary(summary_path, 128)

    def test_ghidra_summary_rejects_wrong_text_size_and_invalid_counters(self):
        summary_path = self.work / "ghidra-summary-size.json"
        summary_path.write_text(json.dumps(self._valid_ghidra_summary()), encoding="utf-8")
        with self.assertRaisesRegex(intake.IntakeError, "text-size"):
            intake.sanitize_ghidra_summary(summary_path, 256)
        invalid = self._valid_ghidra_summary(functions_le_64_bytes=99)
        summary_path.write_text(json.dumps(invalid), encoding="utf-8")
        with self.assertRaisesRegex(intake.IntakeError, "ordering"):
            intake.sanitize_ghidra_summary(summary_path, 128)

    def test_ghidra_summary_rejects_invalid_mnemonic_histogram(self):
        invalid = self._valid_ghidra_summary(
            top_mnemonics_in_leaf_functions_le_64_bytes=[
                {"mnemonic": "mov r0, [0x1234]", "count": 1}
            ]
        )
        summary_path = self.work / "ghidra-summary-mnemonic.json"
        summary_path.write_text(json.dumps(invalid), encoding="utf-8")
        with self.assertRaisesRegex(intake.IntakeError, "non-mnemonic"):
            intake.sanitize_ghidra_summary(summary_path, 128)

    def test_extract_container_title_id_from_ncsd_ncch_header(self):
        self.assertEqual(
            "00040000001b5000",
            intake.extract_container_title_id(self.image_path, "cci", 0),
        )

    def test_cia_container_title_id_is_not_claimed_without_tmd_parser(self):
        self.assertIsNone(intake.extract_container_title_id(self.image_path, "cia", 0))

    def test_ncsd_title_id_rejects_invalid_magic(self):
        invalid = self.work / "invalid.3ds"
        invalid.write_bytes(b"X" * 0x1000)
        with self.assertRaisesRegex(intake.IntakeError, "NCSD header"):
            intake.extract_container_title_id(invalid, "3ds", 0)

    def test_ncsd_title_id_rejects_absent_partition_and_bad_index(self):
        no_partition = self.work / "no-partition.cci"
        empty = bytearray(0x1000)
        empty[0x100:0x104] = b"NCSD"
        no_partition.write_bytes(empty)
        with self.assertRaisesRegex(intake.IntakeError, "partition is absent"):
            intake.extract_container_title_id(no_partition, "cci", 0)
        with self.assertRaisesRegex(intake.IntakeError, "index must be from 0 to 7"):
            intake.extract_container_title_id(self.image_path, "cci", 8)

    def test_format_mapping(self):
        self.assertEqual(("3ds", "ncsd"), intake.normalize_format(".3DS"))
        self.assertEqual(("cci", "ncsd"), intake.normalize_format("cci"))
        self.assertEqual(("cia", "cia"), intake.normalize_format(".CIA"))

    def test_ghidra_census_uses_primitive_long_address_count_api(self):
        script_path = ROOT / "tools" / "ghidra_scripts" / "FunctionCensusSummary.java"
        source = script_path.read_text(encoding="utf-8")
        self.assertIn("body.getNumAddresses() == 0L", source)
        self.assertIn("long bodySize = body.getNumAddresses();", source)
        self.assertNotRegex(source, r"getNumAddresses\(\)\.(?:signum|longValue)")

    def test_arm_decode_rejection_categories_are_fixed_and_redacted(self):
        cases = (
            ("branch-with-link is unsupported: 0xEB000123", "branch-with-link"),
            ("not a supported immediate data-processing instruction: 0xE5900000", "non-immediate-data-processing"),
            ("flag-setting form is unsupported: 0xE1B00001", "unsupported-flag-setting-form"),
            ("source register r9 is outside r0-r3 subset", "register-outside-r0-r3"),
            ("only the canonical MOV immediate encoding with Rn=0 is supported", "noncanonical-mov-mvn"),
            ("unclassified private decoder error 0x00123456", "other-decode-rejection"),
            ("not a supported data-processing operand form: 0xE5900000", "unsupported-operand-class"),
            ("register Operand2 shifts are unsupported in 0xE0800081", "register-shifted-operand"),
            ("register-specified Operand2 shifts are unsupported in 0xE0800211", "register-shifted-operand"),
            ("register-offset halfword/signed memory access is unsupported: 0xE19100F2", "unsupported-operand-class"),
            ("post-indexed or writeback halfword/signed memory access is unsupported: 0xE0D100B4", "unsupported-operand-class"),
            ("signed-byte store encoding is reserved and unsupported: 0xE1C100D4", "unsupported-operand-class"),
        )
        for message, expected in cases:
            with self.subTest(expected=expected):
                self.assertEqual(expected, intake.classify_arm_decode_rejection(message))

    def test_private_ghidra_candidate_screen_rejects_malformed_sidecar(self):
        sidecar = self.work / "bad-private-ghidra-candidates.json"
        sidecar.write_text(
            json.dumps({
                "schema_version": 1,
                "omitted_candidate_count": 0,
                "addresses": ["0x00101000"],
                "candidates": [],
            }),
            encoding="utf-8",
        )
        with self.assertRaisesRegex(intake.IntakeError, "invalid schema"):
            intake.screen_private_ghidra_candidates(sidecar)

    def test_private_ghidra_candidate_screen_uses_translator_and_syntax_checks_only(self):
        from unittest.mock import patch

        sidecar = self.work / "private-ghidra-candidates.json"
        sidecar.write_text(json.dumps({
            "schema_version": 1,
            "omitted_candidate_count": 4,
            "candidates": [
                {
                    "entry_address": "0x00101000",
                    "body_size_bytes": 8,
                    "instruction_count": 2,
                    "words": ["0xE3A00001", "0xE12FFF1E"],
                },
                {
                    "entry_address": "0x00102000",
                    "body_size_bytes": 8,
                    "instruction_count": 2,
                    "words": ["0xE5D00000", "0xE12FFF1E"],  # supported immediate LDRB in bounded memory model
                },
                {
                    "entry_address": "0x00103000",
                    "body_size_bytes": 8,
                    "instruction_count": 2,
                    "words": ["0xE5900000", "0xE12FFF1E"],  # supported LDR word with bounded model
                },
                {
                    "entry_address": "0x00104000",
                    "body_size_bytes": 8,
                    "instruction_count": 2,
                    "words": ["0xE1D000B0", "0xE12FFF1E"],  # supported immediate LDRH with bounded model
                },
            ],
        }), encoding="utf-8")

        with patch.object(
            intake.shutil, "which",
            side_effect=lambda name: "/usr/bin/cc" if name == "cc" else None,
        ), patch.object(
            intake.subprocess, "run", return_value=type("Result", (), {"returncode": 0})()
        ) as compile_run:
            result = intake.screen_private_ghidra_candidates(sidecar)

        self.assertEqual(4, result["private_candidates_screened"])
        self.assertEqual(4, result["private_candidates_omitted_by_ghidra_cap"])
        self.assertEqual(4, result["sequences_accepted_by_current_arm_subset_translator"])
        self.assertEqual(0, result["candidate_sequences_rejected_by_current_arm_subset_translator"])
        self.assertEqual(0, result["candidate_sequences_with_instruction_decode_rejections"])
        self.assertEqual(0, result["candidate_sequences_rejected_by_sequence_constraints"])
        self.assertEqual({}, result["unsupported_instruction_encodings_by_family"])
        self.assertEqual("passed", result["native_c_syntax_check"])
        self.assertEqual(4, result["native_c_syntax_sample_count"])
        self.assertFalse(result["native_semantic_equivalence_verified"])
        self.assertFalse(result["function_boundaries_independently_verified"])
        self.assertFalse(result["addresses_or_instruction_words_emitted"])
        self.assertNotIn("0x00101000", compile_run.call_args.kwargs["input"])
        self.assertNotIn("0x00102000", compile_run.call_args.kwargs["input"])
        self.assertNotIn("0x00103000", compile_run.call_args.kwargs["input"])
        self.assertNotIn("0x00104000", compile_run.call_args.kwargs["input"])

    def test_private_real_candidate_screen_uses_mixed_a32_stack_translator(self):
        from unittest.mock import patch

        sidecar = self.work / "private-ghidra-mixed-candidate.json"
        sidecar.write_text(json.dumps({
            "schema_version": 1,
            "omitted_candidate_count": 0,
            "candidates": [{
                "entry_address": "0x00105000",
                "body_size_bytes": 20,
                "instruction_count": 5,
                "words": [
                    "0xE3A00003",  # MOV r0, #3
                    "0xE92D4030",  # STMDB sp!, {r4, r5, lr}
                    "0xE2800002",  # ADD r0, r0, #2
                    "0xE8BD4030",  # LDMIA sp!, {r4, r5, lr}
                    "0xE12FFF1E",  # BX lr
                ],
            }],
        }), encoding="utf-8")

        with patch.object(
            intake.shutil, "which",
            side_effect=lambda name: "/usr/bin/cc" if name == "cc" else None,
        ), patch.object(
            intake.subprocess, "run", return_value=type("Result", (), {"returncode": 0})()
        ) as compile_run:
            result = intake.screen_private_ghidra_candidates(sidecar)

        self.assertEqual(1, result["private_candidates_screened"])
        self.assertEqual(0, result["sequences_accepted_by_current_arm_subset_translator"])
        self.assertEqual(1, result["sequences_accepted_by_mixed_a32_alu_stack_translator"])
        self.assertEqual("passed", result["native_c_syntax_check"])
        self.assertEqual(1, result["native_c_syntax_sample_count"])
        self.assertNotIn("0x00105000", compile_run.call_args.kwargs["input"])
        self.assertNotIn("0xE3A00003", compile_run.call_args.kwargs["input"])
        self.assertFalse(result["native_semantic_equivalence_verified"])
        self.assertFalse(result["function_boundaries_independently_verified"])

    def test_private_real_candidate_screen_accepts_terminal_ldmia_pc_epilogue(self):
        from unittest.mock import patch

        sidecar = self.work / "private-ghidra-pc-candidate.json"
        sidecar.write_text(json.dumps({
            "schema_version": 1,
            "omitted_candidate_count": 0,
            "candidates": [{
                "entry_address": "0x00106000",
                "body_size_bytes": 12,
                "instruction_count": 3,
                "words": [
                    "0xE3A00003",  # MOV r0, #3
                    "0xE92D4030",  # STMDB sp!, {r4, r5, lr}
                    "0xE8BD8030",  # LDMIA sp!, {r4, r5, pc}
                ],
            }],
        }), encoding="utf-8")

        with patch.object(
            intake.shutil, "which",
            side_effect=lambda name: "/usr/bin/cc" if name == "cc" else None,
        ), patch.object(
            intake.subprocess, "run", return_value=type("Result", (), {"returncode": 0})()
        ) as compile_run:
            result = intake.screen_private_ghidra_candidates(sidecar)

        self.assertEqual(1, result["private_candidates_screened"])
        self.assertEqual(1, result["sequences_accepted_by_mixed_a32_alu_stack_translator"])
        self.assertEqual(1, result["sequences_accepted_with_terminal_ldmia_pc_epilogue"])
        self.assertEqual("passed", result["native_c_syntax_check"])
        self.assertIn("guest_pc_out", compile_run.call_args.kwargs["input"])
        self.assertNotIn("0x00106000", compile_run.call_args.kwargs["input"])
        self.assertNotIn("0xE8BD8030", compile_run.call_args.kwargs["input"])
        self.assertFalse(result["native_semantic_equivalence_verified"])
        self.assertFalse(result["function_boundaries_independently_verified"])

    def test_private_ghidra_candidate_screen_rejects_invalid_candidate_words(self):
        sidecar = self.work / "invalid-candidate-words.json"
        sidecar.write_text(json.dumps({
            "schema_version": 1,
            "omitted_candidate_count": 0,
            "candidates": [{
                "entry_address": "0x00101000",
                "body_size_bytes": 8,
                "instruction_count": 2,
                "words": ["MOV", "0xE12FFF1E"],
            }],
        }), encoding="utf-8")
        with self.assertRaisesRegex(intake.IntakeError, "malformed instruction word"):
            intake.screen_private_ghidra_candidates(sidecar)

    def test_google_drive_share_link_uses_gdown(self):
        from types import SimpleNamespace
        from unittest.mock import patch

        link = "https://drive.google.com/file/d/AbCdEf1234567890/view?usp=sharing&resourcekey=key_123"
        self.assertEqual(
            ("AbCdEf1234567890", "key_123"),
            intake.google_drive_file_details(link),
        )
        destination = self.work / "remote.cci"
        observed = {}

        def fake_download(**kwargs):
            observed.update(kwargs)
            kwargs["progress"](16, 16)
            Path(kwargs["output"]).write_bytes(b"synthetic cci image")
            return kwargs["output"]

        with patch.dict(sys.modules, {"gdown": SimpleNamespace(download=fake_download)}):
            size = intake.download(link, destination)

        self.assertEqual(len(b"synthetic cci image"), size)
        self.assertEqual(b"synthetic cci image", destination.read_bytes())
        self.assertEqual(link, observed["url"])
        self.assertEqual(str(destination), observed["output"])
        self.assertTrue(observed["quiet"])
        self.assertFalse(observed["use_cookies"])
        self.assertTrue(observed["resume"])
        self.assertEqual(3, observed["retries"])

    def test_google_drive_download_failure_does_not_echo_secret_url(self):
        from types import SimpleNamespace
        from unittest.mock import patch

        link = "https://drive.google.com/file/d/AbCdEf1234567890/view?private-secret=never-log-this"
        destination = self.work / "failed.cci"

        def fake_download(**kwargs):
            raise RuntimeError("request failed for " + kwargs["url"])

        with patch.dict(sys.modules, {"gdown": SimpleNamespace(download=fake_download)}):
            with self.assertRaises(intake.IntakeError) as raised:
                intake.download(link, destination)

        self.assertNotIn("never-log-this", str(raised.exception))
        self.assertFalse(destination.exists())

    def test_google_drive_failure_classifier_reports_quota_without_leaking_url(self):
        secret_url = "https://drive.google.com/file/d/SecretIdentifier123456/view?private=never-echo"
        message = (
            "Too many users have viewed or downloaded this file recently. "
            "Please try again later. " + secret_url
        )
        classified = intake.classify_google_drive_download_failure(RuntimeError(message))
        self.assertIn("rate-limiting", classified)
        self.assertNotIn("SecretIdentifier123456", classified)
        self.assertNotIn("never-echo", classified)
        self.assertNotIn(secret_url, classified)

    def test_google_drive_failure_classifier_reports_sharing_problem_safely(self):
        secret_url = "https://drive.google.com/file/d/SecretIdentifier123456/view?private=never-echo"
        message = (
            "Cannot retrieve the public link of the file. Change permission to "
            "'Anyone with the link'. " + secret_url
        )
        classified = intake.classify_google_drive_download_failure(RuntimeError(message))
        self.assertIn("public download link", classified)
        self.assertIn("sharing allows anyone with the link", classified)
        self.assertNotIn("SecretIdentifier123456", classified)
        self.assertNotIn("never-echo", classified)

    def test_google_drive_failure_classifier_reports_timeout_without_leaking_details(self):
        classified = intake.classify_google_drive_download_failure(
            TimeoutError("timed out accessing https://drive.google.com/private-secret")
        )
        self.assertIn("timed out", classified)
        self.assertNotIn("private-secret", classified)

    def test_google_drive_download_enforces_size_limit(self):
        from types import SimpleNamespace
        from unittest.mock import patch

        link = "https://drive.google.com/file/d/AbCdEf1234567890/view"
        destination = self.work / "too-large.cci"

        def fake_download(**kwargs):
            kwargs["progress"](intake.MAX_BYTES + 1, intake.MAX_BYTES + 1)
            return kwargs["output"]

        with patch.dict(sys.modules, {"gdown": SimpleNamespace(download=fake_download)}):
            with self.assertRaisesRegex(intake.IntakeError, "8 GiB limit"):
                intake.download(link, destination)

        self.assertFalse(destination.exists())

    def test_ccd_has_actionable_error(self):
        with self.assertRaisesRegex(intake.IntakeError, r"\.ccd is not a Nintendo 3DS"):
            intake.normalize_format(".ccd")

    def test_unknown_formats_fail_closed(self):
        for name in ("rom", "cxi", "3dsx", ""):
            with self.subTest(name=name), self.assertRaisesRegex(intake.IntakeError, "supported formats"):
                intake.normalize_format(name)

    def test_https_url_policy(self):
        invalid_urls = (
            "http://example.test/game.3ds", "file:///tmp/game.3ds", "",
            "https:///missing-host", "https://user:password@example.test/game.3ds",
            "https://example.test:8443/game.3ds", "https://127.0.0.1/game.3ds",
            "https://192.168.1.10/game.3ds", "https://localhost/game.3ds",
        )
        for url in invalid_urls:
            with self.subTest(url=url), self.assertRaises(intake.IntakeError):
                intake.validate_url(url)

    def test_download_rejects_non_https_without_network_access(self):
        with self.assertRaisesRegex(intake.IntakeError, "direct-download"):
            intake.download("http://example.test/game.3ds", self.work / "not-created.bin")
        self.assertFalse((self.work / "not-created.bin").exists())

    def test_code_locator_requires_single_code_file(self):
        exefs = self.work / "exefs"
        exefs.mkdir()
        (exefs / "code.bin").write_bytes(b"fake")
        self.assertEqual(exefs / "code.bin", intake._locate_code_file(exefs))
        (exefs / ".code").write_bytes(b"ambiguous")
        with self.assertRaisesRegex(intake.IntakeError, "exactly one"):
            intake._locate_code_file(exefs)

    def test_fake_ctrtool_extracts_synthetic_image(self):
        result = intake.extract_and_inspect(
            self.image_path, "ultra-sun", ".3ds",
            [sys.executable, str(self.fake_ctrtool)], self.work_directory,
        )
        self.assertEqual("pass", result["status"])
        self.assertEqual(".3ds", result["format"])
        self.assertTrue(result["container_title_id_supplied"])
        self.assertEqual("matched", result["container_title_id_match"])
        self.assertEqual("base", result["container_title_kind"])
        self.assertEqual(0x80, result["text_size_bytes"])
        self.assertTrue(result["no_game_bytes_or_disassembly_uploaded"])

    def test_work_directory_cannot_be_inside_repository(self):
        with self.assertRaisesRegex(intake.IntakeError, "outside the repository"):
            intake.extract_and_inspect(
                self.image_path, "ultra-sun", ".3ds",
                [sys.executable, str(self.fake_ctrtool)], ROOT / "unsafe-output",
            )


if __name__ == "__main__":
    unittest.main()
