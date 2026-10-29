"""Tests for the local 3DS intake mode using synthetic data only."""

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import local_3ds_intake as local_intake  # noqa: E402
import remote_3ds_intake as intake  # noqa: E402


class Local3DSIntakeTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="local-3ds-intake-test-")
        self.addCleanup(self.temporary.cleanup)
        self.work = Path(self.temporary.name)
        self.image = self.work / "ultra-sun.cci"
        self.image.write_bytes(b"synthetic container bytes")
        self.ctrtool = self.work / "ctrtool"
        self.ctrtool.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")

    def test_validates_local_container_without_copying_it(self):
        resolved = local_intake.validate_local_image(self.image, "cci")
        self.assertEqual(self.image.resolve(), resolved)
        self.assertEqual(b"synthetic container bytes", resolved.read_bytes())

    def test_rejects_split_archive_and_explains_extract_first(self):
        archive_part = self.work / "ultra-sun.7z.001"
        archive_part.write_bytes(b"synthetic split archive part")
        with self.assertRaisesRegex(intake.IntakeError, "extract it locally first"):
            local_intake.validate_local_image(archive_part, "cia")

    def test_rejects_recognized_extension_format_mismatch(self):
        with self.assertRaisesRegex(intake.IntakeError, "format mismatch"):
            local_intake.validate_local_image(self.image, "cia")

    def test_rejects_missing_or_empty_input(self):
        with self.assertRaisesRegex(intake.IntakeError, "does not exist"):
            local_intake.validate_local_image(self.work / "missing.cci", "cci")
        empty = self.work / "empty.cci"
        empty.write_bytes(b"")
        with self.assertRaisesRegex(intake.IntakeError, "empty"):
            local_intake.validate_local_image(empty, "cci")

    def test_rejects_game_image_inside_repository(self):
        with self.assertRaisesRegex(intake.IntakeError, "outside the repository"):
            local_intake.validate_local_image(ROOT / "README.md", "cci")

    def test_process_local_uses_temporary_extraction_and_emits_aggregate_only_result(self):
        expected_internal_result = {
            "status": "pass",
            "target": "ultra-sun",
            "format": ".cci",
            "text_size_bytes": 4096,
            "decompressed_code_size_bytes": 8192,
            "container_title_id_supplied": True,
            "container_title_id_match": "matched",
            "container_title_kind": "base",
            "candidate_census": {"candidate_sites_total": 0},
            "ghidra_function_census": None,
        }
        with patch.object(
            intake,
            "extract_and_inspect",
            return_value=expected_internal_result,
        ) as inspect, patch.object(
            intake,
            "download",
            side_effect=AssertionError("local mode must never download"),
        ):
            result = local_intake.process_local(
                self.image, "ultra-sun", "cci", self.ctrtool, index=0
            )

        inspect.assert_called_once()
        args, kwargs = inspect.call_args
        self.assertEqual(self.image.resolve(), args[0])
        self.assertEqual("ultra-sun", args[1])
        self.assertEqual("cci", args[2])
        work_directory = Path(args[4]).resolve()
        self.assertEqual("extract", work_directory.name)
        self.assertTrue(work_directory.parent.name.startswith("pokeultra-local-intake-"))
        self.assertFalse(work_directory.is_relative_to(ROOT.resolve()))
        self.assertTrue(kwargs["candidate_decode_summary"])
        self.assertEqual("local", result["source_mode"])
        self.assertFalse(result["source_uploaded"])
        self.assertFalse(result["source_path_emitted"])
        self.assertFalse(result["native_semantic_equivalence_verified"])
        self.assertFalse(result["game_started"])
        self.assertNotIn(str(self.image), json.dumps(result))

    def test_seeddb_is_passed_to_ctrtool_but_never_reported(self):
        seeddb = self.work / "existing-seeddb.bin"
        seeddb.write_bytes(b"synthetic seed database fixture")
        expected_internal_result = {
            "status": "pass",
            "target": "ultra-sun",
            "format": ".cci",
            "text_size_bytes": 4096,
            "decompressed_code_size_bytes": 8192,
            "container_title_id_supplied": True,
            "container_title_id_match": "matched",
            "container_title_kind": "base",
            "candidate_census": {"candidate_sites_total": 0},
            "ghidra_function_census": None,
        }
        with patch.object(
            intake, "extract_and_inspect", return_value=expected_internal_result
        ) as inspect:
            result = local_intake.process_local(
                self.image, "ultra-sun", "cci", self.ctrtool,
                seeddb_path=seeddb,
            )

        args, _kwargs = inspect.call_args
        self.assertEqual(
            [str(self.ctrtool.resolve()), f"--seeddb={seeddb.resolve()}"],
            args[3],
        )
        self.assertNotIn(str(seeddb.resolve()), json.dumps(result))
        self.assertFalse(result["source_uploaded"])

    def test_rejects_missing_seeddb_and_seeddb_inside_repository(self):
        with self.assertRaisesRegex(intake.IntakeError, "seed database does not exist"):
            local_intake.process_local(
                self.image, "ultra-sun", "cci", self.ctrtool,
                seeddb_path=self.work / "missing-seeddb.bin",
            )
        with self.assertRaisesRegex(intake.IntakeError, "outside the repository"):
            local_intake.process_local(
                self.image, "ultra-sun", "cci", self.ctrtool,
                seeddb_path=ROOT / "README.md",
            )

    def test_rejects_invalid_partition_index_before_running_tools(self):
        with self.assertRaisesRegex(intake.IntakeError, "from 0 to 65535"):
            local_intake.process_local(
                self.image, "ultra-sun", "cci", self.ctrtool, index=65536
            )

    def test_cli_does_not_need_remote_secret_and_prints_safe_json(self):
        fake_result = {
            "status": "pass",
            "source_mode": "local",
            "source_uploaded": False,
            "source_path_emitted": False,
            "target": "ultra-sun",
            "format": ".cci",
            "native_semantic_equivalence_verified": False,
            "game_started": False,
        }
        seeddb = self.work / "existing-seeddb.bin"
        seeddb.write_bytes(b"synthetic seed database fixture")
        stdout = io.StringIO()
        with patch.object(local_intake, "process_local", return_value=fake_result) as process, patch.dict(
            "os.environ", {"POKEULTRARECOMP_SOURCE_URL": ""}, clear=False
        ), contextlib.redirect_stdout(stdout):
            exit_code = local_intake.main([
                "--image", str(self.image),
                "--target", "ultra-sun",
                "--format", "cci",
                "--ctrtool", str(self.ctrtool),
                "--seeddb", str(seeddb),
            ])
        self.assertEqual(0, exit_code)
        self.assertEqual(fake_result, json.loads(stdout.getvalue()))
        self.assertEqual(seeddb, process.call_args.kwargs["seeddb_path"])


if __name__ == "__main__":
    unittest.main()
