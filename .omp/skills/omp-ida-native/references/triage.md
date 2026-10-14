# Native IDA snapshot and triage

Snapshot/triage were verified on self-authored x64 PE fixtures in the pinned OMP 18.8.9 production worker with real IDA/idalib: strings/imports/functions, no matches, bounded captures and non-function references. See [scoped evidence](https://github.com/2233admin/reverse-skill-evolver/blob/2233admin/repair-open-issues-15/reports/omp-workflow-verification-2026-10-13/README.md). Other architectures, arbitrary inputs and host registry integration remain separate checks. No model is required by these collectors.

Use `scripts/ida_analysis.py` inside an existing OMP native `ida` worker. It defines `collect_snapshot(namespace, database_id, ...)` and `triage(namespace, database_id, ...)`; loading it performs no analysis. Both functions call the real worker helpers passed in `namespace`. They do not start a service or use an MCP adapter, and they do not call database-edit helpers.

## Load without replacing worker helpers

Pass the explicit native database ID to the surrounding `ida` call. In its `code`, use an absolute path to the script from the installed skill directory:

```python
task_analysis_path = __import__("pathlib").Path("/absolute/path/to/omp-ida-native/scripts/ida_analysis.py")
task_analysis_namespace = dict(globals())
exec(compile(task_analysis_path.read_text(encoding="utf-8"), str(task_analysis_path), "exec"), task_analysis_namespace)
task_analysis_triage = task_analysis_namespace["triage"]
task_analysis_result = task_analysis_triage(globals(), "<native-db-id>")
print(__import__("json").dumps(task_analysis_result, ensure_ascii=False))
```

The separate dictionary holds the script's imports and definitions; the worker's `func`, `functions`, `strings`, and other helpers retain their original bindings. Use task-specific variable names because the worker namespace is shared. The caller supplies the ID returned by native `ida`; this collector cannot independently verify that string against the host registry. Each database has a separate worker namespace.

Missing native db/enumeration/function helpers fail with an explicit native exec requirement. Invalid or empty source identity fields fail before an artifact can be exported. Worker warnings can appear alongside printed text; the exclusive full-file save below was exercised on real fixtures and is the artifact boundary.

Use a finite native `ida` exec timeout. Native `functions()`, `strings()`, and `imports()` enumerate their whole underlying collections before the script can apply limits. `callees()`, `xrefs_to()`, and optional `pseudocode()` also finish their native work before results can be shortened. These limits bound captured output and subsequent queries, not the complete native scan or decompiler cost. OMP may save a database as part of its normal exec/lifecycle handling.

Large printed JSON may exceed OMP's inline output cap. Preserve the full returned artifact when available and confirm it contains complete parseable JSON before handing it to another workflow; a truncated display is not a snapshot.

## Save a complete artifact

After either collection call below, save `task_analysis_result` from the worker namespace to a new JSON file in the task's evidence directory. Use an absolute path accessible to the IDA worker; its parent directory must already exist. Serialize before opening the file, and use exclusive creation so an earlier snapshot cannot be overwritten:

```python
task_analysis_output = __import__("pathlib").Path("/absolute/task/evidence/triage.json")
task_analysis_json = __import__("json").dumps(task_analysis_result, ensure_ascii=False, allow_nan=False)
with task_analysis_output.open("x", encoding="utf-8") as task_analysis_file:
    task_analysis_file.write(task_analysis_json + "\n")
print(__import__("json").dumps({
    "artifact": str(task_analysis_output),
    "source_sha256": task_analysis_result["source"]["sha256"],
    "database_id": task_analysis_result["source"]["database_id"],
}, ensure_ascii=False))
```

Use a distinct filename such as `snapshot.json` for `collect_snapshot`. Pass the saved file to the version comparator or dynamic-plan generator. An existing file raises `FileExistsError`; choose a new filename. A missing parent or permission error propagates. A failed write may leave a partial new file; do not pass it downstream. Only a successfully closed, complete JSON file is the evidence artifact. This writes the task's report, without calling database-edit helpers.

## `collect_snapshot` contract

After loading the script, assign the snapshot below, then run the save block above with a new `snapshot.json` path. The assignment alone retains the result in the worker; it does not display or save it.

```python
task_analysis_snapshot = task_analysis_namespace["collect_snapshot"]
task_analysis_result = task_analysis_snapshot(
    globals(), "<native-db-id>",
    max_functions=500, max_strings=200, max_imports=200,
    max_callees=25, max_bytes_per_function=256,
    collect_pseudocode=False,
    max_pseudocode_functions=10, max_pseudocode_chars=8000,
    max_text_chars=4096,
)
```

Limits are nonnegative integers; boolean values are rejected. Text limits require at least one character. Maximum values are 5,000 functions/strings/imports, 500 callees per function, 4,096 bytes per function, 50 pseudocode functions, 20,000 pseudocode characters, and 16,384 string characters. `collect_pseudocode` must be a boolean and defaults to `False`.

The returned JSON object has:

- `schema_version: 1`.
- `source`: input `sha256` (64 lowercase hexadecimal digits), `module`, `format`, `architecture`, integer `bitness` (32 or 64), hexadecimal `image_base`, and the caller's native `database_id`. These metadata fields come from the worker's existing `db` properties.
- `coverage`: native enumeration mode, total function/string/import counts, output truncation flags, callee/byte/text truncation flags, pseudocode request/count/limit flags, and effective `limits`. Counts describe what the native helpers enumerated, not verified analysis completeness.
- `functions`: hexadecimal `ea` and `rva` (`ea = image_base + rva`), `name`, primary function-range `size`, bounded `callees`, `callees_truncated`, byte-hash fields, and optional pseudocode fields.
- `strings`: `ea`, bounded `value`, and `value_truncated`.
- `imports`: `ea`, `module`, and `name`.

Byte hashes cover only the actual bytes returned for a contiguous prefix of the primary function range. `bytes_start_ea` and `bytes_end_ea` delimit that captured prefix, `bytes_hashed` is its length, and `bytes_truncated` is `bytes_hashed < size`. A zero-size function has `bytes_sha256: null`, `bytes_hashed: 0`, and `bytes_truncated: false`. A nonempty range with no captured bytes has `null`, `0`, and `true`. Hash equality is an observation about captured bytes, not semantic equivalence; rebasing or operand changes can change the hash.

With `collect_pseudocode=False`, every row has `pseudocode: null` and `pseudocode_kind: "not_collected"`. An explicit request collects at most `max_pseudocode_functions` among the returned functions and clips each text to `max_pseudocode_chars`. The pinned helper's decompilation-failure marker produces `pseudocode_kind: "assembly_fallback"`; actual pseudocode is labeled `"pseudocode"`. `pseudocode_truncated` records clipping. Assembly fallback is not recovered source code.

## `triage` contract

`triage` accepts optional case-insensitive `function_pattern`, `string_pattern`, and `import_pattern` regexes. Defaults look for names concerning parsing, decoding, authentication, common copy/formatting APIs, network operations, and related strings. Patterns identify leads; a match does not establish a vulnerability.

After loading the script, assign the custom triage result below, then run the save block above with a new `triage.json` path.

```python
task_analysis_triage = task_analysis_namespace["triage"]
task_analysis_result = task_analysis_triage(
    globals(), "<native-db-id>",
    function_pattern=r"parse|decode|verify",
    string_pattern=r"password|invalid|https?://",
    import_pattern=r"memcpy|recv|crypt",
    max_candidates=50, max_matches_per_source=100, max_xref_queries=100,
    max_xrefs_per_source=100, max_evidence_per_candidate=20,
    max_scan_per_source=10000, max_subject_chars=4096,
)
```

Limits reject booleans. Candidate count is 1–50, matches per source and xref queries are 0–100, xref rows per queried source are 0–1,000, evidence per candidate is 1–100, regex scans per source are 0–100,000, and subject characters are 1–16,384. Each regex contains 1–256 characters. Invalid regexes fail before native enumeration.

When any pattern differs from the built-in defaults, the three matching scans run as one JSON-only batch in the adjacent `scripts/regex_worker.py`, with a two-second subprocess deadline. Python regex syntax, case-insensitive matching, scan/match limits and coverage remain the same. Timeout raises `RuntimeError("Custom triage regex batch exceeded 2 seconds")`; child failure also raises `RuntimeError`. No successful partial triage artifact is returned. The matching child is killed and reaped before timeout is reported; it receives only bounded text and patterns. Native enumeration and xref/function helpers still run in the original IDA worker, outside this matching deadline. Install both scripts together and load `ida_analysis.py` with its actual path as the `compile` filename, as above. The built-in default scans do not start a child process.

The output contains `schema_version`, the same `source` contract, `coverage`, and `candidates`. Each candidate has `ea`, `rva`, `name`, integer `score`, `evidence`, and `next_action`. Unique matching function-name evidence adds 3 points; unique string/import xref-site evidence adds 2. This only orders captured leads. Ties sort by address.

String/import targets are interleaved within the xref-query budget. Evidence names its `kind`, `source_ea`, and matched `value`; referenced evidence also includes actual `xref_from` and `xref_type`. Ownership comes from `func(xref["from"]).start_ea`, rather than treating a referencing instruction as the function start. Non-function references are explicitly skipped and counted in `non_function_xrefs_skipped`. Only the pinned helper's specific `LookupError("no function at ...")` is handled as a missing function; other worker errors propagate.

`coverage.source_scans` records total entries, regex-scanned entries, captured matches, scan truncation, and subject clipping for each source. Scanning stops at its entry budget or match budget, so unseen matches remain unknown. Other coverage fields record queried xref counts, returned xref-row totals for queried sources, xref clipping, discarded candidate/evidence output, and effective regex patterns and limits. No coverage field proves all important functions were found.

## Basis

Helper shapes and `db` properties were read from [OMP 18.8.9 worker.py](https://github.com/can1357/oh-my-pi/blob/fa5ff4a3a977a28b93d025f4cf50f046e019f18c/packages/coding-agent/src/ida/worker.py), particularly `func`, `functions`, `strings`, `imports`, `callees`, `xrefs_to`, `pseudocode`, `_view_overview`, and exec namespace initialization. Consult the live native interface before use.
