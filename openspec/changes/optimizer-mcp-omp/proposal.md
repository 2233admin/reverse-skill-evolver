# Repair MCP and OMP recovery and Burp callbacks

关联 #58；父级 #55。用户已授权实现、测试、提交、推送本分支及一个 Draft PR。

## Why

At baseline `d6d085364508215d0019b83f32dc58dd8f170c9e`, malformed stdio frames poison subsequent frames (MEM-02), chunked MCP responses exceed the probe deadline (ER-01), concurrent Burp registration installs duplicate callbacks (CONC-001), custom native triage regexes lack a runtime bound (SEC-03), and limited signature replay snapshots unused fixtures (MEM-03).

## What changes

- Parse each completed stdio line independently and report malformed JSON.
- Keep the synchronous MCP API and injectable transport, use cancellable HTTPX network I/O, consume SSE through the matching RPC response, and share the absolute deadline through negotiation and cleanup.
- Lock Burp callback installation and rule updates/clearing without changing attack scheduling.
- Keep native IDA helpers in their owning worker; isolate custom regex matching in one owned process per batch, terminate/reap on failure, and preserve Python regex syntax and default outputs.
- Validate the complete signature suite, freeze its total, and snapshot/hash only the selected prefix before callbacks run.

## Boundaries and delivery

Only #58's production/test paths, this change directory, and its evidence report are writable. No dependency, CLI/output-v1, ASR/routing, authorization/capability, index identity, version, main-branch, release, or global configuration change. No child agents or competing worktrees. Code Intel's recorded missing DAG registry is accepted; use bounded source reads. Deliver one self-contained Draft PR against main with per-ID original reproduction, behavior parity, improvement, and explicit unverified boundaries.
