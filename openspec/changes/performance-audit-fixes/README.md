# Performance audit fixes

- Proposal: `proposal.md`
- Design and failure modes: `design.md`
- Acceptance scenarios: `specs/performance-audit-fixes/spec.md`
- Work breakdown: `tasks.md`

Scope: implement the 13 audited, locally actionable performance and resilience findings across the Node bridge, Burp extension, Python MCP/IDA CLI, diagram renderer, and Java build scripts. No promotion behavior changes. No issue is created, per the selected direct-fix path.

Acceptance requires behavior-preserving regressions, Python tests, Java compilation/scheduler checks where available, and bridge/diagram/build-path smoke checks. Push a new branch only; do not merge.
