# AIGX-first routing bootstrap

This repository uses AIGX as the mandatory context plane. `.aigx/` is the sole canonical source for project rules and per-file boundaries.

1. Read `.aigx/protocol.aigx` and the concern files touched by the task.
2. Before editing an indexed non-genome file, resolve its binding entry in `.aigx/files.aigx`; validate genome edits with official lint.
3. For a target project, run `python skills/scripts/aigx_context.py --project-path <project-root> --target <repo-relative-file>`; a missing or invalid genome and an unresolved edit target are blocking conditions.
4. Run `python skills/scripts/route_task.py --task <task> --project-path <project-root> --aigx-target <repo-relative-file> --pretty` for deterministic routing.
5. Only after the AIGX preflight passes, load `skills/SKILL.md`, `skills/evolution/SKILL.md`, the selected child skill, and current capability evidence.

Session roles, worktrees, credentials, mutable evidence, and convergence records remain external runtime data. They MUST NOT be written into AIGX or persisted as target-project identity in this generic repository.
