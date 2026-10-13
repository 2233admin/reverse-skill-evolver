# OMP native IDA verification

Base: `53010b3d5591f78333062fe8056782ed769f4a7d`. Feature: native `omp-ida-native` skill, portable references, live backend selection, and native/MCP capability alternatives. No new execution transport was added.

## Observed checks

| Check | Result |
| --- | --- |
| Installed OMP 18.8.9 reads `skill://omp-ida-native/SKILL.md` | Success through its real skill provider |
| Both references read through `skill://` | Success |
| Complete skill copied into a different project, then discovered | Success |
| Toy executable overview | Input SHA matches the frozen fixture |
| Assembly view at `0x140001000` | Actual instructions returned |
| Strings view | Expected unique fixture marker returned |
| Pseudocode at `0x140001000` | Actual C pseudocode returned, not assembly fallback |
| Xrefs at `0x140001000` | Expected caller instruction at `0x14000107b` returned |
| Imports | Empty, as expected for this no-CRT fixture |
| Missing configured Python | Exit 1 with explicit dependency error, no successful result |
| Project pytest | 234 passed, 5 skipped on Windows |

Read commands use the installed `omp` executable's production `read` entry. They do not submit a model prompt. They use the native IDA implementation, not the previously tested HTTP MCP server. Four skill/reference reads and six binary views succeeded; one deliberately invalid runtime configuration failed as expected.

Native runtime: IDA Professional 9.4 installation, Python 3.13.15, isolated `ida-domain 0.5.1`, `idapro 0.0.11`, `packaging 26.3`, `typing-extensions 4.16.0`. The OMP executable SHA-256 and complete normalized command outputs are in [verified.json](verified.json). Local machine paths are replaced with `<repo>`, `<artifacts>`, and `<omp>`.

## Reproduce

1. Use the installed OMP and a suitable native IDA environment as described in [setup](../../.omp/skills/omp-ida-native/references/setup.md).
2. From the checkout, run `omp read skill://omp-ida-native/SKILL.md` and read both `skill://omp-ida-native/references/` files.
3. Copy the complete skill directory to a different project's `.omp/skills/`, then repeat the skill read there.
4. Use the frozen self-authored toy executable from the [earlier IDA fixture receipt](https://github.com/2233admin/reverse-skill-evolver/issues/20#issuecomment-6124347972). SHA-256: `6c5a1b1e6988365bd05c7334d9b8c3b1154eb95c12a52621911b3e7951895cfa`; its C source is also preserved as [toy.c](toy.c).
5. Run the six `omp read` view arguments recorded in `verified.json`, using a separate test project and database store. Confirm the output oracles in the table.
6. In another isolated test project, set `ida.python` to a nonexistent executable and confirm the reported failure. Preserve the actual user configuration.

## Limits

- No model requests or API credential changes. Host configuration and the original fixture were preserved.
- No performance comparison or claim of reduced model cost. The six view timings cover different operations and cannot establish a speedup.
- Native `ida` edit, save, close, shared write ownership, batch `exec`, resource-limit eviction, and timeout recovery were checked against versioned source instructions; they were not executed by these read checks.
- The scoped daemon listing had no active native daemons afterwards. Its observed exited daemon code was 1; this does not establish graceful shutdown or saved-edit durability.
- The official Hex-Rays OMP extension was not installed or tested. Existing mrexodia MCP tests are separate evidence.
- Windows checks skipped five platform-dependent cases; CI results belong to the exact PR head and are recorded in the PR.
