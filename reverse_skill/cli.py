from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Mapping

import click

from . import __version__
from .aigx import inspect_project
from .case import (
    CaseContractError,
    CasePackageError,
    init_case,
    normalize_network_profile,
    render_markdown as render_case_review_markdown,
    review_case,
    validate_case_name,
)
from .errors import EnvironmentUnavailable, ReverseSkillError, ToolOperationError
from .ida import find_latest_ida, ida_release_version, install_ida_mcp, start_server
from .ida_capabilities import build_report as build_ida_capability_report
from .ida_plugins import validate_plugin_tree
from .integrations import annotate_yara_matches, integration_inventory, scan_yara
from .mcp import McpClient, probe_tool_count
from .routing import build_plan, execute_plan
from .search import search as search_workspace
from .teams_collaboration import build_collaboration_report, read_contract
from .teams_preflight import build_report as build_teams_preflight
from .teams_worktree_lab import build_lab_plan, create_lab


SCHEMA_VERSION = "1"
COMMAND_NAMES = {
    "install",
    "register",
    "start",
    "status",
    "doctor",
    "tools",
    "integrations",
    "context",
    "route",
    "search",
    "plugins",
    "teams",
    "yara-scan",
    "open",
    "sessions",
    "call",
    "close",
    "case",
    "gates",
    "index",
    "retrieve",
}


class State:
    def __init__(self, url: str, name: str, json_output: bool, timeout: float) -> None:
        self.url = url
        self.name = name
        self.json_output = json_output
        self.timeout = timeout


def _envelope(command: str, *, data: Any = None, error: Mapping[str, Any] | None = None) -> dict[str, Any]:
    return {
        "schemaVersion": SCHEMA_VERSION,
        "ok": error is None,
        "command": command,
        "data": data,
        "error": error,
    }


def _human(value: Any) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, indent=2)


def emit(
    state: State,
    command: str,
    data: Any,
    *,
    error: Mapping[str, Any] | None = None,
) -> None:
    if state.json_output:
        click.echo(json.dumps(_envelope(command, data=data, error=error), ensure_ascii=False))
    else:
        click.echo(_human(data))
        if error:
            click.echo(f"Error: {error['message']}", err=True)


def structured_content(result: Mapping[str, Any]) -> Mapping[str, Any]:
    value = result.get("structuredContent")
    return value if isinstance(value, Mapping) else result


def codex_registration(name: str) -> dict[str, Any] | None:
    codex = shutil.which("codex")
    if not codex:
        return None
    completed = subprocess.run(
        [codex, "mcp", "get", name, "--json"], capture_output=True, text=True, check=False
    )
    if completed.returncode != 0 or not completed.stdout.strip():
        return None
    try:
        value = json.loads(completed.stdout)
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


