"""SQLite index store for the reverse-skill deterministic document index.

This module owns the single machine truth for index persistence: schema,
FTS5/trigram capability gating, transactions, and atomic replace. No
parallel manifest is generated anywhere (ENG: single source of truth).

Schema v1 tables:
- index_meta : key/value facts (schema_version, index_revision, root_hash, built_at, built_by)
- documents  : relative_path / kind / sha256 / line_count / size_bytes
- nodes      : stable node_id, parent_id, depth, ordinal, title, kind,
               start_line/end_line (exact 1-based), body_sha256, tree_path,
               source_kind, symbol_kind
- edges      : parent edges plus Markdown relative-link edges (kind = parent|link)
- fts_terms  : FTS5 unicode61 over (title, body)
- fts_trigram: FTS5 trigram over (title, body) for Chinese/substring search

Read operations open the database with ``mode=ro``; write operations use
explicit transactions. Missing index, incompatible schema, or unavailable
FTS5/trigram MUST block explicitly (fail closed, never silently degrade).
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from .errors import ReverseSkillError

SCHEMA_VERSION = "1"

NODE_ID_RE = re.compile(r"^[0-9a-f]{16}$")

META_SCHEMA_VERSION = "schema_version"
META_INDEX_REVISION = "index_revision"
META_ROOT_HASH = "root_hash"
META_BUILT_AT = "built_at"
META_BUILT_BY = "built_by"


class IndexError(ReverseSkillError):
    """Base error for index operations; public exit code is 5 (blocked)."""

    exit_code = 5
    code = "index_blocked"


class IndexPathNotFound(IndexError):
    code = "index_path_not_found"


class IndexNotFound(IndexError):
    code = "index_not_found"


class IndexCorrupt(IndexError):
    code = "index_corrupt"


class IndexSchemaIncompatible(IndexError):
    code = "index_schema_incompatible"


class IndexCapabilityUnavailable(IndexError):
    code = "index_capability_unavailable"


class NodeNotFound(IndexError):
    code = "node_not_found"


class InvalidNodeId(IndexError):
    code = "invalid_node_id"


SCHEMA_SQL = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS index_meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS documents (
    document_id   INTEGER PRIMARY KEY,
    relative_path TEXT NOT NULL UNIQUE,
    kind          TEXT NOT NULL,
    sha256        TEXT NOT NULL,
    line_count    INTEGER NOT NULL,
    size_bytes    INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS nodes (
    node_id      TEXT PRIMARY KEY,
    document_id  INTEGER NOT NULL REFERENCES documents(document_id) ON DELETE CASCADE,
    parent_id    TEXT REFERENCES nodes(node_id) ON DELETE CASCADE,
    depth        INTEGER NOT NULL,
    ordinal      INTEGER NOT NULL,
    title        TEXT NOT NULL,
    kind         TEXT NOT NULL,
    start_line   INTEGER NOT NULL,
    end_line     INTEGER NOT NULL,
    body_sha256  TEXT NOT NULL,
    tree_path    TEXT NOT NULL,
    source_kind  TEXT NOT NULL,
    symbol_kind  TEXT
);
CREATE INDEX IF NOT EXISTS nodes_document ON nodes(document_id);
CREATE INDEX IF NOT EXISTS nodes_parent  ON nodes(parent_id);
CREATE INDEX IF NOT EXISTS nodes_tree    ON nodes(tree_path);

CREATE TABLE IF NOT EXISTS edges (
    source_node TEXT NOT NULL REFERENCES nodes(node_id) ON DELETE CASCADE,
    target_node TEXT NOT NULL REFERENCES nodes(node_id) ON DELETE CASCADE,
    kind        TEXT NOT NULL,
    PRIMARY KEY (source_node, target_node, kind)
) WITHOUT ROWID;
CREATE INDEX IF NOT EXISTS edges_target ON edges(target_node);

CREATE VIRTUAL TABLE IF NOT EXISTS fts_terms USING fts5(
    node_id UNINDEXED,
    title,
    body,
    tokenize = 'unicode61'
);

CREATE VIRTUAL TABLE IF NOT EXISTS fts_trigram USING fts5(
    node_id UNINDEXED,
    title,
    body,
    tokenize = 'trigram'
);
"""


