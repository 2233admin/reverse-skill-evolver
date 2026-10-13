---
name: omp-js-replay
description: Use in OMP to reproduce a captured JavaScript request signature against fixed fixtures using persistent eval, and report exact matches, failures and partial coverage.
---

# JavaScript signature replay

## ACTION REQUIRED

1. Establish the owned target and obtain real captured signature examples. Preserve method, canonical path/body, timestamp, nonce and relevant session inputs in private fixtures. Do not invent expected signatures from a model answer.
2. Inspect OMP's actual `eval` interface and read [replay instructions](references/replay.md). Use its existing persistent JavaScript runtime and module-import support; this skill adds no tool or extension.
3. Import [signature comparison](scripts/signature-replay.mjs), supply the actual reconstructed signing function, and compare a bounded fixture set. Do not execute code provided inside fixture fields or initiate network requests implicitly.
4. Report exact observed coverage, signature mismatches and failures. Synthetic signer cases were checked in Node/Bun and a real OMP persistent eval session; see [scoped evidence](https://github.com/2233admin/reverse-skill-evolver/blob/2233admin/repair-open-issues-15/reports/omp-workflow-verification-2026-10-13/README.md). Examples below remain illustrative, not real third-party capture results.

Keep cookies, keys and full captured requests in private task inputs. The default report retains only input digests, fixture IDs and expected/actual signatures; these signatures can themselves be sensitive. Inspect the artifact before sharing it.

Use task-specific persistent variable names. Do not place keys in host configuration or commit fixtures containing secrets. A successful comparison proves only the listed captures; it does not prove broader authentication compatibility, fresh server acceptance or runtime performance.

## Completion check

- Expected values came from real captures, with timestamp/nonce/session dependencies frozen.
- The actual signing callback was used, not an LLM-produced expected-value oracle.
- Input fixtures were preserved; no third-party request or hidden network activity was introduced.
- Coverage is complete before claiming suite success; failed and mismatched cases remain visible.
- Saved evidence excludes raw request inputs, and observed results are distinguished from examples and untested implementation.
