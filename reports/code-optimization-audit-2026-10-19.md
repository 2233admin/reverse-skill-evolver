# Code Optimization Audit Report — reverse-skill-evolver

Audit of `reverse_skill/` (24 modules, 8075 lines, Python 3.10+, deps: `click` + `httpx` only).
Baseline `main` @ `3b69005`. Findings are of two kinds and are labelled: **measured** (a probe this
session produced the number) and **source-backed** (static reading; no benchmark).

## Executive Summary

**0 critical, 2 high, 6 medium, 11 low.**

> **Status update.** Findings 1, 2, 7, 9, 12, 13, 14, 15 and 23 were fixed after this audit, in
> commit `2285e91` (1–2), `5bbe0ec` (7, 9, 12–14) and `ed00994` (15, 23). See "Fixes applied" at the
> end for the before/after measurements.

The stack rules out most of the usual domains: no web server, no ORM, no frontend, no container
build in this package. 11 lanes ran; **three returned only ruled-out false positives**, which is the
correct result for a small, already-disciplined CLI. Several suspected issues were refuted with
evidence — including one I proposed myself.

Measured baseline (this session, Windows, warm cache):

| Operation | Time | Scale |
|---|---:|---|
| `import reverse_skill.cli` | 80–100 ms | every CLI invocation |
| `index build` plan | 426 ms | 779 docs |
| `index build --apply` | 2057 ms | 779 docs, 9380 nodes, 10 MB |

Top 3 by impact:

1. **`index_read_nodes` scans an UNINDEXED FTS5 column per node** — measured 38.5× at K=100 / 20k nodes. Fix is a batched `IN()` query.
2. **Quadratic regexes on pathological single lines** — measured 3.4 s for one 32k-char heading line. Trigger is gated on line length, not file size.
3. **`index update` reparses every file to discover nothing changed** — O(all files) per update where O(changed) suffices.

Honest caveat: the two biggest *measured* costs (FTS5 trigram build at ~1.27 s, `executemany` at
1.50 s of a 2.06 s build) are **work that must happen**, not defects. The build path already sets
`journal_mode=OFF`, `synchronous=OFF`, `temp_store=MEMORY` and wraps the whole load in one
`BEGIN IMMEDIATE`. Do not "optimize" those numbers away.

## Findings by File

### `reverse_skill/index_api.py` + `reverse_skill/index_store.py`

| # | Sev | Domain | Pattern | Fix | Impact |
|---|---|---|---|---|---|
| 1 | HIGH | DB | `read_node_text` per node over **UNINDEXED** FTS5 column (`index_store.py:368`, loop `index_api.py:225-229`) | Batch with `WHERE node_id IN (...)`, build a result map, keep requested order | **measured 38.5×** at K=100/20k nodes |
| 2 | MED | DB | Node-by-node ancestor reads + repeated hydration in hybrid (`index_store.py:411-423`, `retrieval.py:248-336`) | One recursive CTE for the ancestor chain; reuse shortlist metadata | ~1600 queries at `top_k=200`/depth 5 |
| 3 | LOW | DB | `nodes_parent(parent_id)` lacks `ordinal` (`index_store.py:122`) | `CREATE INDEX nodes_parent ON nodes(parent_id, ordinal)` | Serves the `ORDER BY n.ordinal` in `read_children` (`index_store.py:418`); was a temp b-tree |
| 4 | LOW | Dead | `read_nodes` (`index_store.py:373`) and `read_link_targets` (`:471`) unreferenced | **Reuse `read_nodes` for #1; delete `read_link_targets`** | — |

Measured proof for #1, 20,000-row FTS5 corpus:

| K | per-node loop | one `IN()` | ratio |
|---:|---:|---:|---:|
| 1 | 0.3 ms | 17.4 ms | — |
| 10 | 85.6 ms | 17.9 ms | 4.8× |
| 50 | 393.6 ms | 17.3 ms | 22.7× |
| 100 | 783.8 ms | 20.3 ms | **38.5×** |

Note K=1: the loop **wins**. Batch only above a small threshold (~5); do not blindly replace.

