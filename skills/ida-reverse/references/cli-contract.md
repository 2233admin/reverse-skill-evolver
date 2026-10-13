# Python CLI contract

`reverse-skill` is the human and automation entry point for the IDA MCP workflow. The executable is installed from `pyproject.toml`; a source checkout can run the identical interface with `python -m reverse_skill`.

The execution path is:

```text
reverse-skill -> HTTP MCP -> idalib-mcp.exe -> newest usable local IDA
```

No shell runtime is part of this path. `install` may start the upstream interactive installer because login and user interaction are explicitly expected there.

`start --replace-stale` uses Windows PowerShell only to inspect the selected port and stop its verified listener. Healthy services are always reused. An unknown owner is preserved; inspect `Get-NetTCPConnection -LocalPort PORT` and its `OwningProcess` before deciding how to recover. Other ports and process trees are not cleaned up. Non-Windows replacement requires manual ownership inspection.

New starts return `server.pid` and `server.logPath`. Early exit and readiness timeout retain stdout/stderr in that log and include PID, exit code and the log tail in the existing error envelope. A readiness timeout leaves the launched process running for inspection; inspect that PID and log before retrying.

## Machine interface

- Put root options before the command: `reverse-skill --json --timeout 30 status`.
- `open` uses the root `--timeout` unchanged (default 120 seconds); for complex samples use `reverse-skill --timeout 600 open sample.exe`. Timeout is an error and does not automatically reopen the sample.
- `--json` writes exactly one JSON object to stdout.
- `install` is interactive and rejects `--json`; login or installer prompts remain attached to the terminal.
- [`reverse-skill-output.schema.json`](../../../reverse-skill-output.schema.json) is the output contract; `schemaVersion` changes only for a breaking envelope change.
- [`reverse-skill.opencli.json`](../../../reverse-skill.opencli.json) describes commands, options, arguments, and exit codes using the OpenCLI 0.1 proposal.
- Dynamic MCP tool schemas still come from `tools/list`; the OpenCLI document describes the stable local command surface, not a frozen copy of server tools.

Exit codes are stable: `0` success, `1` internal failure, `2` usage, `3` unavailable local environment, `4` MCP transport/protocol failure, and `5` tool operation failure.

`doctor` and `status` print IDA discovery, Codex registration and MCP health with next actions in human mode. In JSON mode successful `data` keeps the existing fields and adds `stages`. On failure `ok:false`, `data:null` and the original error code remain unchanged; `error.message` includes a `Diagnostics: ` JSON snapshot after the error text, preserving local discovery and stage actions without changing schema v1. A local discovery/registration warning does not by itself turn a healthy remote MCP connection into a transport failure.

## Examples

`start --port` launches a local listener on `127.0.0.1`; root `--url` selects the endpoint used by status, doctor, register, open and call. Setting a remote URL does not launch a remote process or change start's default port. Root options precede the subcommand. Default start/status/register all use port 13337. For a non-default port keep these commands together:

```text
reverse-skill start --port 24444
reverse-skill --url http://127.0.0.1:24444/mcp status
reverse-skill --url http://127.0.0.1:24444/mcp register
reverse-skill --url http://127.0.0.1:24444/mcp --timeout 600 open sample.exe
```

```text
python -m pip install -e .
reverse-skill install
reverse-skill register
reverse-skill start
reverse-skill --json status
reverse-skill integrations
reverse-skill yara-scan "C:\path\sample.exe" --rules "C:\rules\triage.yar"
reverse-skill open "C:\path\sample.exe"
reverse-skill call decompile --database SESSION --arguments-json '{"addr":"0x140001000"}'
```

## IDA companion integrations

`reverse-skill integrations` reports both local availability and implementation state. `ready` means the CLI has a tested execution path; `discovery_only` means the tool is detected but no result-import bridge is claimed yet.

YARA is the first ready bridge. Install the optional dependency with `python -m pip install -e ".[ida-integrations]"`, scan normally with `yara-scan`, and add `--database SESSION --annotate` to append comments to the active IDA database. Annotation is deliberately conservative: the CLI verifies that the session opened the same target and writes only matched byte sequences that resolve to exactly one IDA address. Short, missing, or ambiguous matches remain in the JSON result and are not written.
