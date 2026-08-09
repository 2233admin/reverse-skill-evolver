"""End-to-end tests for isolated Teams worktree lab creation."""

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ida-reverse" / "scripts"))

from teams_worktree_lab import build_lab_plan, create_lab, validate_lab_contract


@unittest.skipUnless(shutil.which("git"), "requires Git")
class TeamsWorktreeLabTests(unittest.TestCase):
    git = shutil.which("git")

    def run_git(self, *arguments: str) -> None:
        result = subprocess.run([self.git, *arguments], capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)

    def make_source_and_contract(self, root: Path) -> tuple[Path, dict]:
        source = root / "source"
        source.mkdir()
        self.run_git("init", str(source))
        (source / "tracked.txt").write_text("committed\n", encoding="utf-8")
        self.run_git("-C", str(source), "add", "tracked.txt")
        self.run_git(
            "-C",
            str(source),
            "-c",
            "user.name=Test User",
            "-c",
            "user.email=test@example.invalid",
            "commit",
            "-m",
            "fixture",
        )
        (source / "local-only.txt").write_text("must-not-enter-lab\n", encoding="utf-8")
        return source, {
            "schema_version": 1,
            "source_repo_path": str(source),
            "lab_root_path": str(root / "isolated-lab"),
            "base_ref": "HEAD",
            "participants": [
                {"id": "static", "role": "static_analyst", "branch": "teams/static", "scope": "range-a"},
                {"id": "runtime", "role": "runtime_analyst", "branch": "teams/runtime", "scope": "range-b"},
                {"id": "integrate", "role": "integrator", "branch": "teams/integration", "scope": "merge"},
            ],
        }

    def source_snapshot(self, source: Path) -> tuple[str, tuple[str, ...]]:
        status = subprocess.run([self.git, "-C", str(source), "status", "--porcelain=v1"], capture_output=True, text=True, check=False)
        self.assertEqual(status.returncode, 0, status.stderr)
        metadata = tuple(
            sorted(
                f"{item.relative_to(source)}|{item.stat().st_size}|{item.stat().st_mtime_ns}"
                for item in (source / ".git").rglob("*")
                if item.is_file()
            )
        )
        return status.stdout, metadata

    def test_plan_identifies_dirty_source_without_writing_it(self):
        with tempfile.TemporaryDirectory() as directory:
            source, contract = self.make_source_and_contract(Path(directory))
            before = self.source_snapshot(source)
            report = build_lab_plan(contract)
            after = self.source_snapshot(source)
        self.assertEqual(report["status"], "observed")
        self.assertEqual(report["lab"]["source_dirty_file_count"], 1)
        self.assertTrue(report["lab"]["dirty_changes_excluded"])
        self.assertEqual(before, after)

    def test_apply_creates_worktrees_without_copying_dirty_source_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            source, contract = self.make_source_and_contract(Path(directory))
            before = self.source_snapshot(source)
            report = create_lab(build_lab_plan(contract))
            after = self.source_snapshot(source)
            lab = Path(contract["lab_root_path"])
            self.assertEqual(report["status"], "created")
            self.assertTrue((lab / "control").is_dir())
            self.assertFalse((lab / "control" / "local-only.txt").exists())
            for worktree in report["created_worktrees"]:
                self.assertTrue(Path(worktree["path"]).is_dir())
                self.assertFalse((Path(worktree["path"]) / "local-only.txt").exists())
        self.assertEqual(before, after)

    def test_contract_rejects_existing_lab_or_secret(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _, contract = self.make_source_and_contract(root)
            Path(contract["lab_root_path"]).mkdir()
            contract["access_token"] = "not-allowed"
            errors, _ = validate_lab_contract(contract)
        self.assertIn("lab_root_path_must_not_exist", errors)
        self.assertTrue(any(error.startswith("contract_must_not_contain_credentials") for error in errors))

    def test_contract_rejects_a_lab_nested_inside_the_dirty_source(self):
        with tempfile.TemporaryDirectory() as directory:
            source, contract = self.make_source_and_contract(Path(directory))
            contract["lab_root_path"] = str(source / "isolated-lab")
            errors, _ = validate_lab_contract(contract)
        self.assertIn("lab_root_must_be_outside_source_repo", errors)

    def test_router_applies_an_isolated_lab_without_touching_dirty_source(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, contract = self.make_source_and_contract(root)
            contract_path = root / "private-worktree-contract.json"
            contract_path.write_text(json.dumps(contract), encoding="utf-8")
            before = self.source_snapshot(source)
            router = Path(__file__).resolve().with_name("route_task.py")
            completed = subprocess.run(
                [
                    sys.executable,
                    str(router),
                    "--task",
                    "IDA Teams worktree lab",
                    "--teams-worktree-contract",
                    str(contract_path),
                    "--apply-teams-lab",
                    "--execute",
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
            )
            after = self.source_snapshot(source)
            report = json.loads(completed.stdout)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertEqual(report["status"], "ready")
            self.assertEqual(report["execution"]["status"], "passed")
            self.assertEqual(report["dispatch"]["reason"], "controlled_teams_worktree_lab")
            self.assertEqual([stage["phase"] for stage in report["tool_plan"]["stages"]], ["teams-isolated-lab", "teams-git-preflight", "teams-ui"])
            self.assertEqual(report["tool_plan"]["stages"][1]["activation"], "excluded:teams worktree")
            self.assertTrue((root / "isolated-lab" / "control").is_dir())
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
