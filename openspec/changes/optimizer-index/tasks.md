# Tasks

- [x] Restore remote #57/#55, labels, native parent/children and exact execution binding; confirm clean baseline and no existing PR.
- [x] Copy audit prototypes to this worktree's ignored verification directory; reproduce current source without touching shared audit artifacts.
- [x] MEM-01: bounded export read with sentinel, close and unchanged validation errors.
- [x] SEC-02: forward delimiter scan with legacy lexical equivalence.
- [x] DB-01: batch source deletion and one IDA FTS preservation read, retaining rollback and body validation.
- [x] DB-02: title index on build/apply only, legacy read compatibility and both OR query branches indexed.
- [x] DB-03: exact descendant count, bounded wide rows, original sort and consistent read snapshot.
- [x] ALG-01/02: child ordinals and parent-local syntax counters with row/ID equivalence.
- [x] ALG-03: target/first-title cache shared across all link sources and rebuilt per operation.
- [x] DATA-01/02: one removed/seen set, preserving plan order, IDA retention, ranks and top-k.
- [x] Add meaningful baseline-failing regression tests and compare baseline/current behavior digests.
- [x] Run relevant regressions, full Python suite, gates all, existing offline Java check and grammar checks; record skipped/unavailable checks separately.
- [ ] Commit and push only owned files; create and reread one Draft PR targeting main.
- [ ] Record PR/head/evidence on #57, reread it, set worktree in-review and stop execution.

Independent PR review, three-PR integration and release acceptance are owned by #55 and are not marked complete here.
