# Issue #2 repair and verification

**Verification point:** 2026-10-10 UTC. Results below describe only commands run in this session.
**Tracker:** [Issue #2](https://github.com/2233admin/reverse-skill-evolver/issues/2).

## Repairs

- Evolution reflection now receives frozen task, route, failure-diagnostic, and successful-case context. Candidate artifacts, parent lineage, and input/candidate content digests are retained for reproducibility.
- Model route answers are parsed as whole responses with one documented OMP progress-line framing exception. Windows process argv size is measured after command-line quoting before model invocation.
- TraceCard v2 now has structural and semantic validation, including evidence-reference integrity, oracle results, outcome-affecting unknowns, validated tier, and promotion-candidate constraints. The `tracecard-validate --input FILE` CLI command exposes this validation without claiming external evidence truth.
- OpenCLI marks required evolve options and the Click boundary rejects incompatible budgets as usage errors.
- Burp async candidate scheduling replenishes its bounded request window on completion rather than submission order. Its Java regression covers refill while the first request is blocked, concurrency cap, early-hit drain, and deadline cancellation/no post-deadline submission; the regression is wired into Gradle `check`.
- Release notes and package versions are recorded in `CHANGELOG.md`; Python CLI is 1.1.0 and Burp extension is 1.0.1.
- Promotion remains a manual review decision.

## Verification evidence

| Check | Observed result |
|---|---|
| `python -m pytest -q` | Exit 0; 152 passed, 1 skipped in 7.64s. |
| Real CLI, valid TraceCard JSON | Exit 0; JSON envelope reported `ok: true`, `command: tracecard-validate`, and `semantics_valid: true`. |
| Real CLI, invalid `{}` TraceCard JSON | Exit 5; JSON envelope reported `ok: false`, `ToolOperationError`, and `schema_version must be 2`. |
| JDK availability | `java` and `javac` available as Temurin 25.0.4.1. |

The Java Gradle gate was not run: this checkout has no `gradlew`/`gradlew.bat` or wrapper JAR, and the host's standalone Gradle command was unavailable in the earlier environment check. The project config targets Java 21; the available JDK is 25. No compile/test result is claimed for Java.

Live OMP/model and MCP calls were not made. Issue #2 records that `idalib-mcp` is not installed; no service was launched and no live-server result is claimed.
