# v1.2.0-beta.2 verification scope

The release candidate starts from main `05a884cbff4bbf636a4fc1d873ebb351435a0cce`, which is a main that already contains the MCP error-classification repair (PR #63, commits `09344cc`, `9bb7a16`) and the `.gitignore` hygiene commit. Preparation changes package/version metadata, release documentation and the version assertion. It introduces no runtime logic or dependency change of its own. Python version is `1.2.0b2`; OpenCLI and the release use `1.2.0-beta.2`.

## Actual validation

| Check | Result and scope |
|---|---|
| Base main Linux CI | [Project checks](https://github.com/2233admin/reverse-skill-evolver/actions/runs/38524505615): Python 3.10, 788 passed / 55 skipped; gates all clean; Java 21 check and POSIX build entrypoints passed. This run predates the MCP classification repair and therefore covers the repaired runtime only up to `5f84b569`. |
| Candidate clean clone | Version/documentation changes applied on main `05a884cb`, a new isolated editable test environment: **840 passed / 5 skipped**. This is the first run in this document that exercises the candidate together with the merged MCP repair. |
| MCP classification coverage | The merged repair's own regression (`tests/test_mcp.py`, server-error classification with and without a well-formed JSON-RPC body) passes inside the candidate suite above. |
| Candidate metadata and distribution regression | **90 passed** across CLI, repository gates and whole-skill distribution. OpenSpec strict validation passed with an explicit metadata/documentation-only change. |
| Candidate repository contracts | gates all clean; Python metadata, CLI and OpenCLI prerelease versions agree. |
| Java component | A clean Git export built with isolated JDK 21 passed Gradle `check jar`, including behavior, scheduler and HTTP-handler race regressions. The attached JAR contains Java 21 bytecode, class major 65; the component retains version `2.0.0`. |
| Wheel installation | Built with PyPA build/setuptools, installed in a separate fresh environment, executed from an unrelated directory. Both CLI helps, version `1.2.0b2`, route and ASR list passed; imported code came from that environment's site-packages. |
| Repaired runtime independent review | Installation/CLI, index and protocol slices were independently reviewed before integration. The OMP payload bound and ordinary low-match-limit scan received an additional independent review and real-worker parity scenarios. See [integration evidence](https://github.com/2233admin/reverse-skill-evolver/issues/55#issuecomment-6162700316). |

The five candidate skips are one missing optional YARA dependency and four Windows filename cases involving literal quote/backslash characters. Linux CI runs the filename cases. The earlier Windows main combination once exceeded the existing ten-second port-inspection timeout; an isolated retry and full rerun passed. That failure was retained in the integration evidence.

## Artifact provenance and installation checks

The final bundle is assembled from a precise committed Git export with `core.autocrlf=false` and `core.eol=lf`, which avoids adding local Gradle caches, virtual environments, temporary files or Windows checkout line-ending conversions. The packaging verification checks ZIP CRC, every tracked source entry against that export, all route module paths, adjacent OMP helpers, wheel Python/data bytes against source, source archive metadata, Java class version, and equality between embedded packages and standalone assets.

A first Windows export inherited checkout line-ending conversion; its assets were replaced after comparison with Git blobs exposed the difference. A fresh Gradle script compile under the host JDK 25 also failed; the final build used an isolated JDK 21 without changing host configuration. These preparation failures are retained in the local evidence and are not counted as passed builds.

The top-level `SHA256SUMS.txt` covers the complete ZIP, wheel, Python source archive and Burp JAR. The bundle's `packages/SHA256SUMS.txt` covers its three embedded packages. Installation verification uses an isolated consumer project and private Python runtime; it does not write global agent configuration.

The exact release-source commit and final artifact checks belong to the release notes and attached checksums. Preparation, a Draft Release and public publication are separate states. Consult the release PR's current-head Project checks for the candidate's Linux result.

## Remaining environment boundaries

- Synthetic protocol services, SQLite databases, exported IDA JSON, native-helper namespaces and a compiled Java callback test verify their documented paths. They do not prove a user's licensed IDA, OMP native worker, Burp GUI or connected device is configured.
- Real Apktool/Jadx downloads, Kali system installation, SSH fleet operations, Linux/macOS user setup and real network dependency repair were not repeated for this release candidate.
- The built-in regex path stays in the native owner. Custom matching children receive bounded text, share a deadline across preparation and matching, and are reaped. Full native enumeration still occurs in the original helper, outside that matching deadline.
- Swarm outputs remain advisory; model quality and usefulness require the user's own permitted evidence and configured provider. There is no claim that a partial run is a passed analysis.
- Reported optimization timings are local comparisons on the listed workloads. They do not establish overall or cross-platform speedups.

This is a testing release with these boundaries made explicit.
