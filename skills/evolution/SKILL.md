---
name: evolution
description: Goal-contract, capability graph, TraceCard, and promotion-gate control plane for self-evolving reverse/security skill routing. Use before macro-routing when the task needs end-to-end completion, route repair, or reusable learning.
---

# Evolution Control Plane

This skill turns the routing pack from "pick a static module" into a closed loop:

`GOAL -> capability graph -> macro route -> micro route -> TraceCard -> evaluator feedback -> candidate search -> promotion gate`

It does not replace `apk-reverse`, `ida-reverse`, `js-reverse`, `pentest-tools`, or the CTF skills. It wraps them with a target contract, local capability facts, step-level evidence, and controlled learning.

## ACTION REQUIRED

1. `NOW`: Create or update a task-local GOAL using `goal.template.yaml` before choosing a route.
2. `NOW`: For OMP native IDA, record the current native tool schema and actual operation result through `../ida-reverse/SKILL.md`. For external tools, read `../capability-graph.json` if present; otherwise run `../scripts/refresh-tool-index.ps1` and use the generated graph.
3. `NEXT`: Use `../routing.json` for machine routing and `../routing.md` for human-readable fallback context.
4. `ACT`: Route to the selected child skill and record each material decision in a TraceCard.
5. `EVOLVE`: When changing a skill or route, use the candidate search loop below; do not optimize by editing stable files directly.
6. `END`: Classify the result through the promotion gate before changing stable routing or skill docs.
7. `DOGFOOD`: When Code Intel emits `code-intel-dogfood-finding.v1`, read `code-intel-dogfood-finding.md`; keep the finding in `candidate` until a re-run oracle proves the proposed tool repair.

## Goal Contract

Every non-trivial reverse/security task MUST define:

- `inputs`: artifacts, URLs, package names, captures, binaries, scope text, or fixture IDs.
- `authorization_scope`: CTF, own asset, lab fixture, bug bounty scope, or explicit engagement boundary.
- `desired_outputs`: what the user actually needs, such as function map, bypass replay, decoded algorithm, PoC, report, or diagram.
- `success_oracles`: deterministic checks that prove completion.
- `budgets`: max time, max tool calls, model/tool escalation limits.
- `stop_conditions`: what ends the task or requires user confirmation.

Use `goal.template.yaml` as the minimum shape. A route that cannot name its oracle is not ready to become an evolved skill.

## Capability Graph

The capability graph is a session fact cache, not a wish list.

OMP's native `ida` is a session-provided interface. Record its live schema, selected native database, and operation evidence instead of requiring the external CLI index to contain `idapro`. Graph lookup and bootstrap below apply to external tools; a native worker failure follows `omp-ida-native` setup guidance.

Required fields per tool or service:

- exact path or startup command
- version or fixed package identity
- availability state
- smoke status
- service/MCP registration state when relevant
- owning skill and bootstrap method
- `last_checked`

If the graph says a required tool is missing, use the normal bootstrap path. Do not guess paths.

## Macro Route

Macro routing chooses the module family:

- APK / Android -> `apk-reverse`
- JS / browser signature -> `js-reverse`
- binary / native / stripped -> `ida-reverse`, `radare2`, or `reverse-engineering`
- patch diff / N-day -> `binary-diff` plus `patch-diff-exploit`
- pwn -> `pwn-chain`
- protocol / pcap -> `reverse-engineering` or CTF protocol skill
- active security assessment -> `pentest-tools`, `api-security`, `attack-chain`, or related skill

Use `routing.json` first for machine decisions. Use `routing.md` when the JSON route is incomplete.

## Micro Route

Before each costly or irreversible step, choose the next action using current evidence:

- If static analysis stops producing new facts, switch to dynamic verification.
- If Java-layer evidence points to native validation, branch to IDA/radare2.
- If browser observation lacks the signing function, switch to CDP/hook/sourcemap recovery.
- If a tool fails twice for the same reason, record the failure and choose an alternate edge.
- If the required oracle cannot be tested, downgrade the conclusion to candidate or forensic memory.

