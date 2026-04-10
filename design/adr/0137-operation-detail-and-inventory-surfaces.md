# ADR 0137: Operation detail and inventory surfaces

- Date: 2026-04-10

## Status

Accepted

## Implementation Status

Implemented

Skim-safe current truth on 2026-04-10:

- `implemented`: `operator tasks`, `operator memory`, `operator artifacts`, and `operator attention`
  already exist as public operation-scoped detail surfaces
- `implemented`: each covered command already supports default human-readable output and `--json`
  machine-readable output
- `implemented`: current CLI docs already list this family as secondary detail/inventory surfaces
- `verified`: focused CLI coverage for this family already exists in `tests/test_cli.py`
- `partial`: this ADR's broader RFC 0014 family-output closure remains incomplete because the RFC is
  still draft and ahead of shipped examples in places

## Commands Covered

- `operator tasks`
- `operator memory`
- `operator artifacts`
- `operator attention`

## Not Covered Here

- `status`
- `watch`
- `report`
- `log`

## Context

The CLI vision retains several operation-scoped detail surfaces as secondary commands.

They are useful, but easy to under-specify because the main product energy tends to focus on:

- `status`
- `watch`
- `session`
- TUI

RFC 0014 now gives these commands a shared home as detail/inventory surfaces, but the ADR corpus
does not yet have one explicit owner for them as a family.

## Decision

The CLI should treat `tasks`, `memory`, `artifacts`, and `attention` as the retained operation
detail and inventory family beneath `status`.

### Family posture

These commands exist to answer deeper structured questions that `status` intentionally keeps brief.

They remain secondary rather than primary because the default operator workflow should start from
summary/live surfaces first.

### Command roles

- `tasks`: task-board and work-structure detail
- `memory`: durable memory entries associated with the operation
- `artifacts`: durable produced artifacts
- `attention`: detailed attention inventory beyond the summary line in `status`

## Relationship To `status`

`status` may summarize these domains, but it does not replace them.

Accepted rule:

- `status` answers "what matters now?"
- detail commands answer "show me the structured underlying domain"

## Consequences

Positive:

- retained detail commands gain one explicit product owner
- RFC 0014 family D examples become grounded in a dedicated ADR

Tradeoffs:

- these commands must remain clearly secondary to avoid flattening the CLI back into a bag of
  peers

## Verification

Current evidence for the landed slice:

- `verified`: `tasks`, `memory`, `artifacts`, and `attention` human-readable / `--json` behavior
  are covered in `tests/test_cli.py`
- `not yet verified`: full RFC 0014 closure for this command family

The repository should preserve these conditions:

- these commands expose structured detail, not another summary flavor
- `attention` remains useful even though `status` summarizes blocking attention
- `tasks`, `memory`, and `artifacts` remain human-readable by default

## Related

- [ADR 0096](./0096-one-operation-control-and-summary-surface.md)
- [ADR 0116](./0116-cli-parity-gaps-for-fleet-operation-and-session-surfaces.md)
- [RFC 0014](../rfc/0014-cli-output-contract-and-example-corpus.md)
