# Plan 0002: Delivery Surfaces

Status: `complete`

## Goal

Build CLI, TUI, and REST delivery surfaces over shared application contracts
without creating separate business authority.

## Scope

- CLI command family completion.
- TUI workbench first slice.
- REST API first slice.
- Shared operation resolver.
- Shared status/fleet/query payloads.
- Shared command response and error taxonomy.
- Live-feed envelope delivery.

## Dependencies

- Plan 0001 exit gate.
- ADR 0002 shared delivery surfaces.
- ADR 0005 fleet and live chat.
- ADR 0006 REST API delivery surface.
- ADR 0007 minimum moving parts.

## Work Items

1. Define shared delivery DTOs.
2. Implement operation resolver.
3. Expand CLI command coverage.
4. Implement TUI view models and pure renderers.
5. Implement REST endpoints for operations, commands, messages, attention,
   fleet, and events.
6. Wire all surfaces through `CommandApplication` and `ProjectionService`.
7. Add live-feed transport for CLI watch, TUI, and REST.

## Verification

- VS-005 delivery parity scenarios.
- VS-006 CLI contract scenarios.
- VS-007 TUI projection and reducer scenarios.
- VS-008 REST API contract scenarios.
- VS-009 REST safety and exposure scenarios before non-local exposure.
- VS-010 fleet and live chat scenarios.
- VS-012 architecture fitness scenarios.

## Exit Gate

CLI JSON, TUI view models, and REST responses must use shared DTOs for covered
operation status, fleet rows, command responses, errors, and live-feed
envelopes.

No delivery surface may introduce per-surface command handlers or separate
operation/fleet state.
