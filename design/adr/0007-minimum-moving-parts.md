# ADR 0007: Minimum Moving Parts

- Date: 2026-05-23

## Decision Status

Accepted

## Implementation Status

Verified

Scope: first implementation slice.

## Context

`vibechord` must cover operation lifecycle, event-backed replay, adapters,
CLI/TUI/REST delivery, fleet, live chat, proactive projection safety, and local
verification without recreating `operator`'s accumulation of authority
boundaries.

The design already has strong authority rules, but the application-service list
could still split into too many independently evolving services.

## Decision

The first implementation will use six core moving parts:

1. `Domain Model`;
2. `CommandApplication`;
3. `OperationDriver`;
4. `EventStore`;
5. `ProjectionService`;
6. `AdapterGateway`.

CLI, TUI, REST, future SDK, future MCP, and concrete vendor adapters are
extensions over those core parts. They are not independent business authorities.

[MOVING-PARTS.md](../MOVING-PARTS.md) is the detailed design contract for this
decision.

## Consequences

Positive:

- The first implementation has fewer authority boundaries to test and reason
  about.
- Fleet, status, and live feed projections share one projection authority.
- Delivery surfaces can expand without multiplying command/query semantics.
- Adapter variety is isolated behind one gateway boundary.

Negative:

- `ProjectionService` may become internally dense if implementation does not
  keep its functions/modules organized.
- Some future features may need a new boundary, but they must earn it through
  an ADR rather than local convenience.

## Verification Plan

- Scenario coverage: VS-005 and VS-012 in
  [VERIFICATION-SCENARIOS.md](../VERIFICATION-SCENARIOS.md).
- Architecture fitness checks reject per-surface command handlers.
- Architecture fitness checks reject delivery modules that bypass
  `CommandApplication` or `ProjectionService`.
- Architecture review checks any new core moving part against
  [MOVING-PARTS.md](../MOVING-PARTS.md).