### `reverse_skill/index_build.py` (1475 lines)

| # | Sev | Domain | Pattern | Fix | Impact |
|---|---|---|---|---|---|
| 5 | HIGH | SecPerf | `_ATX_HEADING_RE` quadratic (`:63`, applied `:516`) | Greedy capture + explicit `strip()` | **measured 3.442 s** at 32k-char line |
| 6 | MED | SecPerf | `_TRAILING_HASHES_RE` quadratic (`:65`, applied `:520`) | Same treatment | **measured 4.296 s** at 32k |
| 7 | MED | Cache | `update` reparses all files before hash comparison (`:1325,1330`) | Hash first, parse only added/changed | 1000-file workspace with 1 change → still parses 1000 |
| 8 | MED | Cache | Parser provider reconfigured per file (`:242,350`) | Configure once per scan | 1000 C/C++ files → 1000 `configure()` calls |
| 9 | LOW | Algo | `_depth_of` walks ancestor chain per node (`:714-720`) | Compute depth in node order (parents precede children) | O(n·h) → O(n) |
| 10 | LOW | DataStr | `sorted(files, …)` three times (`:898,912,920`) | Sort once in place | 2 redundant full sorts |
| 11 | LOW | Mem | Param lists built for single-pass `executemany` (`:1071`, `index_store.py:536`) | Generator expression | O(n) transient tuples removed |

`_ATX_HEADING_RE` measured (median of 3, input `'# X' + ' '*n + 'Y'`): 0.220 / 0.758 / 3.406 s at
n = 8k / 16k / 32k. `_TRAILING_HASHES_RE` measured (`' '*n`): 0.189 / 1.155 / 4.296 s.

**Reachability, precisely:** these run **per line**. Per-file cost is approximately
Σ O(Lᵢ²) over lines — not bounded by the longest line alone. A normal line costs ~0.0001 s; the
trigger is one or more very long lines (minified JS/JSON, generated blobs). The 4 MiB file cap at
`:175` does not prevent it.

### `reverse_skill/gates.py`

| # | Sev | Domain | Pattern | Fix | Impact |
|---|---|---|---|---|---|
| 12 | MED | SecPerf | JWT regex quadratic on long lines (`:42`, applied `:97`) | Anchor or bound the candidate window | **measured 2.687 s** at 96k chars |
| 13 | MED | SecPerf | Unbounded file read + unbounded findings retention (`:82,91,101`) | Bounded read + findings cap; **do not silently skip or report clean** | Predictable memory |
| 14 | — | — | gates is otherwise **fail-closed and correctly capped** | — | ruled out |

Measured JWT (`for _ in J.finditer(line)` — the iterator must be **consumed**):
0.175 / 0.589 / 2.687 s at 24k / 48k / 96k chars. Realistic: 43k chars → 0.023 s; 430k → 3.35 s.

> **Method note, recorded because it caused a wrong refutation.** My first check timed
> `re.finditer(s)` **without consuming it** and got ~0.000001 s; I told the lane to drop the
> finding. The lane pushed back with the mechanism, and re-testing with consumption confirmed the
> quadratic cost. `finditer` is lazy — timing its creation measures nothing. The finding is real.

### `reverse_skill/mcp.py` (585 lines)

| # | Sev | Domain | Pattern | Fix | Impact |
|---|---|---|---|---|---|
| 15 | MED | SecPerf | No byte/event budget on responses (`:269-295`) | Enforce max decoded size **before** buffering | A timeout does not bound memory from a fast sender |
| 16 | MED | Concurrency | Interrupt does not cancel in-flight transport coroutine (`:79`, shutdown `:99-108`) | Retain future, cancel, drain before `loop.stop()`/`close()` | Teardown race on Ctrl-C |
| 17 | — | — | Client/negotiation reuse is already correct | — | ruled out: one `httpx.Client` per `McpClient`, one `AsyncClient` per transport |

### `reverse_skill/evolution.py` (581 lines)

