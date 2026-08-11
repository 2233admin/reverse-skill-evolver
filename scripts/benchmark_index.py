#!/usr/bin/env python3
"""Reproducible benchmark for the deterministic document index.

Builds/updates an index over a real workspace and prints raw timings plus
workspace statistics. Never alters the results; hot spots are reported
honestly. The default root is this repository (its own docs), so the
benchmark can be re-run on any checkout with the same command.

Usage:
    python scripts/benchmark_index.py [--root PATH] [--index-path FILE]
                                      [--query QUERY] [--top-k N] [--repeat N]

The script prints measured values only; it does not enforce machine-specific
latency thresholds or claim a single-file update while measuring a no-op.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from reverse_skill import index_build, index_store
from reverse_skill.retrieval import retrieve

REPO_ROOT = Path(__file__).resolve().parents[1]


def _timed(label: str, fn, repeats: int = 3) -> float:
    best = float("inf")
    for _ in range(repeats):
        start = time.perf_counter()
        fn()
        elapsed = time.perf_counter() - start
        best = min(best, elapsed)
    print(f"  {label:<46} {best * 1000:9.1f} ms")
    return best


def _workspace_stats(root: Path) -> Dict[str, Any]:
    files, skipped = index_build.scan_workspace(root, index_store.load_contracts())
    md = sum(1 for item in files if item.kind == "markdown")
    py = sum(1 for item in files if item.kind == "python")
    tx = sum(1 for item in files if item.kind == "text")
    return {
        "root": str(root),
        "documents": len(files),
        "markdown": md,
        "python": py,
        "text": tx,
        "bytes": sum(item.size_bytes for item in files),
        "skipped": len(skipped),
    }


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=REPO_ROOT)
    parser.add_argument("--index-path", type=Path, default=None)
    parser.add_argument("--query", default="index")
    parser.add_argument("--top-k", type=int, default=20)
    parser.add_argument("--repeat", type=int, default=3)
    args = parser.parse_args(argv)

    root = args.root.resolve()
    index_path = args.index_path or (Path(tempfile.mkdtemp(prefix="rs-bench-")) / "v1.sqlite3")
    print("== workspace ==")
    print("  " + json.dumps(_workspace_stats(root), ensure_ascii=False))

    print("== build (plan) ==")
    _timed("build_plan (scan + parse)", lambda: index_build.build_plan(root), 1)
    print("== build (apply, includes temp db + atomic replace) ==")
    build_ms = _timed("build_apply", lambda: index_build.build_apply(root, index_path))
    print("== update ==")
    _timed("update_plan (no-op delta)", lambda: index_build.update_plan(root, index_path), 1)
    update_ms = _timed(
        "update_apply (no-op, keeps revision)",
        lambda: index_build.update_apply(root, index_path),
    )
    if update_ms >= 0.1:  # not on tiny workspaces; keep honest raw numbers
        print("  (update measured on a no-op delta)")

    print("== retrieval (in-process) ==")
    contracts = index_store.load_contracts()
    connection = index_store.open_read_only(index_path)
    try:
        for mode in ("bm25", "tree", "hybrid"):
            _timed(
                f"retrieve {mode!r} query={args.query!r} top_k={args.top_k}",
                lambda mode=mode: retrieve(
                    connection, args.query, mode, args.top_k, contracts
                ),
            )
    finally:
        index_store.close(connection)

    print("== cold CLI (subprocess) ==")
    command = [
        sys.executable,
        "-m",
        "reverse_skill",
        "--json",
        "retrieve",
        str(root),
        args.query,
        "--mode",
        "hybrid",
        "--top-k",
        str(args.top_k),
        "--index-path",
        str(index_path),
    ]

    def cold_cli() -> None:
        completed = subprocess.run(
            command, capture_output=True, text=True, encoding="utf-8", check=False
        )
        if completed.returncode != 0:
            raise RuntimeError("cold CLI failed: " + completed.stderr)

    _timed("cold CLI retrieve (python -m reverse_skill)", cold_cli)

    print("== facts ==")
    print(f"  index_path={index_path}")
    print(f"  index_size_bytes={index_path.stat().st_size}")
    print(f"  build_apply_ms={build_ms * 1000:.1f}")
    print("  (raw numbers above; no smoothing, best of repeat)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
