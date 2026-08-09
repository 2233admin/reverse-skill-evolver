"""Tests for health-aware, no-write CLI workspace search."""

import tempfile
import unittest
from pathlib import Path

from skills.scripts.cli_search import search


class CliSearchTests(unittest.TestCase):
    def test_native_rg_search_is_read_only(self):
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
