"""Read-only IDA plugin compatibility validator.

The validator inventories plugin metadata and performs a Python compile/static-
API preflight. It never imports a plugin into IDA and therefore deliberately
keeps runtime loading and action smoke states separate.
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


NATIVE_SUFFIXES = (".dll", ".so", ".dylib")
VERSION_RE = re.compile(r"^(>=|<=|==|!=|~=|>|<|=)?\s*(\d+(?:\.\d+)*)(?:sp(\d+))?$", re.IGNORECASE)


def version_tuple(value: str) -> tuple[int, ...]:
    match = re.search(r"\d+(?:\.\d+)+|\d+", value)
    if not match:
        raise ValueError(f"version has no numeric component: {value!r}")
    return tuple(int(part) for part in match.group(0).split("."))


def padded(value: tuple[int, ...], length: int = 4) -> tuple[int, ...]:
    return value + (0,) * max(0, length - len(value))


def match_constraint(actual: tuple[int, ...], constraint: str) -> bool:
    match = VERSION_RE.fullmatch(constraint.strip())
    if not match:
        raise ValueError(f"unsupported IDA version constraint: {constraint!r}")
    operator = match.group(1) or "=="
    expected = version_tuple(match.group(2))
    if match.group(3) is not None:
        expected = padded(expected, 3) + (int(match.group(3)),)
    left, right = padded(actual), padded(expected)
    if operator in ("=", "=="):
        return left == right
    if operator == "!=":
        return left != right
    if operator == ">=":
        return left >= right
    if operator == "<=":
        return left <= right
    if operator == ">":
        return left > right
    if operator == "<":
        return left < right
    if operator == "~=":
        upper = (expected[0] + 1, 0) if len(expected) < 2 else (expected[0] + 1, 0)
        return left >= right and left < padded(upper)
    raise ValueError(f"unsupported IDA version operator: {operator}")


def ida_version_compatible(actual_version: str, declared: object) -> bool | None:
    if declared is None:
        return None
    actual = version_tuple(actual_version)
    if isinstance(declared, list):
        if not declared:
            raise ValueError("idaVersions list is empty")
        return any(match_constraint(actual, str(item)) for item in declared)
    if not isinstance(declared, str) or not declared.strip():
        raise ValueError("idaVersions must be a non-empty string or list")
    parts = [part.strip() for part in declared.split(",") if part.strip()]
    if not parts:
        raise ValueError("idaVersions contains no constraints")
    has_operator = any(VERSION_RE.fullmatch(part) and VERSION_RE.fullmatch(part).group(1) for part in parts)
    if len(parts) > 1 and not has_operator:
        return any(match_constraint(actual, part) for part in parts)
    return all(match_constraint(actual, part) for part in parts)


def query_python_version(python_executable: Path) -> tuple[int, int, int]:
    command = [
        str(python_executable),
        "-c",
        "import json,sys; print(json.dumps(list(sys.version_info[:3])))",
    ]
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        timeout=15,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    if result.returncode != 0:
        raise RuntimeError((result.stderr or result.stdout or "Python version query failed").strip())
    values = json.loads(result.stdout)
    return int(values[0]), int(values[1]), int(values[2])


def issue(code: str, severity: str, message: str) -> dict[str, str]:
    return {"code": code, "severity": severity, "message": message}


def discover_manifests(plugin_root: Path) -> tuple[list[Path], list[dict[str, str]]]:
    manifests: list[Path] = []
    errors: list[dict[str, str]] = []

    def on_error(exc: OSError) -> None:
        errors.append(issue("plugin_tree_unreadable", "error", str(exc)))

    for current, _, files in os.walk(plugin_root, onerror=on_error, followlinks=False):
        if "ida-plugin.json" in files:
            manifests.append(Path(current) / "ida-plugin.json")
    return sorted(manifests, key=lambda path: str(path).casefold()), errors


def resolve_entrypoint(plugin_dir: Path, entry_point: str) -> tuple[Path | None, str | None]:
    requested = Path(entry_point)
    if requested.is_absolute():
        return None, None
    candidate = (plugin_dir / requested).resolve()
    try:
        candidate.relative_to(plugin_dir.resolve())
    except ValueError:
        return None, None
    if candidate.is_file():
        return candidate, "python" if candidate.suffix.casefold() == ".py" else "native"
    if candidate.suffix:
        return None, None
    for suffix in NATIVE_SUFFIXES:
        native = candidate.with_suffix(suffix)
        if native.is_file():
            return native, "native"
    return None, None


def compile_python_entrypoint(python_executable: Path, entrypoint: Path) -> tuple[bool, str]:
    command = [
        str(python_executable),
        "-c",
        "from pathlib import Path; import sys; p=Path(sys.argv[1]); compile(p.read_bytes(), str(p), 'exec')",
        str(entrypoint),
    ]
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=30,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, str(exc)
    output = "\n".join(part.strip() for part in (result.stdout, result.stderr) if part.strip())
    return result.returncode == 0, output


def removed_python_api_issues(entrypoint: Path, python_version: tuple[int, int, int]) -> list[dict[str, str]]:
    if python_version < (3, 12, 0):
        return []
    try:
        tree = ast.parse(entrypoint.read_bytes(), filename=str(entrypoint))
    except (OSError, SyntaxError):
        return []
    findings: list[dict[str, str]] = []
    if any(isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "readfp" for node in ast.walk(tree)):
        findings.append(
            issue(
                "python_removed_api_readfp",
                "error",
                "configparser readfp() was removed in Python 3.12; use read_file()",
            )
        )
    return findings


def invalid_plugin_row(manifest: Path, issues: Iterable[dict[str, str]]) -> dict[str, Any]:
    return {
        "name": manifest.parent.name,
        "manifest": str(manifest),
        "version": None,
        "declared_ida_versions": None,
        "manifest_valid": False,
        "ida_version_compatible": None,
        "entrypoint": None,
        "entrypoint_exists": False,
        "entrypoint_kind": None,
        "python_syntax_compatible": None,
        "runtime_compatible": None,
        "runtime_loaded": "not_run",
        "action_verified": "not_run",
        "status": "incompatible",
        "issues": list(issues),
    }


def validate_manifest(
    manifest: Path,
    ida_version: str,
    python_executable: Path,
    python_version: tuple[int, int, int],
) -> dict[str, Any]:
    try:
        payload = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return invalid_plugin_row(manifest, [issue("manifest_invalid_json", "error", str(exc))])

    metadata = payload.get("plugin") if isinstance(payload, dict) else None
    if not isinstance(metadata, dict):
        return invalid_plugin_row(manifest, [issue("manifest_plugin_missing", "error", "manifest.plugin must be an object")])

    problems: list[dict[str, str]] = []
    missing = [key for key in ("name", "entryPoint", "version") if not isinstance(metadata.get(key), str) or not metadata[key].strip()]
    if missing:
        problems.append(issue("manifest_required_field_missing", "error", "missing: " + ", ".join(missing)))

    declared = metadata.get("idaVersions")
    try:
        compatible = ida_version_compatible(ida_version, declared)
    except ValueError as exc:
        compatible = None
        problems.append(issue("ida_versions_invalid", "error", str(exc)))
    if compatible is False:
        problems.append(issue("ida_version_incompatible", "error", f"declared {declared!r}, requested {ida_version}"))
    elif compatible is None and declared is None:
        problems.append(issue("ida_versions_missing", "warning", "manifest does not declare idaVersions"))

    entry_value = metadata.get("entryPoint")
    entrypoint: Path | None = None
    entry_kind: str | None = None
    if isinstance(entry_value, str) and entry_value.strip():
        entrypoint, entry_kind = resolve_entrypoint(manifest.parent, entry_value)
        if entrypoint is None:
            problems.append(issue("entrypoint_missing", "error", f"entryPoint not found inside plugin directory: {entry_value}"))

    syntax_compatible: bool | None = None
    runtime_compatible: bool | None = None
    if entrypoint and entry_kind == "python":
        syntax_compatible, compile_output = compile_python_entrypoint(python_executable, entrypoint)
        if not syntax_compatible:
            problems.append(issue("python_compile_failed", "error", compile_output or "Python compile failed"))
        elif compile_output:
            problems.append(issue("python_compile_warning", "warning", compile_output))
        problems.extend(removed_python_api_issues(entrypoint, python_version))
        runtime_compatible = syntax_compatible and not any(
            item["severity"] == "error" and item["code"].startswith("python_")
            for item in problems
        )

    has_error = any(item["severity"] == "error" for item in problems)
    return {
        "name": metadata.get("name") or manifest.parent.name,
        "manifest": str(manifest),
        "version": metadata.get("version"),
        "declared_ida_versions": declared,
        "manifest_valid": not bool(missing),
        "ida_version_compatible": compatible,
        "entrypoint": str(entrypoint) if entrypoint else None,
        "entrypoint_exists": entrypoint is not None,
        "entrypoint_kind": entry_kind,
        "python_syntax_compatible": syntax_compatible,
        "runtime_compatible": runtime_compatible,
        "runtime_loaded": "not_run",
        "action_verified": "not_run",
        "status": "incompatible" if has_error else "compatible_preflight",
        "issues": problems,
    }


def validate_plugin_tree(
    plugin_root: Path,
    *,
    ida_version: str,
    python_executable: Path,
    python_version: tuple[int, int, int] | None = None,
) -> dict[str, Any]:
    root = plugin_root.resolve()
    executable = python_executable.resolve()
    global_issues: list[dict[str, str]] = []
    if not root.is_dir():
        global_issues.append(issue("plugin_root_missing", "error", f"plugin root is not a directory: {root}"))
        manifests: list[Path] = []
    else:
        manifests, discovery_issues = discover_manifests(root)
        global_issues.extend(discovery_issues)
    if not executable.is_file():
        global_issues.append(issue("python_executable_missing", "error", f"Python executable not found: {executable}"))
        detected_version = python_version or (0, 0, 0)
    else:
        try:
            detected_version = python_version or query_python_version(executable)
        except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as exc:
            detected_version = (0, 0, 0)
            global_issues.append(issue("python_version_unavailable", "error", str(exc)))

    plugins = [
        validate_manifest(manifest, ida_version, executable, detected_version)
        for manifest in manifests
    ] if not any(item["code"] == "python_executable_missing" for item in global_issues) else []
    invalid = sum(plugin["status"] == "incompatible" for plugin in plugins)
    warnings = sum(item["severity"] == "warning" for plugin in plugins for item in plugin["issues"])
    blocked = invalid > 0 or any(item["severity"] == "error" for item in global_issues)
    return {
        "schema": 1,
        "status": "blocked" if blocked else "observed",
        "policy": "read_only_preflight; runtime_loaded_and_action_verified_are_not_run",
        "generated_at": datetime.now(timezone.utc).astimezone().isoformat(),
        "plugin_root": str(root),
        "requested_ida_version": ida_version,
        "python": {
            "executable": str(executable),
            "version": ".".join(str(part) for part in detected_version),
        },
        "summary": {
            "manifests": len(manifests),
            "compatible_preflight": len(plugins) - invalid,
            "invalid": invalid,
            "warnings": warnings,
        },
        "issues": global_issues,
        "plugins": plugins,
    }


def main() -> int:
    default_root = Path(os.environ.get("APPDATA", "")) / "Hex-Rays" / "IDA Pro" / "plugins"
    parser = argparse.ArgumentParser(description="Read-only IDA plugin compatibility validator")
    parser.add_argument("--plugin-root", default=str(default_root))
    parser.add_argument("--ida-version", default="9.4")
    parser.add_argument("--python-exe", default=sys.executable)
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args()
    report = validate_plugin_tree(
        Path(args.plugin_root),
        ida_version=args.ida_version,
        python_executable=Path(args.python_exe),
    )
    print(json.dumps(report, ensure_ascii=False, indent=2 if args.pretty else None))
    return 2 if report["status"] == "blocked" else 0


if __name__ == "__main__":
    raise SystemExit(main())
