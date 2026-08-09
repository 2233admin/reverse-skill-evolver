#!/usr/bin/env python3
"""Read-only readiness probe for IDA 9.4 Teams' Git backend.

The probe never runs ``git-ida initialize``, writes Git configuration, opens
IDA, contacts a remote, or changes an IDB. It only reports the exact state
that must be fixed before an explicit initialization or collaboration action.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Sequence


def run(command: Sequence[str], cwd: Path | None = None, timeout_seconds: int = 20) -> dict[str, Any]:
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
    text = str(result.get("stdout") or result.get("stderr") or "")
    return text.splitlines()[0].strip() if text else ""


def find_git_ida(explicit_path: str = "") -> Path | None:
    candidates = [
        explicit_path,
        shutil.which("git-ida"),
        str(Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "IDA Professional 9.4" / "tools" / "teams" / "git-ida.exe"),
    ]
    for candidate in candidates:
        if candidate:
            path = Path(candidate)
            if path.is_file():
                return path.resolve()
    return None


def redact_remote(url: str) -> str:
    """Keep the remote useful while never reporting an embedded credential."""
    return re.sub(r"(?i)(https?://)[^/@\s]+@", r"\1***@", url.strip())


def classify(status: dict[str, Any]) -> tuple[str, list[str]]:
    filter_ready = bool(status.get("drivers", {}).get("filter", {}).get("installed"))
    merge_ready = bool(status.get("drivers", {}).get("merge", {}).get("installed"))
    attributes_ready = bool(status.get("gitattributes", {}).get("ok"))
    ida_ready = str(status.get("ida_path", {}).get("status", "")).casefold() == "ok"
    missing: list[str] = []
    if not filter_ready:
        missing.append("git-ida clean/smudge filter")
    if not merge_ready:
        missing.append("git-ida merge driver")
    if not attributes_ready:
        missing.append(".gitattributes *.i64 rule")
    if not ida_ready:
        missing.append("repository-local ida.path")
    return ("ready" if not missing else "not_initialized"), missing


def build_report(repo_path: str, explicit_git_ida: str = "") -> dict[str, Any]:
    requested = Path(repo_path).expanduser()
    git = shutil.which("git")
    base: dict[str, Any] = {
        "schema_version": 1,
        "mode": "read_only",
        "writes_performed": False,
        "repository": {"requested_path": str(requested)},
    }
    if not requested.is_dir():
        base.update({"status": "blocked", "reason": "repository_path_not_found"})
        return base
    if not git:
        base.update({"status": "blocked", "reason": "git_not_on_path"})
        return base

    root_result = run([git, "-C", str(requested), "rev-parse", "--show-toplevel"])
    if root_result["returncode"] != 0:
        base.update({"status": "blocked", "reason": "not_a_git_repository", "detail": first_line(root_result)})
        return base
    root = Path(str(root_result["stdout"])).resolve()
    git_ida = find_git_ida(explicit_git_ida)
    if not git_ida:
        base.update({"status": "blocked", "reason": "git_ida_not_found", "repository": {"requested_path": str(requested), "root": str(root)}})
        return base

    version_result = run([str(git_ida), "version"], cwd=root)
    status_result = run([str(git_ida), "status", "--json"], cwd=root)
    if status_result["returncode"] != 0:
        base.update(
            {
                "status": "blocked",
                "reason": "git_ida_status_failed",
                "repository": {"requested_path": str(requested), "root": str(root)},
                "git_ida": {"path": str(git_ida), "version": first_line(version_result)},
                "detail": first_line(status_result),
            }
        )
        return base
    try:
        status = json.loads(str(status_result["stdout"]))
    except json.JSONDecodeError as error:
        base.update({"status": "blocked", "reason": "git_ida_status_invalid_json", "detail": str(error)})
        return base

    remote_result = run([git, "-C", str(root), "remote", "get-url", "origin"])
    remote = redact_remote(str(remote_result["stdout"])) if remote_result["returncode"] == 0 else ""
    readiness, missing = classify(status)
    base.update(
        {
            "status": "observed",
            "readiness": readiness,
            "repository": {
                "requested_path": str(requested),
                "root": str(root),
                "origin": remote or None,
                "remote_configured": bool(remote),
            },
            "git": {"path": git, "version": first_line(run([git, "--version"]))},
            "git_ida": {
                "path": str(git_ida),
                "version": first_line(version_result),
                "drivers": status.get("drivers", {}),
                "gitattributes": status.get("gitattributes", {}),
                "ida_path": status.get("ida_path", {}),
                "tracked_files": status.get("tracked_files", []),
                "call_site": status.get("call_site"),
            },
            "missing": missing,
            "next_action": (
                "ready for a separate IDB collaboration smoke"
                if readiness == "ready"
                else "requires explicit initialization in the target IDB repository; this probe did not modify it"
            ),
        }
    )
    return base


def main(argv: Sequence[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Read-only IDA Teams Git-backend readiness probe")
    parser.add_argument("--repo", required=True, help="existing Git repository to inspect")
    parser.add_argument("--git-ida", help="optional explicit git-ida executable path")
    parser.add_argument("--pretty", action="store_true", help="pretty-print JSON")
    args = parser.parse_args(argv)
    report = build_report(args.repo, args.git_ida or "")
    print(json.dumps(report, ensure_ascii=False, indent=2 if args.pretty else None))
    return 0 if report["status"] == "observed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
