---
name: evolution
description: Goal-contract, capability graph, TraceCard, and promotion-gate control plane for self-evolving reverse/security skill routing. Use before macro-routing when the task needs end-to-end completion, route repair, or reusable learning.
---

# Evolution Control Plane

This skill turns the routing pack from "pick a static module" into a closed loop:

`GOAL -> capability graph -> macro route -> micro route -> TraceCard -> oracle -> promotion gate`

It does not replace `apk-reverse`, `ida-reverse`, `js-reverse`, `pentest-tools`, or the CTF skills. It wraps them with a target contract, local capability facts, step-level evidence, and controlled learning.

## ACTION REQUIRED

1. `NOW`: Create or update a task-local GOAL using `goal.template.yaml` before choosing a route.
2. `NOW`: Read `../capability-graph.json` if present; otherwise run `../scripts/refresh-tool-index.ps1` and use the generated graph.
3. `NEXT`: Use `../routing.json` for machine routing and `../routing.md` for human-readable fallback context.
4. `ACT`: Route to the selected child skill and record each material decision in a TraceCard.
5. `END`: Classify the result through the promotion gate before changing stable routing or skill docs.

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

## Memory Tiers

Write field-journal output into one of three tiers:

- `validated`: oracle passed, route worked, safe to retrieve for future routing.
- `candidate`: promising but not regression-tested; may inform, must not control routing.
- `forensic`: failed, ambiguous, sensitive, or adversarial; useful for analysis only.

All memory entries MUST include provenance: source trace, tool versions, verification time, and applicable environment.

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
- [ ] Capability graph was read or refreshed.
- [ ] Macro route and any micro-route switches are recorded.
- [ ] TraceCard includes evidence, not just narration.
- [ ] Field-journal tier is selected.
- [ ] Stable routing changes passed the promotion gate.

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