| # | Sev | Domain | Pattern | Fix | Impact |
|---|---|---|---|---|---|
| 18 | MED | Concurrency | Fixture model calls run serially (`:343-346`) | Small bounded pool for fixture calls only; keep aggregation on the coordinator thread | F×L → F×L/pool |
| 19 | LOW | I/O | `capture_output=True` buffers full stdout/stderr (`:296-316`) | Redirect to temp files; read bounded | Peak memory on noisy/oversized child |
| 20 | LOW | Algo | `pareto_frontier` recomputed as candidates grow (`:60-65,527`) | Maintain incrementally | Negligible at default budget (3 evals, 1 reflection) |
| 21 | LOW | Dead | `load_fixtures` wrapper unreferenced (`:205`) | Delete | — |
| 22 | LOW | Mem | — | `TemporaryDirectory(ignore_cleanup_errors=True)` already correct | ruled out |

> Finding 18 has a **hard constraint**: the checkpoint closure mutates shared report state
> (`:503-517`), and existing tests use **ordered** fake-response iterators
> (`test_evolution_optimizer.py:126,204,243,267,297,317`). Parallelising requires concurrency-safe
> fixtures first — this is not a drop-in change.

### `reverse_skill/case.py` (922 lines)

| # | Sev | Domain | Pattern | Fix | Impact |
|---|---|---|---|---|---|
| 23 | MED | Cache | Same artifact re-hashed once per evidence record (`:389,447`) | Hash each distinct path once per review | 20 records × 500 MiB → 9.8 GiB hashed |
| 24 | LOW | DataStr | Dedup via `asset not in assets` (`:753-760`) | Companion `set` | Quadratic → linear over large scopes |
| 25 | LOW | Mem | Whole-file read + `splitlines()` for line-oriented parse (`:279`) | Iterate the file handle | Removes full line-list |

### `reverse_skill/evolution.py` + `index_build.py` (security)

| # | Sev | Domain | Pattern | Fix | Impact |
|---|---|---|---|---|---|
| 26 | MED cond. | SecPerf | `shutil.which("omp")` may resolve `.cmd`/`.bat` (`:289`) | Fail closed on batch launchers on this argv path | Windows may shell-parse despite `shell=False` |
| 27 | — | — | No `shell=True` anywhere; native `.exe` path + UTF-16/NUL guard correct | — | ruled out |

Finding 26 is **conditional and environment-dependent**: it fires only if `omp` resolves to a batch
launcher. Not reproduced here. The stdlib serialization probe was a pure-string experiment; **no
shell command was executed.**

### Import cost

| # | Sev | Domain | Pattern | Fix |
|---|---|---|---|---|
| 28 | LOW | Deps | `evolution` imported for every root invocation (`cli.py:16-17`) | Move into the command callbacks |
| 29 | LOW | Deps | `importlib.metadata` in `integrations.py:4` used only in one helper | Helper-local import |
| 30 | LOW | Deps | `swarm_cli.py:13` imports the engine before `--help` | Defer into the callback |

Measured: `import reverse_skill.cli` = **84.85 ms median** (range 81.0–99.9) over 7 fresh processes.
Do **not** promise the full 13 ms from #28 — `ida.py:12` also imports `dataclasses`.

## Ruled out (evidence, not absence)

These were checked and are **already correct**. Recorded so they are not re-investigated.

