# ADR 0164: Initial Policy Applicability And Matching Semantics

## Decision Status

Superseded

## Implementation Status

N/A

Repository-governance note on 2026-04-13:

- this document was renumbered from duplicate `ADR 0028` to remove identifier ambiguity
- its decision text is retained as historical design provenance only
- the canonical accepted policy-applicability ADR is [ADR 0029](./0029-policy-applicability-matching.md)

## Context

[ADR 0019](/Users/thunderbird/Projects/operator/design/adr/0019-policy-memory-and-promotion-workflow.md)
introduced explicit project-local policy memory, promotion, inspection, and revocation.

That slice made policy durable and inspectable, but it left one important gap open on purpose:

- active policy was included by project scope only
- all active policy in that scope was injected into operation context
- and there was no explicit matching model for when one policy should apply to one operation

This weakens the product in two ways:

- the operator sees irrelevant policy noise for many runs
- and a missing relevant policy cannot be distinguished cleanly from "some project policy exists"

The architecture and ADR 0019 both reject hidden heuristics here.
The next step needs to stay deterministic, inspectable, and grounded in persisted operation truth.

## Decision

`operator` will add a small explicit applicability model to `PolicyEntry` and use deterministic
matching against persisted operation truth when refreshing active policy context.

The first accepted applicability slice supports:

- objective and harness keyword matching
- task title, goal, and note keyword matching
- adapter-key matching
- run-mode matching
- involvement-level matching

Matching is:

- explicit in stored policy records
- conjunctive across configured fields
- disjunctive within one field
- and explainable from current operation state

If a policy has no applicability filters, it remains a scope-wide policy for all operations in the
project scope.

## Alternatives Considered

- Option A: keep project-scope-only inclusion
- Option B: use fuzzy brain-side policy selection with no explicit matching model
- Option C: add explicit deterministic applicability filters on `PolicyEntry`

Option A was rejected because policy memory would stay too blunt to materially improve autonomy.

Option B was rejected because it would hide policy applicability inside prompt behavior and weaken
auditability.

Option C was accepted because it tightens policy relevance without creating a second hidden policy
system.

## Consequences

- Active policy context becomes smaller and more relevant for each operation.
- Existing CLI surfaces such as `context`, `dashboard`, and `policy inspect` can explain why a
  policy applied.
- Policy promotion stays explicit; this ADR changes applicability, not promotion semantics.
- Novelty and policy-gap detection still remain follow-on work; this slice provides the substrate
  rather than claiming full automatic gap detection.
