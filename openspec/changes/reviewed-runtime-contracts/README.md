# Reviewed runtime contracts repair

- Proposal: `proposal.md`
- Design and failure modes: `design.md`
- Acceptance scenarios: `specs/reviewed-runtime-contracts/spec.md`
- Work breakdown: `tasks.md`
- Tracker: GitHub issue [#2](https://github.com/2233admin/reverse-skill-evolver/issues/2)

Scope: repair the observed evolution-runner audit/response contracts, CLI validation metadata, and bounded async Burp scheduling. Candidate promotion remains manual. Runtime MCP validation stays conditional on the local service being available; do not install it as part of this change.
