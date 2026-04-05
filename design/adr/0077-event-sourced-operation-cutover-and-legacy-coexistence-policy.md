# ADR 0077: Event-sourced operation cutover and legacy coexistence policy

## Status

Accepted

## Context

[`RFC 0009`](../rfc/0009-operation-event-sourced-state-model-and-runtime-architecture.md)
chooses one canonical domain event stream per operation and demotes mutable snapshots from source of
truth to derived state.

Accepted foundations now exist for:

- canonical `OperationEventStore` and derived `OperationCheckpointStore` (`ADR 0069`)
- fact translation boundaries (`ADR 0070`)
- projection into canonical replay state (`ADR 0071`)
- process-manager and planning-trigger bridge behavior (`ADR 0072`, `ADR 0073`, `ADR 0074`)

What remains open is the cutover rule itself. The repository still runs a snapshot-first runtime,
so migration to event-sourced truth must answer a narrow but high-impact question:

- how a given operation is classified as snapshot-canonical or event-canonical
- whether both modes can coexist during migration
- what guarantees exist for old operations during the cutover window

Without this decision, later ADRs risk creating dual canonicality, ambiguous recovery behavior, or
an implicit per-codepath migration.

### Current truth

Repository truth today is still snapshot-first:

- `OperationState` remains the primary write target for the main runtime path
- accepted event-sourcing components exist, but are not yet the only canonical path
- the repository does not yet declare, per operation, which persistence mode is canonical

## Decision

Cutover to event-sourced operation truth is per-operation and explicit.

### Canonical mode is declared per operation

Each operation must declare one canonical persistence mode:

- `snapshot_legacy`
- `event_sourced`

This declaration is durable operation metadata and must be inspectable without inference from file
presence or runtime heuristics.

### No dual canonicality

At any point in time, one operation has exactly one canonical mode.

Forbidden:

- treating `OperationState` and `OperationEventStore` as simultaneously canonical for the same
  operation
- resolving conflicts by whichever representation was written last
- inferring canonicality from partial migration side effects

### Initial cutover policy

The default migration route is:

- existing operations remain `snapshot_legacy`
- newly created operations may be created directly as `event_sourced` once the event-sourced path
  is ready for production use

This ADR prefers new-operations-first cutover over in-place canonical migration of already-running
operations.

### Legacy operation handling

Legacy snapshot-backed operations remain resumable during the migration window.

They are not automatically rewritten into event-canonical operations on resume. Any later migration
of an existing operation from `snapshot_legacy` to `event_sourced` requires an explicit migration
mechanism and its own verification path.

### Snapshot role after cutover

For `event_sourced` operations:

- `OperationCheckpoint` is canonical replay state
- mutable snapshot state, if it still exists, is compatibility read model only
- snapshot persistence must not become the primary business write path again

For `snapshot_legacy` operations:

- mutable `OperationState` remains canonical until an explicit migration route says otherwise

### Cutover discipline

Every runtime path that opens or resumes an operation must branch first on canonical mode and then
use one internally coherent write/replay path for that mode.

The repository must not mix:

- snapshot writes with event-canonical command handling
- event appends with snapshot-canonical recovery
- partial fallback from one canonical mode into the other inside the same operation lifecycle

## Consequences

- Later ADRs can define event-sourced write and replay paths without re-opening coexistence policy.
- New operations can move first without forcing risky in-place migration of already-running
  snapshot-backed operations.
- The repository gains an explicit way to detect and reject dual-canonical drift.
- Any eventual legacy-to-event migration becomes a deliberate follow-up decision instead of an
  accidental side effect of runtime rollout.

## Closure Notes

- `OperationState` now persists explicit `canonical_persistence_mode`.
- Legacy operation payloads that predate this field hydrate as `snapshot_legacy`.
- New operations created by the current runtime default to `snapshot_legacy`.
- Snapshot-era runtime entrypoints now reject `event_sourced` operations explicitly instead of
  inferring canonical mode from file presence or partially handling them through snapshot logic.
- Verification:
  - targeted runtime and service tests pass
  - full repository test suite passes (`278 passed, 11 skipped`)

## This ADR does not decide

- the exact storage field or file format that records canonical mode
- how commands become domain events once an operation is `event_sourced`
- how replay and checkpoint refresh are implemented for event-canonical operations
- whether a future explicit legacy-to-event migration tool will exist

Those are covered by later ADRs in this RFC 0009 batch.

## Alternatives Considered

### Migrate all operations in place at once

Rejected. That creates a high-risk cutover with weak rollback properties and forces recovery,
resume, and historical-operation behavior to change simultaneously.

### Infer canonical mode from whichever files exist

Rejected. That is ambiguous under partial rollout, repair, or crash recovery, and would permit
silent dual-canonical drift.

### Keep snapshot and event persistence both canonical during migration

Rejected. That violates the central event-sourcing premise of RFC 0009 and makes conflict
resolution underdefined.