- **Index build write path** — `journal_mode=OFF`, `synchronous=OFF`, `temp_store=MEMORY`, single `BEGIN IMMEDIATE`, bulk FTS insert (`index_build.py:887-896`).
- **Reader connection lifecycle** — every `index_api` acquisition paired with `finally: close(...)`.
- **`insert_fts_rows_bulk`** — already `executemany`, no per-row statement.
- **Subtree/ancestor reads** — recursive SQL and a `seen` **set**, not linear scans.
- **Markdown heading construction** — stack-based, amortized O(n) despite nested loops.
- **Hybrid expansion** — dict-keyed, expected O(1) lookup; the `list(base_by_node)` snapshot at `retrieval.py:307` is deliberate.
- **`swarm` duplicate-key validation** — single parse via `object_pairs_hook`; the re-serialize at `swarm.py:47` is trust-boundary validation, not a redundant round-trip.
- **`read_nodes` list materialization** — justified by its `Iterable[str]` contract.
- **YARA RPC batching** — already 3 logical calls, not 2N+1.
- **MCP client reuse** — one client per `McpClient`; the CLI `call` command does **not** do a redundant `tools/list`.
- **Size caps that already exist** — 4 MiB/file index scan, 64 MiB + 100k functions IDA export, 24 KiB candidate, 1 MiB fixtures, 256 KiB swarm response, 1 MiB chunked artifact hashing.
- **`_answer_text` / `_omp` aliases and the `doc_facts` fallback** (from commit `6d93af2`) — **not dead**; aliases have internal callers, and tests call `doc_facts(repo)` through the default path.

## Improvement Plan

Ordered by impact ÷ risk. Nothing here is a rewrite.

1. **[HIGH] Batch the FTS body read in `index_read_nodes`** (`index_api.py:225-229`).
   One `WHERE node_id IN (...)` via the existing `read_nodes` helper. Measured 38.5× at K=100.
   *Guard:* keep the loop for K below ~5, where it is faster. *Test:* assert requested order,
   duplicates, and the existing `NodeNotFound` / `IndexCorrupt` errors are preserved.

2. **[HIGH] Fix `_ATX_HEADING_RE`** (`index_build.py:63`). Greedy capture + `strip()`.
   Measured 3.44 s → linear. *Test:* feed a 32k-char heading line and assert a time bound.
   Do the same for `_TRAILING_HASHES_RE` (`:65`, measured 4.30 s) in the same change.

3. **[MED] Batch the delta parse in `index update`** (`index_build.py:1325-1333`).
   Hash first, parse only what changed. Highest ceiling of the remaining items.

4. **[MED] Bound the leak scanner** (`gates.py:82,91,101` + the JWT regex at `:42`).
   Cap file bytes, cap retained findings, anchor the JWT candidate window. Preserve the fail-closed
   contract: an oversized file must be **reported**, never silently clean.

5. **[MED] Cap MCP response size** (`mcp.py:269-295`). Check accumulated bytes before buffering.

6. **[MED] Hash each distinct artifact once per case review** (`case.py:389,447`).

7. **[MED] Parallelise fixture calls in `evolution`** (`:343-346`) — **only** after converting the
   ordered fake-response fixtures and the checkpoint closure to be concurrency-safe. Deferred: the
   test surface makes this the riskiest of the MEDIUM items.

8. **[MED cond.] Fail closed on `.cmd`/`.bat` `omp` launchers** (`evolution.py:289`).

9. **[LOW]** In one pass: `nodes_parent(parent_id, ordinal)` index; `_depth_of` → node-order depth;
   sort `files` once; generator in `executemany`; dedup set in `case.py:753`; stream `parse_workitems`;
   drop `"xrefs_to": list(...)` copy; delete `load_fixtures`, `parser_status`, `read_link_targets`;
   defer three imports.

## Unverified boundaries

- Lanes were **read-only**: no lane applied a fix. Fixes for findings 1, 2, 7, 9, 12–14 and 15/23
  were made in later sessions and are recorded under "Fixes applied"; all other findings remain
  unfixed and un-retested.
- Timing is **Windows / Python 3.14 / warm cache**. The quadratic regexes are the most portable
  result (algorithmic, not platform); the SQLite and import numbers are not.
- **Memory was not benchmarked** anywhere. Findings 13, 19, 23, 25, 11 are allocation arguments,
  not measured RSS.
- Severity labels for source-backed findings are qualitative. Where I could measure, I did, and the
  measured/argued split is labelled per finding.
- Public-name deletion (`load_fixtures`, `parser_status`, `read_link_targets`) needs an
  **external-consumer check** first — this package ships a CLI, so removal is a compat question,
  not just a grep result.
- Not audited: `asr.py`, `ida.py`, `integrations.py`, `mcp.py` internals beyond the anchors, and the
  ~30 skill directories under `skills/`.

