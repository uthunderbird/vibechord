# ADR 0203: Canonical v2 Persistence Authority

- Date: 2026-04-23

## Decision Status

Proposed

## Implementation Status

Partial

Phase 2 implementation status on 2026-04-25:

- `implemented`: `OperatorServiceV2` creates operations by appending `operation.created` domain
  events through `OperationEventStore` and drives through `DriveService`.
- `implemented`: `OperatorServiceV2.cancel()` delegates cancellation to
  `EventSourcedCommandApplicationService` when that service is wired.
- `implemented`: `DriveService` reloads aggregate state from replay, appends new domain events, and
  saves derived checkpoints through `OperationCheckpointStore`.
- `implemented`: `EventSourcedReplayService` rejects checkpoints whose sequence is ahead of the
  event stream.
- `implemented`: canonical resolution now checks v2 event-sourced state before legacy snapshots for
  exact loads and merged operation lists.
- `implemented`: status payload construction now prefers v2 replay over stale legacy snapshots for
  the same operation id.
- `implemented`: MCP list and SDK list use the canonical merged v2-plus-legacy operation state
  service.
- `verified`: targeted ADR 0203 regression/static tests and the full `uv run pytest` suite passed
  on 2026-04-25.
- `partial`: some converse/detail/control paths still call legacy snapshot reads directly, so this
  ADR remains `Proposed` / `Partial` rather than `Accepted` / `Verified`. Remaining work is tracked
  in `../internal/adr-0203-phase-1-design-artifact-2026-04-25.md`.

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
