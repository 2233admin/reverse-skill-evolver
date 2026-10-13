from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path
from typing import Any, Mapping

import click

from . import __version__
from .evolution import evolve as run_evolution
from .evolution import validate_trace_card
from .errors import EnvironmentUnavailable, ReverseSkillError, ToolOperationError
from .ida import find_latest_ida, install_ida_mcp, start_server
from .integrations import annotate_yara_matches, integration_inventory, scan_yara
from .mcp import McpClient, probe_tool_count


SCHEMA_VERSION = "1"
DEFAULT_TIMEOUT = 120.0
COMMAND_NAMES = {
    "install",
    "register",
    "start",
    "status",
    "doctor",
    "tools",
    "integrations",
    "yara-scan",
    "open",
    "sessions",
    "call",
    "close",
    "evolve",
    "tracecard-validate",
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
        "data": data if error is None else None,
        "error": error,
    }


def _human(value: Any) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, indent=2)


def emit(state: State, command: str, data: Any) -> None:
    if state.json_output:
        click.echo(json.dumps(_envelope(command, data=data), ensure_ascii=False))
    else:
        click.echo(_human(data))


def structured_content(result: Mapping[str, Any]) -> Mapping[str, Any]:
    value = result.get("structuredContent")
    return value if isinstance(value, Mapping) else result


