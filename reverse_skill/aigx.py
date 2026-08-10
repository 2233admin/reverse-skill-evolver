#!/usr/bin/env python3
"""Fail-closed AIGX context gate for project-aware routing.

The gate delegates genome validation and boundary resolution to the official
``aigx``/``aigx-lint`` reference CLI.  It stores no project registry: callers
provide a project root and optional target files for each invocation.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import site
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, Optional, Sequence


EXIT_READY = 0
EXIT_BLOCKED = 2
EXIT_INVALID = 4
RunJson = Callable[[str, Sequence[str], Path], Dict[str, Any]]


def _candidate_commands(explicit: Optional[str] = None) -> Iterable[Path]:
    """Yield portable official CLI candidates without persisting host paths."""
    if explicit:
        yield Path(explicit).expanduser()
    if os.environ.get("AIGX_COMMAND"):
        yield Path(os.environ["AIGX_COMMAND"]).expanduser()
    for name in ("aigx", "aigx-lint"):
        resolved = shutil.which(name)
        if resolved:
            yield Path(resolved)

    user_base = Path(site.getuserbase())
    script_dirs = [user_base / "Scripts", user_base / "bin"]
    if os.name == "nt":
        script_dirs.extend(sorted(user_base.glob("Python*/Scripts"), reverse=True))
    for directory in script_dirs:
        for filename in ("aigx.exe", "aigx-lint.exe", "aigx", "aigx-lint"):
            yield directory / filename


def discover_aigx_command(explicit: Optional[str] = None) -> Optional[str]:
    """Return the first runnable official AIGX CLI path."""
    seen: set[str] = set()
    for candidate in _candidate_commands(explicit):
        normalized = str(candidate.resolve()) if candidate.exists() else str(candidate)
        if normalized in seen:
            continue
        seen.add(normalized)
        if candidate.is_file():
            return str(candidate.resolve())
    return None


def run_aigx_json(command: str, args: Sequence[str], cwd: Path) -> Dict[str, Any]:
    """Run the official CLI and return a bounded, machine-readable result."""
    try:
        completed = subprocess.run(
            [command, *args],
            cwd=str(cwd),
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        return {"returncode": None, "data": None, "summary": str(error)[:1000]}

    data: Any = None
    if completed.stdout.strip():
        try:
            data = json.loads(completed.stdout)
        except json.JSONDecodeError:
            data = None
    summary = "\n".join(part.strip() for part in (completed.stdout, completed.stderr) if part.strip())
    return {"returncode": completed.returncode, "data": data, "summary": summary[:4000]}


def _relative_target(project: Path, target: str) -> tuple[Optional[str], Optional[str]]:
    candidate = Path(target).expanduser()
    if not candidate.is_absolute():
        candidate = project / candidate
    try:
        relative = candidate.resolve().relative_to(project)
    except (OSError, ValueError):
        return None, "aigx_target_outside_project"
    if not candidate.exists():
        return relative.as_posix(), "aigx_target_not_found"
    return relative.as_posix(), None


def inspect_project(
    project_path: str,
    targets: Sequence[str] = (),
    command_hint: Optional[str] = None,
    runner: RunJson = run_aigx_json,
) -> Dict[str, Any]:
    """Validate a root genome and resolve every requested edit boundary."""
    project = Path(project_path).expanduser()
    if not project.is_dir():
        return {"status": "blocked", "reason": "project_path_not_found", "ready": False}
    project = project.resolve()
    genome = project / ".aigx"
    if not genome.is_dir():
        return {
            "status": "blocked",
            "reason": "aigx_genome_missing",
            "ready": False,
            "policy": "project_routes_require_root_aigx_genome",
        }

    command = discover_aigx_command(command_hint)
    if not command:
        return {
            "status": "blocked",
            "reason": "aigx_cli_unavailable",
            "ready": False,
            "policy": "official_aigx_validator_required",
        }

    version = runner(command, ["--version"], project)
    lint = runner(command, ["--root", str(project), "--format", "json"], project)
    lint_data = lint.get("data") if isinstance(lint.get("data"), dict) else {}
    if lint.get("returncode") != 0 or not lint_data.get("ok"):
        return {
            "status": "blocked",
            "reason": "aigx_lint_failed",
            "ready": False,
            "validator": {"path": command, "version": version.get("summary", "")},
            "lint": lint_data or {"summary": lint.get("summary", "")},
        }

    boundaries = []
    reasons = []
    for target in targets:
        relative, path_error = _relative_target(project, target)
        if path_error:
            reasons.append(f"{path_error}:{relative or target}")
            continue
        resolved = runner(
            command,
            ["--root", str(project), "--resolve", str(relative), "--format", "json"],
            project,
        )
        data = resolved.get("data") if isinstance(resolved.get("data"), dict) else {}
        found = resolved.get("returncode") == 0 and bool(data.get("found"))
        boundaries.append({"path": relative, "found": found, "boundary": data if found else None})
        if not found:
            reasons.append(f"aigx_boundary_missing:{relative}")

    ready = not reasons
    result: Dict[str, Any] = {
        "status": "ready" if ready else "blocked",
        "ready": ready,
        "policy": "aigx_is_mandatory_project_context; session_state_remains_external",
        "validator": {"path": command, "version": version.get("summary", "")},
        "lint": lint_data,
        "boundaries": boundaries,
    }
    if reasons:
        result["reasons"] = reasons
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate mandatory AIGX project context")
    parser.add_argument("--project-path", required=True, help="project root containing .aigx")
    parser.add_argument("--target", action="append", default=[], help="file boundary to resolve; repeatable")
    parser.add_argument("--aigx-command", help="explicit official aigx/aigx-lint executable")
    parser.add_argument("--pretty", action="store_true", help="pretty-print JSON")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = build_parser().parse_args(argv)
    result = inspect_project(args.project_path, args.target, args.aigx_command)
    print(json.dumps(result, ensure_ascii=False, indent=2 if args.pretty else None))
    return EXIT_READY if result.get("ready") else EXIT_BLOCKED


if __name__ == "__main__":
    raise SystemExit(main())
