# ADR 0197: Epoch Fencing for Stale-Write Prevention

- Date: 2026-04-21

## Decision Status

Accepted

## Implementation Status

Verified

Skim-safe status on 2026-04-23:

- `implemented`: `OperationCheckpointStore` now exposes epoch-fenced `load`,
  `save_with_epoch`, and `advance_epoch` in the repository protocol surface
- `implemented`: `FileOperationCheckpointStore` now persists `epoch_id` beside
  checkpoint payloads, rejects stale writes with `StaleEpochError`, and can
  advance epochs even before the first checkpoint exists
- `implemented`: `DriveService` now captures `epoch_id` once per drive call and
  uses that same epoch for every checkpoint write in the call
- `verified`: file-store round-trip, stale-epoch rejection, empty-operation
  epoch advancement, drive-loop epoch propagation, and stale-epoch
  propagation-to-caller all have dedicated regression coverage
- `verified`: full repository suite passed on 2026-04-23 via `uv run pytest`
  (`903 passed, 11 skipped`)

## Context

When the `Commander` detects that an operator process has died and reassigns its operations to another operator, there is a race condition: the dead operator's drive loop may have been mid-cycle when the process died and may attempt to write a checkpoint after the new operator has already started. Without protection, the old operator's stale checkpoint would silently overwrite the new operator's progress.

This is not a theoretical concern: asyncio tasks that were in-flight when the process died may be cleaned up by the OS or the async runtime after some delay, and checkpoint writes are async.

### Alternatives considered

**1. Last-writer-wins (no protection).** Accept that stale writes may occasionally occur; rely on event log ordering to detect and correct. Rejected: the event log is append-only and the checkpoint store is the fast-resume path. A stale checkpoint causes the next resume to replay from a wrong base, producing incorrect aggregate state.

**2. Distributed lock (e.g. Redis/PostgreSQL advisory lock).** The operator holds a lock for the duration of the drive cycle; Commander invalidates the lock on reassignment. Rejected: introduces an external dependency (lock service), adds latency to every checkpoint write, and fails open (if the lock service is unavailable, writes proceed anyway).

**3. Optimistic locking with a version field.** Each checkpoint record has a monotonic version; writes must include the expected version. Commander increments the version on reassignment. Rejected: requires the checkpoint store to implement compare-and-swap semantics. SQLite's WAL mode does not provide CAS natively without serializable isolation.

**4. Epoch fencing (chosen).** A monotonically increasing epoch ID is stored with each checkpoint. A `save()` call that presents a stale epoch is rejected at the storage layer with a `StaleEpochError`. Commander advances the epoch on reassignment via `advance_epoch()`.

## Decision

Adopt **epoch fencing** as the stale-write prevention mechanism.

### Mechanism

- `OperationCheckpointStore` maintains an epoch counter per operation alongside the checkpoint payload
- `load(operation_id) -> tuple[OperationCheckpoint | None, int]` — returns the checkpoint payload (or `None` if no checkpoint exists yet) and the current `epoch_id`. The caller must use this `epoch_id` for all subsequent `save()` calls in the same drive call.
- `save(operation_id, checkpoint, epoch_id)` succeeds only if `epoch_id == stored_epoch_id` (exact equality, not `>=`)
- `advance_epoch(operation_id) -> new_epoch_id` atomically increments the epoch and returns the new value; Commander calls this when reassigning an operation
- A `DriveService.drive()` call captures `epoch_id` from the `load()` return value at the start of the drive call and uses it for all checkpoint writes in that drive call. The epoch is read once; it is not re-read between iterations.
- If `StaleEpochError` is raised, the drive loop propagates it unhandled — `InProcessAgentRunSupervisor` treats it as a fatal conflict and stops the operation

### Why exact equality, not `>=`

Exact equality means that even if Commander advances the epoch twice (due to a retry), the old operator's write fails. A `>=` check would allow the old operator's write if it happened to capture a higher epoch than expected — impossible in the design, but the exact check eliminates the entire class of error.

### Scope of protection

Epoch fencing protects checkpoint writes only. Event log writes use append-only semantics with monotonic sequence numbers — out-of-order writes are detected by the event store's sequence constraint and rejected. The two mechanisms are complementary.

## Consequences

- `OperationCheckpointStore` protocol requires `load()`, `save()`, and `advance_epoch()` — implementations (SQLite, in-memory) must implement all three. `load()` must return the epoch alongside the checkpoint payload.
- `DriveService.drive()` obtains `epoch_id` by calling `load()` at the start of each drive call. The caller does not pass `epoch_id` to `drive()` — the checkpoint store is the single source of truth for the current epoch
- A `StaleEpochError` in the drive loop is a hard stop — no retry, no recovery. The Commander will detect the dead process and reassign with a new epoch
- In-memory test implementations must simulate the epoch check to test error handling

## Repository Evidence

- `src/agent_operator/protocols/event_sourcing.py` defines the epoch-fenced
  checkpoint-store contract: `load()`, `save_with_epoch()`, and
  `advance_epoch()`
- `src/agent_operator/runtime/event_sourcing.py` implements epoch persistence,
  exact-equality save fencing, and atomic epoch advancement in
  `FileOperationCheckpointStore`
- `src/agent_operator/application/drive/drive_service.py` captures `epoch_id`
  once at drive start and passes it to every checkpoint write

## Verification

Verified locally on 2026-04-23 with:

- `pytest -q tests/test_event_sourcing_stores.py tests/test_drive_service_v2.py`
- `mypy src/agent_operator/runtime/event_sourcing.py`
- `uv run pytest`