def codex_registration(name: str, *, timeout: float = DEFAULT_TIMEOUT) -> dict[str, Any] | None:
    """Return the named Codex registration, or None when no object is retrieved.

    Missing Codex, nonzero exit status, empty output, and invalid or non-object
    JSON produce None. A subprocess timeout (in seconds) raises
    EnvironmentUnavailable; process-start OSError and output-decoding
    UnicodeDecodeError propagate.
    """
    codex = shutil.which("codex")
    if not codex:
        return None
    try:
        completed = subprocess.run(
            [codex, "mcp", "get", name, "--json"],
            capture_output=True, text=True, check=False, timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        raise EnvironmentUnavailable(
            f"failed to inspect Codex MCP registration {name!r}: timed out after {timeout:g} seconds"
        ) from exc
    if completed.returncode != 0 or not completed.stdout.strip():
        return None
    try:
        value = json.loads(completed.stdout)
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


def register_codex(name: str, url: str, *, timeout: float = DEFAULT_TIMEOUT) -> dict[str, Any]:
    """Ensure Codex has an enabled Streamable HTTP registration for the URL.

    Return its name, URL, change flag, and status. Each get or add
    subprocess uses the supplied timeout in seconds; timeouts and failed
    mutations raise EnvironmentUnavailable without retrying, as does missing
    Codex. Process-start OSError and output-decoding UnicodeDecodeError propagate.
    Codex replaces same-name entries; no separate removal is needed.
    An add failure may follow a saved replacement, so inspect before retrying.
    """
    codex = shutil.which("codex")
    if not codex:
        raise EnvironmentUnavailable("codex CLI is not installed or is not on PATH")
    existing = codex_registration(name, timeout=timeout)
    transport = (existing or {}).get("transport") or {}
    if (
        existing
        and transport.get("type") == "streamable_http"
        and transport.get("url") == url
        and existing.get("enabled") is True
    ):
        return {"name": name, "url": url, "changed": False, "status": "already_registered"}
    try:
        completed = subprocess.run(
            [codex, "mcp", "add", name, "--url", url],
            capture_output=True, text=True, check=False, timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        raise EnvironmentUnavailable(
            f"failed to register Codex MCP server {name!r}: timed out after {timeout:g} seconds; "
            "Codex may have saved the registration; inspect it before retrying"
        ) from exc
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise EnvironmentUnavailable(
            f"failed to register Codex MCP server {name!r}: {detail}; "
            "Codex may have saved the registration; inspect it before retrying"
        )
    return {"name": name, "url": url, "changed": True, "status": "registered"}


@click.group(no_args_is_help=True, context_settings={"help_option_names": ["-h", "--help"]})
@click.option("--url", default="http://127.0.0.1:13337/mcp", show_default=True)
@click.option("--name", default="idapro", show_default=True, help="Codex MCP registration name.")
@click.option("--json", "json_output", is_flag=True, help="Emit one stable JSON envelope on stdout.")
@click.option("--timeout", type=click.FloatRange(min=0.1), default=DEFAULT_TIMEOUT, show_default=True)
@click.version_option(__version__, prog_name="reverse-skill")
@click.pass_context
def cli(ctx: click.Context, url: str, name: str, json_output: bool, timeout: float) -> None:
    """Operate IDA Pro MCP workflows and bounded route-evolution search."""
    ctx.obj = State(url=url, name=name, json_output=json_output, timeout=timeout)


@cli.command(name="tracecard-validate")
@click.option(
    "--input",
    "input_path",
    required=True,
    type=click.Path(exists=True, dir_okay=False, readable=True, path_type=Path),
)
@click.pass_obj
def tracecard_validate(state: State, input_path: Path) -> None:
    """Validate TraceCard semantics, not the truth of external evidence."""
    try:
        trace = json.loads(input_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ToolOperationError(f"Cannot read TraceCard JSON: {exc}") from exc
    validate_trace_card(trace)
    emit(state, "tracecard-validate", {"semantics_valid": True})


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
    emit(state, "register", register_codex(state.name, state.url, timeout=state.timeout))


@cli.command()
@click.option("--ida-dir", type=click.Path(file_okay=False, path_type=Path))
@click.option("--port", type=click.IntRange(1, 65535), default=13337, show_default=True)
@click.option("--server-path", type=click.Path(dir_okay=False, path_type=Path))
@click.option("--replace-stale", is_flag=True, help="Replace an unhealthy Windows listener only after verifying its executable and port.")
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
    """Collect IDA discovery, Codex registration, and live MCP metadata using the state timeout.

    Codex lookup timeouts and MCP transport or protocol errors propagate;
    an unreachable MCP endpoint does not produce an offline status result.
    """
    ida = find_latest_ida()
    registration = codex_registration(state.name, timeout=state.timeout)
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



@cli.command()
@click.option("--candidate", required=True, type=click.Path(exists=True, dir_okay=False, resolve_path=True, path_type=Path))
@click.option("--catalog", required=True, type=click.Path(exists=True, dir_okay=False, resolve_path=True, path_type=Path))
@click.option("--fixtures", required=True, type=click.Path(exists=True, dir_okay=False, resolve_path=True, path_type=Path))
@click.option("--output", required=True, type=click.Path(file_okay=False, path_type=Path))
@click.option("--max-evaluations", type=click.IntRange(min=3), default=3, show_default=True)
@click.option("--max-reflections", type=click.IntRange(min=1), default=1, show_default=True)
@click.option("--model-timeout", type=click.IntRange(min=1, max=3600), default=120, show_default=True)
@click.pass_obj
def evolve(
    state: State,
    candidate: Path,
    catalog: Path,
    fixtures: Path,
    output: Path,
    max_evaluations: int,
    max_reflections: int,
    model_timeout: int,
) -> None:
    """Search routing candidates against a fixed local fixture suite using OMP."""
    if max_reflections > max_evaluations - 2:
        raise click.UsageError("--max-reflections must be between 1 and --max-evaluations - 2")
    report = run_evolution(
        candidate,
        catalog,
        fixtures,
        output,
        max_evaluations,
        max_reflections,
        model_timeout,
    )
    emit(state, "evolve", report)

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


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    json_output = "--json" in arguments
    command = next((arg for arg in arguments if arg in COMMAND_NAMES), "cli")
    try:
        cli.main(args=arguments, prog_name="reverse-skill", standalone_mode=False)
        return 0
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
