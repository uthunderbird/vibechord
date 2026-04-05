# ADR 0079: Live replay and checkpoint materialization authority

## Status

Accepted

## Context

[`ADR 0069`](./0069-operation-event-store-and-checkpoint-store-contracts.md) already states that
`OperationCheckpointStore` is derived from the canonical event stream and may lag behind it.
[`ADR 0071`](./0071-operation-projector-and-reducer-slices.md) already defines the projector fold.

What is still open is the live runtime read path:

- who loads canonical operation truth for `run`, `resume`, and recovery
- whether replay starts from mutable snapshot or from checkpoint plus event suffix
- how much checkpoint staleness is acceptable in hot runtime paths

Without this decision, the repository can claim event-sourced storage while still routing live
runtime truth through snapshot-era loading semantics.

### Current truth

The repository still loads and mutates snapshot-shaped operation state on the main runtime path.
Checkpoint and projector foundations exist, but they are not yet the live recovery authority.

## Decision

For `event_sourced` operations, live canonical operation truth is loaded from:

1. the latest available `OperationCheckpoint`
2. the suffix of domain events after `last_applied_sequence`

Mutable snapshot state is not the canonical live replay authority for those operations.

### Replay authority

One runtime read boundary is responsible for loading canonical business truth for live execution.

Its inputs are:

- operation metadata
- the latest checkpoint, if any
- the suffix of domain events after the checkpoint sequence

Its output is the canonical in-memory replay result used for validation, recovery, and runtime
coordination.

### Checkpoint staleness rule

Stale checkpoints are acceptable as long as:

- they do not claim to include events that are not in the stream
- replay always folds the full suffix after the checkpoint sequence before using the result as
  canonical live truth

This keeps checkpoint refresh an optimization, not a second source of truth.

### Hot-path snapshot rule

For `event_sourced` operations:

- mutable snapshot state may exist as compatibility read model
- it may support observability or temporary bridge surfaces
- it must not be the canonical state loaded for business validation or recovery

### Materialization authority

Checkpoint materialization is owned by the event-sourced replay/projection path, not by ad hoc
snapshot persistence in unrelated services.

The authority that projects domain events into `OperationCheckpoint` may run:

- synchronously after append
- or asynchronously through a guaranteed follow-up path

But it must remain one coherent projection authority over the canonical event stream.

## Consequences

- Event-sourced operations gain a clear live read path that matches `ADR 0069` and `ADR 0071`.
- Checkpoint lag remains acceptable without weakening replay correctness.
- Snapshot-era persistence can be demoted to compatibility/read-model use instead of quietly
  remaining canonical.
- Recovery behavior for event-canonical operations becomes mechanically aligned with replayed
  business truth.

## Closure Notes

- The repository now contains a dedicated `EventSourcedReplayService` that:
  - loads canonical operation truth from the latest checkpoint plus the event suffix after
    `last_applied_sequence`
  - rejects checkpoints that are ahead of the canonical event stream
  - materializes updated derived checkpoints without consulting mutable snapshot state
- `EventSourcedCommandApplicationService` now reuses this replay service instead of maintaining an
  ad hoc checkpoint-plus-suffix loading path.
- This ADR is accepted as the replay/materialization foundation boundary. The main runtime is still
  not fully cut over to use this replay service for `run`, `resume`, and recovery of all
  event-sourced operations; that remains follow-up work under `ADR 0080`.
- Verification:
  - dedicated event-sourced replay tests pass
  - event-sourced command-application tests pass
  - full repository test suite passes (`284 passed, 11 skipped`)

## This ADR does not decide

- the exact checkpoint refresh cadence or batching threshold
- whether projection runs inline or in a follow-up worker
- the command-application boundary that produces new domain events
- how legacy snapshot-backed operations continue to load state during migration

Those are covered by adjacent ADRs.

## Alternatives Considered

### Keep loading mutable snapshot state on the live path for event-canonical operations

Rejected. That would make checkpoint and event storage secondary artifacts rather than real runtime
authority.

### Require perfectly fresh checkpoints before any runtime use

Rejected. That turns checkpoints into a fragile synchronization barrier instead of a replay
acceleration mechanism.

### Let many services materialize checkpoints opportunistically

Rejected. That would create drift in replay semantics and obscure which projector logic is
authoritative.
