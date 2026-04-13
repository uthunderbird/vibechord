# ADR 0086: Event-sourced operation birth and snapshot-legacy retirement policy

## Decision Status

Accepted

## Implementation Status

Implemented

## Context

[`RFC 0009`](../rfc/0009-operation-event-sourced-state-model-and-runtime-architecture.md)
cannot be closed while the main runtime still creates and executes new operations as
`snapshot_legacy`.

`ADR 0077` introduced explicit per-operation canonical persistence mode and allowed a migration
window where:

- legacy operations remain `snapshot_legacy`
- future operations may become `event_sourced`
- snapshot-era runtime entrypoints reject `event_sourced` operations until the canonical path is
  live

That bridge is no longer enough for RFC closure. The repository now needs one unambiguous birth
policy for all newly created operations and one explicit retirement policy for the snapshot-era live
runtime.

### Current truth

Today:

- new operations still default to `snapshot_legacy`
- `run()` creates mutable snapshot truth first
- the live runtime rejects `event_sourced` operations instead of executing them canonically

## Decision

All newly created operations must be born as `event_sourced`.

### Canonical birth rule

`run()` must create a new operation by appending canonical initial domain events and materializing
the first derived checkpoint.

Mutable `OperationState` snapshot persistence must not be the primary birth path for new
operations.

### Snapshot-legacy retirement rule

`snapshot_legacy` ceases to be a live runtime mode once the event-sourced main path is cut over.

The post-cutover runtime must not silently:

- create new `snapshot_legacy` operations
- resume `snapshot_legacy` operations through a compatibility execution path
- keep dual canonicality between mutable snapshots and domain events

### Existing snapshot operations

Existing pre-cutover snapshot-backed operations are not part of the canonical live runtime after
cutover.

If the repository later needs to preserve or import them, that must be handled by a separate
explicit migration/import path, not by runtime fallback logic.

## Verification

- `verified`: new in-memory `OperationState` instances default to
  `canonical_persistence_mode='event_sourced'`.
- `verified`: run-path entrypoint wiring materializes canonical birth artifacts for newly created
  operations through the operation event store and checkpoint store, then reloads from replayed
  checkpoint state.
- `verified`: focused tests cover canonical birth event append, checkpoint materialization,
  persisted default mode, and replay-backed entrypoint loading.
- `verified`: the full repository suite passes at current repository truth (`580 passed, 11 skipped`).

## Implementation notes

Current repository truth satisfies this ADR.

Implemented:

- `OperationState` defaults new operations to `CanonicalPersistenceMode.EVENT_SOURCED`.
- `OperationEntrypointService.prepare_run()` always routes newly created operations through
  `EventSourcedOperationBirthService.birth()` and then reloads canonical state through
  `_load_event_sourced()` when replay wiring is present.
- canonical birth persists initial `operation.created` event-stream truth plus the first derived
  checkpoint.

Still true by design:

- older persisted payloads that predate the canonical mode field still hydrate missing metadata as
  `snapshot_legacy`, but that is legacy data interpretation rather than a second live-runtime birth
  path.
- any future import or migration treatment for pre-cutover snapshot operations remains out of scope
  for this ADR.

## Consequences

- New operation truth becomes canonically event-sourced from the first write.
- The repository no longer needs to preserve long-lived dual runtime authority.
- Snapshot-backed operations become an explicit migration problem instead of an implicit runtime
  obligation.

## This ADR does not decide

- the exact initial event catalog used at operation birth
- the detailed runtime loop that consumes technical facts after birth
- whether a future offline migration/import tool will exist

Those are constrained by adjacent ADRs in this closure wave.

## Alternatives Considered

### Keep creating new snapshot operations until all runtime cutover work is finished

Rejected. That prolongs dual truth and keeps RFC 0009 open by construction.

### Allow long-lived dual support for snapshot and event-sourced live runtimes

Rejected. The repository is pre-release and follows zero-fallback policy. Long coexistence would
increase debugging and closure cost.
