# Code Intel Dogfood Finding Contract

Use this adapter when a real project exposes a Code Intel Pipeline false positive,
false negative, onboarding gap, or other tool limitation.

## Input

Consume only a locally generated `code-intel-dogfood-finding.v1` JSON artifact.
Its evidence must remain bound to:

- the Code Intel `run-complete.json` digest;
- snapshot identity;
- run identity;
- manifest digest; and
- cited diagnostic artifact digest.

Do not replace these references with copied terminal prose.

## Routing

| `target.repository` | Action |
|---|---|
| `code-intel-pipeline` | Create a candidate repair record for the Pipeline. |
| `reverse-skill-evolver` | Create a candidate routing/methodology repair record. |
| other project | Treat as project work, not a tool defect. |

## Promotion boundary

A dogfood finding is advisory evidence. It MUST start in `candidate` and MUST
NOT modify stable routing, a validated field-journal entry, or a tool bootstrap
manifest until:

1. the original condition is reproducible from the cited artifact;
2. the proposed repair has a deterministic oracle;
3. the same project is re-run after the repair; and
4. the repaired result no longer misclassifies the condition.

TraceCards consuming the finding MUST cite the artifact digest and record the
classification, proposed repair, and re-run oracle result.

## First known finding

`tdxcli-rs` demonstrated a missing ignored `.sentrux/baseline.json` causing a
normal Code Intel run to be classified as `domain_failed` with an architecture
gate diagnosis. This is a candidate onboarding finding, not proof of a tdxcli-rs
architecture defect.
