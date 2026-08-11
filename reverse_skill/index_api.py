"""Provider-neutral JSON facade for the deterministic document index.

CLI commands and future MCP adapters both call only these functions; each
returns plain JSON-serializable dicts and raises ``index_store.IndexError``
subclasses carrying stable machine-readable codes. No click, argparse, or
broker imports live here.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from . import index_build as _build_engine
from .index_store import (
    META_BUILT_AT,
    META_BUILT_BY,
    META_INDEX_REVISION,
    META_ROOT_HASH,
    META_SCHEMA_VERSION,
    SCHEMA_VERSION,
    IndexCorrupt,
    IndexPathNotFound,
    InvalidNodeId,
    NodeNotFound,
    close,
    compute_root_hash,
    default_index_path,
    load_contracts,
    open_read_only,
    probe_capabilities,
    read_node,
    read_node_text,
    read_subtree,
    validate_node_id,
)
from .retrieval import retrieve

_MAX_DESCENDANTS = 500


def _resolve_index_path(root: Path, index_path: Optional[Path]) -> Path:
    return Path(index_path) if index_path is not None else default_index_path(root)


def _require_root(root: Path) -> None:
    if not root.is_dir():
        raise IndexPathNotFound(f"workspace path is not a directory: {root}")


def _node_payload(node: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "node_id": node["node_id"],
        "relative_path": node["relative_path"],
        "parent_id": node["parent_id"],
        "depth": node["depth"],
        "ordinal": node["ordinal"],
        "title": node["title"],
        "kind": node["kind"],
        "symbol_kind": node["symbol_kind"],
        "tree_path": node["tree_path"],
        "lines": {"start": node["start_line"], "end": node["end_line"]},
        "content_sha256": node["body_sha256"],
    }


def _read_meta(connection: Any) -> Dict[str, str]:
    return {
        row["key"]: row["value"]
        for row in connection.execute("SELECT key, value FROM index_meta")
    }


def _attach_index_evidence(
    payload: Dict[str, Any], meta: Dict[str, str], resolved: Path
) -> Dict[str, Any]:
    payload["schema_version"] = SCHEMA_VERSION
    payload["index_path"] = str(resolved)
    payload["index_revision"] = meta.get(META_INDEX_REVISION, "0")
    payload["root_hash"] = meta.get(META_ROOT_HASH)
    return payload


def index_status(root: Path, index_path: Optional[Path] = None) -> Dict[str, Any]:
    """Read-only report on the index at the resolved path (never creates it)."""
    _require_root(root)
    resolved = _resolve_index_path(root, index_path)
    capability = probe_capabilities()
    report: Dict[str, Any] = {
        "status": "observed",
        "schema_version": SCHEMA_VERSION,
        "index_path": str(resolved),
        "exists": resolved.is_file(),
        "capability": capability,
    }
    if not resolved.is_file():
        report["status"] = "absent"
        return report
    connection = open_read_only(resolved)
    try:
        meta = _read_meta(connection)
        report["index_revision"] = meta.get(META_INDEX_REVISION, "0")
        report["root_hash"] = meta.get(META_ROOT_HASH)
        report["built_at"] = meta.get(META_BUILT_AT)
        report["built_by"] = meta.get(META_BUILT_BY)
        report["syntax_profile"] = meta.get("syntax_profile") or None
        report["counts"] = {
            "documents": int(
                connection.execute("SELECT COUNT(*) AS n FROM documents").fetchone()["n"]
            ),
            "nodes": int(connection.execute("SELECT COUNT(*) AS n FROM nodes").fetchone()["n"]),
            "edges": int(connection.execute("SELECT COUNT(*) AS n FROM edges").fetchone()["n"]),
            "link_edges": int(
                connection.execute(
                    "SELECT COUNT(*) AS n FROM edges WHERE kind = 'link'"
                ).fetchone()["n"]
            ),
            "xref_edges": int(
                connection.execute(
                    "SELECT COUNT(*) AS n FROM edges WHERE kind = 'xref'"
                ).fetchone()["n"]
            ),
            "ida_documents": int(
                connection.execute(
                    "SELECT COUNT(*) AS n FROM documents WHERE kind = 'ida'"
                ).fetchone()["n"]
            ),
            "ida_nodes": int(
                connection.execute(
                    "SELECT COUNT(*) AS n FROM nodes WHERE source_kind = 'ida'"
                ).fetchone()["n"]
            ),
            "fts_rows": int(
                connection.execute("SELECT COUNT(*) AS n FROM fts_terms").fetchone()["n"]
            ),
        }
    finally:
        close(connection)
    contracts = load_contracts()
    files, _ = _build_engine.scan_workspace(root, contracts)
    workspace_root_hash = compute_root_hash(
        (item.relpath, item.sha256) for item in files
    )
    report["workspace_root_hash"] = workspace_root_hash
    report["fresh"] = workspace_root_hash == report["root_hash"]
    report["stale"] = not report["fresh"]
    return report


def index_search(
    root: Path,
    query: str,
    mode: str,
    top_k: Optional[int] = None,
    index_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """Ranked retrieval; read-only; never builds the index implicitly."""
    _require_root(root)
    contracts = load_contracts()
    if top_k is None:
        top_k = int(contracts["limits"]["default_top_k"])
    resolved = _resolve_index_path(root, index_path)
    connection = open_read_only(resolved)
    try:
        meta = _read_meta(connection)
        result = retrieve(connection, query, mode, top_k, contracts)
    finally:
        close(connection)
    return _attach_index_evidence(result, meta, resolved)


def index_get_tree(
    root: Path,
    node_id: str,
    index_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """Read-only detail for one node plus its ancestors and bounded subtree."""
    _require_root(root)
    validate_node_id(node_id)
    resolved = _resolve_index_path(root, index_path)
    connection = open_read_only(resolved)
    try:
        node = read_node(connection, node_id)
        if node is None:
            raise NodeNotFound(f"node_id not found in index: {node_id}")
        ancestors = read_subtree_ancestors(connection, node_id)
        subtree = read_subtree(connection, node_id)
        descendants = subtree[1:]
        truncated = len(descendants) > _MAX_DESCENDANTS
        limited = descendants[:_MAX_DESCENDANTS]
        meta = _read_meta(connection)
        payload = {
            "status": "observed",
            "node": _node_payload(node),
            "ancestors": [_node_payload(item) for item in ancestors],
            "descendants": [_node_payload(item) for item in limited],
            "descendant_count": len(descendants),
            "descendants_truncated": truncated,
        }
    finally:
        close(connection)
    return _attach_index_evidence(payload, meta, resolved)


def read_subtree_ancestors(connection: Any, node_id: str) -> List[Dict[str, Any]]:
    from .index_store import read_ancestors

    return read_ancestors(connection, node_id)


def index_read_nodes(
    root: Path,
    node_ids: Sequence[str],
    index_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """Read-only bulk node reads for future MCP adapters."""
    _require_root(root)
    for node_id in node_ids:
        validate_node_id(node_id)
    resolved = _resolve_index_path(root, index_path)
    connection = open_read_only(resolved)
    try:
        meta = _read_meta(connection)
        rows = []
        for node_id in node_ids:
            node = read_node(connection, node_id)
            if node is None:
                raise NodeNotFound(f"node_id not found in index: {node_id}")
            text = read_node_text(connection, node_id)
            if text is None:
                raise IndexCorrupt(f"indexed body is missing for node_id: {node_id}")
            payload = _node_payload(node)
            payload["text"] = text
            rows.append(payload)
    finally:
        close(connection)
    return _attach_index_evidence(
        {"status": "observed", "nodes": rows, "node_count": len(rows)},
        meta,
        resolved,
    )


def index_read_xrefs(
    root: Path,
    node_id: str,
    direction: str = "both",
    index_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """Read xref edges for one node without modifying the index."""
    _require_root(root)
    validate_node_id(node_id)
    from .ida_ingest import read_xrefs

    result = read_xrefs(root, node_id, direction=direction, index_path=index_path)
    resolved = _resolve_index_path(root, index_path)
    connection = open_read_only(resolved)
    try:
        meta = _read_meta(connection)
    finally:
        close(connection)
    return _attach_index_evidence(result, meta, resolved)


def index_build(
    root: Path,
    apply: bool,
    index_path: Optional[Path] = None,
    syntax_profile: Optional[str] = None,
    parser_cache: Optional[Path] = None,
) -> Dict[str, Any]:
    """Read-only plan (apply=False) or atomic create/replace (apply=True)."""
    _require_root(root)
    if apply:
        return _build_engine.build_apply(root, index_path, syntax_profile, parser_cache)
    return _build_engine.build_plan(root, index_path, syntax_profile, parser_cache)


def index_update(
    root: Path,
    apply: bool,
    index_path: Optional[Path] = None,
    syntax_profile: Optional[str] = None,
    parser_cache: Optional[Path] = None,
) -> Dict[str, Any]:
    """Read-only delta plan (apply=False) or transactional update (apply=True)."""
    _require_root(root)
    if apply:
        return _build_engine.update_apply(root, index_path, syntax_profile, parser_cache)
    return _build_engine.update_plan(root, index_path, syntax_profile, parser_cache)
