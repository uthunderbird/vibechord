# Plan 0001: Foundation Implementation

Status: `complete`

## Goal

Build the smallest executable `vibechord` foundation that proves the operation
loop, event authority, command application, fake dependencies, and local
verification rails.

## Scope

- Python package skeleton.
- Domain event and operation models.
- File-backed event store.
- Replay state builder.
- Command application service.
- Operation driver with fake brain and fake agent adapter.
- CLI `init`, `run`, `status`, and `fleet --once`.
- E2E fake harness.

## Dependencies

- ADR 0001 operation-loop event authority.
- ADR 0003 adapter and brain protocols.
- ADR 0004 testing rails.
- ADR 0007 minimum moving parts.

## Out of Scope

- Real LLM provider.
- Real external agent process adapter.
- Interactive TUI.
- REST server.

## Work Items

1. Create package and tooling configuration.
2. Define domain models and event schemas.
3. Implement event store contract and file-backed store.
4. Implement replay builder.
5. Implement `CommandApplication` for start, cancel, attention answer, and
   operator message.
6. Implement `OperationDriver` using fake brain/adapter protocols.
7. Implement `ProjectionService` for status, fleet, and live-feed envelopes.
8. Implement `AdapterGateway` with fake brain/adapter integrations.
9. Implement initial CLI commands.
10. Add fast/focused/full verification commands.
11. Add E2E fake harness summary artifact.

## Verification

- VS-001 domain and guardrail unit scenarios.
- VS-002 protocol conformance scenarios.
- VS-003 event store and replay scenarios.
- VS-004 operation loop fake-harness scenarios.
- VS-006 CLI contract scenarios for the first CLI slice.
- VS-012 architecture fitness scenarios.

## Exit Gate

Plan 0002 should not begin until the fake harness can create an operation,
append and replay events, submit a command, rebuild status/fleet projections,
and emit an inspectable summary artifact.

The exit gate must prove the six-part core in
[MOVING-PARTS.md](../MOVING-PARTS.md): Domain Model, `CommandApplication`,
`OperationDriver`, `EventStore`, `ProjectionService`, and `AdapterGateway`.
