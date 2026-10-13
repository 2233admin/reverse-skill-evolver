"""Deterministic BM25 / tree / hybrid retrieval over the frozen index schema.

No vector database. Two real FTS5 indexes back retrieval:

- ``fts_terms``   (unicode61): word/phrase tokens, including whole CJK runs
- ``fts_trigram`` (trigram):   Chinese and substring search, >= 3 characters

Mode semantics (frozen in index-contracts.json):

- bm25   : rank-only. Union of unicode61 + trigram shortlists ordered by
           best (bm25 rank, node_id); short queries (< 3 chars) skip trigram
           and use exact structured matches plus a bounded substring scan.
- tree   : structure/title navigation. Exact title/node_id matches rank first,
           then title substring (LIKE); each hit carries its ancestor chain and
           bounded children so callers can navigate the deterministic tree.
- hybrid : BM25 shortlist (top_k * expansion) plus tree expansion of every
           shortlist hit (ancestors, bounded children); merged deterministically
           with explainable decay factors.

Scores are deterministic: 1/(1+rank) with ties broken by node_id ascending.
Queries are always wrapped as FTS5 phrase queries so user input can never
inject FTS syntax.
"""

from __future__ import annotations

import sqlite3
from typing import Any, Dict, List, Sequence, Tuple

from .index_store import (
    NODE_ID_RE,
    IndexCorrupt,
    IndexError,
    read_ancestors,
    read_children,
    read_node,
)


def _fts_phrase(query: str) -> str:
    return '"' + query.replace('"', '""') + '"'


def _like_escaped(query: str) -> str:
    return query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _bm25_shortlist(
    connection: sqlite3.Connection,
    table: str,
    query: str,
    limit: int,
) -> List[Tuple[str, float]]:
    """Ranked shortlist from one FTS5 table: (node_id, raw bm25 rank)."""
    phrase = _fts_phrase(query)
    try:
        rows = connection.execute(
            f"SELECT node_id, bm25({table}, 1.0, 1.0) AS rank "
            f"FROM {table} WHERE {table} MATCH ? "
            "ORDER BY rank ASC, node_id ASC LIMIT ?",
            (phrase, limit),
        ).fetchall()
    except sqlite3.OperationalError as exc:
        raise IndexCorrupt(f"FTS query failed for {table}: {exc}") from exc
    return [(row["node_id"], float(row["rank"])) for row in rows]


def _hit_payload(connection: sqlite3.Connection, node: Dict[str, Any], contracts: Dict[str, Any]) -> Dict[str, Any]:
    """Expand a node row into the evidence-bearing hit payload."""
    tree_max_children = int(contracts["limits"]["tree_max_children"])
    ancestors = read_ancestors(connection, node["node_id"])
    children = read_children(connection, node["node_id"], limit=tree_max_children)
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
        "score": None,
        "score_components": {},
        "ancestors": [ancestor["tree_path"] for ancestor in ancestors],
        "children": [child["tree_path"] for child in children],
    }


def _exact_structured_stage(
    connection: sqlite3.Connection, query: str, limit: int
) -> List[Tuple[str, float]]:
    """Exact node_id, tree_path, or title matches."""
    hits: List[Tuple[str, float]] = []
    if NODE_ID_RE.match(query):
        node = read_node(connection, query)
        if node is not None:
            hits.append((node["node_id"], 0.0))
    rows = connection.execute(
        "SELECT node_id FROM nodes WHERE title = ? OR tree_path = ? "
        "ORDER BY node_id LIMIT ?",
        (query, query, limit),
    ).fetchall()
    for index, row in enumerate(rows, start=1 if not hits else 0):
        if row["node_id"] not in {node_id for node_id, _ in hits}:
            hits.append((row["node_id"], float(index)))
    return hits[:limit]


