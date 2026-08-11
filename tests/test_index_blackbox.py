"""Black-box CLI tests for the deterministic index/retrieve surface.

Fixture expectations are hand-written and fixed; they are derived from the
frozen contract and the checked-in fixture files, never from the
implementation at test time.
"""

from __future__ import annotations

import json
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "data" / "index-fixtures"

# Hand-fixed expectations for tests/data/index-fixtures/.
FIXTURE_DOCS = 5
FIXTURE_NODES = 25
FIXTURE_LINK_EDGES = 2


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "reverse_skill", "--json", *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


def run_cli_text(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "reverse_skill", *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


@pytest.fixture()
def workspace(tmp_path: Path) -> Path:
    for source in sorted(FIXTURES.rglob("*")):
        if source.is_file():
            relative = source.relative_to(FIXTURES)
            target = tmp_path / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(source.read_bytes())
    return tmp_path


def _index_path(workspace: Path) -> Path:
    return workspace / ".reverse-skill" / "index" / "v1.sqlite3"


# --- Read-only defaults -----------------------------------------------------


def test_build_without_apply_is_read_only_plan(workspace: Path) -> None:
    result = run_cli("index", "build", str(workspace))
    assert result.returncode == 0
    value = json.loads(result.stdout)
    assert value["ok"] is True
    assert value["command"] == "index"
    data = value["data"]
    assert data["status"] == "planned"
    assert data["applied"] is False
    assert data["documents"]["scanned"] == FIXTURE_DOCS
    assert data["documents"]["nodes"] == FIXTURE_NODES
    assert not _index_path(workspace).exists()
    assert not (workspace / ".reverse-skill").exists()


def test_build_apply_then_status_reports_frozen_counts(workspace: Path) -> None:
    built = run_cli("index", "build", str(workspace), "--apply")
    assert built.returncode == 0
    applied = json.loads(built.stdout)["data"]
    assert applied["status"] == "applied"
    assert applied["documents"]["indexed"] == FIXTURE_DOCS
    assert applied["documents"]["nodes"] == FIXTURE_NODES

    status = run_cli("index", "status", str(workspace))
    assert status.returncode == 0
    data = json.loads(status.stdout)["data"]
    assert data["exists"] is True
    assert data["index_revision"] == "1"
    assert data["counts"]["documents"] == FIXTURE_DOCS
    assert data["counts"]["nodes"] == FIXTURE_NODES
    assert data["counts"]["link_edges"] == FIXTURE_LINK_EDGES


def test_status_on_missing_index_reports_absent_with_exit_zero(workspace: Path) -> None:
    result = run_cli("index", "status", str(workspace))
    assert result.returncode == 0
    data = json.loads(result.stdout)["data"]
    assert data["status"] == "absent"
    assert data["exists"] is False


def test_index_path_override(workspace: Path, tmp_path: Path) -> None:
    custom = tmp_path / "custom" / "idx.sqlite3"
    result = run_cli("index", "build", str(workspace), "--apply", "--index-path", str(custom))
    assert result.returncode == 0
    assert custom.is_file()
    assert not _index_path(workspace).exists()
    status = run_cli("index", "status", str(workspace), "--index-path", str(custom))
    assert json.loads(status.stdout)["data"]["exists"] is True


# --- Retrieval modes --------------------------------------------------------


def test_retrieve_chinese_short_query_uses_exact_stage(workspace: Path) -> None:
    run_cli("index", "build", str(workspace), "--apply")
    result = run_cli("retrieve", str(workspace), "安装", "--mode", "bm25")
    assert result.returncode == 0
    data = json.loads(result.stdout)["data"]
    assert data["mode"] == "bm25"
    # "安装" is 2 chars: below the trigram minimum, so no trigram stage.
    assert data["stages"] == ["exact_structured_path", "short_substring_scan"]
    assert data["hit_count"] >= 1
    first = data["hits"][0]
    assert first["tree_path"] == "zh/guide.md#使用指南/安装"
    assert first["score"] == 1.0
    assert first["lines"] == {"start": 5, "end": 8}
    assert set(first) >= {
        "node_id",
        "relative_path",
        "tree_path",
        "lines",
        "content_sha256",
        "score",
        "score_components",
    }


def test_retrieve_two_character_body_substring(workspace: Path) -> None:
    run_cli("index", "build", str(workspace), "--apply")
    result = run_cli("retrieve", str(workspace), "第一", "--mode", "bm25")
    assert result.returncode == 0
    data = json.loads(result.stdout)["data"]
    assert data["stages"] == ["exact_structured_path", "short_substring_scan"]
    assert any(hit["tree_path"] == "zh/guide.md#使用指南/安装" for hit in data["hits"])


def test_retrieve_english_tree_exact_title(workspace: Path) -> None:
    run_cli("index", "build", str(workspace), "--apply")
    result = run_cli("retrieve", str(workspace), "getItem", "--mode", "tree")
    assert result.returncode == 0
    data = json.loads(result.stdout)["data"]
    assert data["stages"] == ["title_navigation"]
    first = data["hits"][0]
    assert first["tree_path"] == "en/api.md#API Reference/getItem"
    assert first["score_components"]["title_exact"] is True
    assert first["ancestors"] == ["en/api.md", "en/api.md#API Reference"]


def test_retrieve_tree_accepts_exact_tree_path(workspace: Path) -> None:
    run_cli("index", "build", str(workspace), "--apply")
    tree_path = "en/api.md#API Reference/getItem"
    result = run_cli("retrieve", str(workspace), tree_path, "--mode", "tree")
    assert result.returncode == 0
    first = json.loads(result.stdout)["data"]["hits"][0]
    assert first["tree_path"] == tree_path
    assert first["score_components"]["title_exact"] is True


def test_retrieve_short_id_hybrid_expands_tree(workspace: Path) -> None:
    run_cli("index", "build", str(workspace), "--apply")
    result = run_cli("retrieve", str(workspace), "A1", "--mode", "hybrid", "--top-k", "5")
    assert result.returncode == 0
    data = json.loads(result.stdout)["data"]
    assert "exact_structured_path" in data["stages"]
    assert "tree_expansion" in data["stages"]
    assert "trigram_shortlist" not in data["stages"]
    paths = [hit["tree_path"] for hit in data["hits"]]
    assert "en/ids.md#ID Table/A1" in paths
    top = data["hits"][0]
    assert top["score"] == 1.0
    # expanded ancestors carry decayed scores and explainable components
    expanded = [hit for hit in data["hits"] if hit["score_components"]["primary"] == "ancestor"]
    assert expanded
    assert expanded[0]["score"] == pytest.approx(0.5)


def test_retrieve_chinese_substring_via_trigram(workspace: Path) -> None:
    run_cli("index", "build", str(workspace), "--apply")
    result = run_cli("retrieve", str(workspace), "使用方法", "--mode", "hybrid")
    assert result.returncode == 0
    data = json.loads(result.stdout)["data"]
    assert "trigram_shortlist" in data["stages"]
    assert data["hit_count"] >= 1
    assert any("zh/guide.md" in hit["tree_path"] for hit in data["hits"])


def test_retrieve_missing_index_is_blocked(workspace: Path) -> None:
    result = run_cli("retrieve", str(workspace), "x", "--mode", "bm25")
    assert result.returncode == 5
    value = json.loads(result.stdout)
    assert value["ok"] is False
    assert value["error"]["code"] == "index_not_found"
    # retrieve must never create the index
    assert not _index_path(workspace).exists()


def test_retrieve_invalid_mode_is_usage_error(workspace: Path) -> None:
    result = run_cli("retrieve", str(workspace), "x", "--mode", "vector")
    assert result.returncode == 2
    assert json.loads(result.stdout)["error"]["code"] == "usage"


def test_retrieve_is_deterministic(workspace: Path) -> None:
    run_cli("index", "build", str(workspace), "--apply")
    first = run_cli("retrieve", str(workspace), "item", "--mode", "hybrid")
    second = run_cli("retrieve", str(workspace), "item", "--mode", "hybrid")
    assert first.stdout == second.stdout


# --- Inspect ----------------------------------------------------------------


def test_inspect_node_and_tree(workspace: Path) -> None:
    run_cli("index", "build", str(workspace), "--apply")
    retrieved = json.loads(
        run_cli("retrieve", str(workspace), "getItem", "--mode", "tree").stdout
    )["data"]
    node_id = retrieved["hits"][0]["node_id"]
    result = run_cli("index", "inspect", str(workspace), node_id)
    assert result.returncode == 0
    data = json.loads(result.stdout)["data"]
    assert data["node"]["tree_path"] == "en/api.md#API Reference/getItem"
    assert [ancestor["tree_path"] for ancestor in data["ancestors"]] == [
        "en/api.md",
        "en/api.md#API Reference",
    ]
    assert data["descendant_count"] == 0


def test_inspect_invalid_and_unknown_node_id(workspace: Path) -> None:
    run_cli("index", "build", str(workspace), "--apply")
    bad = run_cli("index", "inspect", str(workspace), "../../etc/passwd")
    assert bad.returncode == 5
    assert json.loads(bad.stdout)["error"]["code"] == "invalid_node_id"
    unknown = run_cli("index", "inspect", str(workspace), "0" * 16)
    assert unknown.returncode == 5
    assert json.loads(unknown.stdout)["error"]["code"] == "node_not_found"


# --- Corrupt / incompatible index -------------------------------------------


def test_corrupt_index_is_blocked(workspace: Path) -> None:
    index_path = _index_path(workspace)
    index_path.parent.mkdir(parents=True, exist_ok=True)
    index_path.write_bytes(b"garbage not sqlite")
    result = run_cli("retrieve", str(workspace), "x", "--mode", "bm25")
    assert result.returncode == 5
    assert json.loads(result.stdout)["error"]["code"] == "index_corrupt"


def test_schema_incompatible_index_is_blocked(workspace: Path) -> None:
    index_path = _index_path(workspace)
    index_path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(index_path))
    con.execute("CREATE TABLE index_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
    con.execute(
        "INSERT INTO index_meta (key, value) VALUES ('schema_version', '999')"
    )
    con.commit()
    con.close()
    result = run_cli("retrieve", str(workspace), "x", "--mode", "bm25")
    assert result.returncode == 5
    assert json.loads(result.stdout)["error"]["code"] == "index_schema_incompatible"


# --- Incremental update via CLI ---------------------------------------------


def test_update_plan_apply_and_deleted_file(workspace: Path) -> None:
    run_cli("index", "build", str(workspace), "--apply")

    (workspace / "en" / "api.md").write_text(
        "# API Reference\n\n## getItem\n\nnew body.\n", encoding="utf-8"
    )
    (workspace / "en" / "ids.md").unlink()
    (workspace / "new.md").write_text("# New\n\nadded.\n", encoding="utf-8")

    plan = run_cli("index", "update", str(workspace))
    assert plan.returncode == 0
    plan_data = json.loads(plan.stdout)["data"]
    assert plan_data["status"] == "planned"
    assert plan_data["documents"]["changed"] == 1
    assert plan_data["documents"]["removed"] == 1
    assert plan_data["documents"]["added"] == 1
    # plan is read-only
    assert json.loads(run_cli("index", "status", str(workspace)).stdout)["data"][
        "index_revision"
    ] == "1"

    applied = run_cli("index", "update", str(workspace), "--apply")
    assert applied.returncode == 0
    apply_data = json.loads(applied.stdout)["data"]
    assert apply_data["status"] == "applied"
    assert apply_data["index_revision"] == "2"

    status = json.loads(run_cli("index", "status", str(workspace)).stdout)["data"]
    assert status["counts"]["documents"] == FIXTURE_DOCS  # -1 removed, +1 added
    assert status["index_revision"] == "2"

    # deleted doc is gone from retrieval; added doc is searchable
    removed = run_cli("retrieve", str(workspace), "B2", "--mode", "bm25")
    assert json.loads(removed.stdout)["data"]["hit_count"] == 0
    added = run_cli("retrieve", str(workspace), "added", "--mode", "hybrid")
    assert json.loads(added.stdout)["data"]["hit_count"] >= 1


def test_update_on_missing_index_is_blocked(workspace: Path) -> None:
    result = run_cli("index", "update", str(workspace))
    assert result.returncode == 5
    assert json.loads(result.stdout)["error"]["code"] == "index_not_found"


def test_status_reports_stale_then_fresh_after_update(workspace: Path) -> None:
    run_cli("index", "build", str(workspace), "--apply")
    fresh = json.loads(run_cli("index", "status", str(workspace)).stdout)["data"]
    assert fresh["fresh"] is True and fresh["stale"] is False

    (workspace / "en" / "api.md").write_text("# Changed\n\nnew body\n", encoding="utf-8")
    stale = json.loads(run_cli("index", "status", str(workspace)).stdout)["data"]
    assert stale["fresh"] is False and stale["stale"] is True
    assert stale["workspace_root_hash"] != stale["root_hash"]

    run_cli("index", "update", str(workspace), "--apply")
    refreshed = json.loads(run_cli("index", "status", str(workspace)).stdout)["data"]
    assert refreshed["fresh"] is True and refreshed["stale"] is False


# --- Text output matches JSON facts -----------------------------------------


def test_text_output_contains_same_facts_as_json(workspace: Path) -> None:
    run_cli("index", "build", str(workspace), "--apply")
    json_result = run_cli("retrieve", str(workspace), "getItem", "--mode", "tree")
    text_result = run_cli_text("retrieve", str(workspace), "getItem", "--mode", "tree")
    assert text_result.returncode == 0
    json_data = json.loads(json_result.stdout)["data"]
    for hit in json_data["hits"]:
        assert hit["tree_path"] in text_result.stdout
    assert "en/api.md#API Reference/getItem" in text_result.stdout


# --- Existing search regression ---------------------------------------------


def test_legacy_search_semantics_unchanged_and_no_index_side_effect(tmp_path: Path) -> None:
    (tmp_path / "sample.txt").write_text("alpha\nbeta gamma\n", encoding="utf-8")
    result = run_cli("search", str(tmp_path), "beta", "--engine", "python")
    assert result.returncode == 0
    data = json.loads(result.stdout)["data"]
    assert data["status"] == "observed"
    assert data["engine"] == "python"
    assert any("beta gamma" in match for match in data["matches"])
    assert not (tmp_path / ".reverse-skill").exists(), "search must not create an index"

    # regex semantics: '.' matches any char, as before
    regex = run_cli("search", str(tmp_path), "bet.", "--engine", "python")
    assert json.loads(regex.stdout)["data"]["match_count_reported"] == 1
