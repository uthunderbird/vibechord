# ADR 0203: Canonical v2 Persistence Authority

- Date: 2026-04-23

## Decision Status

Accepted

## Implementation Status

Implemented

Skim-safe status on 2026-04-24:

- `implemented`: `OperatorServiceV2` creates and cancels operations by appending canonical domain
  events through `OperationEventStore`; it does not accept or persist `OperationState` snapshots
- `implemented`: `DriveService` reloads canonical aggregate state from replay, appends new domain
  events, and persists only derived checkpoints through `OperationCheckpointStore`
- `implemented`: event-sourced birth and replay services materialize the
  `operation_events` / `operation_checkpoints` authority pair directly, with checkpoints rejected
  if they ever get ahead of the event stream
- `implemented`: CLI resolution and list surfaces now load canonical v2 operation state from
  replayed checkpoints when `.operator/runs` is absent instead of treating
  `FileOperationStore.list_operations()` as complete
- `implemented`: status/inspect already replay canonical v2 checkpoint truth when no legacy run
  snapshot exists
- `verified`: `uv run pytest` passed on 2026-04-24 at the repository state that closes this ADR

## Context

The v2 architecture intends `operation_events` to be the canonical operation truth and
`operation_checkpoints` to be a derived replay accelerator. The repository still has many paths
where `FileOperationStore` and `.operator/runs` remain authoritative for reads, mutation, history,
or delivery behavior.

This creates split truth:

- v2 operations can exist only in `operation_events`
- legacy commands can fail because they look only in `.operator/runs`
- status/inspect may need event-sourced fallback logic
- tests can pass while public surfaces still depend on snapshots

The operator cannot be fully canonical v2 until persistence authority is singular and explicit.

## Decision

For new v2 operations, canonical operation truth is:

1. `.operator/operation_events/<operation_id>.jsonl`
2. `.operator/operation_checkpoints/<operation_id>.json` as derived replay cache
3. explicit read models projected from the event stream

`.operator/runs` and `FileOperationStore` are not authoritative for v2 operation state. They may
exist only as legacy migration input, forensic artifacts, or compatibility fixtures until removed.

## Required Properties

- No v2 mutation path calls `FileOperationStore.save_operation()`.
- No v2 control path requires `FileOperationStore.load_operation()`.
- No v2 list/status/inspect path treats `FileOperationStore.list_operations()` as complete.
- Checkpoints are always behind or equal to event stream sequence, never ahead.
- Read models identify their authority and refresh path.

## Verification Plan

- Static tests reject new v2 mutation callers of `save_operation()`.
- v2 status/list/inspect work when `.operator/runs` is absent.
- replay from `operation_events` alone reconstructs canonical state.
- checkpoint deletion followed by replay yields the same status/read-model output.
- full CLI smoke creates, observes, and terminates a v2 operation without `.operator/runs`.

## Related

- ADR 0069
- ADR 0144
- ADR 0193
- ADR 0194