def _short_query_stage(
    connection: sqlite3.Connection, query: str, limit: int
) -> List[Tuple[str, float]]:
    """Exact structured hits followed by a bounded literal substring scan."""
    hits = _exact_structured_stage(connection, query, limit)
    seen = {node_id for node_id, _ in hits}
    if len(hits) >= limit:
        return hits
    escaped = "%" + _like_escaped(query) + "%"
    rows = connection.execute(
        "SELECT f.node_id FROM fts_terms f "
        "JOIN nodes n ON n.node_id = f.node_id "
        "WHERE f.title LIKE ? ESCAPE '\\' OR f.body LIKE ? ESCAPE '\\' "
        "ORDER BY f.node_id LIMIT ?",
        (escaped, escaped, limit),
    ).fetchall()
    for row in rows:
        if row["node_id"] in seen:
            continue
        hits.append((row["node_id"], float(len(hits))))
        seen.add(row["node_id"])
        if len(hits) >= limit:
            break
    return hits


def _tree_title_stage(
    connection: sqlite3.Connection, query: str, limit: int
) -> List[Tuple[str, float]]:
    """Structure navigation: exact id/path/title, then title substring."""
    hits = _exact_structured_stage(connection, query, limit)
    seen = {node_id for node_id, _ in hits}
    escaped = _like_escaped(query)
    if len(hits) < limit:
        remaining = limit - len(hits)
        rows = connection.execute(
            "SELECT node_id FROM nodes WHERE title LIKE ? ESCAPE '\\' "
            "ORDER BY node_id LIMIT ?",
            ("%" + escaped + "%", remaining),
        ).fetchall()
        for index, row in enumerate(rows):
            if row["node_id"] in seen:
                continue
            hits.append((row["node_id"], float(len(seen) + index)))
            seen.add(row["node_id"])
    return hits


def _merge_shortlists(
    shortlists: Sequence[List[Tuple[str, float]]],
) -> Dict[str, Dict[str, Any]]:
    """Merge stage shortlists into {node_id: {stage: rank}}."""
    merged: Dict[str, Dict[str, Any]] = {}
    for stage_index, shortlist in enumerate(shortlists):
        for node_id, rank in shortlist:
            entry = merged.setdefault(node_id, {})
            entry["stage_{}".format(stage_index)] = rank
    return merged


def _best_rank(entry: Dict[str, Any]) -> float:
    return min(value for value in entry.values())


