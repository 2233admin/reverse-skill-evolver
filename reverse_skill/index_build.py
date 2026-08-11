"""Deterministic workspace scanning and index build/update.

Read-only scanning with frozen exclusions, fence-aware Markdown ATX tree
parsing (same-name headings, preamble, exact 1-based line ranges), Python
AST symbol nodes, raw-byte SHA-256 comparison for incremental updates, and
atomic build replacement.

Write operations are explicit: ``build_plan``/``update_plan`` never touch
the filesystem beyond reading; ``build_apply`` uses a temporary database in
the destination directory plus atomic replace; ``update_apply`` runs inside
one SQLite transaction and rolls back cleanly on failure.
"""

from __future__ import annotations

import ast
import fnmatch
import hashlib
import os
import re
import sqlite3
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .index_store import (
    META_BUILT_AT,
    META_BUILT_BY,
    META_INDEX_REVISION,
    META_ROOT_HASH,
    META_SCHEMA_VERSION,
    SCHEMA_VERSION,
    IndexError,
    IndexNotFound,
    IndexPathNotFound,
    ParserUnavailable,
    atomically_replace,
    close,
    compute_root_hash,
    create_schema,
    default_index_path,
    delete_document_cascade,
    insert_document,
    insert_edge,
    insert_fts_rows_bulk,
    insert_nodes,
    load_contracts,
    node_id_for,
    open_read_only,
    open_read_write,
    path_is_link_like,
    read_all_documents,
    require_capability,
    set_meta,
)

_ATX_HEADING_RE = re.compile(r"^(#{1,6})(?:[ \t]+(.*?))?[ \t]*$")
_FENCE_OPEN_RE = re.compile(r"^(```+|~~~+)")
_TRAILING_HASHES_RE = re.compile(r"[ \t]+#+$")
_MARKDOWN_LINK_RE = re.compile(r"\[[^\]]*\]\(([^)]+)\)")


@dataclass
class NodeSpec:
    """One parsed node before it becomes a database row."""

    kind: str
    title: str
    start: int
    end: int
    tree_path: str
    occurrence: int
    parent_index: Optional[int] = None  # index into the same node list
    symbol_kind: Optional[str] = None
    children: List[int] = field(default_factory=list)


@dataclass
class ParsedDocument:
    relpath: str
    kind: str  # markdown | python | syntax | text
    sha256: str
    line_count: int
    size_bytes: int
    lines: List[str]
    nodes: List[NodeSpec]
    python_parse_failed: bool = False


@dataclass
class SkippedFile:
    relpath: str
    reason: str


# --- Scanning ---------------------------------------------------------------


def _is_virtualenv_dir(path: Path, name: str) -> bool:
    if name not in {"venv", ".venv", "env"}:
        return False
    return (path / "pyvenv.cfg").is_file()


def _is_credential_file(relpath: str, patterns: Sequence[str]) -> bool:
    name = Path(relpath).name.casefold()
    return any(fnmatch.fnmatchcase(name, pattern.casefold()) for pattern in patterns)


def _is_link_like(path: Path) -> bool:
    """Treat POSIX symlinks and Windows junctions as traversal boundaries."""
    return path_is_link_like(path)


def _looks_binary(head: bytes) -> bool:
    return b"\x00" in head


def _decode_text(data: bytes) -> str:
    return data.decode("utf-8", errors="replace")


def scan_workspace(
    root: Path,
    contracts: Dict[str, Any],
    syntax_profile: Optional[str] = None,
    parser_cache: Optional[Path] = None,
) -> Tuple[List[ParsedDocument], List[SkippedFile]]:
    """Read-only deterministic scan; never follows symlinks."""
    if _is_link_like(root):
        raise IndexPathNotFound(f"workspace path must not be a symlink or junction: {root}")
    exclusions = contracts["default_exclusions"]
    dir_names = set(exclusions["directory_names"])
    credential_patterns = list(exclusions["credential_file_patterns"])
    max_bytes = int(exclusions["max_file_bytes"])
    syntax_extensions = _syntax_extensions(contracts, syntax_profile)
    if syntax_profile is not None:
        _require_parser_cache(parser_cache)

    files: List[ParsedDocument] = []
    skipped: List[SkippedFile] = []

    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        kept: List[str] = []
        for dirname in sorted(dirnames):
            candidate = Path(dirpath) / dirname
            rel_dir = os.path.relpath(candidate, root).replace(os.sep, "/")
            if _is_link_like(candidate):
                skipped.append(SkippedFile(rel_dir + "/", "symlink"))
                continue
            if dirname in dir_names:
                skipped.append(SkippedFile(rel_dir + "/", "directory_excluded"))
                continue
            if _is_virtualenv_dir(candidate, dirname):
                skipped.append(SkippedFile(rel_dir + "/", "virtualenv"))
                continue
            kept.append(dirname)
        dirnames[:] = kept
        for filename in sorted(filenames):
            candidate = Path(dirpath) / filename
            relpath = os.path.relpath(candidate, root).replace(os.sep, "/")
            if _is_link_like(candidate):
                skipped.append(SkippedFile(relpath, "symlink"))
                continue
            try:
                stat = candidate.stat()
            except OSError:
                skipped.append(SkippedFile(relpath, "read_error"))
                continue
            if stat.st_size > max_bytes:
                skipped.append(SkippedFile(relpath, "too_large"))
                continue
            if _is_credential_file(relpath, credential_patterns):
                skipped.append(SkippedFile(relpath, "credential_file"))
                continue
            try:
                with open(candidate, "rb") as handle:
                    data = handle.read()
            except OSError:
                skipped.append(SkippedFile(relpath, "read_error"))
                continue
            if data and _looks_binary(data[:8192]):
                skipped.append(SkippedFile(relpath, "binary"))
                continue
            files.append(
                _parse_file(
                    relpath,
                    data,
                    stat.st_size,
                    language=syntax_extensions.get(Path(relpath).suffix.lower()),
                    parser_cache=parser_cache,
                )
            )
    return files, skipped


