# ASR commands

From any working directory, run `python "<PACK_ROOT>/scripts/run.py"`, where `<PACK_ROOT>` contains the complete installed skill's root `SKILL.md`. The launcher prepares the package's private Python environment when needed. An installed `reverse-skill` command or a configured source checkout's `python -m reverse_skill` uses the same CLI. Put `--json` and `--timeout SECONDS` **before** `asr`. JSON output uses the existing envelope with `command: "asr"`, and `data: { action, result }`; transport failures exit 4, operation failures 5, and missing credentials 3.

| Command | ASR API | Use |
|---|---|---|
| `asr list` | `GET /api/asr` | All audited skills/goals/workflows, all pages by default; `--kind`, `--search`, `--sort-by`, `--page`, `--per-page`, `--single-page`, `--mine` |
| `asr show ID` | `GET /api/asr/{id}` | Metadata and original files; rejects unaudited and server items |
| `asr install ID --destination PATH` | `GET /api/asr/{id}` | Save original files to a new directory, preserving references; never executes content or overwrites an existing destination |
| `asr install-script ID` | `GET /api/asr/{id}/install` | Preview upstream installation; `--location project\|global`, `--harness agents\|claude`, `--shell powershell\|bash` |
| `asr authors` | `GET /api/asr/authors` | Leaderboard: `--search`, `--sort-by score\|downloads\|hearts\|items\|recent`, `--page`, `--per-page`; top items filtered by audit and kind |
| `asr author KEY` | `GET /api/asr/authors/{key}` | GitHub owner's profile and filtered `items_list` |
| `asr plugin ID` | `GET /api/asr/plugins/{id}` | Bundle verdict, supply-chain/quality findings, audited members; removes MCP server definitions and server alerts |
| `asr scans` | `GET /api/asr/scans` | Scan history: `--search`, `--page`, `--per-page`, `--mine`; scans can concern unreviewed sources and are not recommendations |
| `asr scan GITHUB_URL` | `POST /api/asr/scans` | Public, rate-limited scan submission: `--commit-sha`, `--skill-path`, `--plugin`; always `mcp: false` |
| `asr scan-result ID` | `GET /api/asr/scans/{id}` | Fetch or poll an existing scan, preserving `scan`, `history`, registry audit state, and result fields |
| `asr import-repo GITHUB_URL` | `POST /api/asr/import` | Publish skills/goals/workflows, idempotently; `--commit-sha`, repeated `--path`/`--skill-name`, `--is-benchmark`, `--parent-benchmark-id`; always `include_server: false` |
| `asr create-goal --input FILE` | `POST /api/asr/goals` | Publish a structured goal definition; forwards the complete JSON object |
| `asr record-download ID` | `POST /api/asr/{id}/download` | Explicit download accounting; optional `--source`; installation itself does not update the remote counter |

## Current-task chains

Read the conversation and use item descriptions to choose a chain; the CLI returns source data rather than inventing semantic matches. For example, to augment a Python security-tool repository, look for applicable groundwork and verification skills rather than Solidity-only auditing skills.

Use links of the form `https://forefy.com/asr/ID`. A suggested tree contains only registry items and kind/audit annotations. Do not install or run unrelated alternatives. Duplicate names from different authors are distinguished by id and repository URL.

## Installation

```console
python -m reverse_skill --json asr list --search "audit context"
python -m reverse_skill --json asr show ITEM_ID
python -m reverse_skill --json asr install ITEM_ID --destination .agents/skills/ITEM_NAME
python -m reverse_skill --json asr install-script ITEM_ID --shell powershell --harness agents --location project
```

Raw-file installation needs a `SKILL.md`, `goal.md`, or workflow `.js` entry and rejects traversal, absolute paths, Windows device names, alternate data streams, and duplicate paths. It does not run scripts, install the skill's dependencies, invoke `/goal`, or register MCP servers. Some plugin members reference files outside their folder; inspect `portability`/`plugin_context` and use the reviewed pinned-repository script when necessary. The JSON receipt includes source commit and audit metadata, but the API's audit record is not an independent cryptographic verification of file bytes.

## Credentials and publishing

Set `FOREFY_API_KEY` through the caller's environment; do not put keys in tracked files, command arguments, or output. Public reads and scans do not send the key. `--mine`, imports, and goal publishing use it. On 401/403, check expiry and full-account scope. On 429, honor `Retry-After` if returned.

```json
{
  "name": "verify-asr-integration",
  "description": "Verify the ASR integration against its documented contract",
  "end_state": ["Audited-only ASR commands are available"],
  "proof": ["Contract and regression tests pass"],
  "guardrail": {
    "allowed_paths": ["reverse_skill", "tests", "skills/asr-registry"],
    "invariants": ["Exclude MCP server imports"]
  },
  "termination": {"max_turns": 20, "stop_on": ["verification failure"]}
}
```

This is a payload example, not an instruction to create a hosted goal. `asr import-repo` supports narrowing an individual skill with `--path skills/NAME`, or importing the whole repository without path filters. Newly published items are not automatically human-audited and will not appear in this skill's audited-only recommendations until an auditor reviews them.
