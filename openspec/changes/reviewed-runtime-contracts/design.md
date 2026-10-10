# Design: Reviewed runtime contracts

## Decision boundaries

- Keep the evolution loop local and bounded; do not add model providers or runtime dependencies.
- Preserve manual promotion. Candidate search may produce artifacts but cannot accept or promote its own result.
- Keep JSON Schema as the TraceCard structural contract and use a standard-library semantic validator behind the `tracecard-validate` CLI command; runtime validation must not depend on the test-only `jsonschema` extra.
- Keep the Burp attack window bounded; change admission scheduling, not the attack's target-selection or response predicate.

## Data flow

```text
Frozen fixture + route catalog
        ↓
Baseline / curated evaluation ── invalid answer → record exact response + diagnostic
        ↓                                  │
All outcomes ── failures + successful cases + route definitions + frozen tasks
        ↓                                  ↓
Candidate artifact ← reflection prompt ← OMP
        ↓
Full-fixture evaluation → parent-linked immutable run artifacts + input digests
        ↓
Pareto report; never automatic promotion

TraceCard JSON → stdlib parse → validate_trace_card → success/error envelope

Async candidate range → bounded executor + completion queue
        ↓ any task completes
Replenish one slot until hit, exhaustion, or fixed deadline
```

## State and invariant decisions

- A response counts as a valid answer only when the extracted model answer is exactly one allowed one-line JSON object. OMP transport/progress framing may be removed only through an explicit, tested framing rule.
- Candidate text is never inserted into a Windows command line whose actual `subprocess.list2cmdline` UTF-16 length exceeds the platform limit. Check before the first model call; preserve existing stdin use for task/reflection prompts.
- Every evaluated candidate, including curated and non-frontier ancestors, remains recoverable. `results.json` records deterministic content digests for candidate text, catalog, and fixtures and preserves parent IDs.
- TraceCard references are non-empty and resolve uniquely within that card. A passed oracle needs evidence references. `validated` and `promotion_candidate=true` states require all listed oracles passed and no open outcome-affecting unknown. `promotion_candidate=true` requires validated. These checks establish internal consistency, not factual truth of external evidence.
- The request scheduler counts submitted-but-not-completed work against the cap and frees admission when any future completes. Deadline and early-hit rules remain unchanged.

## Failure modes

| Failure | Required behavior |
|---|---|
| Multiple answer objects, prose, malformed JSON, or junk | Record as invalid; do not award a route pass. |
| Candidate exceeds Windows serialized command line bound | Reject before invoking OMP; write no run artifacts. |
| TraceCard has empty, duplicate, or dangling evidence references | Return a useful validation error. |
| Validated/promotion-candidate card has an open outcome-affecting unknown or failed/not-run oracle | Reject validation. |
| Invalid `evolve` budget relationship | Return Click usage exit 2 and the standard JSON usage envelope. |
| Oldest Burp request stalls while newer request completes | Refill the free slot and continue until hit, exhaustion, or deadline. |
| MCP endpoint unavailable | Report the transport/environment failure; do not install or fake a live result. |

## Verification constraints

- Python behavior is verified by the existing full pytest suite plus real CLI invocations.
- Java scheduling regression must execute the same bounded scheduling helper used by production and be wired to the project check/test gate without a new runtime dependency.
- Live MCP validation is conditional: the current host has no `idalib-mcp` installed. This change must not install it or claim successful live service behavior.
