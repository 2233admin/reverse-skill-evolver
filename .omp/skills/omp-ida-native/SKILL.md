---
name: omp-ida-native
description: Analyze executables and IDA databases in OMP using its built-in ida actions, binary read views, and persistent Python helpers. Use for OMP-native decompilation, xrefs, function maps, database edits, or bounded batch analysis when the native IDA interface is available.
---

# OMP native IDA analysis

## ACTION REQUIRED

1. `NOW`: Identify the input, requested result, permitted database edits, and a check that proves the result.
2. `NOW`: Inspect the available IDA interface. The native schema has `action` values `list`, `open`, `save`, `close`, `exec`, `rename`, `comment`, `set_type`, `make_function`, with `db` and `code` parameters. If OMP exposes it through `xd://ida`, read that interface before invoking it.
3. `NEXT`: Call native `ida` with `{"action":"list"}`. Reuse the matching database or open the input; retain its returned native database ID.
4. `ACT`: Read the overview, select relevant functions, then perform the smallest query or batch that answers the task.

If the native interface is absent or a dependency probe fails, read [setup](references/setup.md). An installed `omp` executable or IDA directory alone does not prove this interface works. When an official Hex-Rays extension exposes `ida_*` MCP tools, use that extension's live schema and guidance; this native workflow does not apply.

## Workflow

### Open and inspect

Call `ida` with `{"action":"open","db":"sample.exe"}` or read `sample.exe` for an overview. Executables use a managed database; existing `.i64`/`.idb` files open in place and may be saved there.

Use `read` views for observations: `sample.exe:main:1-80` for pseudocode, `sample.exe:main:asm` for assembly, `sample.exe:strings`, or `sample.exe:xrefs:main`. Read [native interface examples](references/native-ida.md) when selecting a view, batch helper, or edit operation.

Always pass the returned native `db` ID to subsequent `ida` calls, including when only one database is open. Each database has its own Python namespace, shared with other agents in this project. Coordinate edits and use task-specific variable names.

### Query in bounded batches

Prefer a relevant regex and a small result slice. Combine related queries in one `exec` call when they address the same task. The helpers return Python values; print compact JSON when collecting machine-readable evidence. Record what was filtered or truncated.

Persistent variables are a convenience during analysis. Save durable evidence in the task report: input identity, native database ID, addresses, actual outputs, and remaining unknowns. Reopening a closed database resets the namespace.

### Edit and save

Use native `rename`, `comment`, `set_type`, or `make_function` for permitted database edits. Generated `read` views are immutable text; edit the database through `ida`.

After edits, explicitly `save`, re-read the affected view, and compare it with the requested change. Automatic saving is a recovery aid. Close a database only when this task owns its lifecycle and other users have finished with it; `close` saves by default.

### Handle resource and failure limits

OMP shares database daemons across project agents. Defaults are four open databases, automatic saving after about ten idle seconds when dirty, and saving/closing after fifteen idle minutes. Opening beyond the limit evicts an idle database; all-busy requests fail. Live settings and tool descriptions take precedence over these versioned defaults.

Keep `exec` finite; its default timeout is 120 seconds and applies to the queue wait as well. A queued timeout does not cancel another caller's running request. Report failures and retry only after diagnosing them. Worker termination can lose edits since the last save; verify saved state before continuing.

## 任务完成自检

Before claiming completion, MUST confirm:

- The result comes from the requested input and its actual native database ID.
- Function/address evidence satisfies the task's check; fallback assembly is identified as assembly.
- Permitted edits were saved and checked; no other task's database was closed or discarded.
- The report names omitted results, failures, unresolved questions, and checks not run.

This skill uses OMP's existing IDA implementation. Backend contracts and setup are in the linked references; it does not install or register a separate MCP service.
