"""Black-box tests for the packaged case init/review CLI.

These tests exercise the installed command surface (``python -m reverse_skill case ...``)
against synthetic case packages, not the module internals.
"""

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run_cli(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "reverse_skill", *args],
        cwd=cwd or ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


def write_complete_case(root: Path, *, corrupt_hash: bool = False, escape_artifact: bool = False) -> None:
    """Write a handoff-ready synthetic case package (black-box fixture)."""
    (root / "evidence").mkdir(parents=True)
    (root / "report").mkdir(parents=True)
    artifact = root / "evidence" / "sample.bin"
    artifact.write_bytes(b"reverse-skill case review fixture")
    digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
    if corrupt_hash:
        digest = ("0" * 63) + "f"
    artifact_path = "evidence/sample.bin"
    if escape_artifact:
        artifact_path = str(root.parent / "outside.bin")

    (root / "scope.md").write_text(
        """# Case Scope

## auth
- status: granted
- basis: lab_only

## in_scope
- assets:
  - sample.bin

## network_profile
- mode: offline

## signoff
- ready_for_act: true
""",
        encoding="utf-8",
    )
    (root / "workitems.md").write_text(
        """# Work Items

| ID | title | role | targets | surface | status | evidence | notes |
|----|-------|------|---------|---------|--------|----------|-------|
| WI-001 | Recover sample behavior | cre | sample.bin | binary | done | E-001 | |
""",
        encoding="utf-8",
    )
    (root / "timeline.md").write_text(
        """# Timeline (append-only)

## 2026-08-02T00:00:00Z | cre | static
- action: inspect local sample
- evidence_ids: [E-001]
""",
        encoding="utf-8",
    )
    (root / "evidence" / "E-001.md").write_text(
        """### E-001
- title: Sample hash
- severity: info
- status: observed
- content_hash: sha256:%s
- artifact_path: %s
- linked_workitem: WI-001
- repro_command: sha256sum evidence/sample.bin
- raw_excerpt: |
    fixture
""" % (digest, artifact_path),
        encoding="utf-8",
    )
    (root / "report" / "analysis.md").write_text(
        """### F-001
- title: Sample behavior recovered
- severity: info
- category: reverse_algo
- status: validated
- evidence_ids: [E-001]
- location: sample.bin:0x10
- impact: n/a
- confidence: high
- repro_steps: |
    1. Run the fixture command.
- remediation: n/a

### P-001
- title: Static recovery path
- path_type: callflow
- start: sample.bin
- goal: recovered behavior
- steps: |
    1. Hash the sample with E-001.
- residual_risks: n/a
""",
        encoding="utf-8",
    )


def test_case_init_json_envelope_and_package(tmp_path: Path) -> None:
    result = run_cli(
        "--json",
        "case",
        "init",
        "--hint",
        "APK 加固 反编译",
        "--case-name",
        "cli-case",
        "--preset",
        "offline-sample",
        "--package-root",
        str(tmp_path),
    )
    assert result.returncode == 0, result.stderr
    value = json.loads(result.stdout)
    assert value["ok"] is True
    assert value["command"] == "case"
    assert value["data"]["status"] == "created"
    assert value["data"]["primary_id"] == "apk-android"
    case_root = Path(value["data"]["case_root"])
    assert (case_root / "scope.md").is_file()
    scope = (case_root / "scope.md").read_text(encoding="utf-8")
    assert "- mode: offline" in scope


def test_case_init_invalid_network_profile_fails_closed(tmp_path: Path) -> None:
    result = run_cli(
        "--json",
        "case",
        "init",
        "--hint",
        "x",
        "--network-profile",
        "bogus",
        "--package-root",
        str(tmp_path),
    )
    assert result.returncode == 2
    value = json.loads(result.stdout)
    assert value["ok"] is False
    assert value["error"]["code"] == "case_contract_invalid"
    assert "unsupported network profile" in value["error"]["message"]