Record the decision in `trace-card.template.yaml` format.

## Evidence and Unknowns

Every substantive finding MUST distinguish observed evidence, inference, and
unknowns. Each TraceCard step MUST have an `evidence_refs` list; use `[]` when
the step produced no evidence. A reference records its source and version, GOAL
input, examined coverage, and limitations. Prefer a durable evidence ID or path
over copied terminal prose. An evidence ID helps locate a record; it does not
prove the record is authentic or that its conclusion is true.

Record unresolved questions in the TraceCard with supporting and contradicting
evidence references, plus the authority, environment, or observation still
needed to resolve them. Each unknown requires `affects_outcome: true|false`.
Use `unknowns: []` when none remain. Mark an unknown resolved only when at least
one supporting or contradicting evidence ID addresses it. IDs must be nonempty
and resolve to uniquely identified evidence records in this card's steps.
Unresolved questions affecting the requested outcome block `validated` and
promotion-candidate claims.

Each oracle result records `oracle_id`, `status` (`pass|fail|not_run`), and
`evidence_refs` (in-card evidence IDs); `pass` and `fail` require evidence.
Every listed oracle is required: `validated` and `promotion_candidate: true`
require a nonempty oracle list with every oracle passed. Promotion candidacy
additionally requires the `validated` tier; it never promotes automatically.
Step evidence arrays may remain empty when no evidence was produced.

Validate JSON TraceCards at the real acceptance boundary:
`python "<PACK_ROOT>/scripts/run.py" tracecard-validate --input trace-card.json`.
The stdlib `reverse_skill.evolution.validate_trace_card` enforces structure,
unique IDs and reference consistency beyond JSON Schema's structural checks.
This proves neither authenticity nor truth of external evidence; human review
and independent verification still govern promotion.

Claims of absence or equivalence require complete, comparable coverage of the
relevant target and method. Missing, truncated, paginated, or incompatible
evidence means “unknown,” not “absent.” Static differences are leads, not proof
of runtime causation.

Lead the final report with the concise result, then link claims to evidence and
state coverage, limitations, and remaining unknowns. New TraceCards use schema
version 2; retain older version-1 records unchanged.

## Candidate Search Loop

The repository includes a bounded OMP-backed route-selection optimizer. It is scoped to the routing prompt and local fixtures; it does not run child reverse-engineering skills or prove their task outcomes.

From any working directory, using paths within the complete installed package:

```console
python "<PACK_ROOT>/scripts/run.py" evolve --candidate "<SKILL_ROOT>/routing.md" --catalog "<SKILL_ROOT>/routing.json" --fixtures "<SKILL_ROOT>/evolution/fixtures/route-selection.json" --output candidate-runs/run-001 --max-evaluations 3 --max-reflections 1
```

The command uses the configured OMP model without a model override, disables tools, skills, rules, extensions, and session persistence, then evaluates the no-skill baseline, curated prompt, and each proposed prompt on the same complete frozen fixture suite. Reflection receives the full frozen routing catalog (including relevant route/fallback definitions), exact failed tasks, expected/observed routes, invalid-response diagnostics, untouched failed responses, and successful-case context. One bounded targeted proposal is evaluated at a time. Per-track pass rates and invalid responses determine the Pareto frontier; no source prompt is promoted or overwritten.

`results.json` retains every evaluated candidate's text, UTF-8 SHA-256 identity,
artifact path, input digests, and proposal parent ID/digest—even candidates
outside the final frontier. The empty no-skill baseline is retained too.
`catalog.json` and `fixtures.json` archive the exact bytes read once for the run;
their SHA-256 identities bind every evaluation to the same frozen inputs.
Reflection contexts and exact reflection responses are also retained for audit.

