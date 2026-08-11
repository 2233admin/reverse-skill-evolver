# Continue — MCP + multi-language structural index

## Last action

`codex/mcp2-tantivy-routing` is a local feature branch from Beta. The deterministic
SQLite index, BM25/tree/hybrid retrieval, CLI, provider-neutral
`reverse_skill.index_api`, and the first official MCP 2.0 thin adapter are now
implemented. The adapter exposes five read-only tools and delegates to
`index_api`; the build/update operations remain outside MCP. Routing can now use
an explicit fresh package index for advisory candidate discovery; static route
selection, live capability checks, AIGX checks, and authorization remain the
authoritative gates.

The dependency choices are:

- Official `mcp>=2,<3` is an optional extra for the MCP 2026-07-28 server
  surface. The isolated `mcp==2.0.0` smoke passes and the adapter supports
  stdio and Streamable HTTP only.
- `tree-sitter-language-pack>=1.14,<2` is reserved for the next syntax-aware
  extraction batch. Language packages must be explicitly installed or present
  in the approved cache; routing and indexing never download implicitly.
- `ast-grep-py` was rejected for this batch: it is better for structural
  search/rewrite and would require more per-language extraction rules.

The full-text engine is not being replaced by Tantivy solely because its raw
query number is lower. On this workspace (530 documents, 6509 nodes, 6.44 MB),
Tantivy 0.26.0 built a text-only index in 0.66 s and answered a simple query in
0.02–0.03 ms. The existing SQLite FTS5 build took 2.38 s, BM25 9.0 ms, and
hybrid retrieval 11.1 ms. Tantivy does not provide our tree/edge/node-read
contract or the existing atomic metadata store, and its top-20 overlap with
the current BM25 results varied from 0/20 to 11/20 across the sampled queries.
SQLite FTS5 remains the current mature lexical component; Tantivy is a future
backend candidate only if a contract-preserving A/B benchmark justifies the
extra dependency and duplicated storage.

Primary references:

- https://pypi.org/project/mcp/2.0.0/
- https://github.com/modelcontextprotocol/python-sdk/blob/main/docs/whats-new.md
- https://pypi.org/project/tree-sitter-language-pack/1.14.3/
- https://github.com/xberg-io/tree-sitter-language-pack

## Current result

`tree-sitter-language-pack>=1.14,<2` is now an optional `[syntax]` extra behind the
existing index builder. The explicit `index parsers --install` command populates a
caller-selected cache; build/update only read an already populated cache and fail
closed with `parser_unavailable` when the wheel or grammar is missing. The first
`reverse-core` profile covers C, C++, Rust, Go, Java, Kotlin, C#, JavaScript,
TypeScript, Smali, ASM, and x86asm. Nested `StructureItem` results are normalized
to the existing syntax/symbol/node-id contract, while Markdown and Python paths are
unchanged.

The dependency graph is now pinned in `uv.lock`, and CI uses `uv sync --locked`.
The official `aigx==1.2.0` validator runs as an explicit CI step. The repository's
CI installs and imports the MCP 2 and syntax provider extras on every supported
host, without downloading grammars implicitly.

## Why

`index_api` owns validation, error codes, evidence, and SQLite access; the MCP
layer only translates transport calls. The language pack is an extraction provider,
not a second index or MCP surface, and its output is normalized before it reaches
the public index.

## Acceptance evidence

- MCP tools match direct `index_api` outputs and contain no duplicated business logic.
- stdio and Streamable HTTP smoke tests pass on MCP 2.0; no new SSE transport.
- Existing Markdown and Python parsers remain byte-for-byte behavior compatible.
- The normalization unit test produces stable nested nodes and IDs; real C/Smali
  grammar end-to-end fixtures remain unverified because the provider download
  reports languages available but leaves the selected cache empty in this
  environment; the importer remains fail-closed instead of treating that as a
  usable parser cache.
- Missing parser/cache reports `parser_unavailable`; no silent file-level success.
- Parser installation is explicit, e.g. `index parsers --install --profile reverse-core`;
  indexing never downloads grammars implicitly.
- Full pytest, `gates all`, `git diff --check`, benchmark, isolated wheel install,
  and official AIGX 1.2.0 validation pass locally.
- CI installs `[test,mcp,syntax]` from `uv.lock`, verifies both optional provider
  imports on every supported Python/host matrix entry, and runs official AIGX;
  grammar downloads remain explicit.

## Open threads

- IDA functions, addresses, xrefs, and decompiler output now have an explicit
  version-1 JSON ingestion adapter into the same node/edge store. Use
  `reverse-skill index import-ida WORKSPACE --export EXPORT.json --apply` after
  `index build --apply`; `index update` and full rebuild preserve imported IDA
  documents. The export provider remains external (IDA/DeepExtract/idapy) and
  must emit the frozen shape before ingestion.
  The minimum shape is `{"schema_version":1,"module":"sample.exe","functions":[{"address":"0x401000","name":"entry","pseudocode":"...","xrefs_to":[]}]}`;
  xref targets must be present in the same export, so unresolved graph edges
  fail closed.
- MCP build/update tools remain out of the first adapter. If added later, they must
  preserve plan-only defaults and require explicit apply semantics.

## Do not

- Do not expose the language pack's bundled MCP server as a second public surface.
- Do not replace the existing Markdown or Python parsers.
- Do not rely on the globally installed MCP 1.x package; test an isolated MCP 2.0 extra.
- Do not add a vector database, model call, PowerShell project script, or Excel path.
- Do not silently download grammars, swallow parser failures, push, tag, or publish.
