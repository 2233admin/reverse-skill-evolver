# Continue — MCP + multi-language structural index

## Last action

`codex/mcp2-tantivy-routing` is a local feature branch from Beta. The deterministic
SQLite index, BM25/tree/hybrid retrieval, CLI, provider-neutral
`reverse_skill.index_api`, and the first official MCP 2.0 thin adapter are now
implemented. The adapter exposes only four read-only tools and delegates to
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

## Next action

Integrate
`tree-sitter-language-pack>=1.14,<2` behind the existing index builder for the
first reverse-core profile:
C, C++, Rust, Go, Java, Kotlin, C#, JavaScript, TypeScript, Smali, ASM, x86asm.

## Why

`index_api` already owns validation, error codes, evidence, and SQLite access;
the MCP layer must only translate transport calls. The language pack already
extracts the structure we need, but its output must be normalized into the
existing `NodeSpec`/stable-ID contract so third-party schema changes cannot
leak into the public index.

## Acceptance evidence

- MCP tools match direct `index_api` outputs and contain no duplicated business logic.
- stdio and Streamable HTTP smoke tests pass on MCP 2.0; no new SSE transport.
- Existing Markdown and Python parsers remain byte-for-byte behavior compatible.
- C/C++ and Smali fixtures produce stable nested nodes after full and incremental builds.
- Missing parser/cache reports `parser_unavailable`; no silent file-level success.
- Parser installation is explicit, e.g. `parsers install --profile reverse-core`;
  indexing never downloads grammars implicitly.
- Full pytest, `gates all`, AIGX lint, `git diff --check`, benchmark, and isolated
  wheel install pass.

## Open threads

- IDA functions, addresses, xrefs, and decompiler output need a separate IDA
  ingestion adapter into the same node/edge store; Tree-sitter does not parse binaries.
- MCP build/update tools remain out of the first adapter. If added later, they must
  preserve plan-only defaults and require explicit apply semantics.

## Do not

- Do not expose the language pack's bundled MCP server as a second public surface.
- Do not replace the existing Markdown or Python parsers.
- Do not rely on the globally installed MCP 1.x package; test an isolated MCP 2.0 extra.
- Do not add a vector database, model call, PowerShell project script, or Excel path.
- Do not silently download grammars, swallow parser failures, push, tag, or publish.