def register_codex(name: str, url: str) -> dict[str, Any]:
    codex = shutil.which("codex")
    if not codex:
        raise EnvironmentUnavailable("codex CLI is not installed or is not on PATH")
    existing = codex_registration(name)
    transport = (existing or {}).get("transport") or {}
    if (
        existing
        and transport.get("type") == "streamable_http"
        and transport.get("url") == url
        and existing.get("enabled") is True
    ):
        return {"name": name, "url": url, "changed": False, "status": "already_registered"}
    if existing:
        completed = subprocess.run(
            [codex, "mcp", "remove", name], capture_output=True, text=True, check=False
        )
        if completed.returncode != 0:
            detail = completed.stderr.strip() or completed.stdout.strip()
            raise EnvironmentUnavailable(
                f"failed to remove existing Codex MCP registration {name!r}: {detail}"
            )
    completed = subprocess.run(
        [codex, "mcp", "add", name, "--url", url], capture_output=True, text=True, check=False
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise EnvironmentUnavailable(f"failed to register Codex MCP server {name!r}: {detail}")
    return {"name": name, "url": url, "changed": True, "status": "registered"}


@click.group(no_args_is_help=True, context_settings={"help_option_names": ["-h", "--help"]})
@click.option("--url", default="http://127.0.0.1:13337/mcp", show_default=True)
@click.option("--name", default="idapro", show_default=True, help="Codex MCP registration name.")
@click.option("--json", "json_output", is_flag=True, help="Emit one stable JSON envelope on stdout.")
@click.option("--timeout", type=click.FloatRange(min=0.1), default=120.0, show_default=True)
@click.version_option(__version__, prog_name="reverse-skill")
@click.pass_context
def cli(ctx: click.Context, url: str, name: str, json_output: bool, timeout: float) -> None:
    """Route reverse-engineering work and operate IDA MCP from Python."""
    ctx.obj = State(url=url, name=name, json_output=json_output, timeout=timeout)


@cli.command()
@click.option("--upgrade", is_flag=True, help="Upgrade ida-pro-mcp before running its installer.")
@click.pass_obj
def install(state: State, upgrade: bool) -> None:
    """Install ida-pro-mcp and run its interactive installer."""
    if state.json_output:
        raise click.UsageError("install is interactive and does not support --json")
    emit(state, "install", install_ida_mcp(upgrade=upgrade))


@cli.command()
@click.pass_obj
def register(state: State) -> None:
    """Register the Streamable HTTP endpoint with Codex."""
    emit(state, "register", register_codex(state.name, state.url))


@cli.command()
@click.option("--ida-dir", type=click.Path(file_okay=False, path_type=Path))
@click.option("--port", type=click.IntRange(1, 65535), default=13337, show_default=True)
@click.option("--server-path", type=click.Path(dir_okay=False, path_type=Path))
@click.option("--replace-stale", is_flag=True, help="Terminate stale idalib-mcp processes before starting.")
@click.pass_obj
def start(state: State, ida_dir: Path | None, port: int, server_path: Path | None, replace_stale: bool) -> None:
    """Start or reuse the local IDA MCP service."""
    result = start_server(
        probe=probe_tool_count,
        ida_dir=str(ida_dir) if ida_dir else None,
        port=port,
        server_path=str(server_path) if server_path else None,
        replace_stale=replace_stale,
    )
    emit(state, "start", result)


def _status_data(state: State) -> dict[str, Any]:
    ida = find_latest_ida()
    registration = codex_registration(state.name)
    transport = (registration or {}).get("transport") or {}
    with McpClient(state.url, timeout=state.timeout) as client:
        tools = client.request("tools/list")
        return {
            "ida": ida.public() if ida else None,
            "mcp": {
                "url": state.url,
                "online": True,
                "era": client.era,
                "protocolVersion": client.protocol_version,
                "server": client.server_info,
                "protocolSession": bool(client.session_id),
                "toolCount": len(tools.get("tools") or []),
            },
            "codex": {
                "registered": registration is not None,
                "name": state.name,
                "url": transport.get("url"),
                "enabled": bool((registration or {}).get("enabled")),
            },
        }


@cli.command()
@click.pass_obj
def status(state: State) -> None:
    """Report the selected IDA, MCP negotiation, and Codex registration."""
    emit(state, "status", _status_data(state))


@cli.command()
@click.pass_obj
def doctor(state: State) -> None:
    """Alias for status."""
    emit(state, "doctor", _status_data(state))


@cli.command()
@click.pass_obj
def tools(state: State) -> None:
    """List tools discovered from the active MCP endpoint."""
    with McpClient(state.url, timeout=state.timeout) as client:
        emit(state, "tools", client.request("tools/list"))


@cli.command()
@click.pass_obj
def integrations(state: State) -> None:
    """Report local tools that can complement the IDA workflow."""
    values = integration_inventory()
    emit(
        state,
        "integrations",
        {
            "integrations": values,
            "summary": {
                "ready": sum(item["support"] == "ready" and item["available"] for item in values),
                "available": sum(item["available"] for item in values),
            },
        },
    )


@cli.command(name="context")
@click.argument("project_path", type=click.Path(exists=True, file_okay=False, resolve_path=True, path_type=Path))
@click.option("--target", "targets", multiple=True, help="Project-relative edit target; repeatable.")
@click.option("--aigx-command", type=click.Path(dir_okay=False, path_type=Path))
@click.pass_obj
def context_check(state: State, project_path: Path, targets: tuple[str, ...], aigx_command: Path | None) -> int:
    """Validate a project's AIGX context and requested edit boundaries."""
    result = inspect_project(
        str(project_path),
        list(targets),
        str(aigx_command) if aigx_command else None,
    )
    ready = bool(result.get("ready"))
    error = None if ready else {
        "code": "context_blocked",
        "message": str(result.get("reason") or "AIGX context is not ready"),
    }
    emit(state, "context", result, error=error)
    return 0 if ready else 5


@cli.command(name="route")
@click.argument("task", required=False)
@click.option("--task-file", type=click.Path(exists=True, dir_okay=False, resolve_path=True, path_type=Path))
@click.option("--task-json", help="Inline JSON task contract.")
@click.option("--input-path", type=click.Path(path_type=Path))
@click.option("--target-kind")
@click.option("--mode")
@click.option("--route-id")
@click.option(
    "--authorization-scope",
    type=click.Choice(["ctf", "own_asset", "lab_fixture", "bug_bounty", "engagement"]),
)
@click.option("--project-path", type=click.Path(file_okay=False, path_type=Path))
@click.option("--aigx-target", "aigx_targets", multiple=True)
@click.option("--aigx-command", type=click.Path(dir_okay=False, path_type=Path))
@click.option("--search-path", type=click.Path(file_okay=False, path_type=Path))
@click.option("--search-query")
@click.option("--search-engine", type=click.Choice(["auto", "xcmd", "rg", "python"]), default="auto")
@click.option("--search-glob", "search_globs", multiple=True)
@click.option("--repo-path", type=click.Path(file_okay=False, path_type=Path))
@click.option("--teams-contract", type=click.Path(dir_okay=False, path_type=Path))
@click.option("--teams-worktree-contract", type=click.Path(dir_okay=False, path_type=Path))
@click.option("--apply-teams-lab", is_flag=True)
@click.option("--execute", is_flag=True, help="Execute only when every route gate passes.")
@click.pass_obj
def route_command(
    state: State,
    task: str | None,
    task_file: Path | None,
    task_json: str | None,
    input_path: Path | None,
    target_kind: str | None,
    mode: str | None,
    route_id: str | None,
    authorization_scope: str | None,
    project_path: Path | None,
    aigx_targets: tuple[str, ...],
    aigx_command: Path | None,
    search_path: Path | None,
    search_query: str | None,
    search_engine: str,
    search_globs: tuple[str, ...],
    repo_path: Path | None,
    teams_contract: Path | None,
    teams_worktree_contract: Path | None,
    apply_teams_lab: bool,
    execute: bool,
) -> int:
    """Build a deterministic, fail-closed reverse/security dispatch plan."""
    if task_file and task_json:
        raise click.UsageError("use only one of --task-file or --task-json")
    try:
        if task_file:
            contract = json.loads(task_file.read_text(encoding="utf-8-sig"))
        elif task_json:
            contract = json.loads(task_json)
        else:
            contract = {}
    except json.JSONDecodeError as exc:
        raise click.BadParameter(f"invalid task JSON: {exc.msg}") from exc
    if not isinstance(contract, dict):
        raise click.BadParameter("task contract must be a JSON object")

    overlays: dict[str, Any] = {
        "task": task,
        "input_path": str(input_path) if input_path else None,
        "target_kind": target_kind,
        "mode": mode,
        "route_id": route_id,
        "project_path": str(project_path) if project_path else None,
        "aigx_targets": list(aigx_targets) or None,
        "aigx_command": str(aigx_command) if aigx_command else None,
        "search_path": str(search_path) if search_path else None,
        "search_query": search_query,
        "search_engine": search_engine if (search_path or search_query) else None,
        "search_globs": list(search_globs) or None,
        "repo_path": str(repo_path) if repo_path else None,
        "teams_contract_path": str(teams_contract) if teams_contract else None,
        "teams_worktree_contract_path": str(teams_worktree_contract) if teams_worktree_contract else None,
        "teams_lab_apply": True if apply_teams_lab else None,
    }
    contract.update({key: value for key, value in overlays.items() if value is not None})
    if authorization_scope:
        contract["authorization_scope"] = {"kind": authorization_scope}
    if (search_path or search_query) and not contract.get("target_kind"):
        contract["target_kind"] = "workspace-search"
    if not any(contract.get(key) for key in ("task", "intent", "target_kind", "input_path", "search_query")):
        raise click.UsageError("provide TASK, --task-file, --task-json, --target-kind, or --input-path")

    plan = build_plan(contract)
    route_exit = execute_plan(plan) if execute else (0 if plan.get("status") == "ready" else 5)
    error = None
    if route_exit != 0:
        reasons = plan.get("block_reasons") or [plan.get("status") or "route did not complete"]
        error = {
            "code": "route_execution_failed" if execute else "route_blocked",
            "message": "; ".join(str(reason) for reason in reasons),
        }
    emit(state, "route", plan, error=error)
    return 0 if route_exit == 0 else 5


@cli.command(name="search")
@click.argument("path", type=click.Path(exists=True, file_okay=False, resolve_path=True, path_type=Path))
@click.argument("query")
@click.option("--glob", "globs", multiple=True)
@click.option("--engine", type=click.Choice(["auto", "xcmd", "rg", "python"]), default="auto", show_default=True)
@click.option("--max-results", type=click.IntRange(min=1), default=100, show_default=True)
@click.pass_obj
def search_command(
    state: State,
    path: Path,
    query: str,
    globs: tuple[str, ...],
    engine: str,
    max_results: int,
) -> int:
    """Search a workspace through a read-only Python entrypoint."""
    result = search_workspace(path, query, list(globs), engine, max_results)
    observed = result.get("status") == "observed"
    error = None if observed else {
        "code": "search_failed",
        "message": str(result.get("reason") or "workspace search failed"),
    }
    emit(state, "search", result, error=error)
    if observed:
        return 0
    return 3 if result.get("reason") == "search_engine_not_available" else 5


@cli.group(name="index")
def index_group() -> None:
    """Build and maintain the deterministic SQLite document index (PageIndex-style)."""


def _emit_index_error(state: State, exc: Exception) -> int:
    code = getattr(exc, "code", exc.__class__.__name__)
    emit(
        state,
        "index",
        {"status": "blocked"},
        error={"code": code, "message": str(exc)},
    )
    return 5


def _index_path_option() -> click.Path:
    return click.Path(dir_okay=False, path_type=Path)


def _workspace_path_argument() -> click.Path:
    # Let the facade emit the frozen index_path_not_found code instead of
    # Click converting a missing workspace into a generic usage error.
    return click.Path(file_okay=False, resolve_path=True, path_type=Path)


@index_group.command(name="build")
@click.argument("path", type=_workspace_path_argument())
@click.option("--apply", is_flag=True, help="Create or replace the index (default: read-only plan).")
@click.option("--index-path", type=_index_path_option())
@click.pass_obj
def index_build_command(state: State, path: Path, apply: bool, index_path: Path | None) -> int:
    """Plan or apply a full deterministic index build."""
    from .index_api import index_build as run_index_build

    try:
        result = run_index_build(path, apply=apply, index_path=index_path)
    except ReverseSkillError as exc:
        return _emit_index_error(state, exc)
    emit(state, "index", result)
    return 0


@index_group.command(name="update")
@click.argument("path", type=_workspace_path_argument())
@click.option("--apply", is_flag=True, help="Apply the incremental delta (default: read-only plan).")
@click.option("--index-path", type=_index_path_option())
@click.pass_obj
def index_update_command(state: State, path: Path, apply: bool, index_path: Path | None) -> int:
    """Plan or apply an incremental index update."""
    from .index_api import index_update as run_index_update

    try:
        result = run_index_update(path, apply=apply, index_path=index_path)
    except ReverseSkillError as exc:
        return _emit_index_error(state, exc)
    emit(state, "index", result)
    return 0


@index_group.command(name="status")
@click.argument("path", type=_workspace_path_argument())
@click.option("--index-path", type=_index_path_option())
@click.pass_obj
def index_status_command(state: State, path: Path, index_path: Path | None) -> int:
    """Report index existence, revision, root hash, and counts (read-only)."""
    from .index_api import index_status as run_index_status

    try:
        result = run_index_status(path, index_path=index_path)
    except ReverseSkillError as exc:
        return _emit_index_error(state, exc)
    emit(state, "index", result)
    return 0


@index_group.command(name="inspect")
@click.argument("path", type=_workspace_path_argument())
@click.argument("node_id")
@click.option("--index-path", type=_index_path_option())
@click.pass_obj
def index_inspect_command(state: State, path: Path, node_id: str, index_path: Path | None) -> int:
    """Inspect one node plus its ancestors and bounded subtree (read-only)."""
    from .index_api import index_get_tree as run_index_get_tree

    try:
        result = run_index_get_tree(path, node_id, index_path=index_path)
    except ReverseSkillError as exc:
        return _emit_index_error(state, exc)
    emit(state, "index", result)
    return 0


@cli.command(name="retrieve")
@click.argument("path", type=_workspace_path_argument())
@click.argument("query")
@click.option(
    "--mode",
    type=click.Choice(["bm25", "tree", "hybrid"]),
    required=True,
    help="bm25 ranks; tree navigates titles; hybrid expands BM25 shortlist by structure.",
)
@click.option("--top-k", type=click.IntRange(min=1), default=None, help="Default 20, max 200.")
@click.option("--index-path", type=_index_path_option())
@click.pass_obj
def retrieve_command(
    state: State,
    path: Path,
    query: str,
    mode: str,
    top_k: int | None,
    index_path: Path | None,
) -> int:
    """Ranked read-only retrieval from the deterministic index."""
    from .index_api import index_search as run_index_search

    try:
        result = run_index_search(path, query, mode, top_k=top_k, index_path=index_path)
    except ReverseSkillError as exc:
        code = getattr(exc, "code", exc.__class__.__name__)
        emit(
            state,
            "retrieve",
            {"status": "blocked"},
            error={"code": code, "message": str(exc)},
        )
        return 5
    emit(state, "retrieve", result)
    return 0


def _selected_ida_version() -> str:
    installation = find_latest_ida()
    return ida_release_version(installation.version) if installation and installation.version else "9.4"


@cli.group(name="plugins")
def plugins_group() -> None:
    """Inspect IDA plugin compatibility and workflow readiness."""


@plugins_group.command(name="check")
@click.option("--plugin-root", type=click.Path(file_okay=False, path_type=Path))
@click.option("--ida-version")
@click.option("--python-exe", type=click.Path(dir_okay=False, path_type=Path), default=Path(sys.executable))
@click.pass_obj
def plugins_check(state: State, plugin_root: Path | None, ida_version: str | None, python_exe: Path) -> int:
    """Run a read-only manifest and Python compatibility preflight."""
    root = plugin_root or Path(os.environ.get("APPDATA", "")) / "Hex-Rays" / "IDA Pro" / "plugins"
    result = validate_plugin_tree(root, ida_version or _selected_ida_version(), python_exe)
    observed = result.get("status") == "observed"
    error = None if observed else {
        "code": "plugin_preflight_blocked",
        "message": "one or more installed plugins failed compatibility preflight",
    }
    emit(state, "plugins", result, error=error)
    return 0 if observed else 5


@plugins_group.command(name="inventory")
@click.option("--ida-dir", type=click.Path(file_okay=False, path_type=Path))
@click.option("--hcli-path", type=click.Path(dir_okay=False, path_type=Path))
@click.option("--plugin-root", type=click.Path(file_okay=False, path_type=Path))
@click.option("--python-exe", type=click.Path(dir_okay=False, path_type=Path))
@click.option("--skip-upgrade-check", is_flag=True)
@click.pass_obj
def plugins_inventory(
    state: State,
    ida_dir: Path | None,
    hcli_path: Path | None,
    plugin_root: Path | None,
    python_exe: Path | None,
    skip_upgrade_check: bool,
) -> None:
    """Report the latest local IDA and plugin workflow capabilities."""
    args = SimpleNamespace(
        ida_dir=str(ida_dir) if ida_dir else None,
        hcli_path=str(hcli_path) if hcli_path else None,
        plugin_root=str(plugin_root) if plugin_root else None,
        python_exe=str(python_exe) if python_exe else None,
        skip_upgrade_check=skip_upgrade_check,
    )
    emit(state, "plugins", build_ida_capability_report(args))


@cli.group(name="teams")
def teams_group() -> None:
    """Plan isolated IDA Teams collaboration without implicit setup."""


@teams_group.command(name="preflight")
@click.argument("repo", type=click.Path(exists=True, file_okay=False, resolve_path=True, path_type=Path))
@click.option("--git-ida", type=click.Path(exists=True, dir_okay=False, resolve_path=True, path_type=Path))
@click.pass_obj
def teams_preflight_command(state: State, repo: Path, git_ida: Path | None) -> int:
    """Probe Git and git-ida readiness without modifying the repository."""
    result = build_teams_preflight(str(repo), str(git_ida) if git_ida else "")
    observed = result.get("status") == "observed"
    error = None if observed else {
        "code": "teams_preflight_failed",
        "message": str(result.get("reason") or "Teams preflight failed"),
    }
    emit(state, "teams", result, error=error)
    return 0 if observed else 5


@teams_group.command(name="plan")
@click.argument("contract", type=click.Path(exists=True, dir_okay=False, resolve_path=True, path_type=Path))
@click.pass_obj
def teams_plan_command(state: State, contract: Path) -> int:
    """Validate an external multi-agent collaboration contract."""
    try:
        result = build_collaboration_report(read_contract(contract))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise click.BadParameter(f"invalid collaboration contract: {exc}") from exc
    observed = result.get("status") == "observed"
    error = None if observed else {
        "code": "teams_contract_blocked",
        "message": str(result.get("reason") or "Teams collaboration contract is not ready"),
    }
    emit(state, "teams", result, error=error)
    return 0 if observed else 5


@teams_group.command(name="lab")
@click.argument("contract", type=click.Path(exists=True, dir_okay=False, resolve_path=True, path_type=Path))
@click.option("--apply", is_flag=True, help="Create only the isolated lab named by the contract.")
@click.pass_obj
def teams_lab_command(state: State, contract: Path, apply: bool) -> int:
    """Plan or explicitly create an isolated Teams worktree lab."""
    try:
        result = build_lab_plan(read_contract(contract))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise click.BadParameter(f"invalid worktree contract: {exc}") from exc
    if apply:
        result = create_lab(result)
    succeeded = result.get("status") in {"observed", "created"}
    error = None if succeeded else {
        "code": "teams_lab_blocked",
        "message": str(result.get("reason") or "Teams lab operation did not complete"),
    }
    emit(state, "teams", result, error=error)
    return 0 if succeeded else 5


@cli.command(name="yara-scan")
@click.argument("target", type=click.Path(exists=True, dir_okay=False, resolve_path=True, path_type=Path))
@click.option(
    "--rules",
    "rule_paths",
    type=click.Path(exists=True, dir_okay=False, resolve_path=True, path_type=Path),
    multiple=True,
    required=True,
    help="YARA source file; repeat for multiple namespaces.",
)
@click.option("--database", help="Open IDA database session to annotate.")
@click.option("--annotate", is_flag=True, help="Append comments for unique byte matches in IDA.")
@click.option("--scan-timeout", type=click.FloatRange(min=1), default=60.0, show_default=True)
@click.pass_obj
def yara_scan(
    state: State,
    target: Path,
    rule_paths: tuple[Path, ...],
    database: str | None,
    annotate: bool,
    scan_timeout: float,
) -> None:
    """Scan a binary with YARA and optionally annotate its active IDA database."""
    if annotate and not database:
        raise click.UsageError("--annotate requires --database")
    result, instances = scan_yara(target, rule_paths, scan_timeout)
    result["annotation"] = {
        "requested": False,
        "applied": 0,
        "skipped": [],
        "resolved": [],
        "writes": [],
    }
    if annotate and database:
        with McpClient(state.url, timeout=state.timeout) as client:
            result["annotation"] = annotate_yara_matches(client, database, target, instances)
    emit(state, "yara-scan", result)


@cli.command()
@click.argument("path", type=click.Path(exists=True, dir_okay=False, resolve_path=True, path_type=Path))
@click.option(
    "--mode",
    type=click.Choice(["prefer_headless", "force_headless", "prefer_gui", "force_gui"]),
    default="prefer_headless",
    show_default=True,
)
@click.option("--preferred-session-id")
@click.option("--no-auto-analysis", is_flag=True)
@click.option("--no-build-caches", is_flag=True)
@click.pass_obj
def open(
    state: State,
    path: Path,
    mode: str,
    preferred_session_id: str | None,
    no_auto_analysis: bool,
    no_build_caches: bool,
) -> None:
    """Open a binary through the idb_open MCP tool."""
    resolved = path
    windir = Path(str(Path.home()))
    if sys.platform == "win32":
        import os

        windir = Path(os.environ.get("WINDIR", r"C:\Windows")) / "System32"
        try:
            if resolved.is_relative_to(windir):
                target_dir = Path(tempfile.gettempdir()) / "reverse-skill"
                target_dir.mkdir(parents=True, exist_ok=True)
                target = target_dir / f"{uuid.uuid4().hex}-{resolved.name}"
                shutil.copy2(resolved, target)
                resolved = target
        except ValueError:
            pass
    arguments: dict[str, Any] = {
        "input_path": str(resolved),
        "mode": mode,
        "run_auto_analysis": not no_auto_analysis,
        "build_caches": not no_build_caches,
        "init_hexrays": True,
    }
    if preferred_session_id:
        arguments["preferred_session_id"] = preferred_session_id
    with McpClient(state.url, timeout=min(state.timeout, 30.0)) as client:
        output = structured_content(client.call_tool("idb_open", arguments))
    if output.get("success") is not True:
        raise ToolOperationError(f"idb_open failed: {output.get('error') or output.get('message')}")
    emit(state, "open", output)


@cli.command()
@click.pass_obj
def sessions(state: State) -> None:
    """List active and discovered IDA database sessions."""
    with McpClient(state.url, timeout=state.timeout) as client:
        output = structured_content(client.call_tool("idb_list"))
    if output.get("error"):
        raise ToolOperationError(f"idb_list failed: {output['error']}")
    emit(state, "sessions", output)


@cli.command(name="call")
@click.argument("tool")
@click.option("--arguments-json", default="{}", show_default=True)
@click.option("--database")
@click.option("--input-responses-json")
@click.option("--request-state")
@click.pass_obj
def call_tool(
    state: State,
    tool: str,
    arguments_json: str,
    database: str | None,
    input_responses_json: str | None,
    request_state: str | None,
) -> None:
    """Call one dynamically discovered MCP tool."""
    try:
        arguments = json.loads(arguments_json)
        input_responses = json.loads(input_responses_json) if input_responses_json is not None else None
    except json.JSONDecodeError as exc:
        raise click.BadParameter(f"invalid JSON: {exc.msg}") from exc
    if not isinstance(arguments, dict) or (input_responses is not None and not isinstance(input_responses, dict)):
        raise click.BadParameter("arguments and input responses must be JSON objects")
    if database:
        arguments["database"] = database
    with McpClient(state.url, timeout=state.timeout) as client:
        result = client.call_tool(
            tool,
            arguments,
            input_responses=input_responses,
            request_state=request_state,
        )
    emit(state, "call", structured_content(result))


@cli.command()
@click.argument("database")
@click.option("--no-save", is_flag=True)
@click.pass_obj
def close(state: State, database: str, no_save: bool) -> None:
    """Close an IDA database session."""
    with McpClient(state.url, timeout=state.timeout) as client:
        output = structured_content(
            client.call_tool("idb_close", {"database": database, "save": not no_save})
        )
    if output.get("success") is not True:
        raise ToolOperationError(f"idb_close failed: {output.get('error') or output.get('message')}")
    emit(state, "close", output)


@cli.group(name="case")
def case_group() -> None:
    """Initialize and review frozen case packages (work/<case>/)."""


@case_group.command(name="init")
@click.option("--hint", required=True, help="One-line task description used for routing and case naming.")
@click.option("--case-name", help="Case directory name (1-80 chars, no path separators).")
@click.option("--preset", help="Preset: offline-sample | ctf-public | own-system.")
@click.option("--network-profile", help="offline | lab_only | authorized_target_only | unrestricted_lab (aliases: lab, authorized, auth, offline_only).")
@click.option("--auth-status", type=click.Choice(["pending", "granted", "denied", "unknown"]))
@click.option("--auth-basis", help="written_contract | bug_bounty_scope | ctf_public | own_system | lab_only.")
@click.option("--evidence-of-auth")
@click.option("--target-url")
@click.option("--sample", type=click.Path(dir_okay=False, path_type=Path))
@click.option("--in-scope-asset", "in_scope_assets", multiple=True)
@click.option("--package-root", type=click.Path(file_okay=False, path_type=Path), default=".", show_default=True)
@click.pass_obj
def case_init(
    state: State,
    hint: str,
    case_name: str | None,
    preset: str | None,
    network_profile: str | None,
    auth_status: str | None,
    auth_basis: str | None,
    evidence_of_auth: str | None,
    target_url: str | None,
    sample: Path | None,
    in_scope_assets: tuple[str, ...],
    package_root: Path,
) -> int:
    """Create a work/<case>/ package with a frozen scope contract."""
    try:
        result = init_case(
            hint,
            case_name,
            preset=preset,
            network_profile=network_profile,
            auth_status=auth_status,
            auth_basis=auth_basis,
            evidence_of_auth=evidence_of_auth,
            target_url=target_url,
            sample=str(sample) if sample else None,
            in_scope_assets=list(in_scope_assets),
            package_root=str(package_root),
        )
    except CaseContractError as exc:
        error = {"code": "case_contract_invalid", "message": str(exc)}
        emit(state, "case", {"status": "invalid", "hint": hint}, error=error)
        return 2
    except CasePackageError as exc:
        error = {"code": "case_create_failed", "message": str(exc)}
        emit(state, "case", {"status": "failed", "hint": hint}, error=error)
        return 5
    emit(state, "case", result)
    return 0


@case_group.command(name="review")
@click.argument("case_root", type=click.Path(file_okay=False, path_type=Path))
@click.option("--format", "output_format", type=click.Choice(["markdown", "json"]), default="markdown", show_default=True)
@click.option("--strict", is_flag=True, help="Treat warnings as handoff blockers.")
@click.option("--verify-hashes", is_flag=True, help="Verify SHA-256 content_hash values against case-local artifacts.")
@click.pass_obj
def case_review(
    state: State,
    case_root: Path,
    output_format: str,
    strict: bool,
    verify_hashes: bool,
) -> int:
    """Run a read-only Evidence Graph review of an existing case package."""
    report = review_case(str(case_root), strict=strict, verify_hashes=verify_hashes)
    failed = report["status"] == "FAIL"
    errors = report["summary"]["errors"]
    warnings = report["summary"]["warnings"]
    detail = f"{errors} error(s), {warnings} warning(s)"
    if failed and errors == 0 and warnings > 0:
        detail = "strict mode treats warnings as handoff blockers: " + detail
    error = None if not failed else {
        "code": "case_review_failed",
        "message": f"case review {report['status']}: {detail}",
    }
    if state.json_output:
        data = {"format": output_format, "review": report}
    elif output_format == "markdown":
        data = render_case_review_markdown(report)
    else:
        data = report
    emit(state, "case", data, error=error)
    return 5 if failed else 0


def _emit_gate_result(state: State, name: str, result: dict[str, Any]) -> int:
    failed = result.get("status") == "findings"
    error = None if not failed else {
        "code": "gate_failed",
        "message": f"{name} gate found issues: {len(result.get('failures') or [])} failure(s)",
    }
    emit(state, name, result, error=error)
    return 5 if failed else 0


@cli.group(name="gates")
def gates_group() -> None:
    """Run repository quality gates (Python only, no PowerShell gates)."""


@gates_group.command(name="leak-scan")
@click.option("--path", "scan_path", default="skills/field-journal", show_default=True)
@click.option("--report-only", is_flag=True, help="Report findings without a failing exit code.")
@click.pass_obj
def gates_leak_scan(state: State, scan_path: str, report_only: bool) -> int:
    """Scan field-journal/promotion text for un-anonymized sensitive info."""
    from .gates import leak_scan as run_leak_scan

    result = run_leak_scan(scan_path, report_only=report_only)
    if report_only:
        emit(state, "gates", result)
        return 0
    return _emit_gate_result(state, "leak-scan", result)


@gates_group.command(name="doc-facts")
@click.pass_obj
def gates_doc_facts(state: State) -> int:
    """Verify README/OpenCLI/CLI surface and packaged-data drift."""
    from .gates import doc_facts as run_doc_facts_gate

    return _emit_gate_result(state, "doc-facts", run_doc_facts_gate())


@gates_group.command(name="version")
@click.pass_obj
def gates_version(state: State) -> int:
    """Verify pyproject/package/OpenCLI/CHANGELOG version consistency."""
    from .gates import version_consistency as run_version_gate

    return _emit_gate_result(state, "version", run_version_gate())


@gates_group.command(name="routing-coherence")
@click.pass_obj
def gates_routing_coherence(state: State) -> int:
    """Verify routing.json integrity and referenced skill paths."""
    from .gates import routing_coherence as run_routing_coherence_gate

    return _emit_gate_result(state, "routing-coherence", run_routing_coherence_gate())


@gates_group.command(name="all")
@click.option("--path", "scan_path", default="skills/field-journal", show_default=True)
@click.pass_obj
def gates_all(state: State, scan_path: str) -> int:
    """Run every repository gate and aggregate the result."""
    from .gates import run_all

    result = run_all(leak_path=scan_path)
    failed = result.get("status") == "findings"
    error = None if not failed else {
        "code": "gate_failed",
        "message": "gates failed: " + ", ".join(result.get("failures") or []),
    }
    emit(state, "gates", result, error=error)
    return 5 if failed else 0


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    arguments = list(sys.argv[1:] if argv is None else argv)
    json_output = "--json" in arguments
    command = next((arg for arg in arguments if arg in COMMAND_NAMES), "cli")
    try:
        result = cli.main(args=arguments, prog_name="reverse-skill", standalone_mode=False)
        return result if isinstance(result, int) else 0
    except click.ClickException as exc:
        if json_output:
            click.echo(
                json.dumps(
                    _envelope(command, error={"code": "usage", "message": exc.format_message()}),
                    ensure_ascii=False,
                )
            )
        else:
            exc.show(file=sys.stderr)
        return 2
    except ReverseSkillError as exc:
        if json_output:
            click.echo(
                json.dumps(
                    _envelope(command, error={"code": exc.__class__.__name__, "message": str(exc)}),
                    ensure_ascii=False,
                )
            )
        else:
            click.echo(f"Error: {exc}", err=True)
        return exc.exit_code
    except Exception as exc:
        if json_output:
            click.echo(
                json.dumps(
                    _envelope(command, error={"code": "internal", "message": str(exc)}),
                    ensure_ascii=False,
                )
            )
        else:
            click.echo(f"Error: {exc}", err=True)
        return 1
