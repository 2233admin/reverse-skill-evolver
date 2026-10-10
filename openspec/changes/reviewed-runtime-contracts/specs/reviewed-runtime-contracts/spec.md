# Reviewed runtime contracts

## Scenario: Reflection can target a routing failure

**Given** a frozen fixture with an opaque ID, a task whose intent distinguishes two routes, a route catalog, one failed answer, and successful fixtures
**When** the evolution loop constructs a reflection request
**Then** its input contains the exact failed task, relevant route definitions, exact failed response/diagnostic, and successful-case outcomes
**And** the resulting proposal is evaluated against the complete frozen fixture suite.

**Implementation:** Mock the OMP subprocess boundary in `tests/test_evolution_contracts.py`; assert on the concrete prompt passed to `_omp`, then return a proposal and distinct route answers for every fixture. No live model call.

## Scenario: Invalid or ambiguous route output is not a pass

**Given** OMP output contains multiple answer objects, prose surrounding the object, malformed JSON, or trailing junk
**When** the evaluator parses the response
**Then** it records an invalid answer and does not increment the pass count
**And** only explicitly supported OMP framing is excluded from the answer.

**Implementation:** Exercise each output through the evaluator response path; include a separately specified valid framed response.

## Scenario: A run remains reproducible after candidate pruning

**Given** a proposal dominates the curated candidate and an ancestor leaves the Pareto frontier
**When** the run report and artifacts are written
**Then** the curated candidate, every evaluated ancestor, all parent links, and digests of candidate/catalog/fixture content remain available
**And** the results identify the exact input bytes used for each score.

**Implementation:** Run a deterministic fake-OMP proposal path; assert artifact files/digests and lineage after pruning. Do not modify `candidate-runs/run-001/`.

## Scenario: Windows command-line overflow is rejected before model execution

**Given** a candidate with quote/backslash-heavy text whose serialized Windows argv exceeds the process limit
**When** an evolution run starts
**Then** it fails before the first OMP subprocess invocation
**And** no output run is created.

**Implementation:** Monkeypatch platform/serialization or the process boundary deterministically; verify the preflight uses serialized UTF-16 command length, not raw UTF-8 bytes alone.

## Scenario: TraceCard references and status claims are internally consistent

**Given** a TraceCard with unique non-empty evidence IDs, all required oracle results passed with evidence, and no open outcome-affecting unknowns
**When** `reverse-skill tracecard-validate --input <FILE>` validates it
**Then** validation succeeds
**And** `promotion_candidate=true` is permitted only when the card's memory tier is validated.

**Implementation:** Test the public `validate_trace_card(trace)` semantic function and the CLI JSON/human success envelope. Keep JSON Schema structural validation in the contract tests.

## Scenario: Contradictory or dangling TraceCard evidence is rejected

**Given** a TraceCard with empty, duplicate, or dangling evidence refs; a passed oracle without evidence; or a validated/promotion-candidate claim with an open outcome-affecting unknown or non-passed required oracle
**When** the validator processes the card
**Then** it returns a specific validation error
**And** the CLI exits non-zero with the standard operation-error envelope.

**Implementation:** Parameterized negative cases exercise the same public validator and CLI path; assert no case passes merely because an evidence array exists.

## Scenario: Invalid evolution budgets are usage failures

**Given** `max_reflections > max_evaluations - 2`, a value below the independent minimum, or an absent required option
**When** the user invokes `evolve`
**Then** the CLI rejects the invocation with usage exit 2 and `error.code=usage`
**And** it does not call the evolution runner or create output.

**Implementation:** Click runner tests assert exact exit/envelope and no runner call; contract tests compare manifest required flags to Click parameters.

## Scenario: Valid evolution budgets reach the runner

**Given** a valid budget pair such as `(3,1)` or `(4,2)` and required input options
**When** the user invokes `evolve`
**Then** Click forwards the unchanged values and returns the standard success envelope.

**Implementation:** Replace only the execution boundary in CLI tests; do not make OMP calls.

## Scenario: A completed async request frees an admission slot

**Given** a bounded request window where candidate 0 stalls, candidate 1 completes quickly, and a later candidate is a hit
**When** the async attack loop runs
**Then** it submits the later candidate while candidate 0 is still blocked, observes the hit, and preserves the configured in-flight cap/deadline
**And** after cancellation/cleanup no additional candidate is admitted.

**Implementation:** Use latches against the same package-private scheduler helper called by production; do not start Burp or send network requests.

## Scenario: Deadline expiration cancels outstanding requests

**Given** the request deadline expires while a request remains outstanding
**When** the scheduler reaches the expired deadline
**Then** it reports a timeout, cancels the in-flight request, and admits no later candidate.

**Implementation:** Use a deterministic latch-controlled worker against the production scheduler helper; do not start Burp or send network requests.

## Scenario: Missing live MCP service is not misreported as verified

**Given** the local MCP server executable is absent or the endpoint refuses connections
**When** the documented runtime smoke check is attempted
**Then** the failure is recorded as an environment limitation
**And** no dependency is installed and no simulated endpoint is described as live verification.
