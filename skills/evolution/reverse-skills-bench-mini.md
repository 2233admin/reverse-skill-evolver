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

Run identical fixtures with comparable tool versions and settings against:

- no-skill baseline
- curated skill baseline
- each evolved candidate

Before evaluation, record the affected track set and its route/oracle coverage in the GOAL. A shared routing change affects every track; a child-skill change affects its own track and every track that routes through it. If impact is uncertain, include all tracks. When route selection is the behavior being changed, each applicable track needs an oracle for expected route selection, not only the child task outcome.

Promotion requires matching or exceeding the curated baseline on oracle pass rate for every applicable track, with no materially higher invalid or repeated step count. Aggregate gains cannot hide a track regression. Missing or incomparable track results remain unknown and block promotion.

## Candidate Search

One evaluation is one candidate run across the entire frozen fixture set. `max_evaluations` counts the no-skill baseline, curated candidate, and every proposal; reflection calls have a separate `max_reflections` cap. The `reverse-skill evolve` command requires at least three full-suite evaluations and does not count a later, independent promotion check in its search budget. Never report partial-suite scores as comparable results.

Maximum logical OMP invocations are `max_evaluations * fixture_count + max_reflections`; provider retries can increase physical requests. The CLI reports this bound from the actual frozen fixture count and prints baseline/curated/reflection/proposal progress to stderr. JSON stdout remains one final envelope. Inputs and candidate text are frozen before model use; each response is checkpointed to the fresh output directory. Failures/interrupts retain `status:incomplete`, completed responses and a failure location, with no partial-suite rates or Pareto frontier. Inspect the archive before a new run; no automatic restart or resume occurs. If error archiving also fails, the original evaluation error remains visible along with the archive failure. `not_promoted` applies to complete and incomplete runs.

1. Select a parent from the current Pareto frontier.
2. Give the parent and exact failed fixture outputs to the configured OMP model for one targeted text mutation.
3. Evaluate the proposal on every same fixture; record per-track oracle pass counts/rates, invalid responses, and failure diagnostics.
4. Keep a candidate on the frontier unless another is at least as good on every per-track pass rate and invalid-response count, and strictly better on one dimension. Retain incomparable candidates; never optimize a weighted aggregate.
5. Review frontier candidates manually, then run an independent full-suite comparison against the curated baseline. Frontier membership never authorizes stable changes; keep candidates unpromoted until that check passes.

Do not score by evaluator narration alone. Missing oracle outputs, partial fixture coverage, or unlinked diagnostics are unknown, not passes.

## Optimizer Report Fields

The current `reverse-skill evolve` JSON report records:

- fixture count, per-case expected and selected route, pass status, and invalid-response diagnostic
- per-track pass counts/rates and invalid-response counts for the no-skill baseline and each candidate
- evaluation/reflection budgets and consumption, candidate/parent IDs, mutation basis, and Pareto-frontier membership
- termination reason and explicit `not_promoted` status

The route-selection optimizer does not produce TraceCards, tool-version records, elapsed/cost accounting, or downstream task outcomes. Record those separately when required by a promotion review; unavailable measurements remain unknown.

## Non-goals

- No live third-party targets.
- No unbounded exploit automation.
- No skill promotion from narration alone.
