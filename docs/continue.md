# Continue — MCP + multi-language structural index

## Last action

`codex/beta-integration` is clean at `1e70744`. The deterministic SQLite index,
BM25/tree/hybrid retrieval, CLI, and provider-neutral `reverse_skill.index_api`
are implemented and locally fast-forwarded into Beta. Evidence at this checkpoint:
126 tests passed, repository gates clean, AIGX clean (107 registered files before
this handoff), and the isolated `2.0.0b4` wheel smoke passed.

The next dependency choices were verified but **not implemented**:

- Official `mcp==2.0.0` for the MCP 2026-07-28 server surface. It supports
  Python 3.10+ and legacy MCP clients.
- `tree-sitter-language-pack==1.14.3` for functions/classes/imports/symbols and
  syntax-aware chunks across 371 languages. Its parsers download on demand.
- `ast-grep-py` was rejected for this batch: it is better for structural
  search/rewrite and would require more per-language extraction rules.

Primary references:

- https://pypi.org/project/mcp/2.0.0/
- https://github.com/modelcontextprotocol/python-sdk/blob/main/docs/whats-new.md
- https://pypi.org/project/tree-sitter-language-pack/1.14.3/
- https://github.com/xberg-io/tree-sitter-language-pack

## Next action

Start from this commit on a new feature branch. Freeze red tests and the machine
contract for four **read-only** MCP tools before writing the adapter:
`index_status`, `index_search`, `index_get_tree`, and `index_read_nodes`.
Use the MCP SDK's in-memory `Client(MCPServer)` test path and assert each tool's
structured result equals the direct `index_api` result for the same fixture.
Add `mcp>=2,<3` as an optional extra, not a base CLI dependency.

After that contract passes, add `reverse-skill-mcp` as a thin `MCPServer`
entrypoint, then integrate `tree-sitter-language-pack>=1.14,<2` behind the
existing index builder for the first reverse-core profile:
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