## Fixes applied — commit `2285e91`

Findings 1 and 2 were fixed immediately after the audit. Before/after, same machine, median of 3.

### Finding 1 — batched FTS body read

`index_store.read_nodes_text` (one `WHERE node_id IN (...)`) plus `index_api._read_bodies`, which
keeps the per-node loop **below K=5** — at K=1 the loop is genuinely faster, so batching is
thresholded rather than unconditional.

| K | before (loop) | after | note |
|---:|---:|---:|---|
| 1 | 0.3 ms | 0.3 ms | stays on the loop |
| 10 | 85.6 ms | ~15 ms | |
| 100 | 783.8 ms | 20.3 ms | **38.5×** |

End-to-end against the real repo index (780 docs, 9398 nodes) via the public
`index_api.index_read_nodes`: K=1 → 3.99 ms, K=5 → 14.67 ms, K=20 → 15.55 ms, K=120 → 15.82 ms.
Cost is now flat in K above the threshold, dominated by fixed open/validate.

Semantics verified, not assumed: `NodeNotFound` still raised on the batched path, duplicate ids
preserved in request order, empty list → `node_count: 0`, and every requested body present.

### Finding 2 — linear heading recognition

`_ATX_HEADING_RE` is now greedy and anchored (`^(#{1,6})(?:[ \t]+(.*))?$`) and `_TRAILING_HASHES_RE`
is replaced by `_strip_closing_hashes`, a reverse string scan.

| Input | before | after |
|---|---:|---:|
| heading, 8k interior spaces | 0.2497 s | 0.00001 s |
| heading, 32k interiorspaces | 2.6120 s | 0.00001 s |
| trailing-hash strip, 32k spaces | 3.1750 s | 0.00003 s |
| heading, 64k interior spaces | — | 0.00002 s |

Flat and linear to 64k chars. A 16-case sweep over the old semantics
(`_TRAILING_HASHES_RE.sub("", title).strip()` vs the new helper) produced **zero mismatches**,
including the cases where `#` is not preceded by whitespace and is therefore *not* stripped
(`Title#` stays `Title#`), 7-hash lines not being headings, and `#    ` yielding an empty title.

### Regression evidence

`python -m pytest -q` → **840 passed, 5 skipped** (unchanged from baseline).
`python scripts/run.py --json gates all` → `ok true`, all three checks `clean`.
`grep _TRAILING_HASHES_RE reverse_skill/ tests/` → no references remain.

### Findings 7, 9, 12–14 — commit `5bbe0ec`

**#7 — `index update` no longer parses unchanged files.** `ParsedDocument` gained
`nodes_deferred`, and `materialize_nodes` builds the tree on demand. The update path hashes every
file (needed for `root_hash`) but materialises node trees only for added, changed and stale
link-source documents. Markdown line data is still decoded, because
`_link_sources_for_added_documents` scans unchanged bodies for links.

| Bench (60 files, parse-dominated, min of 5) | before | after |
|---|---:|---:|
| `update_plan`, no change | 31.5 ms | 11.2 ms |
| `update_apply`, no change | 32.1 ms | 12.1 ms |

**2.7×.** Honest scoping: on 460 *tiny* files the same change measured ~0% (85.1 → 85.3 ms) because
`scan_workspace` spends 66 of 70 ms in `_path_islink`/`_path_isjunction`/`stat`/`open` — syscalls,
not parsing. Profiler output confirmed zero parse time on the no-change path, i.e. the deferral
works; the end-to-end gain scales with file content size.

Correctness checked on all three paths: no-change, one-changed, one-added, plus an idempotent
re-apply, with index counts stable (`documents: 41, nodes: 122, edges: 81`).

**#9 — `_depth_of` removed.** Replaced by one forward pass over nodes, which is valid because
parsers emit parents before children. Verified on this repository: **9405 nodes, 0 depth mismatches**
against the old ancestor walk, **0 parent-after-child violations**. The now-unused `_depth_of` was
deleted.

