"""Behavior and deterministic resource regressions for issue #57.

Synthetic SQLite and parser-provider inputs exercise production code. No test
uses elapsed time as an assertion or claims to run an actual IDA/parser.
"""

from __future__ import annotations

import io
import itertools
import json
import re
import sqlite3
from contextlib import closing
from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace

import pytest

from reverse_skill import ida_ingest, index_api, index_build as build, index_store as store
from reverse_skill import retrieval


def populate(count=2000, documents=100):
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    store.create_schema(connection)
    store.set_meta(connection, "schema_version", "1")
    rows = []
    for document in range(documents):
        document_id = store.insert_document(connection, {
            "relative_path": f"doc-{document}.md", "kind": "markdown",
            "sha256": "0" * 64, "line_count": count, "size_bytes": count,
        })
        start = document * (count // documents)
        for offset in range(count // documents):
            number = start + offset + 1
            rows.append({
                "node_id": f"{number:016x}", "document_id": document_id,
                "parent_id": None if offset == 0 else f"{start + 1:016x}",
                "depth": 0 if offset == 0 else 1, "ordinal": offset,
                "title": f"Title {number}", "kind": "file" if offset == 0 else "heading",
                "start_line": number, "end_line": number, "body_sha256": "0" * 64,
                "tree_path": f"doc-{document}.md#Title-{number}",
                "source_kind": "markdown", "symbol_kind": None, "_body": "body words",
            })
    store.insert_nodes(connection, rows)
    store.insert_fts_rows_bulk(connection, rows)
    connection.commit()
    return connection


def snapshot(connection):
    return {table: [tuple(row) for row in connection.execute(f"SELECT * FROM {table} ORDER BY 1")]
            for table in ("documents", "nodes", "edges", "fts_terms", "fts_trigram")}


def vm_steps(connection, call):
    ticks = 0

    def tick():
        nonlocal ticks
        ticks += 1
        return 0

    connection.set_progress_handler(tick, 100)
    try:
        result = call()
    finally:
        connection.set_progress_handler(None, 0)
    return result, ticks * 100


def test_batch_deletion_keeps_both_fts_projections_and_rolls_back():
    connection = populate()
    try:
        before = snapshot(connection)
        connection.execute("SAVEPOINT repeated")
        _, repeated_steps = vm_steps(connection, lambda: [
            store.delete_document_cascade(connection, document) for document in range(91, 101)
        ])
        expected = snapshot(connection)
        connection.execute("ROLLBACK TO repeated")
        connection.execute("RELEASE repeated")
        connection.execute("SAVEPOINT batch")
        _, batch_steps = vm_steps(connection, lambda: store.delete_documents_cascade(
            connection, list(range(91, 101)) + [100, 99999]
        ))
        assert snapshot(connection) == expected
        assert batch_steps < repeated_steps // 2
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
        connection.execute("ROLLBACK TO batch")
        connection.execute("RELEASE batch")
        assert snapshot(connection) == before
        store.delete_documents_cascade(connection, [])
        assert snapshot(connection) == before
    finally:
        connection.close()


def test_title_or_path_uses_both_indexes_and_keeps_exact_order():
    connection = populate()
    try:
        query = "doc-99.md#Title-2000"
        sql = "SELECT node_id FROM nodes WHERE title=? OR tree_path=? ORDER BY node_id LIMIT ?"
        plans = [row["detail"] for row in connection.execute("EXPLAIN QUERY PLAN " + sql, (query, query, 20))]
        assert any("nodes_title" in plan for plan in plans)
        assert any("nodes_tree" in plan for plan in plans)
        assert retrieval._exact_structured_stage(connection, query, 20) == [("00000000000007d0", 1.0)]
        connection.execute("UPDATE nodes SET title='same' WHERE node_id IN ('0000000000000002', '0000000000000003')")
        connection.execute("UPDATE nodes SET tree_path='same' WHERE node_id='0000000000000001'")
        assert retrieval._exact_structured_stage(connection, "same", 2) == [
            ("0000000000000001", 1.0), ("0000000000000002", 2.0)
        ]
    finally:
        connection.close()


class CountingCursor:
    def __init__(self, cursor, owner):
        self.cursor, self.owner = cursor, owner

    def __getattr__(self, name):
        return getattr(self.cursor, name)

    def __iter__(self):
        return iter(self.cursor)

    def fetchall(self):
        rows = self.cursor.fetchall()
        if self.cursor.description and len(self.cursor.description) >= 13:
            self.owner.wide_rows += len(rows)
        return rows


class CountingConnection:
    def __init__(self, connection):
        self.connection = connection
        self.wide_rows = 0

    def __getattr__(self, name):
        return getattr(self.connection, name)

    def execute(self, *args):
        return CountingCursor(self.connection.execute(*args), self)


@pytest.mark.parametrize("count", [1, 500, 501, 502, 2000])
def test_tree_counts_exactly_and_only_materializes_returned_descendants(tmp_path, monkeypatch, count):
    connection = populate(count, documents=1)
    root = "0000000000000001"
    expected = store.read_subtree(connection, root)[1:]
    counted = CountingConnection(connection)
    monkeypatch.setattr(index_api, "open_read_only", lambda path: counted)
    result = index_api.index_get_tree(tmp_path, root)
    assert result["descendant_count"] == count - 1
    assert result["descendants_truncated"] == (count - 1 > 500)
    assert result["descendants"] == [index_api._node_payload(row) for row in expected[:500]]
    assert counted.wide_rows == min(count - 1, 500)


class ExportSource:
    def __init__(self, data):
        self.data = data
        self.read_sizes = []
        self.closed = False

    def is_file(self):
        return True

    def read_bytes(self):
        return self.data

    def open(self, mode):
        assert mode == "rb"
        owner = self

        class Reader(io.BytesIO):
            def read(self, size=-1):
                owner.read_sizes.append(size)
                return super().read(size)

            def close(self):
                owner.closed = True
                super().close()

        return Reader(self.data)


@pytest.mark.parametrize("extra", [0, 1, 40])
def test_ida_loader_bounds_read_and_preserves_size_boundary(monkeypatch, extra):
    data = json.dumps({"schema_version": 1, "module": "sample", "functions": []}).encode()
    monkeypatch.setattr(ida_ingest, "MAX_EXPORT_BYTES", len(data))
    source = ExportSource(data + b" " * extra)
    if extra:
        with pytest.raises(ida_ingest.IdaExportInvalid, match="exceeds"):
            ida_ingest.load_export(source)
    else:
        assert ida_ingest.load_export(source).module == "sample"
    assert source.read_sizes == [len(data) + 1]
    assert source.closed


class CountedChildren(list):
    comparisons = 0
    visits = 0

    def index(self, value):
        position = super().index(value)
        # Child indices are unique: the result gives the exact comparisons.
        type(self).comparisons += position + 1
        return position

    def __iter__(self):
        for value in super().__iter__():
            type(self).visits += 1
            yield value


def test_materialization_enumerates_siblings_once_and_preserves_complete_rows(monkeypatch):
    data = ("preamble\n# Same\n## Nested\n# Same\n" + "\n".join(f"# H{i}" for i in range(800))).encode()
    parsed = build._parse_file("flat.md", data, len(data))
    expected = build._materialize_document(parsed, 7)
    for spec in parsed.nodes:
        spec.children = CountedChildren(spec.children)
    CountedChildren.comparisons = CountedChildren.visits = 0
    actual = build._materialize_document(parsed, 7)
    assert actual == expected
    assert CountedChildren.comparisons == 0
    # Body assignment also visits each child once; ordinal work adds one pass.
    assert CountedChildren.visits == 2 * (len(parsed.nodes) - 1)
    assert [row["ordinal"] for row in actual[:5]] == [0, 0, 1, 0, 2]


class CountedTitle(str):
    comparisons = 0

    def __eq__(self, other):
        type(self).comparisons += 1
        return super().__eq__(other)

    __hash__ = str.__hash__


def test_syntax_occurrences_are_parent_local_and_linear(tmp_path, monkeypatch):
    def symbol(name, children=()):
        return SimpleNamespace(name=name, kind="function", children=children,
                               span=SimpleNamespace(start_line=0, end_line=0))

    symbols = [symbol(CountedTitle(f"f{i}")) for i in range(800)]
    symbols += [symbol("Same", [symbol("dup"), symbol("dup")]),
                symbol("Same", [symbol("dup")])]
    pack = SimpleNamespace(ProcessConfig=lambda **kwargs: SimpleNamespace(**kwargs),
                           process=lambda *args: SimpleNamespace(structure=symbols))
    monkeypatch.setattr(build, "_require_parser_cache", lambda path: path)
    monkeypatch.setattr(build, "_language_pack", lambda *args: (pack, {}))
    original_spec = build.NodeSpec

    def counted_spec(**kwargs):
        kwargs["title"] = CountedTitle(kwargs["title"])
        return original_spec(**kwargs)

    monkeypatch.setattr(build, "NodeSpec", counted_spec)
    CountedTitle.comparisons = 0
    nodes = build.parse_tree_sitter("a.c", ["synthetic"], "c", tmp_path)
    assert CountedTitle.comparisons < 1600
    assert [(node.tree_path, node.occurrence) for node in nodes[-5:]] == [
        ("a.c#Same", 1), ("a.c#Same/dup", 1), ("a.c#Same/dup@2", 2),
        ("a.c#Same@2", 2), ("a.c#Same@2/dup", 1),
    ]
    repeated = build.parse_tree_sitter("a.c", ["changed"], "c", tmp_path)
    assert [asdict(node) for node in repeated] == [asdict(node) for node in nodes]


def test_link_cache_is_shared_across_sources_and_expires_per_update(tmp_path, monkeypatch):
    (tmp_path / "target.md").write_text("# Same\n# Same\n# Other\n", encoding="utf-8")
    for name in ("a.md", "b.md"):
        (tmp_path / name).write_text("# Source\n" + "[x](target.md#Same)\n" * 100 +
                                    "[empty](target.md) [missing](target.md#unknown) [local](#Same)\n",
                                    encoding="utf-8")
    original = build._nodes_of_document
    reads = []

    def counted(connection, document_id):
        rows = original(connection, document_id)
        reads.append((document_id, len(rows)))
        return rows

    monkeypatch.setattr(build, "_nodes_of_document", counted)
    build.build_apply(tmp_path)
    assert len(reads) == 1
    path = store.default_index_path(tmp_path)
    connection = store.open_read_only(path)
    try:
        before = [tuple(row) for row in connection.execute("SELECT * FROM edges WHERE kind='link' ORDER BY 1,2")]
        target_rows = original(connection, store.document_id_for(connection, "target.md"))
        first_same = next(row["node_id"] for row in target_rows if row["title"] == "Same")
        assert len(before) == 4
        assert sum(edge[1] == first_same for edge in before) == 2
    finally:
        connection.close()
    reads.clear()
    (tmp_path / "target.md").write_text("# Other\n", encoding="utf-8")
    build.update_apply(tmp_path)
    assert len(reads) == 1
    connection = store.open_read_only(path)
    try:
        after = [tuple(row) for row in connection.execute("SELECT * FROM edges WHERE kind='link'")]
        assert len(after) == 2
        assert all(edge[1] != first_same for edge in after)
    finally:
        connection.close()


def test_exact_stage_keeps_node_id_priority_duplicate_ranks_and_top_k():
    connection = populate(100, documents=1)
    try:
        query = "0000000000000032"
        connection.execute("UPDATE nodes SET title=? WHERE node_id IN ('0000000000000001', ?, '0000000000000064')", (query, query))
        assert retrieval._exact_structured_stage(connection, query, 10) == [
            (query, 0.0), ("0000000000000001", 0.0), ("0000000000000064", 2.0)
        ]
        assert retrieval._exact_structured_stage(connection, query, 1) == [(query, 0.0)]
    finally:
        connection.close()


class CountedId(str):
    hashes = 0

    def __hash__(self):
        type(self).hashes += 1
        return super().__hash__()


class CountedIdsConnection:
    def __init__(self, connection):
        self.connection = connection

    def execute(self, *args):
        cursor = self.connection.execute(*args)
        return SimpleNamespace(fetchall=lambda: [
            {"node_id": CountedId(row["node_id"])} for row in cursor.fetchall()
        ])


def test_exact_stage_tracks_seen_ids_with_linear_hash_work():
    with closing(populate(800, documents=1)) as connection:
        connection.execute("UPDATE nodes SET title='X'")
        CountedId.hashes = 0
        hits = retrieval._exact_structured_stage(CountedIdsConnection(connection), "X", 800)
        assert len(hits) == 800
        assert CountedId.hashes <= 2 * len(hits)


class CountedText(str):
    scanned = 0

    def find(self, needle, start=0, end=None):
        result = super().find(needle, start, len(self) if end is None else end)
        type(self).scanned += (len(self) if result < 0 else result + len(needle)) - start
        return result


def test_markdown_lexical_links_match_legacy_even_on_malformed_input():
    legacy = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
    samples = ["[a[b](x)", "[a]( )", "[a]() [b](x)", "[a](b[c](d)",
               "[a\n](target#中文)", "[a]([b](x))", "[a]x[b](foo)", "\\[a](x)"]
    samples += ("".join(chars) for length in range(7) for chars in itertools.product("[]()x", repeat=length))
    for text in samples:
        assert build._node_links(text) == [match.group(1).strip() for match in legacy.finditer(text)]


@pytest.mark.parametrize("text", ["[" * 32000, "[x]x" * 8000, "[x](" + "[" * 32000],
                         ids=["unclosed-label", "invalid-target", "unclosed-target"])
def test_malformed_markdown_consumes_delimiter_spans_once(text):
    CountedText.scanned = 0
    assert build._node_links(CountedText(text)) == []
    assert 0 < CountedText.scanned <= 3 * len(text)


def test_legacy_schema_is_read_only_until_apply_and_index_creation_rolls_back(tmp_path, monkeypatch):
    (tmp_path / "a.md").write_text("# A\n", encoding="utf-8")
    build.build_apply(tmp_path)
    path = store.default_index_path(tmp_path)
    with closing(sqlite3.connect(path)) as connection, connection:
        connection.execute("DROP INDEX nodes_title")
    before = path.read_bytes()
    build.update_plan(tmp_path)
    index_api.index_search(tmp_path, "A", "tree")
    assert path.read_bytes() == before
    (tmp_path / "a.md").write_text("# Changed\n", encoding="utf-8")
    original = build._insert_document_rows

    def fail(*args):
        raise RuntimeError("injected update failure")

    monkeypatch.setattr(build, "_insert_document_rows", fail)
    with pytest.raises(RuntimeError, match="injected"):
        build.update_apply(tmp_path)
    assert path.read_bytes() == before
    monkeypatch.setattr(build, "_insert_document_rows", original)
    build.update_apply(tmp_path)
    with closing(sqlite3.connect(path)) as connection, connection:
        assert connection.execute("SELECT name FROM sqlite_master WHERE name='nodes_title'").fetchone()
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []


def write_export(path, module):
    path.write_text(json.dumps({
        "schema_version": 1, "module": module, "functions": [
            {"address": "0x1000", "name": "entry", "pseudocode": "return helper();",
             "xrefs_to": ["0x2000"]},
            {"address": "0x2000", "name": "helper", "pseudocode": "return 7;", "xrefs_to": []},
        ],
    }), encoding="utf-8")


def ida_snapshot(connection):
    ids = [row[0] for row in connection.execute("SELECT node_id FROM nodes WHERE source_kind='ida'")]
    placeholders = ",".join("?" for _ in ids)
    return {
        "nodes": [tuple(row) for row in connection.execute(
            "SELECT node_id,parent_id,depth,ordinal,title,kind,start_line,end_line,body_sha256,tree_path,source_kind,symbol_kind "
            "FROM nodes WHERE source_kind='ida' ORDER BY node_id")],
        "edges": [tuple(row) for row in connection.execute(
            f"SELECT * FROM edges WHERE source_node IN ({placeholders}) ORDER BY 1,2,3", ids)],
        "bodies": [tuple(row) for row in connection.execute(
            f"SELECT node_id,title,body FROM fts_terms WHERE node_id IN ({placeholders}) ORDER BY node_id", ids)],
        "meta": [tuple(row) for row in connection.execute("SELECT * FROM index_meta WHERE key LIKE 'ida_%' ORDER BY key")],
    }


@pytest.mark.parametrize("corrupt", [False, True], ids=["complete", "missing-body"])
def test_ida_preservation_reads_fts_once_and_blocks_incomplete_replacement(tmp_path, monkeypatch, corrupt):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "source.md").write_text("# Source\n", encoding="utf-8")
    build.build_apply(workspace)
    export = tmp_path / "export.json"
    for module in ("one", "two", "three"):
        write_export(export, module)
        ida_ingest.import_export(workspace, export, apply=True)
    path = store.default_index_path(workspace)
    with closing(sqlite3.connect(path)) as connection, connection:
        expected = ida_snapshot(connection)
        if corrupt:
            connection.execute("DELETE FROM fts_terms WHERE node_id=?", (expected["bodies"][0][0],))
    before = path.read_bytes()
    statements = []
    original_open = build.open_read_only

    def traced(path):
        connection = original_open(path)
        connection.set_trace_callback(statements.append)
        return connection

    monkeypatch.setattr(build, "open_read_only", traced)
    if corrupt:
        with pytest.raises(store.IndexError, match="incomplete FTS"):
            build.build_apply(workspace)
        assert path.read_bytes() == before
    else:
        result = build.build_apply(workspace)
        assert result["ida_preserved"] == {"documents": 3, "nodes": 9, "edges": 9}
        with closing(sqlite3.connect(path)) as connection, connection:
            assert ida_snapshot(connection) == expected
            assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
    assert sum("FROM fts_terms" in statement for statement in statements) == 1


def test_many_removed_paths_use_linear_membership_and_keep_ida(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    for number in range(160):
        (workspace / f"{number:03}.md").write_text("# Same\n", encoding="utf-8")
    build.build_apply(workspace)
    export = tmp_path / "export.json"
    write_export(export, "sample")
    ida_ingest.import_export(workspace, export, apply=True)
    for number in range(80):
        (workspace / f"{number:03}.md").unlink()
    (workspace / "080.md").write_text("# Changed\n", encoding="utf-8")
    original = build.read_all_documents

    def counted(connection):
        return {CountedTitle(path): value for path, value in original(connection).items()}

    monkeypatch.setattr(build, "read_all_documents", counted)
    CountedTitle.comparisons = 0
    result = build.update_apply(workspace)
    assert CountedTitle.comparisons < 2000
    assert result["documents"]["removed_paths"] == [f"{number:03}.md" for number in range(80)]
    connection = store.open_read_only(store.default_index_path(workspace))
    try:
        paths = [row[0] for row in connection.execute("SELECT relative_path FROM documents ORDER BY relative_path")]
        assert paths == [f"{number:03}.md" for number in range(80, 160)] + ["__ida__/sample"]
        assert len(ida_snapshot(connection)["nodes"]) == 3
        for table in ("fts_terms", "fts_trigram"):
            assert connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 163
    finally:
        connection.close()


def test_ida_plan_leaves_legacy_index_untouched_until_explicit_apply(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "a.md").write_text("# A\n", encoding="utf-8")
    build.build_apply(workspace)
    path = store.default_index_path(workspace)
    with closing(sqlite3.connect(path)) as connection, connection:
        connection.execute("DROP INDEX nodes_title")
    before = path.read_bytes()
    export = tmp_path / "export.json"
    write_export(export, "sample")
    ida_ingest.import_export(workspace, export, apply=False)
    assert path.read_bytes() == before
    ida_ingest.import_export(workspace, export, apply=True)
    with closing(sqlite3.connect(path)) as connection, connection:
        assert connection.execute("SELECT name FROM sqlite_master WHERE name='nodes_title'").fetchone()


def test_tree_count_and_rows_share_snapshot_during_concurrent_update(tmp_path, monkeypatch):
    source = tmp_path / "a.md"
    source.write_text("# A\n# B\n", encoding="utf-8")
    build.build_apply(tmp_path)
    path = store.default_index_path(tmp_path)
    with closing(sqlite3.connect(path)) as connection:
        connection.execute("PRAGMA journal_mode=WAL")
    connection = store.open_read_only(path)
    try:
        root = connection.execute("SELECT node_id FROM nodes WHERE parent_id IS NULL").fetchone()[0]
        expected = store.read_subtree(connection, root)[1:]
    finally:
        connection.close()
    original = index_api.count_descendants

    def count_then_update(connection, node_id):
        count = original(connection, node_id)
        source.write_text("# A\n", encoding="utf-8")
        build.update_apply(tmp_path)
        return count

    monkeypatch.setattr(index_api, "count_descendants", count_then_update)
    result = index_api.index_get_tree(tmp_path, root)
    assert result["descendant_count"] == 2
    assert result["descendants"] == [index_api._node_payload(row) for row in expected]


def _index_columns(connection, name):
    return [row["name"] for row in connection.execute(f"PRAGMA index_info('{name}')").fetchall()]


def test_fresh_schema_widens_nodes_parent_for_children_reads():
    """read_children filters on parent_id and sorts by ordinal; one index must serve both."""
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    store.create_schema(connection)
    assert _index_columns(connection, "nodes_parent") == ["parent_id", "ordinal"]


def test_ensure_query_indexes_upgrades_a_pre_widening_nodes_parent():
    """CREATE INDEX IF NOT EXISTS matches on name, so an existing narrow index must be rebuilt."""
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    store.create_schema(connection)
    connection.execute("DROP INDEX nodes_parent")
    connection.execute("CREATE INDEX nodes_parent ON nodes(parent_id)")
    assert _index_columns(connection, "nodes_parent") == ["parent_id"]

    store.ensure_query_indexes(connection)
    assert _index_columns(connection, "nodes_parent") == ["parent_id", "ordinal"]

    # Idempotent, and never leaves a duplicate index behind.
    store.ensure_query_indexes(connection)
    assert _index_columns(connection, "nodes_parent") == ["parent_id", "ordinal"]
    count = connection.execute(
        "SELECT COUNT(*) AS c FROM sqlite_master WHERE type = 'index' AND name = 'nodes_parent'"
    ).fetchone()["c"]
    assert count == 1


def test_nodes_parent_serves_the_children_sort_without_a_temp_btree():
    """The widening only pays off if the planner actually uses it for the ORDER BY."""
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    store.create_schema(connection)
    plan = " ".join(
        row["detail"]
        for row in connection.execute(
            "EXPLAIN QUERY PLAN SELECT n.node_id FROM nodes n "
            "WHERE n.parent_id = ? ORDER BY n.ordinal",
            ("0000000000000001",),
        ).fetchall()
    )
    assert "nodes_parent" in plan
    assert "TEMP B-TREE" not in plan.upper()
