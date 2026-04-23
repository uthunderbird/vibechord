# ADR 0194: v2 Migration Strategy — Full Rewrite Without Backward Compatibility

- Date: 2026-04-21

## Decision Status

Proposed

## Implementation Status

Planned

## Context

`ARCHITECTURE_v2.md` describes a target architecture that differs from the current codebase in several load-bearing ways:

- `OperationAggregate` replaces `OperationState` (ADR 0193)
- `DriveService` with four decomposed sub-services replaces `OperationDriveService` and its 25+ mixin services
- Event log is the *only* write path — no `save_operation()` snapshot writes
- `PolicyExecutor.decide_and_execute()` returns a pure 4-tuple; no direct aggregate mutation from services
- `OperatorServiceV2` replaces `OperatorService`
- `Commander` is a separate process managing epoch fencing and fleet coordination

The question is how to get from the current codebase to this target.

### Two approaches were considered

**Approach A — Strangler Fig (incremental migration).** Keep v1 running; introduce v2 components alongside; route traffic gradually. This is the standard safe migration pattern.

**Approach B — Full rewrite, no backward compatibility.** Replace the entire v1 layer in a single coordinated sweep. v1 artifacts are deleted, not deprecated.

### Why the standard approach (Strangler Fig) is hard here

The v1 and v2 architectures are incompatible at the aggregate boundary:

- v1 `OperationState` is a mutable snapshot; v2 `OperationAggregate` is immutable and event-sourced
- v1 drive loop reads and writes `OperationState` directly; v2 drive loop receives an aggregate and only returns events
- There is no safe intermediate state where both `OperationState` and `OperationAggregate` can represent the same operation simultaneously — one is the "real" state and the other would be a stale shadow

ADR 0144 already attempted incremental migration (routing commands through `EventSourcedCommandApplicationService` while keeping snapshot writes) and documented that this creates dual-write inconsistency and reproducible failures. Incremental migration at the aggregate level has already been tried and failed.

### The project is pre-production

The operator has no external users and no production data requiring migration. The cost of backward incompatibility is zero: no data migration, no client migration, no deprecation period.

## Decision

Adopt **Approach B — Full rewrite without backward compatibility.**

Specifically:

1. **`OperationState` is deleted**, not deprecated. Code that imports or constructs `OperationState` does not get a shim or compatibility layer — it is updated to use `OperationAggregate` directly.

2. **`OperatorService` is replaced by `OperatorServiceV2`**. The v1 service class is deleted. There is no "legacy mode" flag.

3. **`save_operation()` is removed from all protocols and implementations.** The only persistence path is `event_log.append(operation_id, events)`. The checkpoint store is an acceleration surface, not a write path.

4. **The existing event log and checkpoint data is compatible** — the `EventSourcedReplayService` already exists and works with the stored event format. Operations stored in the current event log can be replayed into `OperationAggregate`.

5. **The migration is layer-by-layer, not feature-by-feature:**
   - Layer 1: Domain (`OperationAggregate`, `DomainEvent` types, `OperationReadModel`)
   - Layer 2: Drive loop (`DriveService`, `PolicyExecutor`, `RuntimeReconciler`, `LifecycleGate`)
   - Layer 3: Application commands and queries (remove snapshot path)
   - Layer 4: `OperatorServiceV2`, CLI, `Commander`

   Each layer is a complete replacement of the corresponding v1 layer. No layer ships in a hybrid state.

6. **No feature flags, no `if v2:` branches.** The codebase at any point in time runs either v1 or v2, not both.

7. **The migration is performed on a dedicated feature branch.** The main branch continues to run v1 until the migration branch is merged. The migration branch is non-runnable from the moment Layer 1 is replaced until all four layers are complete. This is expected and acceptable — the branch exists solely to accumulate the full rewrite before it can be tested end-to-end.

## Alternatives Considered

**Strangler Fig at the service level** (not the aggregate level): Keep v1 `OperationState` but route all writes through event-sourcing services. Already tried in ADR 0144. Failed due to dual-write inconsistency.

**Feature-flag-controlled dual-aggregate**: One operation runs on v1, another on v2, controlled by a flag. Rejected: doubles the surface area of tests and the complexity of every command handler for the duration of the migration.

**Data migration**: Translate existing `OperationState` snapshots to `OperationAggregate` checkpoints. Not needed: existing operations are stored as events; the `EventSourcedReplayService` already replays them into the checkpoint format.

## Cutover Strategy

The full rewrite implies a hard cutover, not a gradual rollout. The following constraints apply:

1. **Drain before cutover.** All running operations must complete under v1 before the v2 process starts. No hot-swap. The operator must enter a drain state (no new operation assignments accepted; existing operations run to completion or cancellation) before the v1 process is stopped. The drain procedure requires a migration runbook (outside the scope of this ADR) specifying: (a) how to signal the operator to stop accepting new assignments, (b) how to confirm zero active operations before stopping v1, and (c) what to do if an operation is stuck and will not complete within a timeout. The cutover must not proceed until this runbook exists and has been rehearsed.

2. **"No migration path" applies to checkpoint format only.** The `OperationAggregate` checkpoint format (v2) is incompatible with the `OperationState` snapshot format (v1). There is no converter script. After drain, the checkpoint store is treated as empty; v2 operations start from a fresh checkpoint.

3. **Event log is forward-compatible.** Existing event log entries can be replayed into v2 `OperationAggregate` via `EventSourcedReplayService`. Operations whose v1 snapshots were discarded can be reconstructed from their event logs.

4. **Field rename caveat.** If any `OperatorMessageReceived` events in the stored event log use the v1 field name `text` (renamed to `content` in v2), a one-time event log conversion script must be run before v2 replay. This script is a deployment artifact, not a schema migration — it rewrites the stored JSON payloads in-place.

5. **Layer replacement order** must follow the dependency graph: Domain → Drive loop → Application layer → Service + CLI. Each layer replaces its v1 counterpart completely before the next layer starts. The system is not runnable during an intermediate partial-layer state.

## Consequences

- No backward compatibility shims anywhere in the codebase
- Layer-by-layer replacement means tests are updated in the same layer as the code they test
- The existing event log data is preserved — only the application layer reading it changes
- Engineers can rely on `ARCHITECTURE_v2.md` as the single authoritative target — no "v1 compatibility mode" to maintain
- Git history preserves v1 code for reference
- Cutover requires a maintenance window: drain running operations, stop v1 process, optionally run event log field-rename script, start v2 process
