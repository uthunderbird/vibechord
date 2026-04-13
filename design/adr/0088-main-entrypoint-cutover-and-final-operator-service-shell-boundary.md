# ADR 0088: Main entrypoint cutover and final OperatorService shell boundary

## Decision Status

Accepted

## Implementation Status

Implemented

## Context

`ADR 0080` established a foundation-shell boundary for `OperatorService`, but accepted that the
repository was not yet fully shell-first by runtime truth.

To close `RFC 0009`, the main entrypoints must stop behaving as snapshot-era business mutation
owners.

### Current truth

`OperatorService` still:

- exposes the main runtime entrypoints
- depends on snapshot-era operation loading and mutation paths
- contains direct business logic in the live `run` / `resume` / `recover` / `cancel` flow

## Decision

After cutover, `OperatorService` remains the public application entrypoint but only as an
orchestration shell.

### Entrypoint rule

The main entrypoints:

- `run`
- `resume`
- `recover`
- `tick`
- `cancel`

must operate on canonical event-sourced truth only.

### Retained shell responsibilities

`OperatorService` may retain:

- public application-facing entrypoint methods
- dependency composition and delegation
- trace/event emission that does not mutate canonical business state
- durable intent dispatch and runtime lifecycle coordination

### Removed responsibilities

`OperatorService` must not directly own:

- snapshot-first business mutation
- canonical state validation through mutable `OperationState`
- replay/materialization authority
- direct fact-to-domain translation ownership
- snapshot-era command mutation services in the live event-sourced path

## Consequences

- The main runtime path finally matches the shell architecture promised by `RFC 0009`.
- `OperatorService` size and private-helper count can shrink for structural rather than cosmetic
  reasons.
- Canonical business mutation becomes auditable outside the public facade layer.

## This ADR does not decide

- the lower runtime contracts beneath the shell
- the exact event catalog used by the canonical loop
- historical migration/import handling for pre-cutover snapshot operations

## Alternatives Considered

### Keep `OperatorService` as the business owner while replacing storage internals underneath it

Rejected. That leaves repository truth procedurally snapshot-era even if persistence changes.

### Replace `OperatorService` entirely as the public application facade

Rejected for this wave. The closure goal is boundary correction, not a public naming rewrite.

## Verification

- `verified`: `run`, `resume`, `recover`, and `tick` delegate entrypoint state preparation to
  `OperationEntrypointService` rather than owning that preparation inline inside `OperatorService`.
- `verified`: `cancel` delegates cancellation-state mutation to `OperationCancellationService`.
- `verified`: attached-turn lifecycle mechanics live in `AttachedTurnService` rather than in the
  public facade.
- `verified`: the main orchestration loop lives in `OperationDriveService`; `_drive_state()` is a
  thin delegation from `OperatorService`.
- `verified`: focused tests cover entrypoint preparation, replay-backed resume, shell delegation,
  drive-loop behavior, and cancellation behavior through the extracted application-service
  boundaries.
- `verified`: the full repository suite passes at current repository truth (`580 passed, 11 skipped`).

## Implementation notes

Current repository truth satisfies this ADR.

Implemented:

- `OperatorService` remains the public facade while delegating run/resume/recover/tick entrypoint
  preparation to `OperationEntrypointService`.
- `OperatorService.cancel()` delegates cancellation flow to `OperationCancellationService`.
- `_drive_state()` delegates directly to `OperationDriveService.drive()`.
- attached-turn mechanics are owned by `AttachedTurnService` instead of the facade.

Residual design debt that does not block this ADR:

- lifecycle and control-state helpers still use persisted `OperationState` checkpoints as the
  runtime view, but the public shell no longer owns those mutation semantics directly.
- further shell thinning remains possible, but it is incremental boundary cleanup rather than an
  open acceptance blocker for the main entrypoint cutover.
