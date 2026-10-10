# Changelog

## reverse-skill-evolver-cli 1.1.1

- Bound IDA startup probes to one deadline and Codex CLI management calls to 30 seconds.
- Stream MCP SSE events and detect diagram formats from a bounded prefix.

## Burp MCP Full Control 1.0.2

- Bound bridge concurrency and HTTP deadlines; stream history pages and response previews without retaining or decoding whole payloads.
- Use linear-time RE2/J patterns for user-supplied Burp regexes; unsupported Java regex constructs return a client error.
- Skip unchanged Java compilation and packaging in the standalone build scripts.

## reverse-skill-evolver-cli 1.1.0

- Add bounded routing evolution with frozen inputs, full candidate lineage, auditable artifacts, strict response parsing, and Windows invocation bounds.
- Add semantic TraceCard validation and the `tracecard-validate --input FILE` command.
- Align the OpenCLI evolve contract with Click validation and usage errors.

## Burp MCP Full Control 1.0.1

- Refill the bounded asynchronous request window as requests complete, while preserving the deadline, concurrency cap, and early-hit behavior.
- Add deterministic scheduler regressions for out-of-order completion and deadline cancellation.