def test_case_init_invalid_case_name_fails_closed(tmp_path: Path) -> None:
    result = run_cli(
        "--json",
        "case",
        "init",
        "--hint",
        "x",
        "--case-name",
        "a/b",
        "--package-root",
        str(tmp_path),
    )
    assert result.returncode == 2
    assert json.loads(result.stdout)["error"]["code"] == "case_contract_invalid"


def test_case_review_passes_complete_case(tmp_path: Path) -> None:
    case_root = tmp_path / "good-case"
    write_complete_case(case_root)
    result = run_cli("--json", "case", "review", str(case_root), "--verify-hashes")
    assert result.returncode == 0, result.stdout
    value = json.loads(result.stdout)
    review = value["data"]["review"]
    assert review["status"] == "PASS"
    assert review["summary"]["evidence"] == 1
    assert review["summary"]["findings"] == 1
    assert review["summary"]["paths"] == 1
    assert review["traceability"]["E-001"] == {"workitems": 1, "timeline": 1, "reports": 2}


def test_case_review_strict_fails_with_warnings(tmp_path: Path) -> None:
    case_root = tmp_path / "warn-case"
    write_complete_case(case_root, escape_artifact=False)
    (case_root / "report" / "analysis.md").unlink()  # drop the report -> warning
    result = run_cli("--json", "case", "review", str(case_root), "--strict")
    assert result.returncode == 5
    value = json.loads(result.stdout)
    assert value["ok"] is False
    assert value["error"]["code"] == "case_review_failed"
    assert value["data"]["review"]["status"] == "FAIL"


def test_case_review_hash_mismatch_is_hard_failure(tmp_path: Path) -> None:
    case_root = tmp_path / "hash-case"
    write_complete_case(case_root, corrupt_hash=True)
    result = run_cli("--json", "case", "review", str(case_root), "--verify-hashes")
    assert result.returncode == 5
    review = json.loads(result.stdout)["data"]["review"]
    assert review["status"] == "FAIL"
    codes = {item["code"] for item in review["issues"]}
    assert "artifact.hash_mismatch" in codes


def test_case_review_path_escape_is_error(tmp_path: Path) -> None:
    case_root = tmp_path / "escape-case"
    write_complete_case(case_root, escape_artifact=True)
    result = run_cli("--json", "case", "review", str(case_root), "--verify-hashes")
    assert result.returncode == 5
    review = json.loads(result.stdout)["data"]["review"]
    codes = {item["code"] for item in review["issues"]}
    assert "artifact.outside_case" in codes
    # Escape must be an error, never a warning (fail-closed).
    assert all(item["level"] == "error" for item in review["issues"] if item["code"] == "artifact.outside_case")


def test_case_review_markdown_output(tmp_path: Path) -> None:
    case_root = tmp_path / "md-case"
    write_complete_case(case_root)
    result = run_cli("case", "review", str(case_root), "--format", "markdown")
    assert result.returncode == 0
    assert result.stdout.startswith("# Case review")
    assert "| status: PASS" in result.stdout or "- status: PASS" in result.stdout


def test_case_review_missing_root_fails(tmp_path: Path) -> None:
    result = run_cli("--json", "case", "review", str(tmp_path / "missing"))
    assert result.returncode == 5
    review = json.loads(result.stdout)["data"]["review"]
    assert review["status"] == "FAIL"
    assert review["issues"][0]["code"] == "case.missing"


def test_case_init_workdir_is_gitignored(tmp_path: Path) -> None:
    # work/ is ignored by the repository; a case created under the repo root
    # must never appear in git status.
    os.chdir(ROOT)
    subprocess.run(
        [sys.executable, "-m", "reverse_skill", "case", "init", "--hint", "x", "--case-name", "gitignored-case", "--preset", "offline-sample"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    try:
        status = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        ).stdout
        assert "work/gitignored-case" not in status
    finally:
        subprocess.run(["git", "clean", "-fdq", "work"], cwd=ROOT, capture_output=True, check=False)
        try:
            (ROOT / "work").rmdir()
        except OSError:
            pass
