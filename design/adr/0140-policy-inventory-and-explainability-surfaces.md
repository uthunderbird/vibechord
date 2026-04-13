# ADR 0140: Policy inventory and explainability surfaces

- Date: 2026-04-10

## Status

Accepted

## Implementation Status

Implemented

Skim-safe current truth on 2026-04-10:

- `implemented`: `operator policy list`, `operator policy inspect`, `operator policy explain`, and
  `operator policy projects` already exist as the policy read-side CLI family
- `implemented`: `policy explain` remains deterministic and separates matched policy entries from
  skipped policy entries instead of collapsing into generic prose
- `implemented`: current CLI docs describe the family in `docs/reference/cli.md`
- `verified`: focused CLI coverage for inventory, inspection, explainability, and project
  aggregation now exists in `tests/test_policy_cli.py`
- `partial`: RFC 0014 remains draft, so broader family-example closure beyond this landed slice is
  still incomplete

## Commands Covered

- `operator policy list`
- `operator policy inspect`
- `operator policy explain`
- `operator policy projects`

## Not Covered Here

- `operator policy record`
- `operator policy revoke`
- `operator answer`

## Context

The policy subgroup already has older ADRs for policy memory and explainability, but the current
CLI vision needs one visible owner for the policy read-side family as exposed in RFC 0014.

These commands answer different questions:

- what policy entries exist?
- what does one policy entry contain?
- why does policy apply or not apply?
- which projects currently have policy?

Without one current ADR, the subgroup risks staying technically capable but UX-fragmented.

## Decision

The CLI should treat `policy list`, `policy inspect`, `policy explain`, and `policy projects` as
one coherent policy inventory and explainability family.

### Command roles

- `policy list`: active policy inventory, optionally scoped
- `policy inspect`: one-entry inspection
- `policy explain`: deterministic coverage/explainability surface
- `policy projects`: project-level aggregation/index over policy-bearing projects

## Distinction Rule

These commands should remain visibly different in purpose:

- inventory
- inspection
- explanation
- aggregation

They should share vocabulary where appropriate, but they should not collapse into one repeated
layout template.

## Consequences

Positive:

- policy read-side UX becomes explainable as one family
- RFC 0014 policy-read examples gain a dedicated ADR owner

Tradeoffs:

- the subgroup must preserve both policy-entry-centric and project-centric views without confusing
  them

## Verification

Current evidence for the landed slice:

- `verified`: `policy explain` remains deterministic rather than generic prose
- `verified`: `policy inspect` remains entry-focused
- `verified`: `policy projects` remains project-aggregation-focused

The repository should preserve these conditions:

- `policy explain` remains deterministic explainability rather than generic prose
- `policy inspect` remains entry-focused
- `policy projects` remains project-aggregation-focused

## Related

- [ADR 0019](./0019-policy-memory-and-promotion-workflow.md)
- [ADR 0024](./0024-effective-control-context-cli-surface.md)
- [ADR 0166](./0166-policy-coverage-and-explainability.md)
- [RFC 0014](../rfc/0014-cli-output-contract-and-example-corpus.md)
