# Tasks

1. **Repair evolution feedback, response parsing, and Windows process bounds.** Update `reverse_skill/evolution.py`; add deterministic reflection, parser, and preflight tests in `tests/test_evolution_contracts.py`. Do not call live OMP. Verify candidate command serialization before any invocation.
2. **Make run artifacts auditable.** Retain curated/ancestor candidate text, parent lineage, and catalog/fixture/candidate content digests. Add a fake-OMP regression that prunes candidates and checks the surviving run can be reconstructed.
3. **Enforce TraceCard semantics at a real boundary.** Update schema/template/skill, implement stdlib `validate_trace_card`, expose `tracecard-validate --input FILE` through the CLI, and cover valid/invalid semantic records plus CLI envelopes. Keep external evidence truth human-reviewed.
4. **Align the evolve CLI contract.** Mark required OpenCLI options and return usage errors for invalid cross-option budgets. Add exact envelope, no-runner, and manifest/Click correspondence tests.
5. **Remove scheduler head-of-line blocking.** Use a completion-driven bounded window in the Burp async scheduler; add a deterministic test wired into the project Java check/test gate, without network calls or a runtime dependency.
6. **Document the repair.** Add a repository-local report referencing issue #2, describing the behavior changes and recording only parent-observed test/runtime evidence and remaining environment limitations.
7. **Integrated verification and PR preparation.** Parent runs `python -m pytest -q`, the real CLI smoke cases, the Java test/build gate if available, and live MCP only if an already-installed service exists. Independently review the integrated diff; create a PR related to #2 only after evidence is ready. Do not merge.
