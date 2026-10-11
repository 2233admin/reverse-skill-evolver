# PR integration acceptance evidence

Observed on 2026-10-12. Implementation revision: `b16f50624dfdb05ef23b88c5040649652866728c`; subsequent changes to this report do not change runtime code. This supplements the historical Issue #2 report rather than rewriting its dated results.

## Repairs and verification

- Removed destructive `codex mcp remove` before replacement. Codex's [official add implementation](https://github.com/openai/codex/blob/main/codex-rs/cli/src/mcp_cmd.rs) inserts the same-name entry and writes the server map. Failed or timed-out calls are surfaced without retries; timeout does not prove whether Codex committed an update. Tests verify no separate removal and preservation when add fails before writing.
- Made the Windows reflected-command rejection test explicitly simulate Windows, preserving the Linux acceptance test.
- Added Python and Java CI, using the pinned Gradle Wrapper. Contributor documentation uses the same Windows/POSIX wrapper commands.
- Added successful-response fixtures for all six sequential attack operations: exactly three sends, three hits, zero errors, response fields, Pitchfork's distinct hit shape, and a real full RE2 grep match. No network or Burp instance is used.

| Actually executed | Observed result and scope |
| --- | --- |
| `python -m pytest -q` | 199 passed, 1 skipped; exit 0. Covers registration and platform fixes. Later changes add only Java tests and documentation. |
| `python -m reverse_skill --version` | `reverse-skill, version 1.1.2`; exit 0. |
| `gradlew.bat --no-daemon check` | BUILD SUCCESSFUL; compiles extension/test sources and executes schedulerRegressionTest, including behavior regressions and the new six-operation success fixture. Local JDK 25, Java source/target 21. |
| Two consecutive `build.bat` invocations in the fresh worktree | First produced `build/libs/burp-mcp-full.jar`; second reported compileJava and jar UP-TO-DATE. Both exit 0. |
| `node --check burp-mcp-full/mcp-bridge.js` | Exit 0. |
| `git diff --check` | Exit 0. |
| [PR #17 CI at a389387](https://github.com/2233admin/reverse-skill-evolver/actions/runs/38174971634) | Linux Python 3.10: 199 passed, 1 skipped. JDK 21 Wrapper check passed. This run predates the additional Java success fixture; final-head CI must be checked separately. |
| [PR #18 CI at 1410fb9](https://github.com/2233admin/reverse-skill-evolver/actions/runs/38175032765) | Python and Java passed. This run predates later base synchronization; final-head CI must be checked separately. |

Independent read-only review covered affected Java scheduling/regex/history, Python evolution, rendering, tests, and the incremental repairs. It found the Linux test issue and success-fixture gaps; both are corrected. No additional concrete blocker was found. CodeRabbit's old remove-before-add finding is addressed by removal of that path. PR #18's four-file difference contains only docstrings/Javadocs, and its registration description has been synchronized.

Subsequent CodeRabbit feedback: checkout credential persistence is disabled in both CI jobs. Codex can save a replacement before a later OAuth error. Automatic rollback would contradict Issue #10's no-retry constraint for possibly completed mutations and overwrite the successfully saved requested configuration. Both pre-write and post-write failure paths are now tested; errors explicitly tell the caller to inspect before retrying. Exact restoration after a partially completed external operation is not claimed.

## Issue acceptance mapping

| Issue | Evidence |
| --- | --- |
| #2 | Evolution optimizer reflection test verifies frozen fixtures, full-suite evaluation, lineage, raw responses and digests; contract tests reject invalid whole answers and TraceCards and bound Windows argv. CLI tests verify required options, budget usage errors and envelopes. Scheduler regression verifies completion-driven refill, cap, early hit and deadline cancellation. This document supplies current verification; promotion stays manual. |
| #4 | Project checks runs pytest and Wrapper check; both root READMEs name the actual gates and declare Cargo inapplicable. |
| #5 | Wrapper 8.7 with distribution SHA256; POSIX launcher mode 100755; local Windows and Linux/JDK 21 CI check results above. Scheduler entry point runs behavior tests too. |
| #6 | Reverse history traversal retains only page rows; pagination regression covers ordering, filtering, indices, totals, and boundaries. |
| #7 | Three caller-regex entry points use RE2J. Behavior tests cover accepted search/extract/grep matches, unsupported syntax rejection, and nested repetition on long input. README documents localhost and incompatible Java regex constructs. |
| #8 | Literal case-insensitive technology-header checks; supported, mixed-case and near-match names tested. |
| #9 | Static headers rendered once; exact request text and conversion count tested. Battering Ram retains per-payload substitution. |
| #10 | Get/add have explicit timeout, clear errors and no retry. Remove is eliminated, safely replacing the original get/remove/add sequence; no obsolete remove operation needs a timeout test. |
| #11 | Remaining response timeout and coordinator deadline tested with cooperative and non-cooperative callbacks, no late submission, cancellation, success, errors, counts and hits. The bounded result is the coordinator wait: Burp controls connection establishment, and cancellation may leave transport work running. |
| #12 | Streaming detection tests cover extension dispatch, early read termination, long/Unicode whitespace, chunk boundaries, malformed UTF-8 and fallback. |
| #13 | Both PlantUML backends share bounded staging; tests cover decoding, newline semantics, output copying, working directory, cleanup and invalid input. |
| #14 | Reflection reuses parsed catalog; frozen-input and prompt/archive assertions verify unchanged context. |
| #15 | Pareto tests cover equality, dominance, dominated candidates, tradeoffs and input order; no algorithm replacement. |
| #16 | Fresh-worktree jar production, repeat UP-TO-DATE result, and documented command/output path above. |

## Limits and reusable evidence

No live OMP, IDA MCP or Burp traffic was executed; no runtime service success is claimed. Cargo is not applicable. Required GitHub checks were not configured at the initial snapshot. CodeRabbit status alone does not prove review: PR #18's bot review was skipped. Final review/check/merge state must be reread for each exact head before integration.

Knowledge candidates remain task evidence in this report: same-name Codex add semantics (official source; recheck when changing supported CLI), Windows-only argv bounds (deterministic platform tests), and coordinator cancellation versus transport termination (non-cooperative callback test; recheck when Montoya changes). No knowledge-store update is authorized here; live configuration atomicity and real transport cancellation remain unverified.
