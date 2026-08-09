"""Tests for the no-write Teams Git-backend preflight."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ida-reverse" / "scripts"))

from teams_preflight import classify, redact_remote


class TeamsPreflightTests(unittest.TestCase):
    def test_classify_requires_all_git_ida_components(self):
        readiness, missing = classify(
            {
                "drivers": {"filter": {"installed": False}, "merge": {"installed": True}},
                "gitattributes": {"ok": False},
                "ida_path": {"status": "fail"},
            }
        )
        self.assertEqual(readiness, "not_initialized")
        self.assertIn("git-ida clean/smudge filter", missing)
        self.assertIn(".gitattributes *.i64 rule", missing)
        self.assertIn("repository-local ida.path", missing)

    def test_classify_ready_requires_an_ida_executable_path(self):
        readiness, missing = classify(
            {
                "drivers": {"filter": {"installed": True}, "merge": {"installed": True}},
                "gitattributes": {"ok": True},
                "ida_path": {"status": "ok"},
            }
        )
        self.assertEqual(readiness, "ready")
        self.assertEqual(missing, [])

    def test_remote_redaction_removes_embedded_credentials(self):
        self.assertEqual(redact_remote("https://token@example.test/ida/re.git"), "https://***@example.test/ida/re.git")
        self.assertEqual(redact_remote("git@github.com:ida/re.git"), "git@github.com:ida/re.git")


if __name__ == "__main__":
    unittest.main()
