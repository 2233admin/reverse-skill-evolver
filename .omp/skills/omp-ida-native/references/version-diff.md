# Compare captured binary versions

Use this workflow for two native IDA snapshots when the task needs a reproducible comparison of function observations. The comparator uses Python 3.10+ and the standard library. It reads JSON files and produces a report; IDA database handles remain with the native collector.

Runtime checks consumed two real native-worker snapshots of self-authored x64 PE fixtures: renamed/layout mappings, unique-name correspondence and explicit unmatched observations. Focused checks cover duplicate names, truncated bytes, fallback kinds, invalid sources, conflicting mappings and exclusive CLI output. See [scoped evidence](https://github.com/2233admin/reverse-skill-evolver/blob/2233admin/repair-open-issues-15/reports/omp-workflow-verification-2026-10-13/README.md). This does not establish semantic equivalence or automatic symbol migration.

## Steps

1. Collect both inputs with the native snapshot collector. Keep each snapshot's source SHA-256, native database ID, image base, and coverage records. Use the same format, architecture, and bitness on both sides.
2. Supply verified function correspondences as an optional mapping JSON array. The comparator applies these first, then matches symbols that occur exactly once in each snapshot. Names beginning with `sub_`, `loc_`, `FUN_`, or `nullsub_` are treated as automatic names and require an explicit mapping. Matching names express a correspondence to inspect, not proof of identity.
3. Run the comparator from a shell with paths to the frozen snapshots:

   ```console
   python <skill-directory>/scripts/binary_diff.py --before old.json --after new.json --output comparison.json
   python <skill-directory>/scripts/binary_diff.py --before old.json --after new.json --mapping mappings.json
   ```

4. Inspect `sources.before.sha256` and `sources.after.sha256`, the mapping basis for every match, changed fields, unmatched observations, and `coverage_truncated`. Record partial collection or unavailable pseudocode in the task report. Expand collection or obtain verified mappings when the requested comparison needs more evidence.

The default output is JSON on stdout. `--output` creates a new file and refuses an input path, mapping path, or any existing file. It does not create missing parent directories. A write failure returns an error and may leave a partial newly created report. Exit codes are 0 for a report, 1 for invalid data or file errors, and 2 for invalid CLI usage.

## Mapping file

```json
[
  {"old_rva":"0x1000","new_rva":"0x2300"},
  {"old_rva":"0x1500","new_rva":"0x2900"}
]
```

Both RVAs must exist in their respective captured function lists. Duplicate or conflicting source or destination RVAs fail; each mapping must contain exactly `old_rva` and `new_rva`. Hexadecimal spelling is normalized when checking identity, so `0x001000` and `0x1000` refer to the same RVA. Equal RVAs alone never create a mapping. Byte hashes do not create automatic mappings.

## Snapshot contract and report

`compare_snapshots(before, after, mappings=None)` is importable from [binary_diff.py](../scripts/binary_diff.py). It returns a report and raises `ValueError` for invalid required fields, addresses, coverage, incompatible sources, or mappings. It leaves both input objects unchanged.

Snapshots use `schema_version: 1`, `source`, `coverage`, and `functions`. Source requires a 64-character hexadecimal `sha256`, nonempty `module`, `format`, `architecture`, and `database_id`, integer `bitness` 32 or 64, and a `0x`-prefixed `image_base`. Format and architecture labels must match exactly between snapshots. Coverage requires nonnegative integer `functions_total` and Boolean `functions_truncated`; a complete list must contain the stated total.

Each function requires `ea`, a unique `rva`, `name`, nonnegative integer `size`, a list of callee names, nullable `bytes_sha256`, nonnegative integer `bytes_hashed`, Boolean `bytes_truncated`, nullable `pseudocode`, and `pseudocode_kind`. Addresses must satisfy `ea = image_base + rva` within the source bitness. Boolean values cannot stand in for integers. `bytes_hashed` cannot exceed size, positive byte counts require a hash, and `bytes_truncated` equals `bytes_hashed < size`. `pseudocode_kind` is `pseudocode`, `assembly_fallback`, or `not_collected`; collected text is a string, and `not_collected` uses null. Extra strings/imports are outside this comparison. Additional `*_truncated` flags must be Boolean and contribute to the report's coverage warning.

The report retains both source identities and coverage objects. Each `matches` entry contains `mapping_basis`, before/after observations, `changed_fields`, and `byte_comparison`. Callees are compared as sets of names; their order and repeated occurrences are ignored, and optional `callees_truncated` is retained. Pseudocode observations record its kind, availability, optional truncation flag, and captured text SHA-256. The report lists unmatched functions as `unmatched_before` and `unmatched_after` with their addresses, names, and sizes.

## Evidence limits

- A complete range hash comparison covers the bytes recorded for the function's contiguous range. Partial or missing bytes yield `partial_or_missing_bytes`; equal partial hashes do not establish whole-function equality.
- Pseudocode hashes compare captured text, including presentation and collector bounds. Assembly fallback stays labeled as assembly. Changed text or callee names do not establish semantic change.
- `coverage_truncated` marks any captured coverage or function truncation flag. Unique symbols are unique within the captured lists; truncated lists cannot establish global uniqueness.
- Unmatched observations remain unmatched. The report does not infer added or removed functions, migrate symbols, or modify IDBs. Further correspondence or behavior claims require their own evidence.
