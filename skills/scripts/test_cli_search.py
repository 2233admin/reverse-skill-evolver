"""Tests for health-aware, no-write CLI workspace search."""

import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from skills.scripts.cli_search import search, select_engine


class CliSearchTests(unittest.TestCase):
    @patch("reverse_skill.search.shutil.which", return_value=None)
    def test_auto_falls_back_to_builtin_python(self, _which):
        engine, state = select_engine("auto")
        self.assertEqual(engine, "python")
        self.assertTrue(state["healthy"])

    def test_builtin_python_search_is_read_only(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "sample.txt"
            target.write_text("alpha\nbeta\n", encoding="utf-8")
            before = target.read_bytes()
            report = search(root, "beta", [], "python", 10)
            after = target.read_bytes()
        self.assertEqual(report["status"], "observed")
        self.assertEqual(report["engine"], "python")
        self.assertEqual(report["match_count_reported"], 1)
        self.assertEqual(before, after)

    def test_native_rg_search_is_read_only(self):
        if not shutil.which("rg"):
            self.skipTest("native rg is not installed")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "sample.txt"
            target.write_text("alpha\nbeta\n", encoding="utf-8")
            before = target.read_bytes()
            report = search(root, "beta", [], "rg", 10)
            after = target.read_bytes()
        self.assertEqual(report["status"], "observed")
        self.assertEqual(report["engine"], "rg")
        self.assertEqual(report["match_count_reported"], 1)
        self.assertEqual(before, after)

    def test_missing_directory_is_blocked(self):
        report = search(Path("C:/missing-workspace-for-cli-search"), "needle", [], "auto", 10)
        self.assertEqual(report["status"], "blocked")
        self.assertEqual(report["reason"], "search_path_not_found")


if __name__ == "__main__":
    unittest.main()
