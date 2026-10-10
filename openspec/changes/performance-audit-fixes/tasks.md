# Tasks

## Implementation
- [x] Stream MCP SSE events and keep only the selected response.
- [x] Share one readiness deadline across IDA discovery and tool-list probes; bound Codex operations.
- [x] Parse JSONL frames independently; cap Node bridge concurrency and destroy timed-out HTTP requests.
- [x] Page Burp history without full filtered-list copies; stop unfiltered traversal at the requested page.
- [x] Use RE2/J for user regexes and bounded decoded previews for HTTP/WebSocket responses.
- [x] Detect diagrams from a bounded prefix and cache invariant header matching.
- [x] Skip unchanged Java builds in both standalone scripts; fail closed on missing dependencies.
- [x] Add behavior regressions, compatibility documentation, changelog entries, and Python/Burp version bumps.

## Verification
- [x] `python -m pytest -q` — 162 passed, 1 skipped.
- [x] `node --test burp-mcp-full/mcp-bridge.test.js` — 4 passed.
- [x] Windows `build.bat` compiled and packaged the extension; Java performance and scheduler regression mains passed.
- [x] Both manual build scripts skipped compilation/packaging for a fresh artifact; `bash -n build.sh` passed.
- [x] Diagram prefix behavior covered by the Python suite.
- [ ] Gradle `check` unavailable in the environment; Java sources and both regression mains were compiled/run directly.
- [ ] Bash changed-input rebuild path unavailable: WSL has no JDK 21; the fresh-artifact Bash path passed.
- [x] Commit and push the new branch to GitHub; do not create an issue, PR, or merge.