def retrieve(
    connection: sqlite3.Connection,
    query: str,
    mode: str,
    top_k: int,
    contracts: Dict[str, Any],
) -> Dict[str, Any]:
    """Run one deterministic retrieval over an open read-only index connection."""
    limits = contracts["limits"]
    max_top_k = int(limits["max_top_k"])
    if top_k < 1 or top_k > max_top_k:
        raise IndexError(f"top_k must be within 1..{max_top_k}")
    if mode not in contracts["retrieval_modes"]:
        raise IndexError(f"mode must be one of {contracts['retrieval_modes']}")

    query = query.strip()
    if not query:
        raise IndexError("query must not be empty")

    shortlist_limit = top_k * int(limits["bm25_shortlist_expansion"])
    trigram_min = int(limits["trigram_min_query_length"])
    query_len = len(query)
    stages: List[str] = []

    if mode == "bm25":
        if query_len < trigram_min:
            stages.extend(["exact_structured_path", "short_substring_scan"])
        else:
            stages.append("unicode61_shortlist")
        shortlists: List[List[Tuple[str, float]]] = []
        if query_len < trigram_min:
            shortlists.append(_short_query_stage(connection, query, shortlist_limit))
        else:
            shortlists.append(
                _bm25_shortlist(connection, "fts_terms", query, shortlist_limit)
            )
            stages.append("trigram_shortlist")
            shortlists.append(
                _bm25_shortlist(connection, "fts_trigram", query, shortlist_limit)
            )
        merged = _merge_shortlists(shortlists)
        ranked = sorted(
            ((node_id, _best_rank(entry), entry) for node_id, entry in merged.items()),
            key=lambda item: (item[1], item[0]),
        )[:top_k]
        hits = []
        for position, (node_id, _, entry) in enumerate(ranked):
            node = read_node(connection, node_id)
            if node is None:
                continue
            payload = _hit_payload(connection, node, contracts)
            payload["score"] = round(1.0 / (1.0 + position), 6)
            payload["score_components"] = {
                "primary": "bm25",
                "bm25_rank": position,
                **{"stage_{}".format(i): entry.get("stage_{}".format(i)) for i in range(len(shortlists))},
            }
            hits.append(payload)
        return {
            "status": "observed",
            "mode": "bm25",
            "stages": stages,
            "top_k": top_k,
            "hit_count": len(hits),
            "hits": hits,
        }

    if mode == "tree":
        stages.append("title_navigation")
        title_hits = _tree_title_stage(connection, query, top_k)
        hits = []
        for position, (node_id, _) in enumerate(title_hits):
            node = read_node(connection, node_id)
            if node is None:
                continue
            payload = _hit_payload(connection, node, contracts)
            exact = bool(
                node["title"] == query
                or (NODE_ID_RE.match(query) and node["node_id"] == query)
                or node["tree_path"] == query
            )
            payload["score"] = round(1.0 / (1.0 + position), 6)
            payload["score_components"] = {
                "primary": "tree",
                "title_exact": exact,
                "title_substring": not exact,
            }
            hits.append(payload)
        return {
            "status": "observed",
            "mode": "tree",
            "stages": stages,
            "top_k": top_k,
            "hit_count": len(hits),
            "hits": hits,
        }

    # hybrid: BM25 shortlist + tree expansion
    if query_len < trigram_min:
        stages.extend(["exact_structured_path", "short_substring_scan"])
    else:
        stages.append("unicode61_shortlist")
    shortlists = []
    if query_len < trigram_min:
        shortlists.append(_short_query_stage(connection, query, shortlist_limit))
    else:
        shortlists.append(_bm25_shortlist(connection, "fts_terms", query, shortlist_limit))
        stages.append("trigram_shortlist")
        shortlists.append(_bm25_shortlist(connection, "fts_trigram", query, shortlist_limit))
    stages.append("tree_expansion")
    merged = _merge_shortlists(shortlists)
    ranked = sorted(
        ((node_id, _best_rank(entry), entry) for node_id, entry in merged.items()),
        key=lambda item: (item[1], item[0]),
    )[:top_k]
    tree_max_children = int(limits["tree_max_children"])
    decay_ancestor = float(contracts["score_model"]["expansion_decay_ancestor"])
    decay_child = float(contracts["score_model"]["expansion_decay_child"])

    base_by_node: Dict[str, float] = {}
    origin: Dict[str, Dict[str, Any]] = {}
    for position, (node_id, _, entry) in enumerate(ranked):
        base = round(1.0 / (1.0 + position), 6)
        base_by_node[node_id] = base
        origin[node_id] = {
            "primary": "bm25",
            "base_score": base,
            "bm25_rank": position,
            **{"stage_{}".format(i): entry.get("stage_{}".format(i)) for i in range(len(shortlists))},
        }
    for node_id in list(base_by_node):
        node = read_node(connection, node_id)
        if node is None:
            continue
        for ancestor in read_ancestors(connection, node_id):
            candidate_score = base_by_node[node_id] * decay_ancestor
            if candidate_score > base_by_node.get(ancestor["node_id"], -1.0):
                base_by_node[ancestor["node_id"]] = candidate_score
                origin[ancestor["node_id"]] = {
                    "primary": "ancestor",
                    "base_score": base_by_node[node_id],
                    "expanded_from": node_id,
                }
        for child in read_children(connection, node_id, limit=tree_max_children):
            candidate_score = base_by_node[node_id] * decay_child
            if candidate_score > base_by_node.get(child["node_id"], -1.0):
                base_by_node[child["node_id"]] = candidate_score
                origin[child["node_id"]] = {
                    "primary": "child",
                    "base_score": base_by_node[node_id],
                    "expanded_from": node_id,
                }

    ordered = sorted(base_by_node.items(), key=lambda item: (-item[1], item[0]))
    hits = []
    for node_id, score in ordered[:top_k]:
        node = read_node(connection, node_id)
        if node is None:
            continue
        payload = _hit_payload(connection, node, contracts)
        payload["score"] = round(score, 6)
        payload["score_components"] = origin[node_id]
        hits.append(payload)
    return {
        "status": "observed",
        "mode": "hybrid",
        "stages": stages,
        "top_k": top_k,
        "hit_count": len(hits),
        "hits": hits,
    }
