from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

import pytest

from reverse_skill import index_api
from reverse_skill.ida_ingest import IdaExportInvalid, import_export
from reverse_skill.index_build import build_apply, update_apply, update_plan
from reverse_skill.index_store import node_id_for


def _write_export(path: Path, *, renamed: bool = False) -> None:
    first_name = "renamed_entry" if renamed else "entry"
    first_body = "int renamed_entry(void) { return helper(); }" if renamed else "int entry(void) { return helper(); }"
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "module": "sample.exe",
                "functions": [
                    {
                        "address": "0x401000",
                        "name": first_name,
                        "pseudocode": first_body,
                        "xrefs_to": ["0x401100"],
                    },
                    {
                        "address": "0x401100",
                        "name": "helper",
                        "pseudocode": "int helper(void) { return 7; }",
                        "xrefs_to": [],
                    },
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def _function_id(address: str) -> str:
    document = "__ida__/sample.exe"
    return node_id_for(document, f"{document}#function@{address}", 1)


@pytest.fixture()
def indexed_workspace(tmp_path: Path) -> tuple[Path, Path]:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "README.md").write_text("# Sample\n", encoding="utf-8")
    build_apply(workspace)
    export = tmp_path / "ida-export.json"
    _write_export(export)
    return workspace, export


def test_ida_import_is_plan_only_by_default(indexed_workspace: tuple[Path, Path]) -> None:
    workspace, export = indexed_workspace
    index_path = workspace / ".reverse-skill" / "index" / "v1.sqlite3"
    before = index_path.read_bytes()

    result = import_export(workspace, export, apply=False)

    assert result["status"] == "planned"
    assert result["documents"] == {"replaced": 0, "functions": 2}
    assert index_path.read_bytes() == before


def test_ida_import_materializes_stable_nodes_and_xrefs(
    indexed_workspace: tuple[Path, Path],
) -> None:
    workspace, export = indexed_workspace
    result = import_export(workspace, export, apply=True)
    assert result["status"] == "applied"
    assert result["edges"]["xrefs"] == 1

    entry_id = _function_id("0x401000")
    helper_id = _function_id("0x401100")
    nodes = index_api.index_read_nodes(workspace, [entry_id, helper_id])
    assert nodes["node_count"] == 2
    texts = {item["node_id"]: item["text"] for item in nodes["nodes"]}
    assert "helper()" in texts[entry_id]

    xrefs = index_api.index_read_xrefs(workspace, entry_id)
    assert [item["node_id"] for item in xrefs["outgoing"]] == [helper_id]
    assert xrefs["incoming"] == []
    incoming = index_api.index_read_xrefs(workspace, helper_id, "incoming")
    assert [item["node_id"] for item in incoming["incoming"]] == [entry_id]

    status = index_api.index_status(workspace)
    assert status["counts"]["ida_documents"] == 1
    assert status["counts"]["ida_nodes"] == 3
    assert status["counts"]["xref_edges"] == 1


def test_ida_reimport_keeps_address_node_ids_and_source_updates(
    indexed_workspace: tuple[Path, Path],
) -> None:
    workspace, export = indexed_workspace
    import_export(workspace, export, apply=True)
    entry_id = _function_id("0x401000")
    _write_export(export, renamed=True)

    result = import_export(workspace, export, apply=True)
    assert result["documents"]["replaced"] == 1
    node = index_api.index_read_nodes(workspace, [entry_id])["nodes"][0]
    assert node["node_id"] == entry_id
    assert "renamed_entry" in node["text"]

    (workspace / "README.md").write_text("# Sample\n\nupdated\n", encoding="utf-8")
    plan = update_plan(workspace)
    assert plan["documents"]["removed"] == 0
    update_apply(workspace)
    status = index_api.index_status(workspace)
    assert status["counts"]["ida_documents"] == 1
    assert status["counts"]["xref_edges"] == 1

    build_apply(workspace)
    status_after_rebuild = index_api.index_status(workspace)
    assert status_after_rebuild["counts"]["ida_documents"] == 1
    assert index_api.index_read_nodes(workspace, [entry_id])["nodes"][0]["text"].startswith(
        "int renamed_entry"
    )


def test_cli_ida_import_and_xref_query(
    indexed_workspace: tuple[Path, Path],
) -> None:
    workspace, export = indexed_workspace
    entry_id = _function_id("0x401000")
    imported = subprocess.run(
        [
            sys.executable,
            "-m",
            "reverse_skill",
            "--json",
            "index",
            "import-ida",
            str(workspace),
            "--export",
            str(export),
            "--apply",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert imported.returncode == 0, imported.stderr
    assert json.loads(imported.stdout)["data"]["status"] == "applied"

    queried = subprocess.run(
        [
            sys.executable,
            "-m",
            "reverse_skill",
            "--json",
            "index",
            "xrefs",
            str(workspace),
            entry_id,
            "--direction",
            "outgoing",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert queried.returncode == 0, queried.stderr
    assert json.loads(queried.stdout)["data"]["outgoing_count"] == 1


@pytest.mark.parametrize(
    "payload",
    [
        {
            "schema_version": 1,
            "module": "C:/absolute.exe",
            "functions": [],
        },
        {
            "schema_version": 1,
            "module": "sample.exe",
            "functions": [
                {"address": "0x1", "name": "bad", "xrefs_to": ["0x2"]}
            ],
        },
    ],
)
def test_ida_import_rejects_unsafe_or_unresolved_exports(
    indexed_workspace: tuple[Path, Path], payload: dict[str, object]
) -> None:
    workspace, export = indexed_workspace
    export.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(IdaExportInvalid):
        import_export(workspace, export, apply=True)
