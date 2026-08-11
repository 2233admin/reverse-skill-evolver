"""Unit tests for the deterministic index core (store + build + retrieval)."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

import pytest

from reverse_skill import index_api, index_build
from reverse_skill.index_build import (
    _normalize_relpath,
    parse_markdown,
    parse_python,
)
from reverse_skill.index_store import (
    NODE_ID_RE,
    SCHEMA_VERSION,
    IndexCapabilityUnavailable,
    IndexCorrupt,
    IndexError as IndexStoreError,
    InvalidNodeId,
    compute_root_hash,
    load_contracts,
    node_id_for,
    open_read_only,
    probe_capabilities,
    require_capability,
)

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "data" / "index-fixtures"


def _build(tmp_path: Path) -> Path:
    index_build.build_apply(tmp_path)
    return tmp_path / ".reverse-skill" / "index" / "v1.sqlite3"


def _query(sql: str, index_path: Path, params=()):
    con = sqlite3.connect(str(index_path))
    try:
        return con.execute(sql, params).fetchall()
    finally:
        con.close()


# --- Contract coherence -----------------------------------------------------


def test_contract_matches_implementation() -> None:
    contracts = load_contracts()
    assert str(contracts["schema_version"]) == SCHEMA_VERSION
    assert contracts["retrieval_modes"] == ["bm25", "tree", "hybrid"]
    assert contracts["index_file"]["default_relative"] == ".reverse-skill/index/v1.sqlite3"
    assert contracts["node_id"]["regex"] == NODE_ID_RE.pattern
    assert len(contracts["evidence_fields"]) >= 12
    assert "credential_file_patterns" in contracts["default_exclusions"]


def test_node_id_derivation_follows_documented_formula() -> None:
    relative_path = "zh/guide.md"
    tree_path = "zh/guide.md#使用指南/安装"
    occurrence = 2
    expected = hashlib.sha256(
        "zh/guide.md\x00zh/guide.md#使用指南/安装\x002".encode("utf-8")
    ).hexdigest()[:16]
    assert node_id_for(relative_path, tree_path, occurrence) == expected
    assert NODE_ID_RE.match(expected)


# --- Markdown parsing -------------------------------------------------------


def test_markdown_fence_lines_are_not_headings() -> None:
    lines = [
        "# Top",
        "",
        "```python",
        "# not a heading",
        "print(1)",
        "```",
        "",
        "## Real",
    ]
    nodes = parse_markdown("a.md", lines)
    titles = [node.title for node in nodes]
    assert "not a heading" not in titles
    assert titles == ["a.md", "Top", "Real"]


def test_markdown_same_name_headings_get_distinct_occurrence_ids() -> None:
    text = (FIXTURES / "zh" / "guide.md").read_text(encoding="utf-8")
    nodes = parse_markdown("zh/guide.md", text.splitlines())
    installs = [node for node in nodes if node.title == "安装"]
    assert len(installs) == 2
    assert installs[0].occurrence == 1
    assert installs[1].occurrence == 2
    assert installs[0].tree_path == "zh/guide.md#使用指南/安装"
    assert installs[1].tree_path == "zh/guide.md#使用指南/安装@2"
    assert installs[0].start == 5
    assert installs[1].start == 16


def test_markdown_duplicate_parents_and_reserved_characters_have_unique_ids() -> None:
    nodes = parse_markdown(
        "x.md",
        ["# A", "## B", "# A", "## B", "# A@2", "## B", "# A/B", "## C"],
    )
    paths = [node.tree_path for node in nodes]
    ids = [node_id_for("x.md", node.tree_path, node.occurrence) for node in nodes]
    assert len(paths) == len(set(paths))
    assert len(ids) == len(set(ids))
    assert "x.md#A@2/B" in paths
    assert "x.md#A~22/B" in paths
    assert "x.md#A~1B/C" in paths


def test_markdown_exact_line_ranges_and_preamble() -> None:
    text = (FIXTURES / "en" / "api.md").read_text(encoding="utf-8")
    nodes = parse_markdown("en/api.md", text.splitlines())
    by_title = {node.title: node for node in nodes}
    assert by_title["(preamble)"].start == 1
    assert by_title["(preamble)"].end == 2
    assert by_title["API Reference"].start == 3
    assert by_title["API Reference"].end == 13
    assert by_title["getItem"].start == 5
    assert by_title["getItem"].end == 8
    assert by_title["setItem"].start == 9
    assert by_title["setItem"].end == 13
    assert by_title["en/api.md"].end == 13


def test_markdown_fixture_node_counts() -> None:
    counts = {
        "README.md": 4,
        "zh/guide.md": 5,
        "en/api.md": 5,
        "en/ids.md": 5,
    }
    for relpath, expected in counts.items():
        text = (FIXTURES / relpath).read_text(encoding="utf-8")
        nodes = parse_markdown(relpath, text.splitlines())
        assert len(nodes) == expected, relpath


# --- Python AST -------------------------------------------------------------


def test_python_ast_symbols_and_ranges() -> None:
    text = (FIXTURES / "symbols" / "sample.py").read_text(encoding="utf-8")
    nodes, failed = parse_python("symbols/sample.py", text.splitlines())
    assert failed is False
    by_title = {node.title: node for node in nodes}
    assert by_title["symbols/sample.py"].kind == "module"
    assert by_title["Foo"].kind == "class"
    assert by_title["Foo"].start == 3 and by_title["Foo"].end == 7
    assert by_title["bar"].kind == "function"
    assert by_title["bar"].start == 6 and by_title["bar"].end == 7
    assert by_title["fetch"].kind == "async_function"
    assert by_title["fetch"].start == 9 and by_title["fetch"].end == 10
    assert by_title["outer"].start == 12 and by_title["outer"].end == 15
    assert by_title["inner"].start == 13 and by_title["inner"].end == 14
    # parent-child: bar under Foo, inner under outer
    assert by_title["bar"].parent_index == nodes.index(by_title["Foo"])
    assert by_title["inner"].parent_index == nodes.index(by_title["outer"])


def test_python_syntax_error_falls_back_to_text_node() -> None:
    lines = ["def broken(:"]
    nodes, failed = parse_python("broken.py", lines)
    assert failed is True
    assert nodes[0].kind == "file"


# --- Scanning / boundaries --------------------------------------------------


def test_scan_skips_excluded_dirs_env_binary_and_credentials(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    (tmp_path / "node_modules").mkdir()
    (tmp_path / ".venv").mkdir()
    (tmp_path / ".venv" / "pyvenv.cfg").write_text("home = x\n", encoding="utf-8")
    # bare env/ is only a virtualenv when it carries pyvenv.cfg
    (tmp_path / "env").mkdir()
    (tmp_path / "env" / "pyvenv.cfg").write_text("home = x\n", encoding="utf-8")
    (tmp_path / ".env").write_text("SECRET=1\n", encoding="utf-8")
    (tmp_path / ".ENV.PROD").write_text("SECRET=2\n", encoding="utf-8")
    (tmp_path / "blob.bin").write_bytes(b"\x00\x01\x02")
    (tmp_path / "ok.md").write_text("# OK\n", encoding="utf-8")
    (tmp_path / "big.txt").write_text("x" * (4 * 1024 * 1024 + 1), encoding="utf-8")

    files, skipped = index_build.scan_workspace(tmp_path, load_contracts())
    assert [item.relpath for item in files] == ["ok.md"]
    reasons = {item.relpath: item.reason for item in skipped}
    assert reasons.get(".git/") == "directory_excluded"
    assert reasons.get("node_modules/") == "directory_excluded"
    assert reasons.get(".venv/") == "directory_excluded"
    assert reasons.get("env/") == "virtualenv"
    assert reasons.get(".env") == "credential_file"
    assert reasons.get(".ENV.PROD") == "credential_file"
    assert reasons.get("blob.bin") == "binary"
    assert reasons.get("big.txt") == "too_large"


def test_scan_skips_symlinks_without_following(tmp_path: Path) -> None:
    (tmp_path / "real").mkdir()
    (tmp_path / "real" / "a.md").write_text("# A\n", encoding="utf-8")
    try:
        (tmp_path / "link.md").symlink_to(tmp_path / "real" / "a.md")
    except OSError:
        pytest.skip("symlink creation not permitted on this host")
    files, skipped = index_build.scan_workspace(tmp_path, load_contracts())
    assert [item.relpath for item in files] == ["real/a.md"]
    assert any(item.relpath == "link.md" and item.reason == "symlink" for item in skipped)


def test_default_index_build_rejects_symlinked_parent(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    outside = tmp_path / "outside"
    workspace.mkdir()
    outside.mkdir()
    (workspace / "README.md").write_text("# Safe\n", encoding="utf-8")
    try:
        (workspace / ".reverse-skill").symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("directory symlink creation not permitted on this host")

    with pytest.raises(IndexStoreError, match="symlink or junction"):
        index_build.build_apply(workspace)
    assert not (outside / "index" / "v1.sqlite3").exists()


def test_scan_skips_excluded_directories_at_any_depth(tmp_path: Path) -> None:
    nested = tmp_path / "a" / "node_modules"
    nested.mkdir(parents=True)
    (nested / "bad.md").write_text("# must not index\n", encoding="utf-8")
    (tmp_path / "ok.md").write_text("# OK\n", encoding="utf-8")
    files, skipped = index_build.scan_workspace(tmp_path, load_contracts())
    assert [item.relpath for item in files] == ["ok.md"]
    assert any(
        item.relpath == "a/node_modules/" and item.reason == "directory_excluded"
        for item in skipped
    )


def test_normalize_relpath_rejects_root_escape() -> None:
    assert _normalize_relpath("docs", "../docs/guide.md") == "docs/guide.md"
    assert _normalize_relpath("docs", "guide.md") == "docs/guide.md"
    assert _normalize_relpath("a/b", "../c.md") == "a/c.md"
    assert _normalize_relpath("a/b", "../..") is None
    assert _normalize_relpath("a/b", "../../../etc/passwd") is None
    assert _normalize_relpath("a", "/abs/path.md") is None
    assert _normalize_relpath("a", "http://example.com/x.md") is None


# --- Capability fail-closed -------------------------------------------------


def test_capability_probe_fails_closed_for_old_sqlite(monkeypatch) -> None:
    monkeypatch.setattr("reverse_skill.index_store.sqlite3.sqlite_version_info", (3, 33, 0))
    result = probe_capabilities()
    assert result["available"] is False
    assert result["reason"] == "sqlite_too_old"
    with pytest.raises(IndexCapabilityUnavailable):
        require_capability()


def test_open_read_only_rejects_corrupt_file(tmp_path: Path) -> None:
    index_path = tmp_path / "v1.sqlite3"
    index_path.write_bytes(b"this is not a sqlite database at all")
    with pytest.raises(IndexCorrupt):
        open_read_only(index_path)


def test_open_read_only_rejects_incomplete_schema(tmp_path: Path) -> None:
    index_path = tmp_path / "v1.sqlite3"
    connection = sqlite3.connect(str(index_path))
    connection.execute("CREATE TABLE index_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
    connection.execute(
        "INSERT INTO index_meta (key, value) VALUES ('schema_version', ?)",
        (SCHEMA_VERSION,),
    )
    connection.commit()
    connection.close()
    with pytest.raises(IndexCorrupt, match="incomplete"):
        open_read_only(index_path)


def test_read_only_uri_handles_hash_and_spaces(tmp_path: Path) -> None:
    (tmp_path / "a.md").write_text("# A\n", encoding="utf-8")
    index_path = tmp_path / "index # one" / "v1.sqlite3"
    index_build.build_apply(tmp_path, index_path)
    connection = open_read_only(index_path)
    connection.close()


def test_validate_node_id_rejects_paths() -> None:
    from reverse_skill.index_store import validate_node_id

    validate_node_id("a" * 16)
    for bad in ("../../etc/passwd", "abc", "A" * 16, "", "a" * 15 + "Z"):
        with pytest.raises(InvalidNodeId):
            validate_node_id(bad)


# --- Build / determinism ----------------------------------------------------


def test_build_apply_is_deterministic(tmp_path: Path) -> None:
    _write_workspace(tmp_path)
    first = index_build.build_apply(tmp_path)
    second = index_build.build_apply(tmp_path)
    assert first["root_hash"] == second["root_hash"]
    assert first["documents"]["nodes"] == second["documents"]["nodes"]
    assert first["index_revision"] == second["index_revision"] == 1


def test_build_plan_is_read_only(tmp_path: Path) -> None:
    _write_workspace(tmp_path)
    plan = index_build.build_plan(tmp_path)
    assert plan["status"] == "planned"
    assert not (tmp_path / ".reverse-skill").exists()
    assert plan["documents"]["scanned"] == 5
    assert plan["documents"]["nodes"] == 25


def test_update_plan_is_read_only(tmp_path: Path) -> None:
    _write_workspace(tmp_path)
    index_path = _build(tmp_path)
    mtime = index_path.stat().st_mtime_ns
    plan = index_build.update_plan(tmp_path)
    assert plan["status"] == "planned"
    assert index_path.stat().st_mtime_ns == mtime
    assert plan["documents"]["unchanged"] == 5


def test_stable_node_ids_across_body_change(tmp_path: Path) -> None:
    _write_workspace(tmp_path)
    _build(tmp_path)
    heading_id = _node_id_for_tree_path(tmp_path, "zh/guide.md#使用指南/安装", occurrence=1)
    (tmp_path / "zh" / "guide.md").write_text(
        "# 使用指南\n\n## 安装\n\n完全不同的正文。\n", encoding="utf-8"
    )
    index_build.update_apply(tmp_path)
    new_id = _node_id_for_tree_path(tmp_path, "zh/guide.md#使用指南/安装", occurrence=1)
    assert new_id == heading_id


def test_title_change_changes_node_id(tmp_path: Path) -> None:
    _write_workspace(tmp_path)
    _build(tmp_path)
    (tmp_path / "zh" / "guide.md").write_text(
        "# 使用指南\n\n## 安装方法\n\n正文。\n", encoding="utf-8"
    )
    index_build.update_apply(tmp_path)
    old_id = _node_id_for_tree_path(tmp_path, "zh/guide.md#使用指南/安装", occurrence=1)
    new_rows = _query(
        "SELECT node_id FROM nodes WHERE tree_path = ?",
        tmp_path / ".reverse-skill" / "index" / "v1.sqlite3",
        ("zh/guide.md#使用指南/安装方法",),
    )
    assert len(new_rows) == 1
    assert new_rows[0][0] != old_id


def _node_id_for_tree_path(tmp_path: Path, tree_path: str, occurrence: int) -> str:
    relpath = tree_path.split("#")[0]
    return node_id_for(relpath, tree_path, occurrence)


# --- Incremental ------------------------------------------------------------


def test_incremental_add_change_delete(tmp_path: Path) -> None:
    _write_workspace(tmp_path)
    index_path = _build(tmp_path)

    (tmp_path / "en" / "api.md").write_text(
        "# API Reference\n\n## getItem\n\nnew body.\n", encoding="utf-8"
    )
    (tmp_path / "added.md").write_text("# Added\n\nbrand new.\n", encoding="utf-8")
    (tmp_path / "en" / "ids.md").unlink()

    plan = index_build.update_plan(tmp_path)
    assert plan["documents"]["changed"] == 1
    assert plan["documents"]["added"] == 1
    assert plan["documents"]["removed"] == 1
    assert plan["documents"]["unchanged"] == 3

    result = index_build.update_apply(tmp_path)
    assert result["index_revision"] == "2"
    docs = {row[0] for row in _query("SELECT relative_path FROM documents", index_path)}
    assert docs == {"README.md", "zh/guide.md", "en/api.md", "added.md", "symbols/sample.py"}
    files, _ = index_build.scan_workspace(tmp_path, load_contracts())
    expected_root_hash = compute_root_hash((item.relpath, item.sha256) for item in files)
    stored_root_hash = _query(
        "SELECT value FROM index_meta WHERE key = 'root_hash'", index_path
    )[0][0]
    assert result["root_hash_after"] == expected_root_hash
    assert stored_root_hash == expected_root_hash


def test_incremental_and_full_build_have_identical_tree_order(tmp_path: Path) -> None:
    (tmp_path / "a.md").write_text("# Common\n\nalpha\n", encoding="utf-8")
    (tmp_path / "b.md").write_text("# Common\n\nbeta\n", encoding="utf-8")
    _build(tmp_path)

    (tmp_path / "a.md").write_text("# Common\n\nalpha changed\n", encoding="utf-8")
    index_build.update_apply(tmp_path)
    incremental = index_api.index_search(tmp_path, "Common", "tree", top_k=10)

    index_build.build_apply(tmp_path)
    rebuilt = index_api.index_search(tmp_path, "Common", "tree", top_k=10)

    def stable_hits(result):
        return [
            (hit["node_id"], hit["tree_path"], hit["score"])
            for hit in result["hits"]
        ]

    assert stable_hits(incremental) == stable_hits(rebuilt)


def test_facade_read_nodes_returns_body_and_index_evidence(tmp_path: Path) -> None:
    _write_workspace(tmp_path)
    index_path = _build(tmp_path)
    node_id = _query(
        "SELECT node_id FROM nodes WHERE tree_path = ?", index_path,
        ("en/api.md#API Reference/getItem",),
    )[0][0]
    result = index_api.index_read_nodes(tmp_path, [node_id])
    assert result["schema_version"] == SCHEMA_VERSION
    assert result["index_revision"] == "1"
    assert result["root_hash"]
    assert result["index_path"] == str(index_path)
    assert "Returns the item" in result["nodes"][0]["text"]


def test_noop_update_keeps_revision(tmp_path: Path) -> None:
    _write_workspace(tmp_path)
    _build(tmp_path)
    result = index_build.update_apply(tmp_path)
    assert result["index_revision"] == "1"


def test_update_transaction_rollback_leaves_index_intact(tmp_path: Path, monkeypatch) -> None:
    _write_workspace(tmp_path)
    index_path = _build(tmp_path)
    (tmp_path / "en" / "api.md").write_text("# Changed\n\nnew content\n", encoding="utf-8")

    original = index_build._insert_document_rows

    def boom(connection, rows):
        original(connection, rows)
        raise RuntimeError("simulated mid-transaction failure")

    monkeypatch.setattr(index_build, "_insert_document_rows", boom)
    with pytest.raises(RuntimeError, match="simulated"):
        index_build.update_apply(tmp_path)
    monkeypatch.setattr(index_build, "_insert_document_rows", original)

    con = sqlite3.connect(str(index_path))
    try:
        revision = con.execute(
            "SELECT value FROM index_meta WHERE key='index_revision'"
        ).fetchone()[0]
        docs = con.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
        fts = con.execute("SELECT COUNT(*) FROM fts_terms").fetchone()[0]
    finally:
        con.close()
    assert revision == "1"
    assert docs == 5
    assert fts == 25
    rows = _query(
        "SELECT tree_path FROM nodes WHERE tree_path LIKE 'en/api.md%'", index_path
    )
    assert any(row[0] == "en/api.md#API Reference" for row in rows)


def test_link_edges_follow_target_changes(tmp_path: Path) -> None:
    _write_workspace(tmp_path)
    index_path = _build(tmp_path)
    link_targets = _query(
        "SELECT n.tree_path FROM edges e JOIN nodes n ON n.node_id = e.target_node "
        "WHERE e.kind = 'link' ORDER BY n.tree_path",
        index_path,
    )
    # Two hand-fixed cross-document links in the fixture:
    #   zh/guide.md#使用指南/安装 (occ 2) -> en/api.md#API Reference/getItem
    #   en/api.md#API Reference/setItem  -> zh/guide.md#使用指南/安装 (occ 1)
    assert [row[0] for row in link_targets] == [
        "en/api.md#API Reference/getItem",
        "zh/guide.md#使用指南/安装",
    ]

    # Remove the anchor heading from the target; the edge must fall back to the file node.
    (tmp_path / "zh" / "guide.md").write_text(
        "# 使用指南\n\n## 安装说明\n\n新内容。\n", encoding="utf-8"
    )
    index_build.update_apply(tmp_path)
    link_targets = _query(
        "SELECT n.tree_path FROM edges e JOIN nodes n ON n.node_id = e.target_node "
        "WHERE e.kind = 'link'",
        index_path,
    )
    assert [row[0] for row in link_targets] == ["zh/guide.md"]

    # Restore the anchor; the edge must point at the heading again.
    (tmp_path / "zh" / "guide.md").write_text(
        "# 使用指南\n\n## 安装\n\n恢复。\n", encoding="utf-8"
    )
    index_build.update_apply(tmp_path)
    link_targets = _query(
        "SELECT n.tree_path FROM edges e JOIN nodes n ON n.node_id = e.target_node "
        "WHERE e.kind = 'link'",
        index_path,
    )
    assert [row[0] for row in link_targets] == ["zh/guide.md#使用指南/安装"]


def test_incremental_add_resolves_previously_missing_link_target(tmp_path: Path) -> None:
    (tmp_path / "source.md").write_text(
        "# Source\n\n[Future](future.md#Target)\n", encoding="utf-8"
    )
    index_path = _build(tmp_path)
    assert _query("SELECT target_node FROM edges WHERE kind = 'link'", index_path) == []

    (tmp_path / "future.md").write_text("# Target\n\nNow present.\n", encoding="utf-8")
    plan = index_build.update_plan(tmp_path)
    assert plan["edges"]["link_rebuild_sources"] == ["source.md"]
    index_build.update_apply(tmp_path)
    targets = _query(
        "SELECT n.tree_path FROM edges e JOIN nodes n ON n.node_id = e.target_node "
        "WHERE e.kind = 'link'",
        index_path,
    )
    assert targets == [("future.md#Target",)]


def test_subtree_facade_preserves_document_order(tmp_path: Path) -> None:
    _write_workspace(tmp_path)
    index_path = _build(tmp_path)
    file_node_id = _query(
        "SELECT node_id FROM nodes WHERE tree_path = 'en/api.md'", index_path
    )[0][0]
    result = index_api.index_get_tree(tmp_path, file_node_id)
    assert [node["title"] for node in result["descendants"]] == [
        "(preamble)",
        "API Reference",
        "getItem",
        "setItem",
    ]


def test_root_hash_contract() -> None:
    entries = [("a.md", "hash-a"), ("b.md", "hash-b")]
    digest = hashlib.sha256()
    digest.update(b"a.md\x00hash-a\nb.md\x00hash-b\n")
    assert compute_root_hash(entries) == digest.hexdigest()


# --- helpers ----------------------------------------------------------------


def _write_workspace(tmp_path: Path) -> None:
    for source in sorted(FIXTURES.rglob("*")):
        if source.is_file():
            relative = source.relative_to(FIXTURES)
            target = tmp_path / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(source.read_bytes())