def _syntax_extensions(
    contracts: Dict[str, Any], profile: Optional[str]
) -> Dict[str, str]:
    if profile is None:
        return {}
    profiles = contracts.get("syntax_profiles", {})
    definition = profiles.get(profile)
    if not isinstance(definition, dict) or not isinstance(definition.get("extensions"), dict):
        raise ParserUnavailable(f"unknown syntax profile: {profile}")
    extensions: Dict[str, str] = {}
    for suffix, language in definition["extensions"].items():
        normalized_suffix = str(suffix).lower()
        if not normalized_suffix.startswith(".") or not str(language):
            raise ParserUnavailable(f"invalid syntax profile entry: {suffix!r}")
        extensions[normalized_suffix] = str(language)
    return extensions


def _require_parser_cache(parser_cache: Optional[Path]) -> Path:
    if parser_cache is None:
        raise ParserUnavailable(
            "syntax indexing requires an existing parser cache; "
            "run 'index parsers --install --cache-dir PATH' first"
        )
    resolved = Path(parser_cache)
    if _is_link_like(resolved) or not resolved.is_dir():
        raise ParserUnavailable(f"parser cache is not an existing directory: {resolved}")
    return resolved


def _language_pack(parser_cache: Path, languages: Sequence[str]) -> Tuple[Any, set[str]]:
    try:
        import tree_sitter_language_pack as language_pack
    except ImportError as exc:
        raise ParserUnavailable(
            "tree-sitter-language-pack is not installed; install the [syntax] extra"
        ) from exc
    try:
        # The package treats PackConfig.languages as a pre-download request.
        # Indexing is cache-only and read-only, so only configure the cache.
        language_pack.configure(language_pack.PackConfig(cache_dir=str(parser_cache)))
        downloaded = {str(item) for item in language_pack.downloaded_languages()}
    except Exception as exc:
        raise ParserUnavailable(
            f"tree-sitter-language-pack cache cannot be opened: {parser_cache}"
        ) from exc
    missing = sorted(set(languages) - downloaded)
    if missing:
        raise ParserUnavailable(
            "parser cache is missing language(s): " + ", ".join(missing)
        )
    return language_pack, downloaded


