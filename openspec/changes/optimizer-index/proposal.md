# Proposal: Bound index resources and remove repeated scans

## Why

The authorized audit repair covers ten current index defects: DB-01/02/03, MEM-01, ALG-01/02/03, DATA-01/02 and SEC-02. A supported byte-limited input can still trigger excessive allocation or quadratic work; multi-document updates repeatedly scan the same FTS corpus, and tree inspection transfers rows that its output discards.

## What changes

- Bound IDA export reads to the 64 MiB budget plus one sentinel byte and close the reader on all paths.
- Batch touched-document FTS deletion and read preserved IDA FTS bodies once.
- Add an optional schema-v1 title index on explicit apply; keep legacy databases readable without migration on read/plan.
- Count descendants exactly and return at most 500 wide rows in the existing order, from one read snapshot.
- Enumerate sibling ordinals once; count syntax names by parent and title; prepare removed and seen sets once.
- Cache target anchor lookup once per link-building transaction and scan Markdown delimiters forward with the existing lexical semantics.
- Add behavioral/resource regressions and repeatable baseline/current evidence.

## Scope and approval

Issue #57 and the user's handoff authorize implementation, tests, commit, branch push and Draft PR creation. No new external API, dependency, configuration, schema version or CLI output field is needed. No source file outside the issue's ownership list is changed. PR review remains pending; implementation does not wait for another proposal approval.