def load_contracts() -> Dict[str, Any]:
    """Load the frozen machine-readable contract (single source of truth)."""
    path = Path(__file__).resolve().parent / "data" / "index-contracts.json"
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def default_index_path(root: Path) -> Path:
    """Resolve the default index location for a workspace root."""
    contracts = load_contracts()
    return Path(root) / contracts["index_file"]["default_relative"]


def path_is_link_like(path: Path) -> bool:
    """Return true for a POSIX symlink or Windows directory junction."""
    if path.is_symlink():
        return True
    is_junction = getattr(path, "is_junction", None)
    return bool(is_junction and is_junction())


def probe_capabilities() -> Dict[str, Any]:
    """Fail-closed probe: this SQLite build must support FTS5 unicode61 AND trigram."""
    if sqlite3.sqlite_version_info < (3, 34, 0):
        return {
            "available": False,
            "reason": "sqlite_too_old",
            "version": sqlite3.sqlite_version,
        }
    connection = sqlite3.connect(":memory:")
    try:
        connection.execute("CREATE VIRTUAL TABLE probe_terms USING fts5(x, tokenize='unicode61')")
        connection.execute("CREATE VIRTUAL TABLE probe_trigram USING fts5(x, tokenize='trigram')")
        return {
            "available": True,
            "reason": "fts5_unicode61_trigram",
            "version": sqlite3.sqlite_version,
        }
    except sqlite3.OperationalError as exc:
        return {
            "available": False,
            "reason": "fts5_or_trigram_missing",
            "version": sqlite3.sqlite_version,
            "detail": str(exc),
        }
    finally:
        connection.close()


def require_capability() -> Dict[str, Any]:
    capability = probe_capabilities()
    if not capability["available"]:
        raise IndexCapabilityUnavailable(
            f"SQLite FTS5/trigram unavailable: {capability.get('reason')} "
            f"(sqlite {capability.get('version')})"
        )
    return capability


def _connect(path: Path, *, read_only: bool) -> sqlite3.Connection:
    if read_only:
        uri = path.resolve().as_uri() + "?mode=ro"
        connection = sqlite3.connect(uri, uri=True, timeout=30.0)
        connection.row_factory = sqlite3.Row
        return connection
    connection = sqlite3.connect(str(path), timeout=30.0)
    connection.row_factory = sqlite3.Row
    return connection


def _meta(connection: sqlite3.Connection) -> Dict[str, str]:
    return {
        row["key"]: row["value"]
        for row in connection.execute("SELECT key, value FROM index_meta")
    }


def _validate_schema(connection: sqlite3.Connection) -> None:
    try:
        meta = _meta(connection)
    except sqlite3.DatabaseError as exc:
        raise IndexCorrupt(f"index file is not a readable SQLite database: {exc}") from exc
    version = meta.get(META_SCHEMA_VERSION)
    if version != SCHEMA_VERSION:
        raise IndexSchemaIncompatible(
            f"index schema_version is {version!r}, expected {SCHEMA_VERSION!r}; rebuild the index"
        )
    required = {"documents", "nodes", "edges", "fts_terms", "fts_trigram"}
    try:
        present = {
            row["name"]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type IN ('table', 'view')"
            )
        }
    except sqlite3.DatabaseError as exc:
        raise IndexCorrupt(f"index schema cannot be inspected: {exc}") from exc
    missing = sorted(required - present)
    if missing:
        raise IndexCorrupt(
            "index schema is incomplete; missing object(s): " + ", ".join(missing)
        )
    required_columns = {
        "documents": {"document_id", "relative_path", "kind", "sha256", "line_count", "size_bytes"},
        "nodes": {
            "node_id", "document_id", "parent_id", "depth", "ordinal", "title", "kind",
            "start_line", "end_line", "body_sha256", "tree_path", "source_kind", "symbol_kind",
        },
        "edges": {"source_node", "target_node", "kind"},
        "fts_terms": {"node_id", "title", "body"},
        "fts_trigram": {"node_id", "title", "body"},
    }
    for table, expected in required_columns.items():
        try:
            actual = {
                row["name"]
                for row in connection.execute(f'PRAGMA table_info("{table}")')
            }
        except sqlite3.DatabaseError as exc:
            raise IndexCorrupt(f"index table {table!r} cannot be inspected: {exc}") from exc
        missing_columns = sorted(expected - actual)
        if missing_columns:
            raise IndexCorrupt(
                f"index table {table!r} is missing column(s): "
                + ", ".join(missing_columns)
            )
    fts_rows = connection.execute(
        "SELECT name, sql FROM sqlite_master WHERE name IN ('fts_terms', 'fts_trigram')"
    ).fetchall()
    for row in fts_rows:
        definition = (row["sql"] or "").upper()
        if "VIRTUAL TABLE" not in definition or "USING FTS5" not in definition:
            raise IndexCorrupt(f"index object {row['name']!r} is not an FTS5 virtual table")


