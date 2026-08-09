"""Read-only IDA 9.4 and plugin capability inventory.

The script intentionally does not install, upgrade, remove, register, or alter IDA.
It is the canonical implementation; refresh-ida-capabilities.ps1 remains a compatibility
entry point for existing Windows callers.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from validate_ida_plugins import validate_plugin_tree


def first_existing(candidates: list[str | None]) -> Path | None:
    for value in candidates:
        if value:
            path = Path(value)
            if path.exists():
                return path.resolve()
    return None


def command_path(names: list[str]) -> Path | None:
    for name in names:
        resolved = shutil.which(name)
        if resolved:
            return Path(resolved).resolve()
    return None


def run_text(command: list[str], env: dict[str, str] | None = None) -> tuple[int, str]:
    try:
        result = subprocess.run(
            command,
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return result.returncode, (result.stdout or result.stderr).strip()
    except (OSError, ValueError) as exc:
        return 1, str(exc)


def command_version(path: Path | None) -> str | None:
    if not path:
        return None
    code, output = run_text([str(path), "--version"])
    if code == 0 and output:
        return output.splitlines()[0].strip()
    return None


def hcli_status(hcli: Path | None, ida_dir: Path | None, skip_upgrade_check: bool) -> tuple[str | None, list[dict[str, Any]], str | None]:
    if not hcli:
        return None, [], None
    env = os.environ.copy()
    if ida_dir:
        # Set only in this child process. Never persist or inherit an ambiguous IDADIR.
        env["IDADIR"] = str(ida_dir)
    args = [str(hcli), "plugin", "status", "--json"]
    if skip_upgrade_check:
        args.append("--skip-upgrade-check")
    code, output = run_text(args, env=env)
    version = command_version(hcli)
    if code != 0 or not output:
        return version, [], output or "hcli plugin status failed"
    try:
        start = output.find("{")
        end = output.rfind("}")
        payload = json.loads(output[start : end + 1])
        return version, list(payload.get("plugins", [])), None
    except (ValueError, json.JSONDecodeError) as exc:
        return version, [], f"invalid hcli JSON: {exc}"


def service_online(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.25):
            return True
    except OSError:
        return False


def capability_present(name: str, installed: set[str], available_tools: set[str], specs: list[dict[str, Any]]) -> bool:
    folded = name.casefold()
    if folded in installed or folded in available_tools:
        return True
    for spec in specs:
        names = {str(spec["name"]).casefold(), *(str(alias).casefold() for alias in spec.get("aliases", []))}
        if folded in names and (
            str(spec["name"]).casefold() in installed
            or any(str(alias).casefold() in installed or str(alias).casefold() in available_tools for alias in spec.get("aliases", []))
        ):
            return True
    return False


def plugin_load_state(installed: bool, validation: dict[str, Any] | None) -> str:
    if not installed:
        return "missing"
    if not validation:
        return "installed_unverified"
    if validation.get("ida_version_compatible") is False:
        return "manifest_incompatible"
    if validation.get("runtime_compatible") is False:
        return "runtime_incompatible"
    if validation.get("status") == "compatible_preflight":
        return "compatible_preflight"
    return "installed_unverified"


def validation_for_spec(spec: dict[str, Any], by_name: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
    for name in [spec["name"], *spec.get("aliases", [])]:
        entry = by_name.get(str(name).casefold())
        if entry:
            return entry
    return None


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    skill_root = Path(__file__).resolve().parents[1]
    reference = skill_root / "ida-reverse" / "references" / "ida-plugin-capabilities.json"
    capabilities = json.loads(reference.read_text(encoding="utf-8"))

    ida_dir = first_existing(
        [
            args.ida_dir,
            os.environ.get("IDA94_ROOT"),
            r"C:\Program Files\IDA Professional 9.4",
            r"C:\IDA Professional 9.4",
            r"C:\Program Files\IDA Pro 9.4",
        ]
    )
    ida_exe = ida_dir / "idat.exe" if ida_dir else None
    ida_gui = first_existing([str(ida_dir / "ida64.exe") if ida_dir else None, str(ida_dir / "ida.exe") if ida_dir else None])
    ida_cfg = ida_dir / "cfg" / "idagui.cfg" if ida_dir else None
    ida_found = bool(ida_exe and ida_exe.exists() and ida_cfg and ida_cfg.exists())
    ida_gui_found = bool(ida_gui and ida_gui.exists())
    plugin_root = Path(args.plugin_root) if args.plugin_root else Path(os.environ.get("APPDATA", "")) / "Hex-Rays" / "IDA Pro" / "plugins"
    python_path = first_existing([args.python_exe, str(command_path(["python", "python3"]) or ""), sys.executable])
    plugin_validation = validate_plugin_tree(
        plugin_root,
        ida_version="9.4",
        python_executable=python_path or Path(sys.executable),
    )
    validation_by_name = {
        str(entry.get("name", "")).casefold(): entry
        for entry in plugin_validation["plugins"]
        if entry.get("name")
    }

    hcli = first_existing(
        [
            args.hcli_path,
            str(command_path(["hcli"]) or ""),
            str(Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "hcli" / "hcli.exe"),
        ]
    )
    hcli_version, hcli_entries, hcli_error = hcli_status(hcli, ida_dir, args.skip_upgrade_check)
    by_name = {str(entry.get("name", "")).casefold(): entry for entry in hcli_entries}

    plugin_rows: list[dict[str, Any]] = []
    for spec in capabilities["plugins"]:
        validation = validation_for_spec(spec, validation_by_name)
        entry = by_name.get(str(spec["name"]).casefold())
        if entry is None:
            for alias in spec.get("aliases", []):
                entry = by_name.get(str(alias).casefold())
                if entry:
                    break
        installed = bool(entry and entry.get("installed")) or validation is not None
        if validation is not None and entry is None:
            manager = "manifest-discovered"
        elif not entry:
            manager = "not-in-hcli-status"
        elif entry.get("kind") == "legacy":
            manager = "legacy-unmanaged"
        elif entry.get("in_repository"):
            manager = "hcli-managed"
        else:
            manager = "installed-unmanaged"
        plugin_rows.append(
            {
                "name": spec["name"],
                "role": spec["role"],
                "priority": spec["priority"],
                "version": (entry.get("version") if entry else None) or (validation.get("version") if validation else None),
                "installed": installed,
                "manager": manager,
                "in_repository": bool(entry and entry.get("in_repository")),
                "upgradable_to": entry.get("upgradable_to") if entry else None,
                "compatibility": spec.get("compatibility", "9.4 metadata expected; smoke-test per machine"),
                "modes": list(spec.get("modes", [])),
                "manifest_compatible": validation.get("ida_version_compatible") if validation else None,
                "runtime_compatible": validation.get("runtime_compatible") if validation else None,
                "runtime_loaded": validation.get("runtime_loaded", "not_run") if validation else "not_run",
                "action_verified": validation.get("action_verified", "not_run") if validation else "not_run",
                "validation_issues": validation.get("issues", []) if validation else [],
                "load_state": plugin_load_state(installed, validation),
                "use": spec["use"],
            }
        )

    idalib_path = first_existing(
        [
            str(command_path(["idalib-mcp"]) or ""),
            str(Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Python" / "Python313" / "Scripts" / "idalib-mcp.exe"),
        ]
    )
    teams_cli = ida_dir / "tools" / "teams" / "git-ida.exe" if ida_dir else None
    git_ida_version: str | None = None
    if teams_cli and teams_cli.exists():
        _, git_ida_output = run_text([str(teams_cli), "version"])
        git_ida_version = git_ida_output.splitlines()[0].strip() if git_ida_output else None
    tool_specs: list[dict[str, Any]] = [
        {"name": "ida-pro-9.4", "kind": "binary", "path": str(ida_exe) if ida_exe else None, "available": ida_found, "version": "9.4-installation" if ida_found else None, "note": "Requires a valid IDA license at runtime."},
        {"name": "hcli", "kind": "cli", "path": str(hcli) if hcli else None, "available": bool(hcli), "version": hcli_version, "note": "Used for plugin inventory and controlled upgrades."},
        {"name": "idalib-mcp", "kind": "mcp", "path": str(idalib_path) if idalib_path else None, "available": bool(idalib_path), "version": None, "note": "Presence is checked; service online state is not assumed."},
        {"name": "python", "kind": "runtime", "path": str(python_path) if python_path else None, "available": bool(python_path and python_path.exists()), "version": command_version(python_path), "note": "Required by idalib-mcp and Python-based IDA plugins."},
        {"name": "cargo", "kind": "runtime", "path": str(command_path(["cargo"]) or "") or None, "available": bool(command_path(["cargo"])), "version": command_version(command_path(["cargo"])), "note": "Required for Rust idalib crates and Rust analysis workflows."},
        {"name": "rustc", "kind": "runtime", "path": str(command_path(["rustc"]) or "") or None, "available": bool(command_path(["rustc"])), "version": command_version(command_path(["rustc"])), "note": "Required for Rust idalib crates and Rust analysis workflows."},
        {"name": "git-ida", "kind": "cli", "path": str(teams_cli) if teams_cli and teams_cli.exists() else None, "available": bool(teams_cli and teams_cli.exists()), "version": git_ida_version, "note": "IDA 9.4 Teams Git-backend driver; repository initialization remains explicit."},
    ]
    native_features: list[dict[str, Any]] = [
        {
            "name": "ida94-navigation",
            "label": "Jump Anywhere / Pathfinder / Xrefs Graph",
            "kind": "ida_native_feature",
            "available": ida_gui_found,
            "load_state": "built_in" if ida_gui_found else "missing",
            "automation": "mcp_equivalent",
            "mcp_tools": ["xref_query", "callgraph", "trace_data_flow"],
            "gates": ["valid IDA license", "GUI mode for Jump Anywhere, Pathfinder, and Xrefs Graph widgets"],
            "use": "Use MCP graph/data-flow calls for repeatable reachability evidence; use the GUI widgets for interactive exploration.",
        },
        {
            "name": "ida94-rust",
            "label": "Native Rust analysis",
            "kind": "ida_native_feature",
            "available": ida_gui_found,
            "load_state": "built_in" if ida_gui_found else "missing",
            "automation": "mcp_assisted",
            "mcp_tools": ["survey_binary", "entity_query", "decompile", "type_query"],
            "gates": ["valid IDA license"],
            "use": "Prefer IDA 9.4's rustc/crate/panic/calling-convention recovery before optional readability plugins.",
        },
        {
            "name": "ida94-swift",
            "label": "Native Swift decompilation",
            "kind": "ida_native_feature",
            "available": ida_found,
            "load_state": "built_in" if ida_found else "missing",
            "automation": "mcp_assisted",
            "mcp_tools": ["survey_binary", "decompile", "type_query", "func_profile"],
            "gates": ["valid IDA license", "Hex-Rays decompiler for pseudocode"],
            "use": "Use native Swift calling-convention and async/throwing recovery before applying manual types.",
        },
        {
            "name": "ida94-go",
            "label": "Native Go analysis",
            "kind": "ida_native_feature",
            "available": ida_found,
            "load_state": "built_in" if ida_found else "missing",
            "automation": "mcp_assisted",
            "mcp_tools": ["survey_binary", "decompile", "func_profile", "callgraph"],
            "gates": ["valid IDA license"],
            "use": "Use native pclntab/buildinfo/type and argument recovery as the first Go analysis pass.",
        },
        {
            "name": "ida94-dyld-shared-cache",
            "label": "Dyld Shared Cache workflow",
            "kind": "ida_native_feature",
            "available": ida_found,
            "load_state": "built_in" if ida_found else "missing",
            "automation": "gui_only",
            "mcp_tools": [],
            "gates": ["valid IDA license", "interactive GUI mode", "a local Dyld Shared Cache input"],
            "use": "Use IDA 9.4's dedicated DSC widgets and component navigation; do not claim headless support without a matching MCP API.",
        },
        {
            "name": "ida-teams",
            "label": "IDA Teams / git-ida",
            "kind": "ida_native_feature",
            "available": bool(teams_cli and teams_cli.exists()),
            "path": str(teams_cli) if teams_cli and teams_cli.exists() else None,
            "load_state": "installed_unverified" if teams_cli and teams_cli.exists() else "missing",
            "automation": "gui_or_cli_with_setup",
            "mcp_tools": [],
            "gates": ["Teams entitlement", "configured shared repository or server", "interactive onboarding/smoke"],
            "use": "Keep collaboration opt-in: installed git-ida.exe is not proof that a Teams workspace is configured or usable.",
        },
    ]

    installed = {str(row["name"]).casefold() for row in plugin_rows if row["installed"]}
    available_tools = {str(tool["name"]).casefold() for tool in tool_specs if tool["available"]}
    workflow_rows: list[dict[str, Any]] = []
    for workflow in capabilities["workflows"]:
        missing_tools = [name for name in workflow.get("required_tools", []) if not capability_present(name, installed, available_tools, capabilities["plugins"])]
        missing_groups = []
        for group in workflow.get("recommended_plugins", []):
            if not any(capability_present(name, installed, available_tools, capabilities["plugins"]) for name in group):
                missing_groups.append(list(group))
        gates = list(workflow.get("gates", []))
        state = "missing" if missing_tools or missing_groups else ("available_with_gates" if gates else "ready")
        workflow_rows.append({"id": workflow["id"], "label": workflow["label"], "state": state, "ready": not missing_tools and not missing_groups, "missing_tools": missing_tools, "missing_plugin_groups": missing_groups, "gates": gates, "selection": workflow["selection"]})

    return {
        "schema": 1,
        "generated_at": datetime.now(timezone.utc).astimezone().isoformat(),
        "ida": {"root": str(ida_dir) if ida_dir else None, "executable": str(ida_exe) if ida_exe else None, "gui_executable": str(ida_gui) if ida_gui else None, "config": str(ida_cfg) if ida_cfg else None, "found": ida_found, "gui_found": ida_gui_found, "requested_version": "9.4"},
        "discovery": {"hcli": str(hcli) if hcli else None, "hcli_version": hcli_version, "hcli_error": hcli_error, "plugin_root": str(plugin_root), "plugin_validation_status": plugin_validation["status"], "plugin_validation_summary": plugin_validation["summary"], "plugin_validation_issues": plugin_validation["issues"], "online_mcp_ports": [port for port in (8745, 13337) if service_online(port)], "policy": "read-only inventory; preflight-compatible does not imply runtime-loaded or action-verified"},
        "tools": tool_specs,
        "native_features": native_features,
        "plugins": plugin_rows,
        "workflows": workflow_rows,
    }


def write_report(report: dict[str, Any], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "ida-capability-graph.json"
    md_path = output_dir / "ida-capability-report.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    ida = report["ida"]
    discovery = report["discovery"]
    lines = [
        "# IDA capability report",
        "",
        f"Generated: {report['generated_at']}",
        f"IDA 9.4 headless: **{ida['found']}**  |  GUI: **{ida.get('gui_found', False)}**  |  HCLI: **{bool(discovery['hcli'])}**  |  MCP listening ports: **{', '.join(map(str, discovery['online_mcp_ports'])) or 'none'}**",
        "",
        "| Plugin | Version | Manager | Installed | Load state | Modes | Use |",
        "|---|---:|---|---|---|---|---|",
    ]
    for row in report["plugins"]:
        use = str(row["use"]).replace("|", "/")
        lines.append(f"| {row['name']} | {row['version'] or ''} | {row['manager']} | {row['installed']} | {row['load_state']} | {', '.join(row['modes'])} | {use} |")
    lines += ["", "## IDA 9.4 native features", "", "| Feature | Available | Automation | State | Gates | Use |", "|---|---|---|---|---|---|"]
    for row in report.get("native_features", []):
        use = str(row["use"]).replace("|", "/")
        lines.append(f"| {row['label']} | {row['available']} | {row['automation']} | {row['load_state']} | {'; '.join(row['gates'])} | {use} |")
    lines += ["", "## Workflow readiness", "", "| Workflow | State | Missing tools | Missing plugin groups | Gates |", "|---|---|---|---|---|"]
    for row in report["workflows"]:
        groups = ", ".join("[" + " / ".join(group) + "]" for group in row["missing_plugin_groups"])
        lines.append(f"| {row['label']} | {row['state']} | {', '.join(row['missing_tools'])} | {groups} | {'; '.join(row['gates'])} |")
    lines += ["", "Inventory is not a smoke test. Run the task-specific offline smoke before promoting a plugin to validated capability."]
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"OK:ida={ida['found']} hcli={bool(discovery['hcli'])} plugins={len(report['plugins'])} native_features={len(report.get('native_features', []))} workflows={len(report['workflows'])} json={json_path} md={md_path}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only IDA 9.4 capability inventory")
    parser.add_argument("--ida-dir")
    parser.add_argument("--hcli-path")
    parser.add_argument("--plugin-root")
    parser.add_argument("--python-exe")
    parser.add_argument("--output-dir")
    parser.add_argument("--skip-upgrade-check", action="store_true")
    args = parser.parse_args()
    output_dir = Path(args.output_dir) if args.output_dir else Path(__file__).resolve().parents[1] / "generated"
    write_report(build_report(args), output_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
