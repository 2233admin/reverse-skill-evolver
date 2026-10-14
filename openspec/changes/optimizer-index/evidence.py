"""Repeatable synthetic before/after evidence for issue #57, without a checkout.

Run from the repo: python -B openspec/changes/optimizer-index/evidence.py
Add --baseline to import only the known baseline modules from temporary files.
Native IDA/Burp/parser execution and whole-process memory are outside this proof.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import runpy
import sqlite3
import subprocess
import sys
import tempfile
import time
import tracemalloc
from contextlib import closing
from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


BASELINE = "d6d085364508215d0019b83f32dc58dd8f170c9e"
REPO = Path(__file__).resolve().parents[3]


def export_baseline(destination):
    paths = [f"reverse_skill/{name}.py" for name in (
        "__init__", "errors", "index_store", "index_build", "index_api", "retrieval", "ida_ingest"
    )] + ["reverse_skill/data/index-contracts.json"]
    for relative in paths:
        content = subprocess.check_output(["git", "show", f"{BASELINE}:{relative}"], cwd=REPO)
        path = destination / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def measure(source):
    sys.path.insert(0, str(source))
    from reverse_skill import ida_ingest, index_api, index_build as build, index_store as store, retrieval

    helpers = runpy.run_path(str(REPO / "tests/test_optimizer_index.py"))
    populate, steps, snapshot = (helpers[name] for name in ("populate", "vm_steps", "snapshot"))
    result = {"python": sys.version.split()[0], "sqlite": sqlite3.sqlite_version,
              "scope": "synthetic production-function evidence; not native tools or total RSS",
              "vm_precision_opcodes": 100}
    with closing(populate(10000)) as connection:
        statements = []
        connection.set_trace_callback(statements.append)
        ids = list(range(91, 101))

        def delete():
            if hasattr(store, "delete_documents_cascade"):
                store.delete_documents_cascade(connection, ids)
            else:
                for document in ids:
                    store.delete_document_cascade(connection, document)

        _, operations = steps(connection, delete)
        result["DB-01"] = {"nodes": 10000, "deleted_documents": 10, "vm_steps": operations,
                           "fts_delete_statements": sum(statement.startswith("DELETE FROM fts_") for statement in statements),
                           "remaining_rows_sha256": digest(snapshot(connection))}
    with closing(populate(10000)) as connection:
        query = "doc-99.md#Title-10000"
        hits, operations = steps(connection, lambda: retrieval._exact_structured_stage(connection, query, 20))
        plans = [row["detail"] for row in connection.execute(
            "EXPLAIN QUERY PLAN SELECT node_id FROM nodes WHERE title=? OR tree_path=? ORDER BY node_id LIMIT ?",
            (query, query, 20))]
        result["DB-02"] = {"vm_steps": operations, "plans": plans, "hits": hits}
    with closing(populate(10000, documents=1)) as connection:
        counted = helpers["CountingConnection"](connection)
        # Keep the connection alive long enough to collect evidence after the API.
        counted.close = lambda: None
        with tempfile.TemporaryDirectory() as root, patch.object(index_api, "open_read_only", return_value=counted):
            tracemalloc.start()
            try:
                tree = index_api.index_get_tree(Path(root), "0000000000000001")
                peak = tracemalloc.get_traced_memory()[1]
            finally:
                tracemalloc.stop()
        result["DB-03"] = {"wide_rows_fetched": counted.wide_rows, "python_peak_bytes": peak,
                           "descendant_count": tree["descendant_count"],
                           "returned": len(tree["descendants"]), "truncated": tree["descendants_truncated"],
                           "payload_sha256": digest({key: tree[key] for key in ("node", "ancestors", "descendants", "descendant_count", "descendants_truncated")})}

    class Export:
        sizes = []
        def is_file(self):
            return True
        def read_bytes(self):
            self.sizes.append(-1)
            return b"x" * (80 * 1024 * 1024)
        def open(self, mode):
            return self
        def __enter__(self):
            return self
        def __exit__(self, *args):
            self.closed = True
        def read(self, size):
            self.sizes.append(size)
            return b"x" * min(size, 80 * 1024 * 1024)

    export = Export()
    tracemalloc.start()
    try:
        ida_ingest.load_export(export)
    except ida_ingest.IdaExportInvalid as exc:
        error = str(exc)
    finally:
        peak = tracemalloc.get_traced_memory()[1]
        tracemalloc.stop()
    result["MEM-01"] = {"input_bytes": 80 * 1024 * 1024, "requested_reads": export.sizes,
                        "closed": getattr(export, "closed", False), "python_peak_bytes": peak, "error": error}

    data = "\n".join(f"# h{i}" for i in range(40000)).encode()
    parsed = build._parse_file("flat.md", data, len(data))
    children = helpers["CountedChildren"]
    for node in parsed.nodes:
        node.children = children(node.children)
    children.comparisons = children.visits = 0
    rows = build._materialize_document(parsed, 1)
    result["ALG-01"] = {"headings": 40000, "sibling_comparisons": children.comparisons,
                        "child_visits_including_body_assignment": children.visits, "rows_sha256": digest(rows)}

    counted_title = helpers["CountedTitle"]
    spec = build.NodeSpec
    def counted_spec(**kwargs):
        kwargs["title"] = counted_title(kwargs["title"])
        return spec(**kwargs)
    symbols = [SimpleNamespace(name=f"f{i}", kind="function", children=[],
                               span=SimpleNamespace(start_line=0, end_line=0)) for i in range(8000)]
    pack = SimpleNamespace(ProcessConfig=lambda **kwargs: SimpleNamespace(**kwargs),
                           process=lambda *args: SimpleNamespace(structure=symbols))
    counted_title.comparisons = 0
    with patch.object(build, "NodeSpec", counted_spec), patch.object(build, "_require_parser_cache", side_effect=lambda path: path), patch.object(build, "_language_pack", return_value=(pack, {})):
        nodes = build.parse_tree_sitter("flat.c", ["synthetic"], "c", Path("."))
    result["ALG-02"] = {"provider": "synthetic structure/span output", "symbols": 8000,
                        "title_comparisons": counted_title.comparisons, "nodes_sha256": digest([asdict(node) for node in nodes])}

    with closing(sqlite3.connect(":memory:")) as connection:
        connection.row_factory = sqlite3.Row
        store.create_schema(connection)
        documents = [build._parse_file("target.md", "\n".join(f"# h{i}" for i in range(2000)).encode(), 0),
                     build._parse_file("source.md", ("# Links\n" + "[link](target.md#h1999)\n" * 2000).encode(), 0)]
        ids, rows = {}, {}
        for parsed in documents:
            document_id = store.insert_document(connection, {"relative_path": parsed.relpath, "kind": parsed.kind,
                "sha256": parsed.sha256, "line_count": parsed.line_count, "size_bytes": parsed.size_bytes})
            ids[parsed.relpath] = document_id
            rows[parsed.relpath] = build._materialize_document(parsed, document_id)
            build._insert_document_rows(connection, rows[parsed.relpath])
        counts = {"queries": 0, "rows": 0}
        original = build._nodes_of_document
        def read(conn, document_id):
            values = original(conn, document_id)
            counts["queries"] += 1
            counts["rows"] += len(values)
            return values
        with patch.object(build, "_nodes_of_document", side_effect=read):
            build._insert_link_edges(connection, documents[1], rows["source.md"], ids)
        edges = [tuple(row) for row in connection.execute("SELECT * FROM edges WHERE kind='link' ORDER BY 1,2,3")]
        result["ALG-03"] = {**counts, "links": 2000, "edges_sha256": digest(edges)}

    with tempfile.TemporaryDirectory() as root:
        workspace = Path(root)
        files = [build._parse_file(f"{i:04}.md", b"# Same", 6) for i in range(8000)]
        current = {counted_title(parsed.relpath): {"document_id": i + 1, "kind": "markdown", "sha256": parsed.sha256}
                   for i, parsed in enumerate(files)}
        current[counted_title("__ida__/sample")] = {"document_id": 8001, "kind": "ida"}
        # Isolate actual update membership from FTS/filesystem costs, retaining
        # its transaction, plan construction and IDA/current mapping.
        with closing(sqlite3.connect(":memory:")) as connection:
            connection.row_factory = sqlite3.Row
            store.create_schema(connection)
            counted_title.comparisons = 0
            patches = [patch.object(build, "open_read_write", return_value=connection),
                       patch.object(build, "read_all_documents", return_value=current),
                       patch.object(build, "_collect_all", return_value=(files[4000:], [])),
                       patch.object(build, "_count_nodes_for_documents", return_value=0),
                       patch.object(build, "_stale_link_source_relpaths", return_value=[]),
                       patch.object(build, "_rebuild_link_edges", return_value=0),
                       patch.object(build, "close", return_value=None)]
            from contextlib import ExitStack
            with ExitStack() as stack:
                for item in patches:
                    stack.enter_context(item)
                if hasattr(build, "delete_documents_cascade"):
                    stack.enter_context(patch.object(build, "delete_documents_cascade"))
                else:
                    stack.enter_context(patch.object(build, "delete_document_cascade"))
                (workspace / "index.sqlite3").touch()
                delta = build.update_apply(workspace, workspace / "index.sqlite3")
            result["DATA-01"] = {"documents": 8001, "removed": 4000, "path_comparisons": counted_title.comparisons,
                                 "plan_sha256": digest(delta["documents"]),
                                 "scope": "actual update membership with IO/FTS mocked; integration regression separately keeps real IDA"}

    with closing(populate(800, documents=1)) as connection:
        connection.execute("UPDATE nodes SET title='X'")
        counted_id = helpers["CountedId"]
        counted_id.hashes = 0
        hits = retrieval._exact_structured_stage(helpers["CountedIdsConnection"](connection), "X", 800)
        result["DATA-02"] = {"matches": 800, "node_id_hash_calls": counted_id.hashes, "hits_sha256": digest(hits),
                             "scope": "actual SQL results with instrumented str node IDs"}

    text = helpers["CountedText"]
    text.scanned = 0
    started = time.perf_counter()
    links = build._node_links(text("[" * 32000))
    result["SEC-02"] = {"unclosed_openings": 32000, "forward_find_characters": text.scanned or None,
                        "links": links, "observed_seconds": time.perf_counter() - started,
                        "limit": "elapsed time is informational; regex backtracking is not measured by str.find instrumentation"}
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", action="store_true")
    parser.add_argument("--source-root", type=Path, default=REPO, help=argparse.SUPPRESS)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.baseline:
        with tempfile.TemporaryDirectory(prefix="optimizer-baseline-") as temporary:
            export_baseline(Path(temporary))
            command = [sys.executable, "-B", str(Path(__file__).resolve()), "--source-root", temporary]
            if args.output:
                command += ["--output", str(args.output.resolve())]
            return subprocess.call(command, cwd=REPO)
    result = measure(args.source_root)
    text = json.dumps(result, indent=2, ensure_ascii=False) + "\n"
    if args.output:
        args.output.write_text(text, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
