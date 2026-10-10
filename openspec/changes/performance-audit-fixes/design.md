# Design: performance audit fixes

## Data flow

```text
stdin JSONL
  -> parse one complete line
  -> admit at most MAX_IN_FLIGHT requests
  -> HTTP request with wall-clock deadline
  -> one JSON-RPC response

Burp history
  -> reverse ListIterator
  -> count/filter while retaining only requested page
  -> serialize page + exact total

HTTP response
  -> stream SSE lines and retain selected event only
  -> bounded preview conversion for Burp tool responses

IDA startup / Codex CLI
  -> one monotonic operation deadline
  -> each probe or subprocess receives remaining time
```

## Decisions

- Use RE2/J 1.8 for untrusted `search_history` and `extract_from_response` patterns. Its linear-time guarantee is preferable to attempting an incomplete regex-danger heuristic. Java-only constructs unsupported by RE2/J fail as client input; document this behavior in the Burp README and test rejection.
- Treat each `readline` `line` event as one complete JSON-RPC frame. A parse error clears/discards that frame; it never becomes a prefix for later frames.
- Bound bridge requests with a named fixed in-flight cap; pause stdin at capacity and resume as requests finish. Use a wall-clock timer that destroys the HTTP request, not a Promise race.
- Stream SSE event lines while preserving response-ID selection and validation of every event, including malformed events after the matching response. `HttpResult.raw_content` has no in-repository consumer; remove it rather than retaining an unbounded duplicate.
- Preserve Burp's text decoding by using `ByteArray.subArray(...).toString()` and growing the byte prefix until the requested character preview is complete. Do not decode a whole payload merely to slice it.
- Use one monotonic deadline for IDA readiness and one bounded timeout per Codex management operation; report actionable timeout errors.
- Keep build scripts standalone. After ensuring dependencies exist, skip `javac` and repackaging only when the output JAR is newer than all Java sources and dependency JARs.
- Auto-detect diagram type from a bounded leading prefix, reading further only to skip leading whitespace or complete a known prefix.

## Failure modes and handling

- Invalid JSONL: emit the existing parse-error envelope, discard only that line, continue with the next frame.
- Bridge timeout: destroy the request and return the existing tool error envelope; discovery failure continues to permit stdio initialization with no tools.
- Request-cap reached: pause stdin; always decrement the active count and resume in `finally`, including request failures.
- Unsupported/invalid regex: return the existing Burp tool error result; never fall back to Java's backtracking engine.
- SSE malformed event: preserve current protocol error behavior and continue validating the remaining stream before returning.
- Deadline expiry: stop polling or terminate the child process, then raise the project's existing actionable error type.
- Build freshness check failure: rebuild. Missing dependency downloads still fail the build rather than treating the output as fresh.

## Compatibility and rollback

The only intentional user-visible narrowing is regex syntax in two Burp tools. Runtime output shapes and page ordering remain unchanged. Reverting the change restores the prior behavior; no persisted data is migrated or deleted.
