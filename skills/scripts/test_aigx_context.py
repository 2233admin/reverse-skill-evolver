"""Tests for the mandatory AIGX project-context gate."""

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))

from aigx_context import _candidate_commands, inspect_project


class AigxContextTests(unittest.TestCase):
    @unittest.skipUnless(os.name == "nt", "Windows path discovery requires Windows")
    @patch("aigx_context.site.getuserbase")
    def test_windows_user_site_candidates_do_not_duplicate_python_directory(self, getuserbase):
        getuserbase.return_value = r"C:\Users\agent\AppData\Roaming\Python"
        candidates = [str(path) for path in _candidate_commands()]
        self.assertFalse(any("\\Python\\Python\\" in path for path in candidates))

    def test_missing_genome_blocks_before_tool_discovery(self):
        with tempfile.TemporaryDirectory() as directory:
            result = inspect_project(directory)
        self.assertFalse(result["ready"])
        self.assertEqual(result["reason"], "aigx_genome_missing")

    def test_valid_genome_and_resolved_boundary_pass(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".aigx").mkdir()
            (root / "src").mkdir()
            (root / "src" / "main.rs").write_text("fn main() {}\n", encoding="utf-8")

            responses = iter(
                [
                    {"returncode": 0, "data": None, "summary": "aigx-lint 1.2.0"},
                    {"returncode": 0, "data": {"ok": True, "errors": []}, "summary": ""},
                    {"returncode": 0, "data": {"found": True, "path": "src/main.rs"}, "summary": ""},
                ]
            )
            with patch("aigx_context.discover_aigx_command", return_value="aigx"):
                result = inspect_project(
                    str(root),
                    ["src/main.rs"],
                    runner=lambda _command, _args, _cwd: next(responses),
                )

        self.assertTrue(result["ready"])
        self.assertTrue(result["boundaries"][0]["found"])

    def test_missing_boundary_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".aigx").mkdir()
            (root / "target.rs").write_text("", encoding="utf-8")
            responses = iter(
                [
                    {"returncode": 0, "data": None, "summary": "aigx-lint 1.2.0"},
                    {"returncode": 0, "data": {"ok": True}, "summary": ""},
                    {"returncode": 0, "data": {"found": False}, "summary": ""},
                ]
            )
            with patch("aigx_context.discover_aigx_command", return_value="aigx"):
                result = inspect_project(
                    str(root),
                    ["target.rs"],
                    runner=lambda _command, _args, _cwd: next(responses),
                )

        self.assertFalse(result["ready"])
        self.assertIn("aigx_boundary_missing:target.rs", result["reasons"])

    def test_target_may_not_escape_project(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".aigx").mkdir()
            responses = iter(
                [
                    {"returncode": 0, "data": None, "summary": "aigx-lint 1.2.0"},
                    {"returncode": 0, "data": {"ok": True}, "summary": ""},
                ]
            )
            with patch("aigx_context.discover_aigx_command", return_value="aigx"):
                result = inspect_project(
                    str(root),
                    [str(root.parent / "outside.rs")],
                    runner=lambda _command, _args, _cwd: next(responses),
                )

        self.assertFalse(result["ready"])
        self.assertTrue(result["reasons"][0].startswith("aigx_target_outside_project:"))


if __name__ == "__main__":
    unittest.main()
