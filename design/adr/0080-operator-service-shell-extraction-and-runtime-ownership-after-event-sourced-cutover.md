# ADR 0080: OperatorService shell extraction and runtime ownership after event-sourced cutover

## Status

Accepted

## Context

[`RFC 0009`](../rfc/0009-operation-event-sourced-state-model-and-runtime-architecture.md)
states that `OperatorService` must become an orchestration shell once canonical business mutation
and replay stop living inside it.

Accepted foundations already exist for:

- event storage and checkpoint derivation (`ADR 0069`)
- projection (`ADR 0071`)
- process-manager behavior (`ADR 0072`)
- command-bus and planning-trigger behavior (`ADR 0073`)

What remains open is the repository-facing ownership boundary after cutover:

- what `OperatorService` still owns
- what it must stop owning
- what shape replaces its current helper-heavy procedural mutation role

Without this decision, event-sourced implementation could still leave the same god object in place,
merely delegating some persistence details.

### Current truth

The repository still routes most operation behavior through `OperatorService`, including business
mutation, reconciliation logic, and recovery behavior. The service remains a large mixed-responsibility
entrypoint rather than a thin shell.

## Decision

After event-sourced cutover for an operation, `OperatorService` is an orchestration shell and
composition root, not the owner of canonical business transition semantics.

### Responsibilities retained by `OperatorService`

`OperatorService` remains responsible for:

- public application entrypoints such as `run`, `resume`, `cancel`, and external command handling
- dependency composition and delegation to narrower application/runtime services
- top-level transaction and error-boundary coordination
- selection of the correct operation mode path based on operation metadata

### Responsibilities removed from `OperatorService`

For `event_sourced` operations, `OperatorService` must no longer directly own:

- command validation against canonical business truth
- business-state mutation through procedural helper ordering
- canonical replay/materialization logic
- hidden reconciliation rules that implicitly decide new business state
- event append authority

### Downstream ownership

The shell delegates to narrower components that own:

- command application and domain-event append
- canonical replay and checkpoint materialization
- process-manager follow-up evaluation
- runtime coordination and recovery execution

Those components may collaborate, but the shell itself must not re-absorb their business logic.

### Sunset rule for snapshot-era helpers

Snapshot-era helper methods that exist only because `OperatorService` currently mutates canonical
business state must be removed or demoted once the event-sourced path becomes canonical for the
target operation mode.

Keeping them around as unused or half-active fallback logic is architectural drift.

## Consequences

- Event-sourced rollout has a concrete service-boundary target instead of only a storage target.
- The repository can reduce `OperatorService` size and private helper count for structural reasons,
  not just aesthetic ones.
- Business transition semantics become easier to test in narrower units.
- Future runtime-layer ADRs can attach operation coordination to dedicated runtime components
  without pretending that `OperatorService` still owns everything.

## Closure Notes

- `OperatorService` now delegates one real business-mutation slice to narrower application
  services instead of owning all operation-scoped mutation semantics directly:
  - `SnapshotOperationCommandService` now owns snapshot-backed operation-scoped command mutation
    logic for pause/resume, involvement-level updates, objective/harness/constraint/success-criteria
    patches, and operator-message injection
  - `EventSourcedCommandApplicationService` owns event-sourced command application and canonical
    domain-event append
  - `EventSourcedReplayService` owns canonical checkpoint-plus-suffix replay and checkpoint
    materialization
- `OperatorService` remains the shell that:
  - selects the path based on operation mode and command kind
  - persists state or command status
  - emits trace/events
  - dispatches process-manager follow-up signals
- This ADR is accepted as a shell-extraction foundation slice. `OperatorService` is not yet fully
  minimized, and several runtime/recovery branches still live there. The repository truth is now
  materially closer to the intended shell boundary, but not at the final end state described by
  RFC 0009.
- Verification:
  - dedicated snapshot-operation-command tests pass
  - service regression tests pass
  - full repository test suite passes (`289 passed, 11 skipped`)

## This ADR does not decide

- the exact class graph or module layout after shell extraction
- whether operation coordination lives behind an `OperationRuntime` protocol or first appears as an
  internal service
- the concrete command-application or replay signatures
- legacy snapshot-mode ownership during the migration window

Those are covered by adjacent ADRs, especially `ADR 0077`, `ADR 0078`, `ADR 0079`, and the RFC
0010 follow-up batch.

## Alternatives Considered

### Keep `OperatorService` as the business mutation owner and only swap persistence internals

Rejected. That preserves the root architecture smell that RFC 0009 exists to remove.

### Split `OperatorService` into many helper classes without changing authority boundaries

Rejected. That is structural refactoring without a truth-model correction.

### Move all runtime and business logic into one new runtime object immediately

Rejected. That over-collapses separate concerns and leaves insufficiently narrow executable
decisions for later ADRs.
