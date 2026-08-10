# AIGX-first routing bootstrap

This repository uses AIGX as the mandatory context plane. `.aigx/` is the sole canonical source for project rules and per-file boundaries; this file is only a compatibility bridge.

1. Read `.aigx/protocol.aigx` and the concern files touched by the task.
2. Run `reverse-skill context <project-root> --target <repo-relative-file>` for project-aware work. A missing genome, failed lint, or unresolved edit boundary is blocking.
3. Run `reverse-skill route <task> --project-path <project-root> --aigx-target <repo-relative-file>` for deterministic routing.
4. Only when the route is `ready`, load `skills/SKILL.md`, the selected child skill, and current capability evidence. Execution remains opt-in through `--execute`.
5. Use `reverse-skill plugins inventory` and `reverse-skill teams preflight <repo>` for IDA plugin and Teams readiness. The newest usable local IDA is selected automatically unless `--ida-dir` is explicit.

Do not write global client configuration, install dependencies, or run compatibility PowerShell scripts as a side effect of reading this package. Interactive IDA sign-in or installation must stay an explicit user-facing action. Session roles, worktrees, credentials, mutable evidence, and target identity remain external runtime data.
