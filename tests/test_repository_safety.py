"""Unit tests for path policy and staged/working-tree Markdown validation."""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import check_repository_safety as guard  # noqa: E402


class ProhibitedPathTests(unittest.TestCase):
    def test_detects_game_image_and_extracted_module(self):
        self.assertIsNotNone(guard.prohibited_path_reason("roms/UltraSun.3DS"))
        self.assertIsNotNone(guard.prohibited_path_reason("out/code.cro"))
        self.assertIsNotNone(guard.prohibited_path_reason("extracted/main.code"))
        self.assertIsNotNone(guard.prohibited_path_reason("private/player.sav"))
        self.assertIsNotNone(guard.prohibited_path_reason("audio/stream.bcstm"))
        self.assertIsNotNone(guard.prohibited_path_reason("archives/data.garc"))
        self.assertIsNotNone(guard.prohibited_path_reason("firmware/boot9.bin"))

    def test_detects_private_configuration_and_keys(self):
        self.assertIsNotNone(guard.prohibited_path_reason(".env.production"))
        self.assertIsNotNone(guard.prohibited_path_reason("data/prod.keys"))

    def test_allows_source_and_environment_example(self):
        self.assertIsNone(guard.prohibited_path_reason("src/runtime.cpp"))
        self.assertIsNone(guard.prohibited_path_reason(".env.example"))
        self.assertIsNone(guard.prohibited_path_reason("docs/AUDIT.md"))


class MarkdownLinkTests(unittest.TestCase):
    def test_resolves_relative_markdown_links(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "docs").mkdir()
            (root / "README.md").write_text("# Root\n", encoding="utf-8")
            markdown = root / "docs" / "guide.md"
            markdown.write_text("[root](../README.md)\n", encoding="utf-8")
            self.assertEqual([], guard.local_markdown_link_errors(root, Path("docs/guide.md"), markdown.read_text()))

    def test_reports_missing_relative_markdown_link_but_ignores_external(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "docs").mkdir()
            markdown = root / "docs" / "guide.md"
            text = "[missing](not-here.md) [external](https://example.com) [anchor](#part)\n"
            errors = guard.local_markdown_link_errors(root, Path("docs/guide.md"), text)
            self.assertEqual(1, len(errors))
            self.assertIn("not-here.md", errors[0])

    def test_ignores_markdown_examples_inside_fenced_code(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "docs").mkdir()
            (root / "docs" / "ok.md").write_text("# ok\n", encoding="utf-8")
            text = "~~~md\n[example](missing.md)\n~~~\n[real](ok.md)"
            errors = guard.local_markdown_link_errors(root, Path("docs/guide.md"), text)
            self.assertEqual([], errors)

    def test_rejects_relative_link_that_escapes_repository(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "repo"
            root.mkdir()
            errors = guard.local_markdown_link_errors(root, Path("docs/guide.md"), "[outside](../../outside.md)")
            self.assertEqual(1, len(errors))
            self.assertIn("escapes repository root", errors[0])


class IndexAndWorkingTreeTests(unittest.TestCase):
    def make_git_repo(self, root: Path, readme: str) -> None:
        subprocess.run(["git", "init", "--quiet"], cwd=root, check=True)
        subprocess.run(["git", "config", "user.email", "test@example.invalid"], cwd=root, check=True)
        subprocess.run(["git", "config", "user.name", "Safety Test"], cwd=root, check=True)
        for relative in guard.REQUIRED_FILES:
            target = root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            if relative == "README.md":
                body = readme
            elif target.suffix.casefold() == ".md":
                body = "# Test document\n"
            else:
                body = "test fixture; not a project license\n"
            target.write_text(body, encoding="utf-8")
        subprocess.run(["git", "add", "--all"], cwd=root, check=True)

    def test_detects_bad_working_tree_even_when_index_is_clean(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.make_git_repo(root, "[roadmap](docs/ROADMAP.md)\n")
            (root / "README.md").write_text("[missing](not-present.md)\n", encoding="utf-8")
            errors, _notes = guard.check_repository(root)
            self.assertTrue(any("working tree" in error and "not-present.md" in error for error in errors))
            self.assertFalse(any("Git index" in error and "not-present.md" in error for error in errors))

    def test_detects_bad_staged_content_even_when_working_tree_is_clean(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.make_git_repo(root, "[missing](not-present.md)\n")
            (root / "README.md").write_text("[roadmap](docs/ROADMAP.md)\n", encoding="utf-8")
            errors, _notes = guard.check_repository(root)
            self.assertTrue(any("Git index" in error and "not-present.md" in error for error in errors))
            self.assertFalse(any("working tree" in error and "not-present.md" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
