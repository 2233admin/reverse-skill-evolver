#!/usr/bin/env python3
"""Controlled, read-only workspace search with explicit engine health.

Auto mode prefers a healthy ``x rg`` wrapper, then native ``rg``, and finally
the bounded built-in Python engine so the CLI stays portable.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
from typing import Any, Sequence


def run(command: Sequence[str], timeout_seconds: int = 30) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            list(command),
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            timeout=timeout_seconds,
        )
        return {"returncode": completed.returncode, "stdout": completed.stdout or "", "stderr": completed.stderr or ""}
    except (OSError, subprocess.TimeoutExpired) as error:
        return {"returncode": None, "stdout": "", "stderr": str(error)}


def xcmd_health() -> dict[str, Any]:
    executable = shutil.which("x")
    if not executable:
        return {"available": False, "healthy": False, "reason": "xcmd_not_on_path"}
    probe = run([executable, "rg", "--version"])
    combined = (str(probe["stdout"]) + "\n" + str(probe["stderr"])).casefold()
    diagnostic = "syntax of the command is incorrect" in combined
    healthy = probe["returncode"] == 0 and not diagnostic
    return {
        "available": True,
        "healthy": healthy,
        "path": executable,
        "reason": "xcmd_windows_wrapper_diagnostic" if diagnostic else ("xcmd_rg_ready" if healthy else "xcmd_rg_probe_failed"),
    }


def select_engine(requested: str) -> tuple[str, dict[str, Any]]:
    native_rg = shutil.which("rg")
    if requested == "python":
        return "python", {
            "available": True,
            "healthy": True,
            "path": sys.executable,
            "reason": "builtin_python",
        }
    if requested == "rg":
        return "rg", {"available": bool(native_rg), "healthy": bool(native_rg), "path": native_rg, "reason": "native_rg"}
    xcmd = xcmd_health()
    if requested == "xcmd":
        return "xcmd", xcmd
    if xcmd.get("healthy"):
        return "xcmd", xcmd
    if native_rg:
        return "rg", {"available": True, "healthy": True, "path": native_rg, "reason": "native_rg_fallback", "xcmd": xcmd}
    return "python", {
        "available": True,
        "healthy": True,
        "path": sys.executable,
        "reason": "builtin_python_fallback",
        "xcmd": xcmd,
    }


def python_search(path: Path, query: str, globs: list[str], max_results: int) -> dict[str, Any]:
    try:
        pattern = re.compile(query)
    except re.error as error:
        return {"status": "blocked", "reason": "invalid_search_pattern", "detail": str(error)}

    matches: list[str] = []
    files_scanned = 0
    files_skipped = 0
    truncated = False
    for candidate in sorted(path.rglob("*"), key=lambda item: item.as_posix().casefold()):
        if candidate.is_symlink() or not candidate.is_file():
            continue
        relative = candidate.relative_to(path).as_posix()
        if globs and not any(fnmatch.fnmatch(relative, glob) for glob in globs):
            continue
        try:
            if candidate.stat().st_size > 4 * 1024 * 1024:
                files_skipped += 1
                continue
            with candidate.open("r", encoding="utf-8", errors="replace") as handle:
                files_scanned += 1
                for line_number, line in enumerate(handle, start=1):
                    if not pattern.search(line):
                        continue
                    if len(matches) >= max_results:
                        truncated = True
                        break
                    matches.append(f"{candidate}:{line_number}:{line.rstrip()}")
        except OSError:
            files_skipped += 1
        if truncated:
            break
    return {
        "status": "observed",
        "matches": matches,
        "match_count_reported": len(matches),
        "truncated": truncated,
        "files_scanned": files_scanned,
        "files_skipped": files_skipped,
    }


def search(path: Path, query: str, globs: list[str], engine_requested: str, max_results: int) -> dict[str, Any]:
    report: dict[str, Any] = {"schema_version": 1, "mode": "read_only", "writes_performed": False}
    if not path.is_dir():
        report.update({"status": "blocked", "reason": "search_path_not_found", "search_path": str(path)})
        return report
    engine, engine_state = select_engine(engine_requested)
    executable = engine_state.get("path")
    if not executable:
        report.update({"status": "blocked", "reason": "search_engine_not_available", "engine": engine, "engine_state": engine_state})
        return report
    if engine == "python":
        result = python_search(path, query, globs, max_results)
        report.update(result)
        report.update(
            {
                "engine": engine,
                "engine_state": engine_state,
                "search_path": str(path),
                "query": query,
            }
        )
        return report
    command: list[str] = [str(executable)]
    if engine == "xcmd":
        command.append("rg")
    command.extend(["--no-heading", "--line-number"])
    for glob in globs:
        command.extend(["--glob", glob])
    command.extend(["--", query, str(path)])
    result = run(command)
    if result["returncode"] not in {0, 1}:
        report.update(
            {
                "status": "blocked",
                "reason": "search_command_failed",
                "engine": engine,
                "engine_state": engine_state,
                "command": command,
                "detail": str(result["stderr"]).splitlines()[0] if result["stderr"] else "",
            }
        )
        return report
    matches = str(result["stdout"]).splitlines()[:max_results]
    report.update(
        {
            "status": "observed",
            "engine": engine,
            "engine_state": engine_state,
            "command": command,
            "search_path": str(path),
            "query": query,
            "match_count_reported": len(matches),
            "matches": matches,
            "truncated": len(str(result["stdout"]).splitlines()) > len(matches),
        }
    )
    return report


def main(argv: Sequence[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Read-only workspace search using x-cmd, rg, or built-in Python")
    parser.add_argument("--path", required=True, help="existing workspace directory")
    parser.add_argument("--query", required=True, help="ripgrep-compatible search pattern")
    parser.add_argument("--glob", action="append", default=[], help="optional ripgrep glob; may be repeated")
    parser.add_argument("--engine", choices=("auto", "xcmd", "rg", "python"), default="auto")
    parser.add_argument("--max-results", type=int, default=100)
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args(argv)
    if args.max_results < 1:
        parser.error("--max-results must be positive")
    report = search(Path(args.path).expanduser(), args.query, list(args.glob), args.engine, args.max_results)
    print(json.dumps(report, ensure_ascii=False, indent=2 if args.pretty else None))
    return 0 if report["status"] == "observed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
