# Plan 0003: Real Adapter Integration

Status: `complete`

## Goal

Add real operator-brain and external-agent adapters without changing core
operation semantics.

## Scope

- Operator brain provider implementation.
- First external agent adapter.
- Provider DTO mapping.
- Permission/approval handling if required by adapter.
- Forensic log capture as evidence, not canonical truth.

## Dependencies

- Plan 0001 exit gate.
- Adapter protocol tests from ADR 0003.
- ADR 0007 minimum moving parts.
- Delivery command/query parity from Plan 0002 for any surfaced adapter status.

## Work Items

1. Select first provider and agent adapter.
2. Implement provider DTOs and mappers.
3. Implement adapter protocol behind `AdapterGateway`.
4. Add adapter conformance tests.
5. Add forensic log capture.
6. Add integration tests guarded from default local fake suite if they require
   external binaries or credentials.

## Verification

- VS-002 protocol conformance scenarios.
- VS-011 adapter integration scenarios.
- VS-012 architecture fitness scenarios.
- Optional integration tests documented separately from default local gates.

## Exit Gate

Real adapters may be enabled only when fake-adapter tests still pass unchanged
and provider-specific failures surface as explicit adapter/runtime events rather
than hidden fallback behavior.

Real adapters must not add new core moving parts unless a new ADR updates
[MOVING-PARTS.md](../MOVING-PARTS.md).
