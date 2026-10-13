"""Opt-in local index maintenance and read-only retrieval."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import click

if TYPE_CHECKING:
    from .cli import State


def emit(state, command, data):
    from .cli import emit as emit_result

    emit_result(state, command, data)


@click.group(name='index')
def index_group() -> None:
    """Build and maintain the deterministic SQLite document index (PageIndex-style)."""


def _index_path_option() -> click.Path:
    return click.Path(dir_okay=False, path_type=Path)


def _workspace_path_argument() -> click.Path:
    return click.Path(file_okay=False, resolve_path=True, path_type=Path)


@index_group.command(name='build')
@click.argument('path', type=_workspace_path_argument())
@click.option('--apply', is_flag=True, help='Create or replace the index (default: read-only plan).')
@click.option('--index-path', type=_index_path_option())
@click.pass_obj
def index_build_command(state: State, path: Path, apply: bool, index_path: Path | None) -> int:
    """Plan or apply a full deterministic index build."""
    from .index_api import index_build as run_index_build
    result = run_index_build(path, apply=apply, index_path=index_path)
    emit(state, 'index', result)
    return 0


@index_group.command(name='update')
@click.argument('path', type=_workspace_path_argument())
@click.option('--apply', is_flag=True, help='Apply the incremental delta (default: read-only plan).')
@click.option('--index-path', type=_index_path_option())
@click.pass_obj
def index_update_command(state: State, path: Path, apply: bool, index_path: Path | None) -> int:
    """Plan or apply an incremental index update."""
    from .index_api import index_update as run_index_update
    result = run_index_update(path, apply=apply, index_path=index_path)
    emit(state, 'index', result)
    return 0


@index_group.command(name='import-ida')
@click.argument('path', type=_workspace_path_argument())
@click.option('--export', 'export_path', type=click.Path(exists=True, dir_okay=False, resolve_path=True, path_type=Path), required=True, help='Explicit versioned IDA JSON export; no IDA process is started.')
@click.option('--apply', is_flag=True, help="Replace the module's IDA layer transactionally.")
@click.option('--index-path', type=_index_path_option())
@click.pass_obj
def index_import_ida_command(state: State, path: Path, export_path: Path, apply: bool, index_path: Path | None) -> int:
    """Plan or explicitly import one IDA JSON export into the shared index."""
    from .ida_ingest import import_export
    result = import_export(path, export_path, apply=apply, index_path=index_path)
    emit(state, 'index', result)
    return 0


@index_group.command(name='xrefs')
@click.argument('path', type=_workspace_path_argument())
@click.argument('node_id')
@click.option('--direction', type=click.Choice(['incoming', 'outgoing', 'both']), default='both', show_default=True)
@click.option('--index-path', type=_index_path_option())
@click.pass_obj
def index_xrefs_command(state: State, path: Path, node_id: str, direction: str, index_path: Path | None) -> int:
    """Read incoming and/or outgoing IDA xrefs for one stable node."""
    from .index_api import index_read_xrefs
    result = index_read_xrefs(path, node_id, direction, index_path=index_path)
    emit(state, 'index', result)
    return 0


@index_group.command(name='status')
@click.argument('path', type=_workspace_path_argument())
@click.option('--index-path', type=_index_path_option())
@click.pass_obj
def index_status_command(state: State, path: Path, index_path: Path | None) -> int:
    """Report index existence, revision, root hash, and counts (read-only)."""
    from .index_api import index_status as run_index_status
    result = run_index_status(path, index_path=index_path)
    emit(state, 'index', result)
    return 0


@index_group.command(name='inspect')
@click.argument('path', type=_workspace_path_argument())
@click.argument('node_id')
@click.option('--index-path', type=_index_path_option())
@click.pass_obj
def index_inspect_command(state: State, path: Path, node_id: str, index_path: Path | None) -> int:
    """Inspect one node plus its ancestors and bounded subtree (read-only)."""
    from .index_api import index_get_tree as run_index_get_tree
    result = run_index_get_tree(path, node_id, index_path=index_path)
    emit(state, 'index', result)
    return 0


@click.command(name='retrieve')
@click.argument('path', type=_workspace_path_argument())
@click.argument('query')
@click.option('--mode', type=click.Choice(['bm25', 'tree', 'hybrid']), required=True, help='bm25 ranks; tree navigates titles; hybrid expands BM25 shortlist by structure.')
@click.option('--top-k', type=click.IntRange(min=1), default=None, help='Default 20, max 200.')
@click.option('--index-path', type=_index_path_option())
@click.pass_obj
def retrieve_command(state: State, path: Path, query: str, mode: str, top_k: int | None, index_path: Path | None) -> int:
    """Ranked read-only retrieval from the deterministic index."""
    from .index_api import index_search as run_index_search
    result = run_index_search(path, query, mode, top_k=top_k, index_path=index_path)
    emit(state, 'retrieve', result)
    return 0