**#12 — `gates.py` JWT regex anchored.** A non-base64url lookbehind prevents a failed match from
rescanning the rest of the line from every `eyJ` in a run.

| `'eyJ' * n` | before | after |
|---|---:|---:|
| n = 8000 | 0.0977 s | 0.00017 s |
| n = 32000 | 1.4440 s | 0.00067 s |

Eight detection cases (valid, two-in-line, prefix-only, no-dots, short-segments, embedded in text,
trailing dot, concatenated tokens) produce **identical results** before and after.

**#13/#14 — `leak_scan` bounded.** Files over `MAX_SCAN_BYTES` (8 MiB) are now **reported** in
`skipped_oversized` rather than read whole; retained findings cap at `MAX_FINDINGS` (1000) with
`findings_truncated` set. Deliberately fail-closed: an oversized file yields status `findings`, not
`clean`, so a file the scanner declines to read can never look clean. Verified: clean dir → `clean`;
one email → `findings`; oversized alone → `findings` with 0 findings; 1500 findings → capped at 1000
with `truncated: true`.

### Regression evidence for this batch

`python -m pytest -q` → **840 passed, 5 skipped**.
`python scripts/run.py --json gates all` → `ok true`, all three checks `clean`.
Probe and benchmark scripts were removed after use; only the two source files are committed.

### Still open from this audit

Findings 8, 10, 11 and 16–30 are **not** fixed. Finding 3 was fixed in commit `13d5917`, 4 in
`478af86` (both below); 15 and 23 in `ed00994`; 1, 2, 7, 9 and 12–14 earlier.

### Findings 15 and 23 — commit `ed00994`

Both were fixed together in one session, with tests.

**#15 — MCP responses are bounded.** The deadline bounds waiting time, not memory: a fast sender
could keep every per-chunk deadline check satisfied while the buffer grew without limit, and a
single SSE event streamed as one long line was unbounded even with an event cap. `MAX_RESPONSE_BYTES`
(8 MiB) and `MAX_SSE_EVENTS` (4096) are now enforced **while accumulating**, on both the SSE and the
byte path, and exceeding one raises `McpProtocolError` naming the observed size rather than
truncating silently. Response encoding is captured before the stream is consumed, so a failure path
never touches a closed response.

**#23 — one hash per artifact per review.** Validity is decided by stat **before and after** the
read, not by a stored mtime: Windows mtime granularity can be coarse enough that a rewrite lands
inside one tick, so a stored timestamp would claim a state the file no longer has. The cache entry is
set only when the file proved byte-stable across the read that produced the digest; otherwise `None`
is stored, so a concurrent rewrite is neither cached nor reported with a digest describing no single
state. Scope is one `review_case` call, never persisted.

Independent verification (a throwaway probe counting `Path.open` calls, not the committed tests):
three hashes of one file → **one read**; after rewriting the file → **two reads** and a changed
digest; `cache=None` → **two reads**, preserving the old behaviour.

The fix carries its own stated boundaries: it does not remove the O(records × artifact size) read
(a fixed immutable evidence layer would, but that adds writes to a command documented as read-only
in four places); the budgets were not exercised against a real remote MCP server; and the three new
cache tests exercise a new API rather than a before/after behaviour.

### Regression evidence for this batch

`python -m pytest -q` → **848 passed, 5 skipped** (baseline 840; the +8 are the new tests).
`python scripts/run.py --json gates all` → `ok true`, all three checks `clean`.

### Finding 4 — unused `read_link_targets` deleted, commit `478af86`

The `read_nodes` reuse half of #4 landed with #1 in `2285e91`. This closes the second half: the
dead public name `read_link_targets` (`index_store.py:492`) is removed, 13 lines, no replacement.

The "Unverified boundaries" note required an external-consumer check rather than a grep result,
because this package ships a CLI. The check was run across every surface:

