# ReverseSkillsBench-mini

This mini benchmark is the promotion gate for evolved routing and skill changes. It must stay small, deterministic, and safe.

## Tracks

| Track | Fixture type | Example oracle |
|---|---|---|
| APK / Android | toy APK or CTF APK | decoded manifest + located validation function + replayed bypass fixture |
| JS / browser | local JS bundle or fixture page | deterministic parameter generator output matches expected value |
| Native binary | toy ELF/PE/so | target function identified and expected string/branch recovered |
| Patch diff | two toy versions | changed function and root cause labeled |
| PCAP / protocol | local pcap fixture | parser extracts expected fields and sequence |
| Report quality | sanitized trace fixture | report contains commands, evidence, and oracle result |

## Baselines

Run each fixture against:

- no-skill baseline
- curated skill baseline
- evolved candidate

Promotion requires the evolved candidate to match or exceed the curated baseline on oracle pass rate and avoid materially higher invalid step count.

## Required Result Fields

- fixture id
- route selected
- tools used
- oracle status
- invalid or repeated step count
- elapsed time
- memory tier decision
- promotion decision

## Non-goals

- No live third-party targets.
- No unbounded exploit automation.
- No skill promotion from narration alone.
