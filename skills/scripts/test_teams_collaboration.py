"""Tests for the generic, no-write IDA Teams collaboration contract."""

import tempfile
import unittest
from pathlib import Path
import shutil
import subprocess
import sys
import json

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ida-reverse" / "scripts"))

from teams_collaboration import build_collaboration_report, validate_contract
from teams_preflight import find_git_ida


class TeamsCollaborationTests(unittest.TestCase):
    def make_contract(self, root: Path) -> dict:
        lab = root / "lab"
        source = root / "source"
        lab.mkdir()
        source.mkdir()
        binary = root / "target.exe"
        binary.write_bytes(b"fixture")
        idb = lab / "analysis" / "target.i64"
        idb.parent.mkdir()
        idb.write_bytes(b"idb-fixture")
        return {
            "schema_version": 1,
            "lab_repo_path": str(lab),
            "source_project_path": str(source),
            "target": {"binary_path": str(binary), "idb_path": "analysis/target.i64", "evidence_dir": "evidence"},
            "participants": [
                {"id": "triage", "role": "triage", "branch": "teams/triage", "scope": "map"},
                {"id": "static", "role": "static_analyst", "branch": "teams/static", "scope": "range-a"},
                {"id": "runtime", "role": "runtime_analyst", "branch": "teams/runtime", "scope": "range-b"},
                {"id": "review", "role": "reviewer", "branch": "teams/review", "scope": "review"},
                {"id": "integrate", "role": "integrator", "branch": "teams/integration", "scope": "merge"},
            ],
        }

    def test_valid_contract_keeps_source_and_lab_separate(self):
        with tempfile.TemporaryDirectory() as directory:
            errors, normalized = validate_contract(self.make_contract(Path(directory)))
        self.assertEqual(errors, [])
        self.assertTrue(normalized["participants"][1]["may_write_idb"])
        self.assertFalse(normalized["participants"][0]["may_write_idb"])
        self.assertTrue(normalized["participants"][-1]["may_merge"])

    def test_contract_rejects_credential_fields_and_duplicate_writer_scopes(self):
        with tempfile.TemporaryDirectory() as directory:
            contract = self.make_contract(Path(directory))
            contract["authToken"] = "not-allowed"
            contract["nested"] = {"private_key": "also-not-allowed"}
            contract["participants"][2]["scope"] = "range-a"
            errors, _ = validate_contract(contract)
        self.assertTrue(any(error.startswith("contract_must_not_contain_credentials") for error in errors))
        self.assertIn("duplicate_analysis_scope:range-a", errors)

    def test_contract_rejects_a_source_path_that_is_the_lab(self):
        with tempfile.TemporaryDirectory() as directory:
            contract = self.make_contract(Path(directory))
            contract["source_project_path"] = contract["lab_repo_path"]
            errors, _ = validate_contract(contract)
        self.assertIn("source_project_must_be_separate_from_lab_repo", errors)

    def test_observed_report_never_claims_to_modify_the_source_project(self):
        with tempfile.TemporaryDirectory() as directory:
            contract = self.make_contract(Path(directory))
            report = build_collaboration_report(
                contract,
                {"status": "observed", "readiness": "ready", "writes_performed": False},
            )
        self.assertEqual(report["status"], "observed")
        self.assertEqual(report["readiness"], "ready_for_collaboration")
        self.assertTrue(report["policy"]["source_project_is_not_modified_by_this_command"])
        self.assertFalse(report["writes_performed"])

    @unittest.skipUnless(shutil.which("git") and find_git_ida(), "requires local Git and IDA 9.4 git-ida")
    def test_local_git_ida_smoke_reports_uninitialized_lab_without_writes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            contract = self.make_contract(root)
            lab = Path(contract["lab_repo_path"])
            initialized = subprocess.run([shutil.which("git"), "init", str(lab)], capture_output=True, text=True, check=False)
            self.assertEqual(initialized.returncode, 0, initialized.stderr)
            idb = lab / "analysis" / "target.i64"
            before = idb.read_bytes()
            report = build_collaboration_report(contract)
            self.assertEqual(report["status"], "observed")
            self.assertEqual(report["readiness"], "requires_explicit_git_ida_initialization")
            self.assertFalse(report["writes_performed"])
            self.assertEqual(idb.read_bytes(), before)

    @unittest.skipUnless(shutil.which("git") and find_git_ida(), "requires local Git and IDA 9.4 git-ida")
    def test_router_executes_the_contract_planner_without_a_duplicate_repo_path(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            contract = self.make_contract(root)
            lab = Path(contract["lab_repo_path"])
            initialized = subprocess.run([shutil.which("git"), "init", str(lab)], capture_output=True, text=True, check=False)
            self.assertEqual(initialized.returncode, 0, initialized.stderr)
            contract_path = root / "collaboration.json"
            contract_path.write_text(json.dumps(contract), encoding="utf-8")
            router = Path(__file__).resolve().with_name("route_task.py")
            result = subprocess.run(
                [
                    sys.executable,
                    str(router),
                    "--task",
                    "IDA Teams git-ida multi-agent collaboration",
                    "--teams-contract",
                    str(contract_path),
                    "--execute",
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            routed = json.loads(result.stdout)
            self.assertEqual(routed["status"], "ready")
            self.assertEqual(routed["execution"]["status"], "passed")
            self.assertEqual(routed["dispatch"]["reason"], "controlled_teams_collaboration_plan")


if __name__ == "__main__":
    unittest.main()
