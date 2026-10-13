"""Explicit, provider-neutral IDA export ingestion for the shared index.

IDA and its plugins remain external providers.  This module accepts one
versioned JSON export, validates it completely before opening the index, and
materializes functions as stable nodes plus xrefs as ``xref`` edges.  It never
starts IDA, downloads anything, or writes unless ``apply=True`` is explicit.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .index_store import (
    META_BUILT_AT,
    META_BUILT_BY,
    META_INDEX_REVISION,
    SCHEMA_VERSION,
    IndexError,
    IndexNotFound,
    IndexPathNotFound,
    NodeNotFound,
    close,
    default_index_path,
    delete_document_cascade,
    insert_document,
    insert_edge,
    insert_fts_rows_bulk,
    insert_nodes,
    node_id_for,
    open_read_only,
    open_read_write,
    read_document,
    read_node,
    read_xref_sources,
    read_xref_targets,
    require_capability,
    set_meta,
)


EXPORT_SCHEMA_VERSION = 1
IDA_DOCUMENT_PREFIX = "__ida__/"
MAX_EXPORT_BYTES = 64 * 1024 * 1024
MAX_FUNCTIONS = 100_000
MAX_NAME_BYTES = 4096
MAX_PSEUDOCODE_BYTES = 4 * 1024 * 1024
_HEX_ADDRESS_RE = re.compile(r"^(?:0[xX])?[0-9a-fA-F]+$")
_DRIVE_RE = re.compile(r"^[A-Za-z]:")


class IdaExportInvalid(IndexError):
    """The explicit IDA export is absent, malformed, or unsafe to import."""

    code = "ida_export_invalid"


@dataclass(frozen=True)
class IdaFunction:
    address: str
    name: str
    pseudocode: str
    xrefs_to: Tuple[str, ...]


@dataclass(frozen=True)
class IdaExport:
    module: str
    document_path: str
    functions: Tuple[IdaFunction, ...]
    export_sha256: str


def _invalid(message: str) -> IdaExportInvalid:
    return IdaExportInvalid(message)


def _bounded_text(value: Any, field: str, limit: int, *, required: bool = True) -> str:
    if not isinstance(value, str) or (required and not value.strip()):
        raise _invalid(f"IDA export field {field!r} must be a non-empty string")
    if len(value.encode("utf-8")) > limit:
        raise _invalid(f"IDA export field {field!r} exceeds {limit} UTF-8 bytes")
    if "\x00" in value:
        raise _invalid(f"IDA export field {field!r} contains NUL")
    return value


def _relative_module(value: Any) -> str:
    module = _bounded_text(value, "module", 4096)
    if (
        module.startswith(("/", "\\"))
        or "\\" in module
        or _DRIVE_RE.match(module)
    ):
        raise _invalid("IDA export module must be a relative POSIX name")
    parts = module.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise _invalid("IDA export module must not contain empty, '.' or '..' path segments")
    return "/".join(parts)


def _address(value: Any, field: str) -> str:
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        raise _invalid(f"IDA export field {field!r} must be an integer or hexadecimal string")
    if isinstance(value, str):
        raw = value.strip()
        if not _HEX_ADDRESS_RE.fullmatch(raw):
            raise _invalid(f"IDA export field {field!r} is not a valid address")
        try:
            number = int(raw, 16) if raw.lower().startswith("0x") else int(raw, 16)
        except ValueError as exc:
            raise _invalid(f"IDA export field {field!r} is not a valid address") from exc
    else:
        number = value
    if number < 0 or number > 0xFFFFFFFFFFFFFFFF:
        raise _invalid(f"IDA export field {field!r} is outside the 64-bit address range")
    return f"0x{number:x}"


def _canonical_payload(module: str, functions: Sequence[IdaFunction]) -> bytes:
    payload = {
        "schema_version": EXPORT_SCHEMA_VERSION,
        "module": module,
        "functions": [
            {
                "address": item.address,
                "name": item.name,
                "pseudocode": item.pseudocode,
                "xrefs_to": list(item.xrefs_to),
            }
            for item in functions
        ],
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )


def load_export(export_path: Path) -> IdaExport:
    """Read and validate one explicit export before any index access."""
    if not export_path.is_file():
        raise _invalid(f"IDA export file does not exist: {export_path}")
    try:
        raw = export_path.read_bytes()
    except OSError as exc:
        raise _invalid(f"IDA export cannot be read: {exc}") from exc
    if len(raw) > MAX_EXPORT_BYTES:
        raise _invalid(f"IDA export exceeds {MAX_EXPORT_BYTES} bytes")
    try:
        payload = json.loads(raw.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise _invalid(f"IDA export is not valid UTF-8 JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise _invalid("IDA export root must be a JSON object")
    version = payload.get("schema_version")
    if type(version) is not int or version != EXPORT_SCHEMA_VERSION:
        raise _invalid(
            f"unsupported IDA export schema_version {version!r}; expected {EXPORT_SCHEMA_VERSION}"
        )
    module = _relative_module(payload.get("module"))
    raw_functions = payload.get("functions")
    if not isinstance(raw_functions, list) or len(raw_functions) > MAX_FUNCTIONS:
        raise _invalid(f"IDA export functions must be a list of at most {MAX_FUNCTIONS} items")

    functions: List[IdaFunction] = []
    addresses: set[str] = set()
    total_pseudocode_bytes = 0
    for position, raw_function in enumerate(raw_functions, start=1):
        if not isinstance(raw_function, dict):
            raise _invalid(f"IDA export function {position} must be an object")
        address = _address(raw_function.get("address"), f"functions[{position}].address")
        if address in addresses:
            raise _invalid(f"IDA export contains duplicate function address {address}")
        addresses.add(address)
        name = _bounded_text(
            raw_function.get("name"), f"functions[{position}].name", MAX_NAME_BYTES
        )
        pseudocode = raw_function.get("pseudocode", "")
        if not isinstance(pseudocode, str):
            raise _invalid(f"IDA export functions[{position}].pseudocode must be a string")
        if len(pseudocode.encode("utf-8")) > MAX_PSEUDOCODE_BYTES:
            raise _invalid(
                f"IDA export functions[{position}].pseudocode exceeds {MAX_PSEUDOCODE_BYTES} UTF-8 bytes"
            )
        if "\x00" in pseudocode:
            raise _invalid(f"IDA export functions[{position}].pseudocode contains NUL")
        total_pseudocode_bytes += len(pseudocode.encode("utf-8"))
        xrefs = raw_function.get("xrefs_to", [])
        if not isinstance(xrefs, list):
            raise _invalid(f"IDA export functions[{position}].xrefs_to must be a list")
        normalized_xrefs = tuple(sorted({_address(item, f"functions[{position}].xrefs_to") for item in xrefs}))
        functions.append(IdaFunction(address, name, pseudocode, normalized_xrefs))

    if total_pseudocode_bytes > MAX_EXPORT_BYTES:
        raise _invalid("IDA export pseudocode exceeds the total export size budget")
    known = {item.address for item in functions}
    unresolved = sorted(
        {target for item in functions for target in item.xrefs_to if target not in known}
    )
    if unresolved:
        raise _invalid("IDA export xref target(s) do not name an exported function: " + ", ".join(unresolved))
    canonical = _canonical_payload(module, functions)
    return IdaExport(
        module=module,
        document_path=IDA_DOCUMENT_PREFIX + module,
        functions=tuple(functions),
        export_sha256=hashlib.sha256(canonical).hexdigest(),
    )


def _require_root(root: Path) -> None:
    if not root.is_dir():
        raise IndexPathNotFound(f"workspace path is not a directory: {root}")


def _resolve_index_path(root: Path, index_path: Optional[Path]) -> Path:
    return Path(index_path) if index_path is not None else default_index_path(root)


def _function_body(item: IdaFunction) -> str:
    return item.pseudocode or f"{item.name} @ {item.address}"


def _rendered_body(export: IdaExport) -> str:
    return "\n".join(_function_body(item) for item in export.functions)


def _function_rows(export: IdaExport, document_id: int) -> Tuple[List[Dict[str, Any]], Dict[str, str]]:
    rows: List[Dict[str, Any]] = []
    addresses_to_nodes: Dict[str, str] = {}
    line_cursor = 1
    root_body = _rendered_body(export)
    root_lines = root_body.splitlines() or [""]
    root_node = node_id_for(export.document_path, export.document_path, 1)
    rows.append(
        {
            "node_id": root_node,
            "document_id": document_id,
            "parent_id": None,
            "depth": 0,
            "ordinal": 0,
            "title": export.module,
            "kind": "file",
            "start_line": 1,
            "end_line": len(root_lines),
            "body_sha256": hashlib.sha256(root_body.encode("utf-8")).hexdigest(),
            "tree_path": export.document_path,
            "source_kind": "ida",
            "symbol_kind": None,
            "_body": root_body,
        }
    )
    for ordinal, item in enumerate(export.functions, start=1):
        body = _function_body(item)
        lines = body.splitlines() or [""]
        tree_path = f"{export.document_path}#function@{item.address}"
        node_id = node_id_for(export.document_path, tree_path, 1)
        addresses_to_nodes[item.address] = node_id
        rows.append(
            {
                "node_id": node_id,
                "document_id": document_id,
                "parent_id": root_node,
                "depth": 1,
                "ordinal": ordinal,
                "title": f"{item.name} [{item.address}]",
                "kind": "function",
                "start_line": line_cursor,
                "end_line": line_cursor + len(lines) - 1,
                "body_sha256": hashlib.sha256(body.encode("utf-8")).hexdigest(),
                "tree_path": tree_path,
                "source_kind": "ida",
                "symbol_kind": "ida_function",
                "_body": body,
            }
        )
        line_cursor += len(lines)
    return rows, addresses_to_nodes


def _summary(export: IdaExport, resolved: Path, *, applied: bool, existing: bool) -> Dict[str, Any]:
    return {
        "status": "applied" if applied else "planned",
        "operation": "ida-import",
        "applied": applied,
        "schema_version": SCHEMA_VERSION,
        "index_path": str(resolved),
        "export_sha256": export.export_sha256,
        "module": export.module,
        "documents": {"replaced": int(existing), "functions": len(export.functions)},
        "edges": {
            "xrefs": sum(len(item.xrefs_to) for item in export.functions),
        },
        "writes": (
            "none (read-only plan; rerun with --apply to import the export)"
            if not applied
            else "replaced one IDA export document transactionally"
        ),
    }


def import_export(
    root: Path,
    export_path: Path,
    *,
    apply: bool,
    index_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """Plan or apply one complete IDA export replacement."""
    _require_root(root)
    require_capability()
    export = load_export(export_path)
    resolved = _resolve_index_path(root, index_path)
    if not resolved.is_file():
        raise IndexNotFound(f"index file does not exist: {resolved}; run 'index build --apply' first")
    if not apply:
        connection = open_read_only(resolved)
        try:
            existing = read_document(connection, export.document_path)
        finally:
            close(connection)
        if existing is not None and existing["kind"] != "ida":
            raise _invalid(
                f"IDA document path collides with a non-IDA document: {export.document_path}"
            )
        return _summary(export, resolved, applied=False, existing=existing is not None)

    connection = open_read_write(resolved)
    connection.isolation_level = None
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        connection.execute("BEGIN IMMEDIATE")
        existing = read_document(connection, export.document_path)
        if existing is not None and existing["kind"] != "ida":
            raise _invalid(
                f"IDA document path collides with a non-IDA document: {export.document_path}"
            )
        if existing is not None:
            delete_document_cascade(connection, int(existing["document_id"]))
        document_id = insert_document(
            connection,
            {
                "relative_path": export.document_path,
                "kind": "ida",
                "sha256": export.export_sha256,
                "line_count": max(1, len(_rendered_body(export).splitlines())),
                "size_bytes": len(_rendered_body(export).encode("utf-8")),
            },
        )
        rows, address_nodes = _function_rows(export, document_id)
        insert_nodes(connection, rows)
        for row in rows:
            if row["parent_id"] is not None:
                insert_edge(connection, row["node_id"], row["parent_id"], "parent")
        for item in export.functions:
            source = address_nodes[item.address]
            for target_address in item.xrefs_to:
                insert_edge(connection, source, address_nodes[target_address], "xref")
        insert_fts_rows_bulk(connection, rows)
        meta = {
            row["key"]: row["value"]
            for row in connection.execute("SELECT key, value FROM index_meta")
        }
        next_revision = str(int(meta.get(META_INDEX_REVISION, "0") or 0) + 1)
        set_meta(connection, META_INDEX_REVISION, next_revision)
        set_meta(connection, META_BUILT_AT, str(int(time.time())))
        set_meta(connection, META_BUILT_BY, "ida-import")
        set_meta(connection, "ida_export_sha256", export.export_sha256)
        connection.execute("COMMIT")
    except Exception:
        try:
            connection.execute("ROLLBACK")
        except sqlite3.Error:
            pass
        close(connection)
        raise
    close(connection)
    result = _summary(export, resolved, applied=True, existing=existing is not None)
    result["index_revision"] = next_revision
    return result


def read_xrefs(
    root: Path,
    node_id: str,
    *,
    direction: str = "both",
    index_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """Read outgoing/incoming xrefs for one stable node."""
    _require_root(root)
    if direction not in {"incoming", "outgoing", "both"}:
        raise _invalid("xref direction must be incoming, outgoing, or both")
    resolved = _resolve_index_path(root, index_path)
    connection = open_read_only(resolved)
    try:
        node = read_node(connection, node_id)
        if node is None:
            raise NodeNotFound(f"node_id not found in index: {node_id}")
        outgoing = read_xref_targets(connection, node_id) if direction in {"outgoing", "both"} else []
        incoming = read_xref_sources(connection, node_id) if direction in {"incoming", "both"} else []
    finally:
        close(connection)
    return {
        "status": "observed",
        "node_id": node_id,
        "direction": direction,
        "outgoing": outgoing,
        "incoming": incoming,
        "outgoing_count": len(outgoing),
        "incoming_count": len(incoming),
        "index_path": str(resolved),
    }
