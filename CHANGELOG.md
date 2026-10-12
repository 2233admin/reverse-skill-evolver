# Changelog

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
