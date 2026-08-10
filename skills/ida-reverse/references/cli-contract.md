# Python CLI contract

`reverse-skill` is the human and automation entry point for the IDA MCP workflow. The executable is installed from `pyproject.toml`; a source checkout can run the identical interface with `python -m reverse_skill`.

The execution path is:

```text
reverse-skill -> HTTP MCP -> idalib-mcp.exe -> newest usable local IDA
```

No shell runtime is part of this path. `install` may start the upstream interactive installer because login and user interaction are explicitly expected there.

## Machine interface

- Put root options before the command: `reverse-skill --json --timeout 30 status`.
- `--json` writes exactly one JSON object to stdout.
- `install` is interactive and rejects `--json`; login or installer prompts remain attached to the terminal.
- [`reverse-skill-output.schema.json`](../../../reverse-skill-output.schema.json) is the output contract; `schemaVersion` changes only for a breaking envelope change.
- [`reverse-skill.opencli.json`](../../../reverse-skill.opencli.json) describes commands, options, arguments, and exit codes using the OpenCLI 0.1 proposal.
- Dynamic MCP tool schemas still come from `tools/list`; the OpenCLI document describes the stable local command surface, not a frozen copy of server tools.

Exit codes are stable: `0` success, `1` internal failure, `2` usage, `3` unavailable local environment, `4` MCP transport/protocol failure, and `5` tool operation failure.

## Examples

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
