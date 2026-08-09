#!/usr/bin/env python3
"""Read-only planner for an IDA Teams Git-backend collaboration lab.

The contract is deliberately external to this skill: it may name a private
source project and target binary, but the generic skill never stores either.
This command does not initialize git-ida, create worktrees, write an IDB, or
contact a remote. It validates the ownership model before those explicit
actions are considered.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
from typing import Any, Sequence

from teams_preflight import build_report as build_git_ida_preflight


ROLE_POLICIES: dict[str, dict[str, bool]] = {
    "triage": {"may_write_idb": False, "may_merge": False},
    "static_analyst": {"may_write_idb": True, "may_merge": False},
    "runtime_analyst": {"may_write_idb": True, "may_merge": False},
    "reviewer": {"may_write_idb": False, "may_merge": False},
    "integrator": {"may_write_idb": True, "may_merge": True},
}
SENSITIVE_KEY_SUFFIXES = {
    "credential",
    "credentials",
    "password",
    "secret",
    "token",
    "apikey",
    "privatekey",
}


def resolve_path(base: Path, raw_path: str) -> Path:
    path = Path(raw_path).expanduser()
    return path.resolve() if path.is_absolute() else (base / path).resolve()


def is_within(path: Path, root: Path) -> bool:
    try:
        return os.path.commonpath([os.path.normcase(str(path)), os.path.normcase(str(root))]) == os.path.normcase(str(root))
    except ValueError:
        return False


def is_same_path(left: Path, right: Path) -> bool:
    try:
        return left.samefile(right)
    except OSError:
        return os.path.normcase(str(left)) == os.path.normcase(str(right))


def is_sensitive_key(key: object) -> bool:
    compact = "".join(character for character in str(key).casefold() if character.isalnum())
    return any(compact.endswith(suffix) for suffix in SENSITIVE_KEY_SUFFIXES)


def sensitive_key_paths(value: Any, prefix: str = "") -> list[str]:
    """Reject credentials in the collaboration contract before it is reported."""
    if isinstance(value, dict):
        found: list[str] = []
        for key, nested in value.items():
            current = f"{prefix}.{key}" if prefix else str(key)
            if is_sensitive_key(key):
                found.append(current)
            found.extend(sensitive_key_paths(nested, current))
        return found
    if isinstance(value, list):
        return [item for index, nested in enumerate(value) for item in sensitive_key_paths(nested, f"{prefix}[{index}]")]
    return []


def read_contract(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8-sig") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError("collaboration contract root must be an object")
    return value


def validate_participants(participants: Any) -> tuple[list[str], list[dict[str, Any]]]:
    """Validate the reusable role, branch, and scope layout for a Teams lab."""
    errors: list[str] = []
    normalized: list[dict[str, Any]] = []
    if not isinstance(participants, list) or not participants:
        return ["participants_required"], normalized
    ids: set[str] = set()
    branches: set[str] = set()
    scopes: set[str] = set()
    integrators = 0
    for index, participant in enumerate(participants):
        prefix = f"participants[{index}]"
        if not isinstance(participant, dict):
            errors.append(f"{prefix}_must_be_object")
            continue
        participant_id = participant.get("id")
        role = participant.get("role")
        branch = participant.get("branch")
        scope = participant.get("scope")
        if not isinstance(participant_id, str) or not participant_id.strip():
            errors.append(f"{prefix}.id_required")
            continue
        if participant_id in ids:
            errors.append(f"duplicate_participant_id:{participant_id}")
        ids.add(participant_id)
        if role not in ROLE_POLICIES:
            errors.append(f"{prefix}.role_invalid")
            continue
        if role == "integrator":
            integrators += 1
        if not isinstance(branch, str) or not branch.startswith("teams/") or branch in {"main", "master"}:
            errors.append(f"{prefix}.branch_must_be_a_teams_branch")
        elif branch in branches:
            errors.append(f"duplicate_branch:{branch}")
        else:
            branches.add(branch)
        if not isinstance(scope, str) or not scope.strip():
            errors.append(f"{prefix}.scope_required")
        elif role in {"static_analyst", "runtime_analyst"} and scope in scopes:
            errors.append(f"duplicate_analysis_scope:{scope}")
        elif role in {"static_analyst", "runtime_analyst"}:
            scopes.add(scope)
        normalized.append(
            {
                "id": participant_id,
                "role": role,
                "branch": branch,
                "scope": scope,
                **ROLE_POLICIES.get(str(role), {}),
            }
        )
    if integrators != 1:
        errors.append("exactly_one_integrator_required")
    return errors, normalized


def validate_contract(contract: dict[str, Any]) -> tuple[list[str], dict[str, Any]]:
    """Validate role isolation and path boundaries without making changes."""
    errors: list[str] = []
    normalized: dict[str, Any] = {"participants": []}
    if contract.get("schema_version") != 1:
        errors.append("schema_version_must_be_1")
    sensitive = sensitive_key_paths(contract)
    if sensitive:
        errors.append("contract_must_not_contain_credentials:" + ",".join(sensitive))

    lab_raw = contract.get("lab_repo_path")
    if not isinstance(lab_raw, str) or not lab_raw.strip():
        errors.append("lab_repo_path_required")
        return errors, normalized
    lab_repo = Path(lab_raw).expanduser().resolve()
    normalized["lab_repo_path"] = str(lab_repo)
    if not lab_repo.is_dir():
        errors.append("lab_repo_path_not_found")

    source_raw = contract.get("source_project_path")
    if source_raw is not None:
        if not isinstance(source_raw, str) or not source_raw.strip():
            errors.append("source_project_path_invalid")
        else:
            source_project = Path(source_raw).expanduser().resolve()
            normalized["source_project_path"] = str(source_project)
            if not source_project.is_dir():
                errors.append("source_project_path_not_found")
            elif is_same_path(source_project, lab_repo):
                errors.append("source_project_must_be_separate_from_lab_repo")

    target = contract.get("target")
    if not isinstance(target, dict):
        errors.append("target_object_required")
        return errors, normalized
    binary_raw = target.get("binary_path")
    idb_raw = target.get("idb_path")
    if not isinstance(binary_raw, str) or not binary_raw.strip():
        errors.append("target.binary_path_required")
    else:
        binary = Path(binary_raw).expanduser().resolve()
        normalized["binary_path"] = str(binary)
        if not binary.is_file():
            errors.append("target.binary_path_not_found")
    if not isinstance(idb_raw, str) or not idb_raw.strip():
        errors.append("target.idb_path_required")
    else:
        idb = resolve_path(lab_repo, idb_raw)
        normalized["idb_path"] = str(idb)
        if not is_within(idb, lab_repo):
            errors.append("target.idb_path_must_be_inside_lab_repo")
        elif not idb.is_file():
            errors.append("target.idb_path_not_found")

    evidence_raw = target.get("evidence_dir", "evidence")
    if not isinstance(evidence_raw, str) or not evidence_raw.strip():
        errors.append("target.evidence_dir_invalid")
    else:
        evidence_dir = resolve_path(lab_repo, evidence_raw)
        normalized["evidence_dir"] = str(evidence_dir)
        if not is_within(evidence_dir, lab_repo):
            errors.append("target.evidence_dir_must_be_inside_lab_repo")

    participant_errors, normalized_participants = validate_participants(contract.get("participants"))
    errors.extend(participant_errors)
    normalized["participants"] = normalized_participants
    return errors, normalized


def build_collaboration_report(contract: dict[str, Any], preflight: dict[str, Any] | None = None) -> dict[str, Any]:
    errors, normalized = validate_contract(contract)
    base: dict[str, Any] = {
        "schema_version": 1,
        "mode": "read_only",
        "writes_performed": False,
        "contract_valid": not errors,
        "errors": errors,
    }
    if errors:
        base.update({"status": "blocked", "reason": "invalid_collaboration_contract", "collaboration": normalized})
        return base
    git_preflight = preflight if preflight is not None else build_git_ida_preflight(normalized["lab_repo_path"])
    base.update({"collaboration": normalized, "git_ida_preflight": git_preflight})
    if git_preflight.get("status") != "observed":
        base.update({"status": "blocked", "reason": "git_ida_preflight_failed"})
        return base
    readiness = str(git_preflight.get("readiness", "unknown"))
    base.update(
        {
            "status": "observed",
            "readiness": "ready_for_collaboration" if readiness == "ready" else "requires_explicit_git_ida_initialization",
            "policy": {
                "agents_must_use_separate_teams_branches": True,
                "only_integrator_may_merge": True,
                "source_project_is_not_modified_by_this_command": True,
                "credentials_are_out_of_contract": True,
            },
            "next_action": (
                "run a separate, explicit collaboration smoke in the lab repository"
                if readiness == "ready"
                else "initialize git-ida only after an operator explicitly approves the named lab repository"
            ),
        }
    )
    return base


def main(argv: Sequence[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Read-only IDA Teams multi-agent collaboration planner")
    parser.add_argument("--contract", required=True, help="external JSON collaboration contract")
    parser.add_argument("--pretty", action="store_true", help="pretty-print JSON")
    args = parser.parse_args(argv)
    try:
        report = build_collaboration_report(read_contract(Path(args.contract)))
    except (OSError, ValueError, json.JSONDecodeError) as error:
        report = {
            "schema_version": 1,
            "mode": "read_only",
            "writes_performed": False,
            "status": "blocked",
            "reason": "collaboration_contract_read_failed",
            "detail": str(error),
        }
    print(json.dumps(report, ensure_ascii=False, indent=2 if args.pretty else None))
    return 0 if report["status"] == "observed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
