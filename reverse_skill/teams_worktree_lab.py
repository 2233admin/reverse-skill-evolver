#!/usr/bin/env python3
"""Create an isolated IDA Teams lab from a dirty source repository.

Planning is read-only. Creation is explicit (``--apply``) and clones only the
source repository's committed base revision with ``git clone --no-local``.
Uncommitted source changes are deliberately excluded. The command never
initializes git-ida, opens or writes an IDB, contacts a network remote, or
writes to the source repository.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Any, Sequence

from .teams_collaboration import is_same_path, is_within, read_contract, sensitive_key_paths, validate_participants


def run(command: Sequence[str], cwd: Path | None = None, timeout_seconds: int = 120) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            list(command),
            cwd=str(cwd) if cwd else None,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            timeout=timeout_seconds,
        )
        return {
            "returncode": completed.returncode,
            "stdout": (completed.stdout or "").strip(),
            "stderr": (completed.stderr or "").strip(),
        }
    except (OSError, subprocess.TimeoutExpired) as error:
        return {"returncode": None, "stdout": "", "stderr": str(error)}


def first_line(result: dict[str, Any]) -> str:
    text = str(result.get("stderr") or result.get("stdout") or "")
    return text.splitlines()[0].strip() if text else ""


def git_value(git: str, source: Path, *arguments: str) -> tuple[str, str]:
    result = run([git, "--no-optional-locks", "-C", str(source), *arguments])
    if result["returncode"] != 0:
        return "", first_line(result)
    return str(result["stdout"]).strip(), ""


def validate_lab_contract(contract: dict[str, Any]) -> tuple[list[str], dict[str, Any]]:
    """Validate a private lab contract without creating the lab or worktrees."""
    errors: list[str] = []
    normalized: dict[str, Any] = {"participants": []}
    if contract.get("schema_version") != 1:
        errors.append("schema_version_must_be_1")
    sensitive = sensitive_key_paths(contract)
    if sensitive:
        errors.append("contract_must_not_contain_credentials:" + ",".join(sensitive))

    source_raw = contract.get("source_repo_path")
    if not isinstance(source_raw, str) or not source_raw.strip():
        errors.append("source_repo_path_required")
        return errors, normalized
    source = Path(source_raw).expanduser().resolve()
    normalized["source_repo_path"] = str(source)
    if not source.is_dir():
        errors.append("source_repo_path_not_found")

    lab_raw = contract.get("lab_root_path")
    if not isinstance(lab_raw, str) or not lab_raw.strip():
        errors.append("lab_root_path_required")
        return errors, normalized
    lab_root = Path(lab_raw).expanduser().resolve()
    normalized["lab_root_path"] = str(lab_root)
    if lab_root.exists():
        errors.append("lab_root_path_must_not_exist")
    elif not lab_root.parent.is_dir():
        errors.append("lab_root_parent_not_found")
    elif source.is_dir() and (is_same_path(source, lab_root) or is_within(lab_root, source)):
        errors.append("lab_root_must_be_outside_source_repo")

    base_ref = contract.get("base_ref", "HEAD")
    if not isinstance(base_ref, str) or not base_ref.strip() or base_ref.startswith("-"):
        errors.append("base_ref_invalid")
    else:
        normalized["base_ref"] = base_ref

    participant_errors, participants = validate_participants(contract.get("participants"))
    errors.extend(participant_errors)
    normalized["participants"] = participants
    return errors, normalized


def build_lab_plan(contract: dict[str, Any]) -> dict[str, Any]:
    errors, normalized = validate_lab_contract(contract)
    report: dict[str, Any] = {
        "schema_version": 1,
        "mode": "read_only",
        "writes_performed": False,
        "contract_valid": not errors,
        "errors": errors,
    }
    if errors:
        report.update({"status": "blocked", "reason": "invalid_worktree_lab_contract", "lab": normalized})
        return report

    git = shutil.which("git")
    if not git:
        report.update({"status": "blocked", "reason": "git_not_on_path", "lab": normalized})
        return report
    source_requested = Path(normalized["source_repo_path"])
    source_root_raw, source_error = git_value(git, source_requested, "rev-parse", "--show-toplevel")
    if source_error:
        report.update({"status": "blocked", "reason": "source_not_a_git_repository", "detail": source_error, "lab": normalized})
        return report
    source_root = Path(source_root_raw).resolve()
    revision, revision_error = git_value(git, source_root, "rev-parse", "--verify", f"{normalized['base_ref']}^{{commit}}")
    if revision_error:
        report.update({"status": "blocked", "reason": "base_ref_not_found", "detail": revision_error, "lab": normalized})
        return report
    status, status_error = git_value(git, source_root, "status", "--porcelain=v1")
    if status_error:
        report.update({"status": "blocked", "reason": "source_status_failed", "detail": status_error, "lab": normalized})
        return report

    lab_root = Path(normalized["lab_root_path"])
    normalized.update(
        {
            "source_repo_path": str(source_root),
            "source_base_revision": revision,
            "source_dirty_file_count": len(status.splitlines()) if status else 0,
            "dirty_changes_excluded": True,
            "control_repository_path": str(lab_root / "control"),
            "worktrees": [
                {
                    "participant": participant["id"],
                    "branch": participant["branch"],
                    "path": str(lab_root / "worktrees" / participant["id"]),
                    "may_write_idb": participant["may_write_idb"],
                    "may_merge": participant["may_merge"],
                }
                for participant in normalized["participants"]
            ],
        }
    )
    report.update(
        {
            "status": "observed",
            "lab": normalized,
            "policy": {
                "source_repository_is_read_only": True,
                "source_dirty_changes_are_excluded": True,
                "clone_uses_no_local": True,
                "git_ida_initialization_is_not_performed": True,
                "idb_write_is_not_performed": True,
            },
            "next_action": "review the plan, then rerun with --apply to create only the isolated lab",
        }
    )
    return report


def create_lab(plan: dict[str, Any]) -> dict[str, Any]:
    """Create the lab control clone and agent worktrees, never touching the source."""
    if plan.get("status") != "observed":
        return plan
    lab = dict(plan["lab"])
    lab_root = Path(lab["lab_root_path"])
    source = Path(lab["source_repo_path"])
    git = shutil.which("git")
    if not git:
        plan.update({"status": "blocked", "reason": "git_not_on_path"})
        return plan
    if lab_root.exists():
        plan.update({"status": "blocked", "reason": "lab_root_path_already_exists"})
        return plan

    lab_root.mkdir()
    control = Path(lab["control_repository_path"])
    clone = run([git, "clone", "--no-local", "--no-tags", "--no-checkout", str(source), str(control)])
    if clone["returncode"] != 0:
        plan.update({"status": "failed", "reason": "control_clone_failed", "detail": first_line(clone), "partial_lab_path": str(lab_root)})
        return plan
    checkout = run([git, "-C", str(control), "checkout", "--detach", str(lab["source_base_revision"])])
    if checkout["returncode"] != 0:
        plan.update({"status": "failed", "reason": "control_checkout_failed", "detail": first_line(checkout), "partial_lab_path": str(lab_root)})
        return plan

    (lab_root / "worktrees").mkdir()
    created: list[dict[str, Any]] = []
    for worktree in lab["worktrees"]:
        result = run(
            [
                git,
                "-C",
                str(control),
                "worktree",
                "add",
                "-b",
                str(worktree["branch"]),
                str(worktree["path"]),
                str(lab["source_base_revision"]),
            ]
        )
        if result["returncode"] != 0:
            plan.update(
                {
                    "status": "failed",
                    "reason": "worktree_create_failed",
                    "detail": first_line(result),
                    "created_worktrees": created,
                    "partial_lab_path": str(lab_root),
                }
            )
            return plan
        created.append(worktree)

    plan.update(
        {
            "status": "created",
            "mode": "create_isolated_lab",
            "writes_performed": True,
            "created_worktrees": created,
            "next_action": "create an IDB inside one worktree, then run the separate read-only git-ida preflight",
        }
    )
    return plan


def main(argv: Sequence[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Plan or create an isolated IDA Teams Git worktree lab")
    parser.add_argument("--contract", required=True, help="external JSON worktree-lab contract")
    parser.add_argument("--apply", action="store_true", help="explicitly create the isolated clone and worktrees")
    parser.add_argument("--pretty", action="store_true", help="pretty-print JSON")
    args = parser.parse_args(argv)
    try:
        report = build_lab_plan(read_contract(Path(args.contract)))
    except (OSError, ValueError, json.JSONDecodeError) as error:
        report = {
            "schema_version": 1,
            "mode": "read_only",
            "writes_performed": False,
            "status": "blocked",
            "reason": "worktree_lab_contract_read_failed",
            "detail": str(error),
        }
    if args.apply:
        report = create_lab(report)
    print(json.dumps(report, ensure_ascii=False, indent=2 if args.pretty else None))
    return 0 if report.get("status") in {"observed", "created"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
