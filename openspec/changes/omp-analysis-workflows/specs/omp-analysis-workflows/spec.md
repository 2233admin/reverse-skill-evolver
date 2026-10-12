# OMP analysis workflows

## Scope and authorization

The owner requested implementation of four proposed OMP workflows on 2026-10-13 and explicitly allowed testing to follow later. Deliver reusable code, discoverable skill navigation, four open issues, and a reviewable Draft PR based on the native IDA support branch.

This change does not call models, start IDA or target processes, run tests, install additional runtime dependencies, modify host configuration, or merge unverified work. Syntax checks and source review are recorded separately from behavioral verification.

## Contracts

- The native collector accepts OMP's actual worker namespace and an explicit native database ID. It emits a versioned source-identified snapshot and an evidence-based candidate report with bounded subsequent work and coverage flags.
- Version comparison consumes two snapshots, user mappings or unique meaningful names, and reports observable fields and unresolved matches. It does not infer identity from matching RVA, mutate databases, or claim semantic equivalence from partial bytes.
- The dynamic plan consumes a snapshot/candidate report and explicit module identity, validates static EA/RVA relationships, and generates a finite Frida observation script. It leaves live identity and execution hypotheses unverified until actual target observations exist.
- JS replay accepts JSON fixtures and a supplied signing callback in OMP's persistent JS runtime. It isolates callback inputs and reports per-case outcomes, errors, omitted cases and aggregate coverage. Fixture data never becomes executable code.

## Required future verification

- Collector: positive/no-match cases, native helper errors, non-function references, output and query budgets, skipped pseudocode and assembly fallback.
- Comparison: layout change, explicit mappings, repeated/automatic symbols, unsupported architecture, inconsistent RVA, incomplete fingerprints and coverage.
- Dynamic plan: correct/incorrect module, actual binary identity, ASLR, executable ranges, supported architecture, hit/no-hit and event/time limits.
- JS replay: synchronous/asynchronous callbacks, match/mismatch/error, JSON validation, input isolation, duplicate IDs, partial and empty runs.

Implementation delivery and runtime acceptance are separate. Keep the issues open and the new PR in draft until later validation and review establish acceptance; do not reuse the earlier read-view checks as proof for these new functions.
