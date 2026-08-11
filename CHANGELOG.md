# Changelog

All notable changes to **reverse-skill-evolver** are documented in this file.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versioning follows [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [2.0.0b3] — 2026-08-11

### Added
- **Case contract freeze** — `reverse_skill/data/case-contracts.json` is the single machine-readable
  source for case enums, presets, ID patterns, and review statuses. `skills/ops/*.md` are human-readable
  mirrors; no parallel enums.
- **Python case chain** — `reverse-skill case init` / `case review` implement upstream
  `case-init.sh` + `review_case.py` behavior in the packaged Python CLI: network profile
  normalization (aliases `lab`, `authorized`, `auth`, `offline_only`), SHA-256 fixity verification,
  fail-closed path-escape protection (`artifact.outside_case` is an error, not a warning), strict
  mode, and stable JSON envelope + exit codes (0/2/5).
- **Routing benchmark migration** — upstream `skills/tests/routing-benchmark.json` (163 cases)
  migrated to `tests/data/routing-benchmark.json` as an independent black-box fixture with explicit
  `expect_local` (stable route id or `no_route`); `reverse_skill/data/upstream-route-crosswalk.json`
  is the explicit R0-R40 crosswalk. Rejected domains are registered, not keyword-fallbacked.
- **Python repository gates** — `reverse-skill gates` (`leak-scan`, `doc-facts`, `version`,
  `routing-coherence`, `all`) replace the PowerShell gates; CI calls the Python gates only.
- **Adopted `case-review` skill** — `skills/case-review/SKILL.md` + stable route id `case-review`.
- **DSL-VM and 19 upstream top-level modules audited** — see `docs/UPSTREAM-DOMAIN-COVERAGE.md`
  for the adopted / superseded / rejected matrix.

### Fixed
- `skills/field-journal/anonymization.md` contained a real public IP (`45.32.10.5`); replaced with
  the documentation-reserved `203.0.113.5` so the leak-scan gate stays clean.

### Changed
- Version bumped to `2.0.0b3` across pyproject, package, OpenCLI, READMEs, and ARCHITECTURE.
- Removed `skills/scripts/verify-routing-coherence.ps1` and `skills/scripts/refresh-ida-capabilities.ps1`
  (fully superseded by Python gates / `refresh_ida_capabilities.py`).
- Overnight-run dogfood `TEST_CMD` now uses `python -m reverse_skill gates routing-coherence`.

### Removed
- PowerShell gates replaced by Python gates; PowerShell remains only a compatibility surface
  (`ENG-python-primary`).

## [2.0.0b2] — 2026-08-11

### Added
- Packaged Python CLI with AIGX context gate, deterministic router, IDA MCP dual-era client,
  plugins inventory, Teams collaboration preflight, and YARA integration.
- OpenCLI 0.1 description and stable JSON output envelope.

## [1.0.x] — upstream line

Prior 1.0.x releases belong to the upstream `reverse-skill` repository line
(https://github.com/zhaoxuya520/reverse-skill). This repository tracks the Python-main-chain
evolution (`2.0.0b*`).
