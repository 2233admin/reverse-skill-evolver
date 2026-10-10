# Proposal: performance audit fixes

## Why

1. `burp-mcp-full/mcp-bridge.js` retains malformed line input, admits unlimited in-flight calls, and waits indefinitely for HTTP responses.
2. Burp history paging stores and reverses all matches; caller regexes use Java's backtracking engine; preview paths decode full bodies before truncating.
3. Python MCP SSE parsing duplicates response-sized line storage, IDA startup can exceed its configured wait, and Codex subprocesses have no wait bound.
4. Diagram auto-detection reads entire unrecognized inputs, and both manual Java build scripts rebuild unchanged inputs.

## What Changes

- **Add:** bounded parsing/dispatch tests and a Java safe-regex dependency.
- **Modify:** bridge request lifecycle, Burp history/regex/preview paths, Python SSE parsing and process deadlines, diagram prefix detection, Java manual build freshness checks.
- **Preserve:** JSON-RPC response IDs, proxy-history order/total/index semantics, TraceCard behavior, and manual promotion.

## Capabilities

### New
- Safe regex execution for untrusted Burp tool patterns.
- Bounded bridge request lifetimes and outstanding-call admission.

### Modified
- Paginated history uses page-bounded auxiliary storage.
- Large response previews and SSE parsing avoid unnecessary full intermediate representations.
- Startup, child-process, and manual-build paths honor bounded or incremental work.

## Impact

- **Add:** focused Node and Java regressions; OpenSpec packet.
- **Modify:** Python, Java, Node, build scripts, version metadata, and changelog.
- **Dependencies:** add `com.google.re2j:re2j:1.8` to Gradle and both manual Java build scripts. RE2/J rejects Java regex constructs outside its linear-time dialect; preserve supported common syntax and return a clear validation error for unsupported syntax.

## Risk

Regex lookbehind/backreferences and other unsupported Java-only constructs stop working in these two Burp tools. This is an intentional safety contract change. Java packaging and the unavailable local Gradle command require explicit verification evidence.
