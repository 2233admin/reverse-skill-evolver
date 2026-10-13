# OMP native IDA setup

## Discover the skill

From a source checkout, start `omp` in the repository and invoke `/skill:omp-ida-native`. OMP discovers `.omp/skills/omp-ida-native/SKILL.md` and reads its references on demand through `skill://omp-ida-native/`.

For another project, copy the complete `omp-ida-native` directory into that project's `.omp/skills/`. Keep `SKILL.md` and `references/` together. The Python `pip` package does not install this skill. No npm package, empty extension, or model configuration is required.

## Select the actual backend

| Available interface | Workflow |
| --- | --- |
| OMP native `ida` actions with `db`/`code`, plus binary `read` views | This skill |
| Existing `idapro` MCP tools with `database` | The project's `skills/ida-reverse/SKILL.md` MCP workflow |
| Official Hex-Rays extension's `ida_*` MCP tools | That extension's guidance and current schema |

Choose the interface by its schema and a successful operation. Native `db`, mrexodia `database`, and official plugin instance handles are different contracts. The official extension attempts to disable the OMP built-in IDA tool and binary views at runtime; do not combine its examples with this skill's native arguments.

## Dependencies and configuration

OMP requires an IDA installation containing idalib and a Python interpreter that can find `ida_domain` and `idapro`. Validate the actual worker opening the input; merely having these packages listed is insufficient.

Use an existing suitable Python environment. If it lacks dependencies, install `ida-domain` into that environment and satisfy its declared `idapro` requirement. An IDA-supplied wheel must also satisfy that requirement; avoid forcing an incompatible older loader. Pin the interpreter through `ida.python`; let IDA select its licensed installation or set `ida.installDir` explicitly when necessary. IDA installation and licensing use the vendor's supported flow.

A project-local `.omp/config.yml` can contain an installation-specific selection:

```yaml
ida:
  enabled: true
  python: /absolute/path/to/ida-python
  installDir: /absolute/path/to/ida-install
```

These are placeholders to replace locally, not repository defaults. Keep credentials and machine paths out of shared configuration. Preserve existing configuration; a portable skill does not need to rewrite it.

Native defaults checked at 18.8.9 are `ida.maxOpen=4` and `ida.idleCloseSec=900`. Increase the limit only for an observed need. `ida.idleCloseSec=0` disables idle closing, so it retains resources until another lifecycle action closes them.

## Diagnose failures

- Missing native interface: check `ida.enabled`, the installation, allowed tools, and whether the official extension replaced it. If tools are discoverable, inspect `xd://ida` rather than assuming absence.
- No compatible Python: set `ida.python` to the environment containing both packages; check the actual open result.
- IDB in use: coordinate with its owner or close it in the owning IDA application. Do not delete its lock to bypass ownership.
- All databases busy: wait for their requests, or close an owned idle database. A queue timeout is a failure, not a completed analysis.
- Lost worker: reopen and check saved changes. A reopened namespace does not contain previous Python variables.

## Sources

- [OMP skill discovery](https://github.com/can1357/oh-my-pi/blob/fa5ff4a3a977a28b93d025f4cf50f046e019f18c/docs/skills.md)
- [Native IDA settings](https://github.com/can1357/oh-my-pi/blob/fa5ff4a3a977a28b93d025f4cf50f046e019f18c/packages/coding-agent/src/ida/settings.ts)
- [Python runtime probe](https://github.com/can1357/oh-my-pi/blob/fa5ff4a3a977a28b93d025f4cf50f046e019f18c/packages/coding-agent/src/ida/runtime.ts)
- [IDA Domain installation](https://github.com/HexRaysSA/ida-domain#-installation)
- [Official Hex-Rays OMP extension](https://github.com/HexRaysSA/ida-mcp/blob/df6de7985b534a964c125d5a86e41b26b17b14f6/ida-mcp.ts)
