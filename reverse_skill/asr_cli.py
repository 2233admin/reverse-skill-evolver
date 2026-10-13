from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

import click

from .asr import AsrClient, KINDS, install_item
from .errors import ToolOperationError


@click.group(no_args_is_help=True)
def asr() -> None:
    """Browse and manage Forefy ASR; audited items only, excluding MCP servers."""


def run(state: Any, action: str, operation: Callable[[AsrClient], Any]) -> None:
    from .cli import emit

    with AsrClient(timeout=state.timeout) as client:
        result = operation(client)
    emit(state, "asr", {"action": action, "result": result})


@asr.command(name="list")
@click.option("--kind", type=click.Choice(["all", *KINDS]), default="all", show_default=True)
@click.option("--search", default="", help="Search names, descriptions, authors, and repository URLs.")
@click.option("--sort-by", type=click.Choice(["audited", "created_at", "popular", "downloads"]), default="audited")
@click.option("--page", type=click.IntRange(min=1), default=1)
@click.option("--per-page", type=click.IntRange(1, 100), default=100)
@click.option("--all-pages/--single-page", default=True, show_default=True)
@click.option("--mine", is_flag=True, help="List your items using FOREFY_API_KEY.")
@click.pass_obj
def list_items(state: Any, **options: Any) -> None:
    """List audited skills, goals, and workflows, following every page by default."""
    run(state, "list", lambda client: client.list_items(**options))


@asr.command()
@click.argument("item_id")
@click.pass_obj
def show(state: Any, item_id: str) -> None:
    """Read an audited item's metadata and raw files."""
    run(state, "show", lambda client: client.item(item_id))


@asr.command(name="install-script")
@click.argument("item_id")
@click.option("--location", type=click.Choice(["project", "global"]), default="project")
@click.option("--harness", type=click.Choice(["agents", "claude"]), default="agents")
@click.option("--shell", type=click.Choice(["powershell", "bash"]), default="powershell")
@click.pass_obj
def install_script(state: Any, item_id: str, **options: Any) -> None:
    """Retrieve the upstream install script for review."""
    run(state, "install-script", lambda client: client.install_script(item_id, **options))


@asr.command()
@click.argument("item_id")
@click.option("--destination", required=True, type=click.Path(file_okay=False, path_type=Path))
@click.pass_obj
def install(state: Any, item_id: str, destination: Path) -> None:
    """Save audited raw files into a new directory without running them."""
    run(state, "install", lambda client: install_item(client.item(item_id), destination))


@asr.command()
@click.option("--search", default="")
@click.option("--sort-by", type=click.Choice(["score", "downloads", "hearts", "items", "recent"]), default="score")
@click.option("--page", type=click.IntRange(min=1), default=1)
@click.option("--per-page", type=click.IntRange(1, 100), default=20)
@click.pass_obj
def authors(state: Any, **options: Any) -> None:
    """List contributors with audited top items."""
    run(state, "authors", lambda client: client.authors(**options))


@asr.command()
@click.argument("key")
@click.pass_obj
def author(state: Any, key: str) -> None:
    """Read a GitHub owner's profile and audited items."""
    run(state, "author", lambda client: client.author(key))


@asr.command()
@click.argument("plugin_id")
@click.pass_obj
def plugin(state: Any, plugin_id: str) -> None:
    """Inspect a bundle's audited skill members and supply-chain verdicts."""
    run(state, "plugin", lambda client: client.plugin(plugin_id))


@asr.command()
@click.option("--search", default="")
@click.option("--page", type=click.IntRange(min=1), default=1)
@click.option("--per-page", type=click.IntRange(1, 100), default=20)
@click.option("--mine", is_flag=True)
@click.pass_obj
def scans(state: Any, **options: Any) -> None:
    """List recent security and quality scans (a scan is not a human audit)."""
    run(state, "scans", lambda client: client.scans(**options))


@asr.command()
@click.argument("github_url")
@click.option("--commit-sha")
@click.option("--skill-path")
@click.option("--plugin", "scan_plugin", is_flag=True, help="Scan the whole plugin at --skill-path.")
@click.pass_obj
def scan(state: Any, github_url: str, commit_sha: str | None, skill_path: str | None, scan_plugin: bool) -> None:
    """Submit a public repository scan and return its id for scan-result."""
    options = {key: value for key, value in {
        "commit_sha": commit_sha, "skill_path": skill_path, "plugin": scan_plugin,
    }.items() if value is not None}
    run(state, "scan", lambda client: client.scan(github_url, **options))


@asr.command(name="scan-result")
@click.argument("scan_id")
@click.pass_obj
def scan_result(state: Any, scan_id: str) -> None:
    """Fetch or poll a scan's findings, quality checks, and AI-slop score."""
    run(state, "scan-result", lambda client: client.scan_result(scan_id))


@asr.command(name="import-repo")
@click.argument("github_url")
@click.option("--commit-sha")
@click.option("--path", "paths", multiple=True, help="Limit publishing to these path prefixes.")
@click.option("--skill-name", "skill_names", multiple=True)
@click.option("--is-benchmark", is_flag=True)
@click.option("--parent-benchmark-id")
@click.pass_obj
def import_repo(state: Any, github_url: str, **options: Any) -> None:
    """Publish repository skills, goals, and workflows using FOREFY_API_KEY."""
    body = {key: list(value) if isinstance(value, tuple) else value
            for key, value in options.items() if value is not None and value != ()}
    run(state, "import-repo", lambda client: client.import_repo(github_url, **body))


@asr.command(name="create-goal")
@click.option("--input", "input_path", required=True,
              type=click.Path(exists=True, dir_okay=False, readable=True, path_type=Path))
@click.pass_obj
def create_goal(state: Any, input_path: Path) -> None:
    """Publish a structured goal JSON definition using FOREFY_API_KEY."""
    try:
        body = json.loads(input_path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, ValueError) as exc:
        raise ToolOperationError(f"Cannot read ASR goal JSON: {exc}") from exc
    if not isinstance(body, dict):
        raise ToolOperationError("ASR goal JSON must be an object.")
    run(state, "create-goal", lambda client: client.create_goal(body))


@asr.command(name="record-download")
@click.argument("item_id")
@click.option("--source", default="reverse-skill")
@click.pass_obj
def record_download(state: Any, item_id: str, source: str) -> None:
    """Record an audited item's download in the registry."""
    run(state, "record-download", lambda client: client.record_download(item_id, source))
