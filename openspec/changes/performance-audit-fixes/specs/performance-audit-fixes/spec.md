# Acceptance: performance audit fixes

## Scenario 1 — Recover after malformed JSONL

- **Given** the bridge receives a malformed complete line followed by a valid JSON-RPC line
- **When** it handles both lines
- **Then** it returns a parse-error response for the malformed frame and processes the valid request without retaining or reparsing the earlier line.

**Implementation:** launch `mcp-bridge.js` against a local stub HTTP server; write one malformed line and one valid initialize line; assert the first output is error code `-32700`, the second has the matching ID, and the bridge remains alive.

## Scenario 2 — Bound outstanding bridge work and HTTP waiting

- **Given** a local stub server holds tool responses open and stdin supplies more calls than the configured in-flight cap
- **When** the bridge processes the calls
- **Then** outstanding HTTP requests never exceed the cap; after the deadline, each timed-out request is destroyed and the bridge resumes reading.

**Implementation:** use a local HTTP server with latches/counters; assert peak active requests is at or below the constant, timeout responses arrive, and a subsequent request is accepted.

## Scenario 3 — Use linear-time regexes for Burp search

- **Given** a supported regex and response/history text
- **When** either Burp regex tool runs
- **Then** it returns the same matches using RE2/J.

- **Given** a Java-only unsupported construct such as a backreference
- **When** either tool compiles it
- **Then** the existing error envelope reports invalid/unsupported input and the backtracking engine is never used.

**Implementation:** call the same package-level safe-pattern helper used by both routes; assert supported search results and rejection of an unsupported construct.

## Scenario 4 — Keep history pagination contract with bounded storage

- **Given** history entries with matching and non-matching URL/method/status filters
- **When** a page with a nonzero offset and finite limit is requested
- **Then** items remain newest-first, each index remains the filtered ordinal, and `total` counts every match while only the page is retained.

- **Given** an unfiltered request
- **When** the requested page is materialized
- **Then** the implementation does not scan entries beyond the page after determining the exact total from list size.

## Scenario 5 — Bound preview and diagram detection work

- **Given** a large Burp body with multi-byte text
- **When** a preview limit is applied
- **Then** output matches the prior character limit and decoding uses only the necessary body prefix.

- **Given** an unrecognized diagram extension with a known prefix after arbitrary leading whitespace
- **When** auto-detection runs
- **Then** it selects the same renderer without reading the full source file.

## Scenario 6 — Stream SSE while preserving response validation

- **Given** an SSE response containing unrelated notifications, the matching response, and a malformed later event
- **When** the MCP client consumes it incrementally
- **Then** it selects by response ID, releases unrelated events, and still raises the existing protocol error for malformed later JSON.

## Scenario 7 — Enforce startup and subprocess deadlines

- **Given** IDA probes consume most of the configured readiness window
- **When** startup polling continues
- **Then** every probe receives only the remaining budget and startup ends by the overall deadline.

- **Given** a Codex management subprocess does not exit
- **When** status or registration waits for it
- **Then** the subprocess is terminated at the deadline and the CLI reports an actionable environment error.

## Scenario 8 — Skip unchanged manual Java builds

- **Given** the output JAR is newer than all Java sources and dependency JARs
- **When** either manual build script runs
- **Then** compilation and repackaging are skipped.

- **Given** a source or dependency JAR is newer than the output
- **When** either script runs
- **Then** compilation and packaging run and failures remain nonzero.