def open_read_only(index_path: Path) -> sqlite3.Connection:
    """Open an existing index for read-only use, fail-closed."""
    require_capability()
    if not index_path.is_file():
        raise IndexNotFound(f"index file does not exist: {index_path}; run 'index build --apply' first")
    try:
        connection = _connect(index_path, read_only=True)
    except sqlite3.Error as exc:
        raise IndexCorrupt(f"index file cannot be opened read-only: {exc}") from exc
    try:
        _validate_schema(connection)
    except Exception:
        connection.close()
        raise
    return connection


def open_read_write(index_path: Path) -> sqlite3.Connection:
    """Open an existing compatible index for an explicit transactional update."""
    require_capability()
    if path_is_link_like(index_path):
        raise IndexError(f"refusing to update an index through a symlink or junction: {index_path}")
    if not index_path.is_file():
        raise IndexNotFound(f"index file does not exist: {index_path}; run 'index build --apply' first")
    try:
        connection = _connect(index_path, read_only=False)
    except sqlite3.Error as exc:
        raise IndexCorrupt(f"index file cannot be opened for update: {exc}") from exc
    try:
        _validate_schema(connection)
    except Exception:
        connection.close()
        raise
    return connection


def create_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(SCHEMA_SQL)


def document_id_for(connection: sqlite3.Connection, relative_path: str) -> Optional[int]:
    row = connection.execute(
        "SELECT document_id FROM documents WHERE relative_path = ?", (relative_path,)
    ).fetchone()
    return row["document_id"] if row is not None else None


def read_document(connection: sqlite3.Connection, relative_path: str) -> Optional[Dict[str, Any]]:
    row = connection.execute(
        "SELECT document_id, relative_path, kind, sha256, line_count, size_bytes "
        "FROM documents WHERE relative_path = ?",
        (relative_path,),
    ).fetchone()
    return dict(row) if row is not None else None


def read_all_documents(connection: sqlite3.Connection) -> Dict[str, Dict[str, Any]]:
    rows = connection.execute(
        "SELECT document_id, relative_path, kind, sha256, line_count, size_bytes FROM documents"
    ).fetchall()
    return {row["relative_path"]: dict(row) for row in rows}


def read_node(connection: sqlite3.Connection, node_id: str) -> Optional[Dict[str, Any]]:
    row = connection.execute(
        "SELECT n.node_id, n.document_id, n.parent_id, n.depth, n.ordinal, n.title, n.kind, "
        "n.start_line, n.end_line, n.body_sha256, n.tree_path, n.source_kind, n.symbol_kind, "
        "d.relative_path "
        "FROM nodes n JOIN documents d ON d.document_id = n.document_id "
        "WHERE n.node_id = ?",
        (node_id,),
    ).fetchone()
    return dict(row) if row is not None else None


def read_node_text(connection: sqlite3.Connection, node_id: str) -> Optional[str]:
    """Return the indexed node body used by retrieval, or ``None`` if absent."""
    row = connection.execute(
        "SELECT body FROM fts_terms WHERE node_id = ? LIMIT 1", (node_id,)
    ).fetchone()
    return str(row["body"]) if row is not None else None


