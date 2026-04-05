# ADR 0088: Main entrypoint cutover and final OperatorService shell boundary

## Status

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

- `verified`: `run`, `resume`, `recover`, and `tick` now delegate entrypoint state preparation to
  `OperationEntrypointService` rather than owning that preparation inline inside `OperatorService`.
- `verified`: `cancel` now delegates cancellation-state mutation to
  `OperationCancellationService`.
- `verified`: attached-turn lifecycle mechanics now live in `AttachedTurnService` rather than in
  the public facade.
- `verified`: the main orchestration loop now lives in `OperationDriveService`; `_drive_state()`
  is reduced to thin delegation from `OperatorService`.
- `verified`: focused tests cover entrypoint preparation and cancellation behavior through the new
  application-service boundaries, and the full suite passes after loop extraction.
- `verified`: a direct smoke-run against `/Users/thunderbird/Projects/femtobot` confirmed that
  attached background execution no longer burns operator iterations while the agent is still
  working. The run remained blocked on the live session until a real background result arrived,
  rather than failing immediately with `Maximum iterations reached.`
- `verified`: a follow-up smoke-run against `/Users/thunderbird/Projects/femtobot` using
  `gpt-5.3-codex-spark` with `effort=high` completed successfully after a reusable-session
  continuation, confirming that the rehydrated background continuation path no longer fails with
  `No live session is available for follow-up message.`

## Implementation notes

This ADR is not yet `Accepted`.

What is implemented now:

- `OperatorService` remains the public facade
- public entrypoints delegate more of their state-loading and state-preparation work into narrower
  application services
- cancellation semantics are no longer owned inline in the public facade
- attached-turn lifecycle mechanics are no longer owned inline in the public facade
- the main orchestration loop is no longer owned inline in the public facade

What remains open before `Accepted`:

- live runtime truth is not yet event-sourced-only by repository behavior
- some operation-lifecycle logic is still delegated through snapshot-era state mutation helpers even
  though those helpers now sit behind narrower application services