def parser_status(
    profile: str,
    parser_cache: Path,
    contracts: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    contracts = contracts or load_contracts()
    extensions = _syntax_extensions(contracts, profile)
    languages = sorted(set(extensions.values()))
    report: Dict[str, Any] = {
        "status": "observed",
        "profile": profile,
        "cache_dir": str(parser_cache),
        "languages": languages,
        "downloaded": [],
        "missing": languages,
    }
    if _is_link_like(parser_cache) or not parser_cache.is_dir():
        report["status"] = "blocked"
        report["reason"] = "cache_not_found"
        return report
    try:
        language_pack, downloaded = _language_pack(parser_cache, [])
    except ParserUnavailable as exc:
        report["status"] = "blocked"
        report["reason"] = str(exc)
        return report
    del language_pack
    report["downloaded"] = sorted(set(languages) & downloaded)
    report["missing"] = sorted(set(languages) - downloaded)
    report["ready"] = not report["missing"]
    return report


def install_parsers(
    profile: str,
    parser_cache: Path,
    contracts: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    contracts = contracts or load_contracts()
    extensions = _syntax_extensions(contracts, profile)
    languages = sorted(set(extensions.values()))
    resolved = Path(parser_cache)
    if _is_link_like(resolved):
        raise ParserUnavailable(f"refusing parser cache symlink or junction: {resolved}")
    try:
        if resolved.exists() and not resolved.is_dir():
            raise ParserUnavailable(f"parser cache is not a directory: {resolved}")
        resolved.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise ParserUnavailable(f"cannot create parser cache: {resolved}") from exc
    try:
        import tree_sitter_language_pack as language_pack
    except ImportError as exc:
        raise ParserUnavailable(
            "tree-sitter-language-pack is not installed; install the [syntax] extra"
        ) from exc
    try:
        language_pack.configure(language_pack.PackConfig(cache_dir=str(resolved)))
        available_count = int(language_pack.download(languages))
        downloaded = {str(item) for item in language_pack.downloaded_languages()}
    except Exception as exc:
        raise ParserUnavailable(
            f"tree-sitter-language-pack parser installation failed: {exc}"
        ) from exc
    missing = sorted(set(languages) - downloaded)
    if missing:
        detail = (
            "parser download did not complete "
            f"(provider reports {available_count} requested language(s) available, "
            f"cache contains {len(downloaded)})"
        )
        detail += ": " + ", ".join(missing)
        raise ParserUnavailable(detail)
    return {
        "status": "applied",
        "profile": profile,
        "cache_dir": str(resolved),
        "languages": languages,
        "downloaded": sorted(downloaded),
    }


def _enum_text(value: Any, default: str) -> str:
    raw = getattr(value, "value", value)
    text = str(raw or default).strip().lower()
    return text.rsplit(".", 1)[-1] or default


def parse_tree_sitter(
    relpath: str,
    lines: List[str],
    language: str,
    parser_cache: Optional[Path],
) -> List[NodeSpec]:
    cache = _require_parser_cache(parser_cache)
    language_pack, _ = _language_pack(cache, [language])
    try:
        result = language_pack.process(
            "\n".join(lines),
            language_pack.ProcessConfig(
                language=language,
                structure=True,
                imports=False,
                exports=False,
            ),
        )
    except Exception as exc:
        raise ParserUnavailable(
            f"tree-sitter parser failed for {relpath} ({language})"
        ) from exc

    line_count = len(lines)
    root = NodeSpec(
        kind="file",
        title=relpath,
        start=1,
        end=max(line_count, 1),
        tree_path=relpath,
        occurrence=1,
        symbol_kind=language,
    )
    nodes: List[NodeSpec] = [root]

    def visit(item: Any, parent_index: int) -> None:
        span = getattr(item, "span", None)
        if span is None:
            raise ParserUnavailable(
                f"tree-sitter returned a structural item without a span for {relpath}"
            )
        start = int(getattr(span, "start_line")) + 1
        end = int(getattr(span, "end_line")) + 1
        line_limit = max(line_count, 1)
        if start < 1 or end < start or start > line_limit:
            raise ParserUnavailable(
                f"tree-sitter returned an invalid span for {relpath}: {start}-{end}"
            )
        end = min(end, line_limit)
        kind = _enum_text(getattr(item, "kind", None), "symbol")
        title = str(getattr(item, "name", None) or f"<{kind}>")
        parent = nodes[parent_index]
        occurrence = 1 + sum(
            1
            for candidate in nodes
            if candidate.parent_index == parent_index and candidate.title == title
        )
        segments = _segment_chain(nodes, parent_index)
        segments.append(_identity_segment(title, occurrence))
        spec = NodeSpec(
            kind="symbol",
            title=title,
            start=start,
            end=end,
            tree_path="{}#{}".format(relpath, "/".join(segments)),
            occurrence=occurrence,
            parent_index=parent_index,
            symbol_kind=kind,
        )
        parent.children.append(len(nodes))
        nodes.append(spec)
        child_index = len(nodes) - 1
        for child in getattr(item, "children", []) or []:
            visit(child, child_index)

    for item in getattr(result, "structure", []) or []:
        visit(item, 0)
    return nodes


def _parse_file(
    relpath: str,
    data: bytes,
    size_bytes: int,
    *,
    language: Optional[str] = None,
    parser_cache: Optional[Path] = None,
) -> ParsedDocument:
    sha256_hex = hashlib.sha256(data).hexdigest()
    text = _decode_text(data)
    lines = text.splitlines()
    line_count = len(lines)
    suffix = Path(relpath).suffix.lower()
    if suffix in {".md", ".markdown"}:
        nodes = parse_markdown(relpath, lines)
        return ParsedDocument(relpath, "markdown", sha256_hex, line_count, size_bytes, lines, nodes)
    if suffix == ".py":
        nodes, failed = parse_python(relpath, lines)
        kind = "text" if failed else "python"
        return ParsedDocument(relpath, kind, sha256_hex, line_count, size_bytes, lines, nodes, failed)
    if language is not None:
        nodes = parse_tree_sitter(relpath, lines, language, parser_cache)
        return ParsedDocument(relpath, "syntax", sha256_hex, line_count, size_bytes, lines, nodes)
    nodes = [
        NodeSpec(
            kind="file",
            title=relpath,
            start=1,
            end=max(line_count, 1),
            tree_path=relpath,
            occurrence=1,
        )
    ]
    return ParsedDocument(relpath, "text", sha256_hex, line_count, size_bytes, lines, nodes)


def _node_links(text: str) -> List[str]:
    return [match.group(1).strip() for match in _MARKDOWN_LINK_RE.finditer(text)]


# --- Markdown ---------------------------------------------------------------


def parse_markdown(relpath: str, lines: List[str]) -> List[NodeSpec]:
    """Fence-aware ATX heading tree with preamble and same-name occurrence."""
    line_count = len(lines)
    headings: List[Dict[str, Any]] = []
    in_fence = False
    fence_char = ""
    fence_len = 0
    for idx, line in enumerate(lines):
        stripped = line.lstrip()
        indent = len(line) - len(stripped)
        if in_fence:
            if indent <= 3 and stripped.startswith(fence_char * fence_len):
                rest = stripped[fence_len:]
                if rest.strip() == "" or rest.startswith(fence_char * fence_len):
                    in_fence = False
            continue
        opener = _FENCE_OPEN_RE.match(stripped)
        if indent <= 3 and opener:
            in_fence = True
            fence_char = opener.group(1)[0]
            fence_len = len(opener.group(1))
            continue
        match = _ATX_HEADING_RE.match(stripped)
        if not match:
            continue
        title = match.group(2) or ""
        title = _TRAILING_HASHES_RE.sub("", title).strip()
        headings.append({"level": len(match.group(1)), "title": title, "line": idx + 1})

    nodes: List[NodeSpec] = []
    file_node = NodeSpec(
        kind="file",
        title=relpath,
        start=1,
        end=max(line_count, 1),
        tree_path=relpath,
        occurrence=1,
    )
    nodes.append(file_node)

    if not headings:
        preamble = NodeSpec(
            kind="preamble",
            title="(preamble)",
            start=1,
            end=max(line_count, 1),
            tree_path="{}#~preamble".format(relpath),
            occurrence=1,
            parent_index=0,
        )
        file_node.children.append(1)
        nodes.append(preamble)
        return nodes

    # Section end lines: next heading with level <= current, else EOF.
    # The reverse stack keeps strictly-deeper headings; a same-level heading
    # to the right closes the current section (do NOT pop on equal levels).
    next_section_end: List[int] = [line_count] * len(headings)
    stack: List[Tuple[int, int]] = []
    for i in range(len(headings) - 1, -1, -1):
        level = headings[i]["level"]
        while stack and stack[-1][0] > level:
            stack.pop()
        if stack:
            next_section_end[i] = stack[-1][1] - 1
        stack.append((level, headings[i]["line"]))

    # Document-order parent stack: (spec_index, heading_level); file node is depth 0.
    parent_stack: List[Tuple[int, int]] = [(0, 0)]
    occurrence_by_parent: Dict[Tuple[int, str], int] = {}
    first_line = headings[0]["line"]
    if first_line > 1:
        preamble = NodeSpec(
            kind="preamble",
            title="(preamble)",
            start=1,
            end=first_line - 1,
            tree_path="{}#~preamble".format(relpath),
            occurrence=1,
            parent_index=0,
        )
        file_node.children.append(len(nodes))
        nodes.append(preamble)

    for index, heading in enumerate(headings):
        level = heading["level"]
        while parent_stack[-1][1] >= level:
            parent_stack.pop()
        parent_index, _ = parent_stack[-1]
        key = (parent_index, heading["title"])
        occurrence = occurrence_by_parent.get(key, 0) + 1
        occurrence_by_parent[key] = occurrence
        segments = _segment_chain(nodes, parent_index)
        segments.append(_identity_segment(heading["title"], occurrence))
        tree_path = "{}#{}".format(relpath, "/".join(segments))
        node = NodeSpec(
            kind="heading",
            title=heading["title"],
            start=heading["line"],
            end=next_section_end[index],
            tree_path=tree_path,
            occurrence=occurrence,
            parent_index=parent_index,
        )
        nodes[parent_index].children.append(len(nodes))
        nodes.append(node)
        parent_stack.append((len(nodes) - 1, level))

    return nodes


def _identity_segment(title: str, occurrence: int) -> str:
    """Return one collision-free, readable tree-path segment.

    Ordinary titles stay unchanged. ``~``, ``/``, and ``@`` are escaped so
    the ``@N`` duplicate-sibling suffix cannot collide with a literal title.
    """
    escaped = title.replace("~", "~0").replace("/", "~1").replace("@", "~2")
    return escaped if occurrence == 1 else f"{escaped}@{occurrence}"


def _segment_chain(nodes: List[NodeSpec], parent_index: int) -> List[str]:
    """Identity segments from the root down through ``parent_index``."""
    chain: List[str] = []
    cursor = parent_index
    while cursor != 0:
        spec = nodes[cursor]
        chain.append(_identity_segment(spec.title, spec.occurrence))
        cursor = spec.parent_index if spec.parent_index is not None else 0
    chain.reverse()
    return chain


def _assign_bodies(nodes: List[NodeSpec], lines: List[str]) -> None:
    """Compute each node's own body (excluding direct children's line ranges)."""
    for node in nodes:
        body_lines: List[str] = []
        cursor = node.start
        for child_index in sorted(node.children):
            child = nodes[child_index]
            body_lines.extend(lines[cursor - 1 : child.start - 1])
            cursor = child.end + 1
        body_lines.extend(lines[cursor - 1 : node.end])
        node.body_lines = body_lines  # type: ignore[attr-defined]


# --- Python -----------------------------------------------------------------


def parse_python(relpath: str, lines: List[str]) -> Tuple[List[NodeSpec], bool]:
    """AST-based module/class/function/async-function tree with real line ranges."""
    line_count = len(lines)
    module_node = NodeSpec(
        kind="module",
        title=relpath,
        start=1,
        end=max(line_count, 1),
        tree_path=relpath,
        occurrence=1,
        symbol_kind="module",
    )
    try:
        tree = ast.parse("\n".join(lines), filename=relpath)
    except SyntaxError:
        fallback = NodeSpec(
            kind="file",
            title=relpath,
            start=1,
            end=max(line_count, 1),
            tree_path=relpath,
            occurrence=1,
        )
        return [fallback], True

    nodes: List[NodeSpec] = [module_node]
    stack: List[int] = [0]
    occurrence_by_parent: Dict[Tuple[int, str], int] = {}

    class Collector(ast.NodeVisitor):
        def _collect(self, kind: str, node: ast.AST) -> None:
            name = getattr(node, "name", "")
            parent_index = stack[-1]
            key = (parent_index, name)
            occurrence = occurrence_by_parent.get(key, 0) + 1
            occurrence_by_parent[key] = occurrence
            segments = _segment_chain(nodes, parent_index)
            segments.append(_identity_segment(name, occurrence))
            tree_path = "{}#{}".format(relpath, "/".join(segments))
            spec = NodeSpec(
                kind=kind,
                title=name,
                start=int(node.lineno),
                end=int(node.end_lineno or node.lineno),
                tree_path=tree_path,
                occurrence=occurrence,
                parent_index=parent_index,
                symbol_kind=kind,
            )
            nodes[parent_index].children.append(len(nodes))
            nodes.append(spec)
            stack.append(len(nodes) - 1)
            self.generic_visit(node)
            stack.pop()

        def visit_ClassDef(self, node: ast.ClassDef) -> None:
            self._collect("class", node)

        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
            self._collect("function", node)

        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
            self._collect("async_function", node)

    Collector().visit(tree)
    return nodes, False


# --- Row materialization ----------------------------------------------------


def _depth_of(nodes: List[NodeSpec], index: int) -> int:
    depth = 0
    cursor = index
    while cursor != 0:
        spec = nodes[cursor]
        cursor = spec.parent_index if spec.parent_index is not None else 0
        depth += 1
    return depth


def _ordinal_of(nodes: List[NodeSpec], index: int) -> int:
    parent = nodes[index].parent_index
    if parent is None:
        return 0
    siblings = nodes[parent].children
    try:
        return siblings.index(index)
    except ValueError:
        return 0


def _materialize_document(parsed: ParsedDocument, document_id: int) -> List[Dict[str, Any]]:
    """Turn parsed nodes into node rows plus (node, body) FTS payloads."""
    _assign_bodies(parsed.nodes, parsed.lines)
    rows: List[Dict[str, Any]] = []
    for index, spec in enumerate(parsed.nodes):
        parent_id = None
        if spec.parent_index is not None:
            parent_spec = parsed.nodes[spec.parent_index]
            parent_id = node_id_for(parsed.relpath, parent_spec.tree_path, parent_spec.occurrence)
        body = "\n".join(getattr(spec, "body_lines", []))
        body_sha256 = hashlib.sha256(body.encode("utf-8")).hexdigest()
        rows.append(
            {
                "node_id": node_id_for(parsed.relpath, spec.tree_path, spec.occurrence),
                "document_id": document_id,
                "parent_id": parent_id,
                "depth": _depth_of(parsed.nodes, index),
                "ordinal": _ordinal_of(parsed.nodes, index),
                "title": spec.title,
                "kind": spec.kind,
                "start_line": spec.start,
                "end_line": spec.end,
                "body_sha256": body_sha256,
                "tree_path": spec.tree_path,
                "source_kind": parsed.kind,
                "symbol_kind": spec.symbol_kind,
                "_body": body,
            }
        )
    return rows


def _summary_of_skipped(skipped: List[SkippedFile], limit: int = 3) -> Dict[str, Any]:
    counts: Dict[str, int] = {}
    samples: Dict[str, List[str]] = {}
    for item in sorted(skipped, key=lambda value: value.relpath):
        counts[item.reason] = counts.get(item.reason, 0) + 1
        if len(samples.get(item.reason, [])) < limit:
            samples.setdefault(item.reason, []).append(item.relpath)
    return {"total": len(skipped), "by_reason": counts, "examples": samples}


def _collect_all(
    root: Path,
    syntax_profile: Optional[str] = None,
    parser_cache: Optional[Path] = None,
) -> Tuple[List[ParsedDocument], List[SkippedFile]]:
    return scan_workspace(root, load_contracts(), syntax_profile, parser_cache)


def _kind_counts(files: List[ParsedDocument]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for item in files:
        counts[item.kind] = counts.get(item.kind, 0) + 1
    return counts


# --- Plans ------------------------------------------------------------------


def _resolve_index_path(root: Path, index_path: Optional[Path]) -> Path:
    return Path(index_path) if index_path is not None else default_index_path(root)


def _prepare_default_index_write_path(root: Path, resolved: Path) -> None:
    """Keep the implicit index target inside the real root without link traversal."""
    root_absolute = Path(os.path.abspath(root))
    target_absolute = Path(os.path.abspath(resolved))
    try:
        relative = target_absolute.relative_to(root_absolute)
    except ValueError as exc:
        raise IndexError(f"default index path escapes workspace root: {resolved}") from exc

    cursor = root_absolute
    for part in relative.parts[:-1]:
        cursor /= part
        if path_is_link_like(cursor):
            raise IndexError(
                f"default index path crosses a symlink or junction: {cursor}"
            )
        if cursor.exists() and not cursor.is_dir():
            raise IndexError(f"default index parent is not a directory: {cursor}")
    if path_is_link_like(target_absolute):
        raise IndexError(
            f"default index file must not be a symlink or junction: {target_absolute}"
        )

    target_absolute.parent.mkdir(parents=True, exist_ok=True)
    root_real = root_absolute.resolve(strict=True)
    parent_real = target_absolute.parent.resolve(strict=True)
    try:
        parent_real.relative_to(root_real)
    except ValueError as exc:
        raise IndexError(
            f"default index parent resolves outside workspace root: {parent_real}"
        ) from exc


def build_plan(
    root: Path,
    index_path: Optional[Path] = None,
    syntax_profile: Optional[str] = None,
    parser_cache: Optional[Path] = None,
) -> Dict[str, Any]:
    """Read-only build plan: scan + parse, no writes, no index directory creation."""
    if not root.is_dir():
        raise IndexPathNotFound(f"workspace path is not a directory: {root}")
    require_capability()
    files, skipped = _collect_all(root, syntax_profile, parser_cache)
    resolved = _resolve_index_path(root, index_path)
    parse_failures = sum(1 for item in files if item.python_parse_failed)
    return {
        "status": "planned",
        "operation": "build",
        "applied": False,
        "schema_version": SCHEMA_VERSION,
        "index_path": str(resolved),
        "index_exists": resolved.is_file(),
        "syntax_profile": syntax_profile,
        "documents": {
            "scanned": len(files),
            "by_kind": _kind_counts(files),
            "bytes": sum(item.size_bytes for item in files),
            "lines": sum(item.line_count for item in files),
            "nodes": sum(len(item.nodes) for item in files),
            "python_parse_failures": parse_failures,
        },
        "skipped": _summary_of_skipped(skipped),
        "writes": "none (read-only plan; rerun with --apply to create or replace the index)",
    }


def build_apply(
    root: Path,
    index_path: Optional[Path] = None,
    syntax_profile: Optional[str] = None,
    parser_cache: Optional[Path] = None,
) -> Dict[str, Any]:
    """Create or replace the index via a temporary database and atomic replace."""
    if not root.is_dir():
        raise IndexPathNotFound(f"workspace path is not a directory: {root}")
    require_capability()
    files, skipped = _collect_all(root, syntax_profile, parser_cache)
    resolved = _resolve_index_path(root, index_path)
    if index_path is None:
        _prepare_default_index_write_path(root, resolved)
    else:
        resolved.parent.mkdir(parents=True, exist_ok=True)

    temporary: Optional[Path] = None
    connection: Optional[sqlite3.Connection] = None
    try:
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=".v1.sqlite3.tmp-", suffix=".sqlite3", dir=str(resolved.parent)
        )
        os.close(descriptor)
        temporary = Path(temporary_name)
        connection = sqlite3.connect(str(temporary), timeout=60.0)
        connection.row_factory = sqlite3.Row
        connection.isolation_level = None
        connection.execute("PRAGMA foreign_keys = ON")
        # The file is disposable until atomic replace, so rollback-journal
        # durability would only duplicate writes to a temporary artifact.
        connection.execute("PRAGMA journal_mode = OFF")
        connection.execute("PRAGMA synchronous = OFF")
        connection.execute("PRAGMA temp_store = MEMORY")
        create_schema(connection)
        connection.execute("BEGIN IMMEDIATE")
        document_ids: Dict[str, int] = {}
        for parsed in sorted(files, key=lambda item: item.relpath):
            document_id = insert_document(
                connection,
                {
                    "relative_path": parsed.relpath,
                    "kind": parsed.kind,
                    "sha256": parsed.sha256,
                    "line_count": parsed.line_count,
                    "size_bytes": parsed.size_bytes,
                },
            )
            document_ids[parsed.relpath] = document_id
        materialized: Dict[str, List[Dict[str, Any]]] = {}
        all_rows: List[Dict[str, Any]] = []
        for parsed in sorted(files, key=lambda item: item.relpath):
            document_id = document_ids[parsed.relpath]
            rows = _materialize_document(parsed, document_id)
            materialized[parsed.relpath] = rows
            all_rows.extend(rows)
        _insert_document_rows(connection, all_rows)
        # Link edges resolve after every document's nodes exist (two-pass).
        for parsed in sorted(files, key=lambda item: item.relpath):
            _insert_link_edges(connection, parsed, materialized[parsed.relpath], document_ids)
        ida_preserved = _preserve_ida_layer(resolved, connection)
        root_hash = compute_root_hash((item.relpath, item.sha256) for item in files)
        set_meta(connection, META_SCHEMA_VERSION, SCHEMA_VERSION)
        set_meta(connection, META_INDEX_REVISION, "1")
        set_meta(connection, META_ROOT_HASH, root_hash)
        set_meta(connection, META_BUILT_AT, str(int(time.time())))
        set_meta(connection, META_BUILT_BY, "build")
        set_meta(connection, "syntax_profile", syntax_profile or "")
        connection.execute("COMMIT")
        close(connection)
        connection = None
        if index_path is None:
            _prepare_default_index_write_path(root, resolved)
        atomically_replace(temporary, resolved)
        temporary = None
    except Exception:
        if connection is not None:
            try:
                connection.execute("ROLLBACK")
            except sqlite3.Error:
                pass
            close(connection)
        if temporary is not None:
            try:
                temporary.unlink()
            except OSError:
                pass
        raise

    return {
        "status": "applied",
        "operation": "build",
        "applied": True,
        "schema_version": SCHEMA_VERSION,
        "index_path": str(resolved),
        "syntax_profile": syntax_profile,
        "documents": {
            "indexed": len(files),
            "by_kind": _kind_counts(files),
            "nodes": sum(len(item.nodes) for item in files),
            "bytes": sum(item.size_bytes for item in files),
        },
        "skipped": _summary_of_skipped(skipped),
        "index_revision": 1,
        "root_hash": root_hash,
        "ida_preserved": ida_preserved,
        "writes": {"insert_documents": len(files)},
    }


def _preserve_ida_layer(
    source_path: Path, destination: sqlite3.Connection
) -> Dict[str, int]:
    """Carry explicit IDA documents across a full source-index replacement."""
    if not source_path.is_file():
        return {"documents": 0, "nodes": 0, "edges": 0}
    source = open_read_only(source_path)
    copied_documents = copied_nodes = copied_edges = 0
    try:
        documents = source.execute(
            "SELECT document_id, relative_path, kind, sha256, line_count, size_bytes "
            "FROM documents WHERE kind = 'ida' ORDER BY relative_path"
        ).fetchall()
        for document in documents:
            collision = destination.execute(
                "SELECT document_id FROM documents WHERE relative_path = ?",
                (document["relative_path"],),
            ).fetchone()
            if collision is not None:
                raise IndexError(
                    "full build cannot preserve IDA document because its relative path "
                    f"collides with a source document: {document['relative_path']}"
                )
            document_id = insert_document(destination, dict(document))
            old_nodes = source.execute(
                "SELECT node_id, document_id, parent_id, depth, ordinal, title, kind, "
                "start_line, end_line, body_sha256, tree_path, source_kind, symbol_kind "
                "FROM nodes WHERE document_id = ? ORDER BY depth, ordinal, node_id",
                (document["document_id"],),
            ).fetchall()
            node_ids = {str(row["node_id"]) for row in old_nodes}
            if not node_ids:
                raise IndexError(
                    f"IDA document has no nodes and cannot be preserved: {document['relative_path']}"
                )
            placeholders = ",".join("?" for _ in node_ids)
            node_collision = destination.execute(
                f"SELECT node_id FROM nodes WHERE node_id IN ({placeholders}) LIMIT 1",
                sorted(node_ids),
            ).fetchone()
            if node_collision is not None:
                raise IndexError(
                    f"full build cannot preserve IDA node id collision: {node_collision['node_id']}"
                )
            node_rows = [dict(row) for row in old_nodes]
            for row in node_rows:
                row["document_id"] = document_id
            insert_nodes(destination, node_rows)
            for row in node_rows:
                if row["parent_id"] is not None:
                    insert_edge(destination, row["node_id"], row["parent_id"], "parent")
            edge_rows = source.execute(
                "SELECT source_node, target_node, kind FROM edges "
                f"WHERE source_node IN ({placeholders}) AND target_node IN ({placeholders})",
                sorted(node_ids) + sorted(node_ids),
            ).fetchall()
            for edge in edge_rows:
                insert_edge(destination, edge["source_node"], edge["target_node"], edge["kind"])
            fts_rows = source.execute(
                "SELECT node_id, title, body AS _body FROM fts_terms "
                f"WHERE node_id IN ({placeholders}) ORDER BY node_id",
                sorted(node_ids),
            ).fetchall()
            if len(fts_rows) != len(node_rows):
                raise IndexError(
                    f"IDA document has incomplete FTS rows: {document['relative_path']}"
                )
            insert_fts_rows_bulk(destination, [dict(row) for row in fts_rows])
            for meta in source.execute(
                "SELECT key, value FROM index_meta WHERE key LIKE 'ida_%'"
            ).fetchall():
                set_meta(destination, meta["key"], meta["value"])
            copied_documents += 1
            copied_nodes += len(node_rows)
            copied_edges += len(edge_rows)
    finally:
        close(source)
    return {"documents": copied_documents, "nodes": copied_nodes, "edges": copied_edges}


def _insert_document_rows(connection: sqlite3.Connection, rows: List[Dict[str, Any]]) -> None:
    insert_nodes(connection, rows)
    connection.executemany(
        "INSERT INTO edges (source_node, target_node, kind) VALUES (?, ?, 'parent')",
        [
            (row["node_id"], row["parent_id"])
            for row in rows
            if row["parent_id"] is not None
        ],
    )
    insert_fts_rows_bulk(connection, rows)


def _stale_link_source_relpaths(
    connection: sqlite3.Connection, touched_relpaths: Sequence[str]
) -> List[str]:
    """Unchanged documents whose link edges point into changed/removed documents.

    Those edges are 'related' to the delta: they dangle after the target's old
    nodes are deleted (ON DELETE CASCADE) and must be re-derived from the
    unchanged document's current body.
    """
    if not touched_relpaths:
        return []
    placeholders = ",".join("?" for _ in touched_relpaths)
    rows = connection.execute(
        "SELECT DISTINCT sd.relative_path FROM edges e "
        "JOIN nodes target ON target.node_id = e.target_node "
        "JOIN documents td ON td.document_id = target.document_id "
        "JOIN nodes source ON source.node_id = e.source_node "
        "JOIN documents sd ON sd.document_id = source.document_id "
        f"WHERE e.kind = 'link' AND td.relative_path IN ({placeholders}) "
        "AND source.node_id NOT IN ("
        "  SELECT node_id FROM nodes JOIN documents doc ON doc.document_id = nodes.document_id "
        f"  WHERE doc.relative_path IN ({placeholders})"
        ")",
        list(touched_relpaths) + list(touched_relpaths),
    ).fetchall()
    return sorted({row["relative_path"] for row in rows})


def _rebuild_link_edges(
    connection: sqlite3.Connection,
    parsed_by_relpath: Dict[str, ParsedDocument],
    relpaths: Sequence[str],
    document_ids: Dict[str, int],
) -> int:
    """Delete and re-derive link edges for the given documents; returns edge count."""
    rebuilt = 0
    for relpath in relpaths:
        parsed = parsed_by_relpath.get(relpath)
        if parsed is None or relpath not in document_ids:
            continue
        source_rows = connection.execute(
            "SELECT node_id FROM nodes WHERE document_id = ?", (document_ids[relpath],)
        ).fetchall()
        source_ids = [row["node_id"] for row in source_rows]
        if not source_ids:
            continue
        placeholders = ",".join("?" for _ in source_ids)
        connection.execute(
            f"DELETE FROM edges WHERE kind = 'link' AND source_node IN ({placeholders})",
            source_ids,
        )
        rows = _materialize_document(parsed, document_ids[relpath])
        _insert_link_edges(connection, parsed, rows, document_ids)
        rebuilt += 1
    return rebuilt


def _insert_link_edges(
    connection: sqlite3.Connection,
    parsed: ParsedDocument,
    rows: List[Dict[str, Any]],
    document_ids: Dict[str, int],
) -> None:
    """Resolve relative Markdown links that stay inside the workspace root."""
    base_dir = Path(parsed.relpath).parent.as_posix()
    for row in rows:
        if row["kind"] not in {"heading", "preamble", "file", "module"}:
            continue
        for raw_target in _node_links(row["_body"]):
            target_path, _, anchor = raw_target.partition("#")
            target_path = target_path.strip()
            anchor = anchor.strip()
            if not target_path:
                continue
            if target_path.startswith(("http://", "https://", "mailto:", "ftp://")):
                continue
            candidate = _normalize_relpath(base_dir, target_path)
            if candidate is None or candidate not in document_ids:
                continue
            target_rows = _nodes_of_document(connection, document_ids[candidate])
            if not target_rows:
                continue
            target_node = _resolve_anchor(target_rows, anchor, candidate)
            if target_node is not None:
                insert_edge(connection, row["node_id"], target_node, "link")


def _normalize_relpath(base_dir: str, target: str) -> Optional[str]:
    """Join a link target under base_dir and reject any path escaping the root."""
    if target.startswith("/") or ":" in target.split("/")[0]:
        return None
    parts = (base_dir.split("/") if base_dir else []) + target.split("/")
    out: List[str] = []
    for part in parts:
        if part in {"", "."}:
            continue
        if part == "..":
            if not out:
                return None  # escapes above the root
            out.pop()
        else:
            out.append(part)
    if not out:
        return None
    return "/".join(out)


def _nodes_of_document(connection: sqlite3.Connection, document_id: int) -> List[Dict[str, Any]]:
    rows = connection.execute(
        "SELECT node_id, title, kind FROM nodes WHERE document_id = ? "
        "ORDER BY start_line, depth, ordinal, node_id",
        (document_id,),
    ).fetchall()
    return [dict(row) for row in rows]


def _resolve_anchor(
    target_rows: List[Dict[str, Any]], anchor: str, relpath: str
) -> Optional[str]:
    if not anchor:
        return target_rows[0]["node_id"] if target_rows else None
    for row in target_rows:
        if row["kind"] in {"heading", "preamble"} and row["title"] == anchor:
            return row["node_id"]
    # Unknown anchor falls back to the file/module node (browser semantics).
    for row in target_rows:
        if row["kind"] in {"file", "module"} and row["title"] == relpath:
            return row["node_id"]
    return None


def _link_sources_for_added_documents(
    files: Sequence[ParsedDocument],
    added_relpaths: Sequence[str],
    skip_relpaths: Sequence[str],
) -> List[str]:
    """Find existing sources whose previously-unresolved link target was added."""
    added = set(added_relpaths)
    skipped = set(skip_relpaths) | added
    if not added:
        return []
    sources: List[str] = []
    for parsed in files:
        if parsed.relpath in skipped or parsed.kind != "markdown":
            continue
        base_dir = Path(parsed.relpath).parent.as_posix()
        for raw_target in _node_links("\n".join(parsed.lines)):
            target_path, _, _ = raw_target.partition("#")
            candidate = _normalize_relpath(base_dir, target_path.strip())
            if candidate in added:
                sources.append(parsed.relpath)
                break
    return sorted(sources)


def _resolve_update_syntax(
    meta: Dict[str, str],
    syntax_profile: Optional[str],
    parser_cache: Optional[Path],
) -> Optional[str]:
    stored = meta.get("syntax_profile", "")
    requested = syntax_profile or ""
    if stored != requested:
        raise ParserUnavailable(
            "syntax profile does not match the existing index; "
            f"index={stored or 'none'}, requested={requested or 'none'}"
        )
    if stored:
        _require_parser_cache(parser_cache)
        return stored
    return None


def update_plan(
    root: Path,
    index_path: Optional[Path] = None,
    syntax_profile: Optional[str] = None,
    parser_cache: Optional[Path] = None,
) -> Dict[str, Any]:
    """Read-only incremental delta plan against the existing index."""
    if not root.is_dir():
        raise IndexPathNotFound(f"workspace path is not a directory: {root}")
    require_capability()
    resolved = _resolve_index_path(root, index_path)
    if not resolved.is_file():
        raise IndexNotFound(f"index file does not exist: {resolved}; run 'index build --apply' first")
    connection = open_read_only(resolved)
    try:
        current = read_all_documents(connection)
        source_current = {
            path: document for path, document in current.items() if document["kind"] != "ida"
        }
        meta = {
            row["key"]: row["value"]
            for row in connection.execute("SELECT key, value FROM index_meta")
        }
        effective_profile = _resolve_update_syntax(meta, syntax_profile, parser_cache)
        files, skipped = _collect_all(root, effective_profile, parser_cache)
        touched = sorted(set(source_current) - {item.relpath for item in files}) + [
            item.relpath
            for item in files
            if item.relpath in source_current and source_current[item.relpath]["sha256"] != item.sha256
        ]
        removed_node_count = _count_nodes_for_documents(connection, touched)
        added_relpaths = [item.relpath for item in files if item.relpath not in source_current]
        stale_sources = sorted(
            set(_stale_link_source_relpaths(connection, touched))
            | set(_link_sources_for_added_documents(files, added_relpaths, touched))
        )
    finally:
        close(connection)
    return _delta_plan(
        files, skipped, source_current, meta, resolved, removed_node_count, stale_sources, applied=False
    )


def update_apply(
    root: Path,
    index_path: Optional[Path] = None,
    syntax_profile: Optional[str] = None,
    parser_cache: Optional[Path] = None,
) -> Dict[str, Any]:
    """Transactional incremental update: replace only added/changed/removed documents."""
    if not root.is_dir():
        raise IndexPathNotFound(f"workspace path is not a directory: {root}")
    require_capability()
    resolved = _resolve_index_path(root, index_path)
    if not resolved.is_file():
        raise IndexNotFound(f"index file does not exist: {resolved}; run 'index build --apply' first")
    if index_path is None:
        _prepare_default_index_write_path(root, resolved)
    connection = open_read_write(resolved)
    connection.isolation_level = None
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        connection.execute("BEGIN IMMEDIATE")
        current = read_all_documents(connection)
        meta = {
            row["key"]: row["value"]
            for row in connection.execute("SELECT key, value FROM index_meta")
        }
        effective_profile = _resolve_update_syntax(meta, syntax_profile, parser_cache)
        files, skipped = _collect_all(root, effective_profile, parser_cache)
        source_current = {
            path: document for path, document in current.items() if document["kind"] != "ida"
        }
        added = [item for item in files if item.relpath not in source_current]
        changed = [
            item
            for item in files
            if item.relpath in source_current and source_current[item.relpath]["sha256"] != item.sha256
        ]
        removed = sorted(set(source_current) - {item.relpath for item in files})
        touched = removed + [item.relpath for item in changed]
        removed_node_count = _count_nodes_for_documents(connection, touched)
        stale_sources = sorted(
            set(_stale_link_source_relpaths(connection, touched))
            | set(
                _link_sources_for_added_documents(
                    files,
                    [item.relpath for item in added],
                    touched,
                )
            )
        )
        for relpath in removed:
            delete_document_cascade(connection, source_current[relpath]["document_id"])
        document_ids = {
            relpath: current[relpath]["document_id"]
            for relpath in current
            if relpath not in removed
        }
        parsed_by_relpath = {item.relpath: item for item in files}
        for item in added + changed:
            if item.relpath in source_current:
                delete_document_cascade(connection, source_current[item.relpath]["document_id"])
            document_id = insert_document(
                connection,
                {
                    "relative_path": item.relpath,
                    "kind": item.kind,
                    "sha256": item.sha256,
                    "line_count": item.line_count,
                    "size_bytes": item.size_bytes,
                },
            )
            document_ids[item.relpath] = document_id
            rows = _materialize_document(item, document_id)
            _insert_document_rows(connection, rows)
        # Link edges resolve after every touched document's nodes exist (two-pass).
        for item in added + changed:
            document_id = document_ids[item.relpath]
            rows = _materialize_document(item, document_id)
            _insert_link_edges(connection, item, rows, document_ids)
        rebuilt = _rebuild_link_edges(
            connection, parsed_by_relpath, stale_sources, document_ids
        )
        if added or changed or removed:
            next_revision = str(int(meta.get(META_INDEX_REVISION, "0") or 0) + 1)
            root_hash = compute_root_hash((item.relpath, item.sha256) for item in files)
            set_meta(connection, META_INDEX_REVISION, next_revision)
            set_meta(connection, META_ROOT_HASH, root_hash)
            set_meta(connection, META_BUILT_AT, str(int(time.time())))
            set_meta(connection, META_BUILT_BY, "update")
        connection.execute("COMMIT")
    except Exception:
        try:
            connection.execute("ROLLBACK")
        except sqlite3.Error:
            pass
        close(connection)
        raise
    close(connection)

    result = _delta_plan(
        files, skipped, source_current, meta, resolved, removed_node_count, stale_sources, applied=True
    )
    result["status"] = "applied"
    result["applied"] = True
    if added or changed or removed:
        result["index_revision"] = str(int(meta.get(META_INDEX_REVISION, "0") or 0) + 1)
    return result


def _count_nodes_for_documents(connection: sqlite3.Connection, relpaths: List[str]) -> int:
    if not relpaths:
        return 0
    placeholders = ",".join("?" for _ in relpaths)
    row = connection.execute(
        "SELECT COUNT(*) AS n FROM nodes "
        "JOIN documents d ON d.document_id = nodes.document_id "
        f"WHERE d.relative_path IN ({placeholders})",
        relpaths,
    ).fetchone()
    return int(row["n"]) if row is not None else 0


def _delta_plan(
    files: List[ParsedDocument],
    skipped: List[SkippedFile],
    current: Dict[str, Dict[str, Any]],
    meta: Dict[str, str],
    resolved: Path,
    removed_node_count: int,
    stale_sources: List[str],
    *,
    applied: bool,
) -> Dict[str, Any]:
    added = [item for item in files if item.relpath not in current]
    changed = [
        item
        for item in files
        if item.relpath in current and current[item.relpath]["sha256"] != item.sha256
    ]
    removed = sorted(set(current) - {item.relpath for item in files})
    unchanged = [
        item
        for item in files
        if item.relpath in current and current[item.relpath]["sha256"] == item.sha256
    ]
    root_hash = compute_root_hash((item.relpath, item.sha256) for item in files)
    return {
        "status": "planned",
        "operation": "update",
        "applied": applied,
        "schema_version": SCHEMA_VERSION,
        "index_path": str(resolved),
        "index_revision": meta.get(META_INDEX_REVISION, "0"),
        "root_hash_after": root_hash,
        "documents": {
            "scanned": len(files),
            "added": len(added),
            "changed": len(changed),
            "removed": len(removed),
            "unchanged": len(unchanged),
            "added_paths": [item.relpath for item in added],
            "changed_paths": [item.relpath for item in changed],
            "removed_paths": removed,
        },
        "nodes": {
            "added": sum(len(item.nodes) for item in added + changed),
            "removed": removed_node_count,
        },
        "edges": {
            "link_rebuild_sources": stale_sources,
            "link_rebuild_count": len(stale_sources),
        },
        "skipped": _summary_of_skipped(skipped),
        "writes": (
            "none (read-only plan; rerun with --apply to apply the delta)"
            if not applied
            else f"updated {len(added) + len(changed)} and removed {len(removed)} document(s)"
        ),
    }