Route answers must be one complete JSON object with exactly `route_id`; leading
prose, additional JSON documents, trailing text and fenced JSON are invalid.
OMP print framing is narrowly defined as at most one exact leading
`Working...` line (LF or CRLF), after leading whitespace. Only that line is
removed; matching lines inside or after an answer are never discarded.
The entire remaining answer is validated, while the untouched stdout is saved.

Task and reflection prompts already travel on stdin, not argv. Candidate system
prompts use `--append-system-prompt`. Before the first model call, the curated
candidate is checked against the Windows `CreateProcessW` limit; every actual
subprocess argv and every reflected candidate are checked as well. The bound
includes Python's Windows quoting, executable/options/cwd, UTF-16 code units,
and the terminating NUL (32,767 units). Oversized candidates are refused, not
truncated; no speculative prompt-file transport is introduced.

`max_evaluations` counts complete candidate-suite runs (baseline, curated, proposals); reflections have a separate `max_reflections` cap. The command requires budget for at least three evaluations and one reflection, but stops without proposing when every frontier candidate passes. An independent full-suite verification remains necessary for promotion and is outside this search budget. The built-in route fixture set checks route selection only; expand or replace it with validated fixtures before treating results as representative of other tasks.

## Memory Tiers

Write field-journal output into one of three tiers:

- `validated`: oracle passed, route worked, safe to retrieve for future routing.
- `candidate`: promising but not regression-tested; may inform, must not control routing.
- `forensic`: failed, ambiguous, sensitive, or adversarial; useful for analysis only.

All memory entries MUST include provenance: source trace, tool versions, verification time, and applicable environment.

Code Intel dogfood findings are advisory evidence, not an authority override.
Consume their artifact digests through
[`code-intel-dogfood-finding.md`](code-intel-dogfood-finding.md), then retain
them in `candidate` until the cited project has been re-run after a repair.

## Promotion Gate

Stable routing or child skill docs may change only when a candidate passes:

- oracle success for the source task
- no regression in the mini benchmark or relevant fixtures
- clear tool/capability requirements
- no sensitive or un-anonymized data
- rollback path documented

Use `promotion-record.template.yaml`. If evidence is incomplete, keep the entry in `candidate`.

## Completion Check

- [ ] GOAL exists and names at least one success oracle.
- [ ] OMP native IDA schema and operation evidence were recorded, or the external capability graph was read/refreshed.
- [ ] Macro route and any micro-route switches are recorded.
- [ ] TraceCard records reproducible actions, evidence references, coverage, limitations, and unresolved questions.
- [ ] Field-journal tier is selected.
- [ ] Stable routing changes passed the promotion gate.

## 无人值守模式（Overnight）

本控制面的 Phase 0-3 全闭环无人值守运行由 `overnight-run/` 提供：slot 填表 ↔ `goal.template.yaml`，`.night/REPORT.md` ↔ TraceCard，Phase 结局 ↔ 记忆分层，早上 review ↔ promotion gate。详见 `overnight-run/SKILL.md`。Overnight 产出的经验必须经 promotion gate 回流 `field-journal/{validated,candidate,forensic}/` 后才允许改 stable 路由。

## Fleet Sync

This repo can run on more than one machine in the operator's fleet. Session-local artifacts --
`skills/field-journal/candidate/*.md`, `skills/field-journal/validated/*.md`,
`skills/capability-graph.json`, `skills/tool-index.md` -- only exist on whichever machine
produced them until manually synced.

Run `skills/scripts/fleet-sync.ps1 -RemotePath <remote-repo-path> -Direction Pull|Push` after a
session adds new `candidate/` entries and you are about to switch machines, or periodically to
keep both machines' capability graphs roughly aligned. The script only copies files that do not
already exist on the destination by filename (collision-safe additive merge) -- it never
overwrites and never deletes on either side. Filename collisions are reported, not resolved
automatically; resolve by hand and re-run.
