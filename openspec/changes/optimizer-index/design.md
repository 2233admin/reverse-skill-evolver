# Design and compatibility

## Database writes

`delete_documents_cascade` inserts touched document IDs into a temporary SQLite table, deletes matching rows from each FTS projection once, then cascades document deletion in the caller's transaction. This avoids parameter chunking that would repeat FTS scans. The existing single-document helper delegates to it. Temporary IDs are dropped before return; failures still roll back document, node, edge, FTS and query-index writes together.

Full rebuild reads only IDA bodies through one FTS/nodes/documents join and groups them by document. Existing collisions, incomplete-body checks, stable identities, parent edges, xrefs and IDA metadata survive. Grouping retains all preserved IDA bodies in Python; its memory scales with that layer, not one document. No node-to-FTS identity map or persistent table is introduced.

New builds include `nodes_title(title, node_id)`. Source updates and IDA imports create that optional index after `BEGIN IMMEDIATE`, using `execute` rather than an implicitly committing schema script. Reads and default plans never create it. Schema version remains 1, and old schema-v1 databases continue to work until an authorized apply adds the index. A no-delta explicit update may add this physical query index without changing the content revision/root hash.

## Tree reads

The recursive ID CTE uses `UNION` to retain cycle termination. An exact count and a separate wide-row query with `LIMIT 500` share a read transaction. Sorting remains `(start_line, depth, ordinal, node_id)` and explicitly excludes the requested node. Full subtree callers retain their original helper behavior. SQLite still traverses all descendant IDs and may sort them; only Python row transfer/materialization is bounded.

## Parsing and links

Ordinals come from a single child enumeration. Syntax occurrence counters use `(parent_index, title)`, preserving nested duplicate identity segments and content-independent node IDs. The sorted removed list is retained for plans; a separate set serves membership. Exact retrieval keeps its initial node-ID hit, original stage ranks, ordering, deduplication and top-k while updating one seen set.

Link caches are allocated after all touched nodes exist and shared by added/changed/stale sources during that transaction. Each target stores the first ordered row, the first heading/preamble for each exact title, and the file/module fallback. Empty anchors use the first row; unknown anchors use the fallback; duplicate headings use the first one. The cache expires when the operation returns.

The Markdown scanner consumes one label delimiter span at a time. All openings before the next `]` have the same success/failure outcome. Missing delimiters terminate that suffix search; successful targets consume through the first `)`. Nested `[` labels, newlines, whitespace stripping and the regex's nonempty raw-target rule remain unchanged. Existing stdlib string searches avoid adding a regex dependency.

## Decisions and limits

- Existing SQLite and stdlib collections/IO are sufficient; no installation or third-party dependency is required.
- All helpers stay in owned modules and have current callers; no public contract or ownership change is required.
- The syntax provider is unavailable locally. Only its existing structure/span output is simulated; no native parser or IDA/Burp session is claimed.
- Python 3.10 grammar is checked. A real Python 3.10 runtime is not available locally; grammar evidence alone is not runtime validation.
- Validation evidence and failures are recorded in the report. Independent review and parent-level integration remain separate from this implementation.
