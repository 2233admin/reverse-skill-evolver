# Native IDA interface examples

Contract checked against OMP 18.8.9, commit `fa5ff4a3a977a28b93d025f4cf50f046e019f18c`. Consult the current tool schema before calls. These are native tool arguments, not shell commands or MCP argument envelopes.

## Read views

| `read` path | Result |
| --- | --- |
| `sample.exe` | Overview and function list; opens or creates the database |
| `sample.exe:main:1-80` | Paged pseudocode; substitute a real symbol or `0x` address |
| `sample.exe:main:asm:1-80` | Paged assembly |
| `sample.exe:imports` / `sample.exe:exports` | Import/export views |
| `sample.exe:strings:1-80` | Paged strings |
| `sample.exe:xrefs:main` | References to/from the target |
| `sample.macho:@arm64:main` | Explicit universal Mach-O slice |

`read` accepts executable or `.i64`/`.idb` paths. A failed decompilation may return marked assembly; it is not pseudocode. Views are generated immutable text, so they do not supply anchors for editing the binary with the text `edit` tool.

## Database lifecycle and edits

```json
{"action":"list"}
{"action":"open","db":"sample.exe"}
{"action":"rename","db":"<native-db-id>","target":"sub_140001000","name":"parse_header"}
{"action":"comment","db":"<native-db-id>","target":"parse_header","text":"Parses the captured packet header"}
{"action":"set_type","db":"<native-db-id>","target":"parse_header","decl":"int parse_header(const unsigned char *data, unsigned int size)"}
{"action":"make_function","db":"<native-db-id>","target":"0x140002000"}
{"action":"save","db":"<native-db-id>"}
{"action":"close","db":"<native-db-id>","save":true}
```

Each line is a separate example, not a required sequence. Substitute the returned native ID and verified targets; create functions and apply types only when supported by evidence and permitted by the task. `close` is a shared lifecycle action, not a per-agent disconnect.

## Batch Python

Call `ida` with `action="exec"`, the explicit native `db`, a finite `timeout`, and the following text as `code`:

```python
import json
task_functions = functions("parse|decode|decrypt")[:8]
task_summary = [
    {"ea": hex(ea), "name": name, "callees": callees(ea)[:8]}
    for ea, name in task_functions
]
print(json.dumps(task_summary))
```

This limits emitted functions and callees, not the underlying scan. Narrow the regex and record the bounds. Expand the batch only when the task needs more results.

The persistent namespace includes `db` (an `ida_domain.Database`), IDA modules, `idautils`, and helpers:

- `resolve`, `func`, `name_of`, `pseudocode`, `asm`
- `xrefs_to`, `xrefs_from`, `callers`, `callees`
- `functions`, `strings`, `imports` (optional case-insensitive regex)
- `hexdump`, `read_bytes`, `rename`, `comment`, `set_type`, `make_function`

`help_ida()` lists the current helpers. Captured stdout/stderr and the last expression's representation form the result; check errors instead of treating partial output as a complete answer.

## Sources

- [OMP IDA tool contract](https://github.com/can1357/oh-my-pi/blob/fa5ff4a3a977a28b93d025f4cf50f046e019f18c/docs/tools/ida.md)
- [Binary read views](https://github.com/can1357/oh-my-pi/blob/fa5ff4a3a977a28b93d025f4cf50f046e019f18c/packages/coding-agent/src/tools/read-binary.ts)
- [Native worker helpers](https://github.com/can1357/oh-my-pi/blob/fa5ff4a3a977a28b93d025f4cf50f046e019f18c/packages/coding-agent/src/ida/worker.py)
