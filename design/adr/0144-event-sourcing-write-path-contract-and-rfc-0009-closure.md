# ADR 0144: Event-sourcing write-path contract and RFC 0009 closure

- Date: 2026-04-12

## Decision Status

Accepted

## Implementation Status

Implemented

## Context

`RFC 0009` established event-sourcing as the canonical persistence model for `operator`. `ADR 0086`
and `ADR 0088` introduced `EventSourcedCommandApplicationService` and the checkpoint/replay
services. The repository has been incrementally migrating toward this model.

As of 2026-04-12, `BACKLOG.md` explicitly records that the migration is incomplete:

- New operations are born as `event_sourced`, but the main loop still persists mutable
  `OperationState` snapshots through `save_operation()`.
- The live runtime still depends on snapshot-era command mutation for part of the command surface.
- `OperationDriveService` and adjacent services still treat mutable snapshot state as the working
  write path for some paths.
- `EventSourcedCommandApplicationService` exists but the live command surface is not fully routed
  through it.

This is not cleanup debt. It is an active architectural inconsistency that creates real risk:

- Contributors making new commands must choose between the old snapshot path and the new event path
  without a binding decision to guide them.
- `ADR 0086` and `ADR 0088` cannot be promoted to fully `Accepted` until the live runtime matches
  what they describe.
- `RFC 0009` cannot be promoted from `Proposed` while the live runtime contradicts its model.

### Concrete failure modes caused by the dual-write inconsistency

The dual-write inconsistency causes specific, reproducible failures during `resume` and
`reconcile`:

**Failure 1 — `ExecutionState.session_id` lost on resume.**

When a background run is started, `upsert_background_run()` in `loaded_operation.py` creates a
copy of the run handle with `session_id` set (`run.model_copy(update={"session_id": ...})`), then
replaces the entry in `state.background_runs`. This write lands in the snapshot store via
`save_operation()`. It is not emitted as an event and therefore never reaches the checkpoint.

On the next resume, if the state is loaded from event-sourced replay via `_load_event_sourced()`,
the reconstructed `OperationState` is built from the checkpoint — which carries the original
`background_runs` list with `session_id = None`. The reconciliation service then cannot identify
which agent session the background run belongs to. It classifies the run as stale and transitions
it to `FAILED`. If the underlying ACP session was still live, the operator creates a new run
against the same session or starts a competing new session.

**Failure 2 — `SessionState` cooldown not cleared on resume.**

`clear_expired_session_cooldowns()` sets `record.cooldown_until = None` via direct mutation and
persists via `save_operation()`. This mutation is not in the event log.

On resume from event-sourced replay: the checkpoint carries the original `cooldown_until` value.
The session appears still in cooldown. The reconcile cycle waits unnecessarily, or decides the
session is unavailable and starts a new one.

**Root cause shared by both failures.**

Both failures arise from the same structure: `OperationDriveService.drive()` makes direct
mutations to `OperationState` and calls `save_operation()` up to 8 times per cycle. None of these
writes are reflected in the checkpoint store. The checkpoint is only updated by
`EventSourcedOperationLoop` and `EventSourcedCommandApplicationService`, which are separate paths
not called by the drive loop's reconciliation cycle.

The resume path in `_load_event_sourced()` performs a manual field-by-field merge from snapshot
and checkpoint. Every time a new field is added to `OperationState` and mutated by the drive loop,
the developer must remember to add it to this merge list or accept the same class of failure. The
merge list is the symptom of the dual-write problem made visible in code.

**Failure 3 — `active_session` pointer stale or absent on resume.**

`OperationState.active_session: AgentSessionHandle | None` is the "currently preferred session"
pointer. It is set via direct mutation in `operation_turn_execution.py`, `attached_turns.py`,
`agent_results.py`, and `loaded_operation.py` (8 call sites total) and persisted via
`save_operation()`. It is not emitted as an event.

`_load_event_sourced()` copies `active_session` from the snapshot (fallback_state) at lines
238–242 of `operation_entrypoints.py`, not from the checkpoint. This means the value is only
as current as the last `save_operation()` call. When `active_session` was last written as `None`
— for example, because one-shot sessions clear it immediately after use — the resumed state has
`active_session = None` even though the operation has live sessions.

The reconciliation service in `operation_runtime_reconciliation.py:591-601` detects `None` and
attempts to restore `active_session` from the `sessions` list via `sync_legacy_active_session()`
— this is a recovery path, not the primary path. If the `sessions` list is itself stale due to
Failure 1, the recovery produces incorrect results. Even when recovery succeeds, it is an extra
reconcile step that masks the root dual-write issue.

**Implication for `SessionState` and `active_session`.**

`SessionState` has 12+ fields tracking operator-side observations about an agent session:
`desired_state`, `observed_state`, `cooldown_until`, `recovery_count`, etc. All of these are
mutated directly by the reconciliation path. None are emitted as events. `active_session` has the
same property. This means the session layer as a whole is the most vulnerable area to resume
divergence. The minimum operator-owned session state that must survive resume correctly is:
`session_id` (to continue the right ACP session) and `cooldown_until` (to avoid false
early-start). The rest can be derived or are unread in practice (`recovery_count` is incremented
but never checked against a threshold). `active_session` can be derived from the `sessions` list
on resume, making it a candidate for removal from persisted state once the sessions list itself
is event-sourced correctly.

The repository needs one ADR that names the target write path explicitly, defines the retirement
condition for `save_operation()`, and establishes when RFC 0009 and its dependent ADRs can be
promoted.

## Decision

The event-sourced path is the canonical write path for all live operation state mutations.

### Write path rule

All live operation state mutations must go through the event-append path:

- business mutations produce `RunEvent` instances appended to the event log,
- the operation state view is derived by replaying or checkpointing from that log,
- `save_operation()` (mutable snapshot write) must not be called for new mutation logic.

The mutable snapshot write path exists only as a transition compatibility mechanism. New code must
not introduce new callers of `save_operation()` for mutation purposes.

### Command routing rule

All live commands must be routed through `EventSourcedCommandApplicationService` or its
successors.

Commands that currently bypass this service and mutate state directly must be migrated before the
live runtime is considered event-sourced.

### Retirement condition for `save_operation()`

`save_operation()` is retired when:

1. All live commands are routed through the event-sourced command application service.
2. No business logic in `OperationDriveService` or adjacent services mutates `OperationState`
   directly outside of event replay/checkpoint reconstruction.
3. The only remaining uses of `save_operation()` are read-path checkpointing helpers, which may be
   renamed to make their role explicit.

### RFC 0009 and dependent ADR promotion

`RFC 0009` should be promoted from `Proposed` to `Accepted` after the retirement condition above
is met and the full test suite is green.

`ADR 0086` and `ADR 0088` should be promoted from `Implemented` to fully `Accepted` at the same
time.

### What does not change

- The checkpoint/replay pattern for read-path reconstruction remains.
- `OperationState` as a domain model remains — it is the replay target, not something to remove.
- `EventSourcedCommandApplicationService` may be refactored or succeeded, but its routing role
  must be preserved.

## Alternatives Considered

### Treat the snapshot path as permanent dual-write for reliability

Rejected.

Dual-write creates permanent consistency risk. The existing snapshot path is a migration artifact,
not a reliability pattern. Checkpointing from the event log is the correct durability mechanism.

### Migrate lazily without a binding write-path rule

Rejected.

Without a binding rule, contributors will continue adding new callers of `save_operation()` for
new commands. The migration will never finish. The BACKLOG evidence shows this risk is already
materializing.

### Write a separate ADR per command being migrated

Rejected.

The binding rule applies to all commands uniformly. One ADR establishing the rule is more useful
than per-command records that never establish the principle.

## Consequences

- The repository has a binding write-path rule that governs all future command development.
- New commands must use the event-sourced path; reviewers have a clear acceptance criterion.
- RFC 0009, ADR 0086, and ADR 0088 have explicit promotion conditions rather than staying in limbo.
- The retirement of `save_operation()` becomes a trackable milestone rather than an open-ended
  cleanup item.
- `OperationDriveService` migration is the main implementation work — it should be the focus of the
  next wave of event-sourcing work.

## Implementation record

The migration was completed in two stages.

### Stage 1 — Quickfix (three new events)

Three new domain events were added to close the concrete resume/reconcile failures:

**`execution.session_linked`** — emitted by callers of `upsert_background_run()` in
`OperationRuntimeReconciliationService` (5 sites) and `OperationTurnExecutionService` (2 sites)
whenever a session_id is associated with a background run. Projector slice in
`_apply_execution_slice` patches `execution.session_id` on the stored `ExecutionState`. Resolves
Failure 1.

**`session.cooldown_cleared`** — emitted by `clear_expired_session_cooldowns()` in
`OperationRuntimeReconciliationService` for each session whose cooldown expires. Projector slice
in `_apply_session_slice` nulls out `cooldown_until`, `cooldown_reason`, `waiting_reason` and
transitions `observed_state` from `WAITING` to `IDLE`. Resolves Failure 2.

**`operation.active_session_updated`** — emitted by all runtime `active_session` write sites:
`OperationTurnExecutionService` (2 sites), `AgentResultService`, `AttachedTurnService` (2 sites).
New `_apply_active_session_slice` in the projector writes `checkpoint.active_session` from the
event payload. `OperationCheckpoint` gained an `active_session: AgentSessionHandle | None = None`
field. `from_checkpoint()` in `OperationStateViewService` copies it into `OperationState`.
The snapshot overlay at `operation_entrypoints.py:238–242` was removed from `_load_event_sourced()`.
Resolves Failure 3.

### Stage 2 — Full migration

All 8 `save_operation()` call sites in `operation_drive.py` were audited and classified as
checkpoint helpers — none were mutation paths. All were consolidated behind a new
`_advance_checkpoint()` method on `OperationDriveService`, which carries explicit documentation
of its read-path-only role.

`cancel_scoped_execution()` in `OperationLifecycleCoordinator` was identified as a mutation
path (sets `session.status = CANCELLED`). Migrated: now emits `session.observed_state.changed`
with `terminal_state=CANCELLED` via the `emit_session_cancelled` callback.

An AST-based lint test was added in `tests/test_application_structure.py`:
`test_drive_loop_save_operation_only_via_advance_checkpoint` — asserts that no function in
`operation_drive.py` other than `_advance_checkpoint` calls `save_operation()` directly.

### Promotion

On completion of Stage 2 with 513 tests green:
- `RFC 0009`: `Proposed` → `Accepted`
- `ADR 0086`: `Implemented` → `Accepted`
- `ADR 0088`: `Implemented` → `Accepted`
- ADR 0144 `Implementation Status`: `Implemented`

### Remaining follow-up (not blocking acceptance)

`SessionState` simplification — reducing `SessionState` to its minimum viable surface — can
proceed in parallel as a separate effort. See ADR 0150.

## Related

- [RFC 0009](../rfc/0009-operation-event-sourced-state-model-and-runtime-architecture.md)
- [ADR 0086](./0086-event-sourced-operation-birth-and-snapshot-legacy-retirement-policy.md)
- [ADR 0088](./0088-main-entrypoint-cutover-and-final-operator-service-shell-boundary.md)
- [ADR 0150](./0150-domain-state-machine-simplification.md)
- [BACKLOG.md](../BACKLOG.md)
