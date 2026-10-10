# Proposal: Repair reviewed runtime contracts

## Why

- The evolution loop cannot reliably target failed routing cases because reflection lacks the frozen task and route context.
- Run reports can lose the curated/ancestor candidate text and do not identify immutable experiment inputs, weakening reproducibility.
- The response parser and TraceCard contract can accept ambiguous or unsupported evidence states.
- The candidate-size guard does not bound the actual Windows process command line.
- The CLI manifest and cross-option validation disagree with the Click contract.
- The Burp async scheduler can stall admission behind one slow oldest request.

## What Changes

### Modify
- Make evolution feedback, response parsing, Windows process sizing, candidate lineage, and TraceCard validation enforce the documented contract.
- Add a real `tracecard-validate` CLI boundary backed by a standard-library semantic validator; keep JSON Schema for structural shape.
- Align `evolve` option metadata and budget errors with Click's usage contract.
- Refill the bounded Burp request window when any request completes.
- Add behavior-focused regression coverage and a local repair record.

### Add
- Deterministic proposal-path tests, TraceCard accept/reject tests, CLI contract tests, and a Java scheduler regression test wired into the project test/check gate.

## Capabilities

### Modified
- Evolution run reproducibility, answer validity, reflection quality, TraceCard validation, CLI usage behavior, and bounded async attack scheduling.

## Impact

- Add: regression tests, a TraceCard validation command, and a local evidence document.
- Modify: evolution runner, CLI/OpenCLI metadata, TraceCard schema/templates, Burp scheduler and relevant documentation.
- Dependencies: no new runtime dependency; test-only dependency only if required by the existing Java test setup.

## Risk

- Strict response validation may expose OMP output framing that was previously tolerated; define the supported framing rather than discarding arbitrary text.
- Stricter TraceCard semantics may reject previously accepted incomplete cards; retain actionable diagnostics and document required evidence.
- Java scheduling changes must keep the global deadline, bounded in-flight window, and early-hit behavior.
- MCP live validation is environment-dependent; do not install missing services or report a simulated request as live proof.

## Approval basis

The user directly authorized fixing the review findings, requested a local document and PR, selected GitHub issue #2, and authorized native OMP child agents. This is the scope for that requested repair.