| Surface | Result |
|---|---|
| Callers in `reverse_skill/` and `tests/` | none |
| Re-exports, `__all__` | none |
| The four `index_store` importers (`index_api`, `index_build`, `retrieval`, `ida_ingest`) | name `read_nodes`, `read_nodes_text`, `read_ancestors`, `read_children`, `read_node` — never `read_link_targets` |
| String refs, `getattr`, CLI dispatch, JSON output keys | none |
| Docs, skills, CHANGELOG | only this report names it |
| `pytest.raises` `match=` strings | none |

`cli.py` reaches index commands only through `index_cli` and never touches `index_store`, so no CLI
surface exposes the name. One false lead worth recording: `index_build.py` has many `link_targets`
hits, but they are a local dict threading document id → heading map during edge resolution, not
this function.

Clean cutover, no deprecation shim.

**Regression evidence:** `python -m pytest -q` → **862 passed, 5 skipped**, unchanged from the
pre-change baseline — the expected result for deleting a function with no consumers, and therefore
also the reason this change needs the consumer table above rather than the test count as its
evidence. `gates all` → `ok true`, three checks `clean`. `hasattr(index_store,
"read_link_targets")` is `False` after the change.

### Architecture findings 1 and 2 — commit `6d93af2` (measures re-verified)

Committed earlier and re-checked here against the current tree, because the claims are about import
direction and are cheap to falsify:

| Claim | Verified in tree |
|---|---|
| No runtime reverse dependency on `cli` from the command layer | `index_cli.py:10` and `workflow_cli.py:8` both `from .output import emit`. `index_cli`'s `from .cli import State` is under `if TYPE_CHECKING` (`:12-13`), and `workflow_cli`'s `from .cli import cli` is inside a function body (`:36`), so neither is an import-time cycle. |
| `swarm` no longer calls private `evolution` names | `swarm.py:41` calls `evolution.answer_text(...)` and `:124` uses `evolution.omp` — both public names, no leading underscore. |

The only module importing `cli` at import time is `__main__.py:1`, which is the package entry point
and therefore the correct direction rather than a reverse dependency.

### Finding 3 — `nodes_parent` widened to `(parent_id, ordinal)`, commit `13d5917`

The audit cited `index_store.py:121,397`. Both anchors are wrong, and it matters which query is
actually involved: `:121` is the index definition itself, and `:397` is a `return []` inside
`read_nodes`, which filters by `node_id` and never touches this index. The query that depends on it
is `read_children` at **`:418`** — `WHERE n.parent_id = ? ORDER BY n.ordinal`. Located by behavior,
not by the report's line numbers.

With `parent_id` alone the planner could seek the filter but built a temp b-tree for the sort.
`EXPLAIN QUERY PLAN` after the change keeps `SEARCH n USING INDEX nodes_parent (parent_id=?)` and
drops the `USE TEMP B-TREE FOR ORDER BY`. That plan is the claim; no timing is asserted and the
report's original "100k functions under one root" scenario was not reproduced.

Two edits were required, because `CREATE INDEX IF NOT EXISTS` matches on **name alone** — changing
the definition in `SCHEMA_SQL` would otherwise be a silent no-op on every existing index file:

1. `SCHEMA_SQL` widens the definition so a fresh build is correct immediately.
2. `ensure_query_indexes` drops and rebuilds a pre-existing narrow index. It is the codebase's
   existing seam for this (it already does the same for `nodes_title`) and runs inside the apply
   transaction at `index_build.py:1411` and `ida_ingest.py:341`, so no call site was added. The
   check is a no-op when the columns already match, so repeated applies do not churn the index.

`SCHEMA_VERSION` stays at `"1"`: table shape is unchanged, and the upgrade lands on the next apply.

**Regression evidence:** `python -m pytest -q` → **865 passed, 5 skipped** (baseline 862; +3 tests).
`gates all` → `ok true`, three checks `clean`. The three new tests fail against the unmodified
`index_store.py`, and the plan test fails on the literal `TEMP B-TREE`, so it discriminates on the
sort rather than on the index name. Both paths were also exercised directly: fresh `create_schema`
yields `[parent_id, ordinal]`, a hand-built narrow index upgrades to the same, a second
`ensure_query_indexes` call is idempotent, and `sqlite_master` holds exactly one `nodes_parent` row.