def read_nodes(connection: sqlite3.Connection, node_ids: Iterable[str]) -> List[Dict[str, Any]]:
    ids = list(node_ids)
    if not ids:
        return []
    placeholders = ",".join("?" for _ in ids)
    rows = connection.execute(
        "SELECT n.node_id, n.document_id, n.parent_id, n.depth, n.ordinal, n.title, n.kind, "
        "n.start_line, n.end_line, n.body_sha256, n.tree_path, n.source_kind, n.symbol_kind, "
        "d.relative_path "
        f"FROM nodes n JOIN documents d ON d.document_id = n.document_id "
        f"WHERE n.node_id IN ({placeholders}) ORDER BY n.node_id",
        ids,
    ).fetchall()
    return [dict(row) for row in rows]


def read_children(
    connection: sqlite3.Connection, node_id: str, *, limit: Optional[int] = None
) -> List[Dict[str, Any]]:
    sql = (
        "SELECT n.node_id, n.document_id, n.parent_id, n.depth, n.ordinal, n.title, n.kind, "
        "n.start_line, n.end_line, n.body_sha256, n.tree_path, n.source_kind, n.symbol_kind, "
        "d.relative_path "
        "FROM nodes n JOIN documents d ON d.document_id = n.document_id "
        "WHERE n.parent_id = ? ORDER BY n.ordinal"
    )
    if limit is not None:
        sql += " LIMIT ?"
        params: Tuple[Any, ...] = (node_id, limit)
    else:
        params = (node_id,)
    rows = connection.execute(sql, params).fetchall()
    return [dict(row) for row in rows]


def read_ancestors(connection: sqlite3.Connection, node_id: str) -> List[Dict[str, Any]]:
    """Return the ancestor chain root-first (excluding the node itself)."""
    ancestors: List[Dict[str, Any]] = []
    current = read_node(connection, node_id)
    seen: set[str] = {node_id}
    while current is not None and current["parent_id"] is not None:
        parent = read_node(connection, current["parent_id"])
        if parent is None:
            raise IndexCorrupt(
                f"node {current['node_id']} references missing parent {current['parent_id']}"
            )
        if parent["node_id"] in seen:
            raise IndexCorrupt(f"cycle detected in node parent chain at {parent['node_id']}")
        ancestors.append(parent)
        seen.add(parent["node_id"])
        current = parent
    ancestors.reverse()
    return ancestors


def read_subtree(connection: sqlite3.Connection, node_id: str) -> List[Dict[str, Any]]:
    """Return the node and all descendants in document order (DFS)."""
    rows = connection.execute(
        "WITH RECURSIVE subtree(node_id) AS ("
        "  SELECT ? "
        "  UNION "
        "  SELECT n.node_id FROM nodes n JOIN subtree s ON n.parent_id = s.node_id"
        ") "
        "SELECT n.node_id, n.document_id, n.parent_id, n.depth, n.ordinal, n.title, n.kind, "
        "n.start_line, n.end_line, n.body_sha256, n.tree_path, n.source_kind, n.symbol_kind, "
        "d.relative_path "
        "FROM nodes n JOIN documents d ON d.document_id = n.document_id "
        "JOIN subtree s ON s.node_id = n.node_id "
        "ORDER BY n.start_line, n.depth, n.ordinal, n.node_id",
        (node_id,),
    ).fetchall()
    return [dict(row) for row in rows]


def read_link_targets(connection: sqlite3.Connection, node_id: str) -> List[Dict[str, Any]]:
    rows = connection.execute(
        "SELECT e.target_node, e.kind, n.title, n.tree_path, d.relative_path "
        "FROM edges e "
        "JOIN nodes n ON n.node_id = e.target_node "
        "JOIN documents d ON d.document_id = n.document_id "
        "WHERE e.source_node = ? AND e.kind = 'link' "
        "ORDER BY d.relative_path, n.start_line, n.node_id",
        (node_id,),
    ).fetchall()
    return [dict(row) for row in rows]


