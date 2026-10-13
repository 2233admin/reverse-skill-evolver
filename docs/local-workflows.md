# Local routing, case records and indexing

Use the installed complete skill's `scripts/run.py` launcher in place of
`reverse-skill` when the CLI is not installed in your shell.

## Route suggestion and repository checks

```console
reverse-skill --json route "Analyze an APK's native library"
reverse-skill --json gates all
reverse-skill --json gates leak-scan ./report
```

Routing returns `selected` or `no_route`. A selection names the skill and its
requirements; it neither checks the live tools nor authorizes or executes the
workflow. The skill remains responsible for the current task's preflight and
success checks. The 163 fixed upstream routing cases cover selection only.

`gates all` checks versions, nested CLI command descriptions, canonical/packaged
routing data, route IDs and referenced workflow paths. Repository gates need
the complete skill or source checkout. Leak scanning runs only for the explicit
path; findings hide matching values. `--report-only` keeps a findings report
without returning a failure exit code.

## Case scope and evidence review

```console
reverse-skill --json case init --hint "Analyze my local PE sample" --case-name local-pe --preset offline-sample --sample ./sample.exe --package-root .
reverse-skill --json case review ./work/local-pe --strict --verify-hashes
```

Initialization creates a new `work/<case>/` directory with scope, work items,
timeline and evidence/report directories. Existing case directories are refused.
Presets record the caller's declared scope; use them only when that declaration
matches the current task's actual authorization. `ready_for_act` records scope
readiness, not tool execution or artifact analysis. Without an explicit preset
or scope declaration, authorization remains pending and network mode is offline.

Review reads the existing case and checks evidence/work-item/report references,
scope readiness and optional SHA-256 hashes. An artifact outside the case is an
error. Granted scopes require a recognized authorization basis and a non-placeholder
evidence reference; review checks the recorded declaration, not external approval.
`--strict` also treats warnings as blockers. Exit 5 indicates a failed
review; the existing output-v1 contract keeps `data=null` and includes the full
report after `Diagnostics: ` in `error.message`. Human output includes the report;
passing reviews can use `--format markdown`.

## Optional SQLite project index

```console
reverse-skill --json index build ./workspace
reverse-skill --json index build ./workspace --apply
reverse-skill --json index update ./workspace --apply
reverse-skill --json retrieve ./workspace "request signature" --mode hybrid
reverse-skill --json index status ./workspace
```

Build/update default to a plan. Explicit `--apply` writes the rebuildable local
index at `.reverse-skill/index/v1.sqlite3`; `--index-path` selects another path.
Markdown headings and Python AST provide structure, with file-level nodes for
other text. Symlinks, binary/oversized files and recognized credential files
are skipped. No model, cloud service or parser download is needed by these commands.
Retrieval offers `bm25`, `tree` and `hybrid`; status, inspect and retrieve are read-only.

An explicit versioned IDA JSON export can be planned/imported with
`index import-ida WORKSPACE --export FILE [--apply]`. This reads supplied export
data without starting IDA. `index xrefs WORKSPACE NODE_ID` reads imported edges.
The index stays optional and does not become a route or authorization authority.

## Migration source

Case and index contracts/engines and routing fixture data originate from
`beta@4a026a6f62849fc39eaac300b76d9b3a7ece0504`. Integration preserves the
current `firmware-iot` route ID, the complete skill layout, ASR, OMP, swarm CLI,
output-v1 error envelopes and existing PowerShell workflows. The fixture maps
beta's `firmware-pentest` ID to `firmware-iot` explicitly. AIGX policy and the
beta MCP server are separate capabilities and are outside this migration.
