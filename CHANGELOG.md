# Changelog

## reverse-skill-evolver-cli 1.2.0b1 — 2026-10-14

- Add the bounded `reverse-skill-swarm` coordinator/analyst/summarizer workflow with evidence snapshots and interrupted-queue cancellation.
- Fix explicit IDA timeouts, offline diagnostics, Windows launcher ownership, and readiness deadlines.
- Preserve routing-evolution budgets, progress, partial checkpoints, and `not_promoted`.
- Restore Burp bridge recovery and operation-error reporting; align PowerShell alias and capability discovery.
- Ship the source-distributed OMP workflows and a beta testing guide. Model analysis remains advisory; automatic OMP skill discovery and real swarm quality are not certified.

## reverse-skill-evolver-cli 1.1.2

- Bound Codex MCP registration subprocesses with explicit timeouts.
- Remove redundant routing-catalog parsing and Pareto scans.
- Stream diagram format detection and PlantUML staging to avoid whole-file buffers.

## Burp MCP Full Control 2.0.0

- Use RE2J for caller-supplied regexes to avoid backtracking blowups; Java-only regex constructs are now rejected.
- Reduce proxy-history pagination memory and repeated request/header processing; bound sequential attack duration.
- Add a pinned Gradle Wrapper and incremental Windows quick build.

## reverse-skill-evolver-cli 1.1.1

- Apply the serialized Windows command-line limit only on Windows, avoiding rejection of valid candidate prompts on other platforms.

## reverse-skill-evolver-cli 1.1.0

- Add bounded routing evolution with frozen inputs, full candidate lineage, auditable artifacts, strict response parsing, and Windows invocation bounds.
- Add semantic TraceCard validation and the `tracecard-validate --input FILE` command.
- Align the OpenCLI evolve contract with Click validation and usage errors.

## Burp MCP Full Control 1.0.1

- Refill the bounded asynchronous request window as requests complete, while preserving the deadline, concurrency cap, and early-hit behavior.
- Add deterministic scheduler regressions for out-of-order completion and deadline cancellation.