def insert_document(connection: sqlite3.Connection, document: Dict[str, Any]) -> int:
    cursor = connection.execute(
        "INSERT INTO documents (relative_path, kind, sha256, line_count, size_bytes) "
        "VALUES (?, ?, ?, ?, ?)",
        (
            document["relative_path"],
            document["kind"],
            document["sha256"],
            document["line_count"],
            document["size_bytes"],
        ),
    )
    return int(cursor.lastrowid)


def insert_nodes(connection: sqlite3.Connection, nodes: Sequence[Dict[str, Any]]) -> None:
    """Bulk insert already parent-before-child node rows."""
    connection.executemany(
        "INSERT INTO nodes (node_id, document_id, parent_id, depth, ordinal, title, kind, "
        "start_line, end_line, body_sha256, tree_path, source_kind, symbol_kind) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            (
                node["node_id"],
                node["document_id"],
                node.get("parent_id"),
                node["depth"],
                node["ordinal"],
                node["title"],
                node["kind"],
                node["start_line"],
                node["end_line"],
                node["body_sha256"],
                node["tree_path"],
                node["source_kind"],
                node.get("symbol_kind"),
            )
            for node in nodes
        ],
    )


def insert_edge(connection: sqlite3.Connection, source_node: str, target_node: str, kind: str) -> None:
    connection.execute(
        "INSERT OR IGNORE INTO edges (source_node, target_node, kind) VALUES (?, ?, ?)",
        (source_node, target_node, kind),
    )


def insert_fts_rows_bulk(
    connection: sqlite3.Connection, rows: Sequence[Dict[str, Any]]
) -> None:
    """Bulk insert both FTS projections for materialized node rows."""
    values = [(row["node_id"], row["title"], row["_body"]) for row in rows]
    connection.executemany(
        "INSERT INTO fts_terms (node_id, title, body) VALUES (?, ?, ?)", values
    )
    connection.executemany(
        "INSERT INTO fts_trigram (node_id, title, body) VALUES (?, ?, ?)", values
    )


def delete_document_cascade(connection: sqlite3.Connection, document_id: int) -> None:
    """Remove FTS rows and the document row; nodes/edges cascade via foreign keys."""
    connection.execute(
        "DELETE FROM fts_terms WHERE node_id IN (SELECT node_id FROM nodes WHERE document_id = ?)",
        (document_id,),
    )
    connection.execute(
        "DELETE FROM fts_trigram WHERE node_id IN (SELECT node_id FROM nodes WHERE document_id = ?)",
        (document_id,),
    )
    connection.execute("DELETE FROM documents WHERE document_id = ?", (document_id,))


def set_meta(connection: sqlite3.Connection, key: str, value: str) -> None:
    connection.execute(
        "INSERT INTO index_meta (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )


def compute_root_hash(entries: Iterable[Tuple[str, str]]) -> str:
    """Deterministic content root hash over sorted (relative_path, sha256) pairs."""
    digest = hashlib.sha256()
    for relative_path, sha256_hex in sorted(entries, key=lambda item: item[0]):
        digest.update(relative_path.encode("utf-8"))
        digest.update(b"\x00")
        digest.update(sha256_hex.encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()


def node_id_for(relative_path: str, tree_path: str, occurrence: int) -> str:
    """Stable structural node id: sha256(relpath, tree_path, occurrence)[:16].

    Content changes under a node never change its id; title/structure changes
    do, which is the intended semantics for a deterministic tree.
    """
    payload = "{}\x00{}\x00{}".format(relative_path, tree_path, occurrence)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def validate_node_id(node_id: str) -> None:
    if not NODE_ID_RE.match(node_id):
        raise InvalidNodeId(f"node_id must match {NODE_ID_RE.pattern!r}: {node_id!r}")


def atomically_replace(source: Path, destination: Path) -> None:
    """Replace destination with source atomically (same filesystem)."""
    os.replace(str(source), str(destination))


def close(connection: Optional[sqlite3.Connection]) -> None:
    if connection is not None:
        connection.close()
