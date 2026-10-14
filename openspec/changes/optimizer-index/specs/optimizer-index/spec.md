# Optimizer index acceptance scenarios

## IDA byte budget (MEM-01)

Given a normal, exactly-at-budget or oversized export, loading requests no more than `MAX_EXPORT_BYTES + 1` and closes its reader. Exactly-at-budget valid JSON keeps its canonical hash/path/function behavior. Oversize input returns the existing invalid-export error before touching the index. Default import remains a read-only plan.

## Batch mutation and preservation (DB-01, DATA-01)

Given many removed and changed source documents plus imported IDA documents, update filters each FTS projection once, cascades touched source rows, retains ordered removed paths and all untouched IDA nodes/xrefs/bodies. An injected update failure restores the complete database, including optional query-index creation. A rebuild reads preserved IDA FTS bodies once; missing bodies block atomic replacement and preserve the original file.

## Indexed exact retrieval (DB-02, DATA-02)

Given a selective title or path match, new/applied indexes use both title and tree-path B-trees. Exact retrieval retains node-ID priority, original rank gaps on deduplication, ascending node-ID ordering and top-k. Existing schema-v1 files without the optional title index remain queryable and byte-identical after read/plan. One seen set serves all exact rows.

## Bounded tree projection (DB-03)

Given subtrees below, at and above the 500-descendant boundary, output keeps the exact count, original sort and truncation flag while materializing no more than 500 descendant rows. A concurrent WAL update between counting and selecting does not mix snapshots. Ancestors and requested-node payload remain unchanged.

## Stable parser identity (ALG-01, ALG-02)

Given sibling headings, preamble, nested symbols and duplicate names, materialization returns the same full rows and stable node IDs using one ordinal preparation pass. Syntax counters distinguish parents and retain duplicate suffixes. Provider-output regression is explicitly synthetic; real native parser execution requires a preinstalled parser and is listed separately when absent.

## Link extraction and cache lifetime (ALG-03, SEC-02)

Given many links from multiple source documents to the same target, target rows and the first title map are prepared once per transaction. Empty/unknown/duplicate anchors and complete link edges match baseline. Changing the target expires the previous cache and rebuilds stale sources. All strings over delimiter alphabet `[]()x` through length 6 and representative nested/newline/empty/whitespace targets match the former regex; long malformed delimiter spans are consumed once without timing assertions.

## Delivery contract

The Draft PR references #57 and #55 and includes every ID's baseline, repair, behavioral comparison and improvement evidence. Failed, skipped and unrun native/runtime checks are separate. Public CLI/output-v1, version, ASR routing priority, capability/authorization gates and default read-only planning remain guarded by the existing full suite and gates all. Independent review and integration are pending after delivery.
