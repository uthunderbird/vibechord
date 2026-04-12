# ADR 0150: Domain state machine simplification

- Date: 2026-04-12

## Decision Status

Accepted

## Implementation Status

Implemented

## Context

A systematic audit of the operation lifecycle identified several places where the domain model
carries redundant, dead, or overcomplicated state — accumulated through incremental feature
growth without a consolidation pass.

The audit examined all `status` and `state` fields in `domain/enums.py` and `domain/operation.py`,
traced usages across the application layer, and verified which fields are actively read for
decisions vs accumulated as tracking with no behavioral wiring.

### What was found to be correct and not changed

The following state machines are fully justified and are explicitly out of scope:

- `OperationStatus` — business lifecycle, used everywhere
- `TaskStatus` — standard task state machine (PENDING→READY→RUNNING→terminal)
- `SchedulerState` including `DRAINING` — used in 11 places; orthogonal to business status
- `AttentionStatus` — blocking item lifecycle
- `ExecutionObservedState` — background run tracking including `LOST` for stale detection
- `MemoryFreshness` — simple staleness marker
- `AgentProgressState` / `AgentResultStatus` — ACP boundary types, not domain state machines
- `PolicyStatus` — clean lifecycle
- `IterationState` — correct log record design; intentionally has no status field
- `active_session` pointer — not a duplicate of `sessions` list; serves as "preferred session"
  pointer with distinct semantics (covered separately in ADR 0144 as dual-write debt)

### What was found to be redundant or dead

#### 1. `ObjectiveState.status` — redundant synchronized field

`ObjectiveState` contained a `status: OperationStatus` field kept in sync with
`OperationState.status` through explicit sync logic in the domain, lifecycle, runtime
reconciliation, and projector paths.

`ObjectiveState` itself conflates three distinct responsibilities:

- **Goal config**: `objective`, `harness_instructions`, `success_criteria`, `metadata` — this is
  already owned by `OperationGoal` and duplicated here
- **Status mirror**: `status: OperationStatus` — a synchronized copy of `OperationState.status`
- **Derived pointer**: `root_task_id` — a pointer into the task graph

`state.objective_state` is used in 15+ places across prompting, CLI rendering, and policies —
but in every case the consumer could access `state.goal.*` and `state.status` directly. The
`objective_state` accessor exists as a convenience wrapper, not as an authoritative source.

The sync logic was a maintenance liability: any new field added to one side had to be manually
mirrored across multiple write paths.

#### 2. `SessionState.desired_state` — dead field

`SessionState` carries three separate enums for session lifecycle:

```python
desired_state: SessionDesiredState      # ACTIVE | PAUSED | STOPPED
observed_state: SessionObservedState    # IDLE | RUNNING | WAITING | TERMINAL
terminal_state: SessionTerminalState | None  # COMPLETED | FAILED | CANCELLED
```

`desired_state` has zero usages outside `domain/operation.py` and `domain/enums.py`. It is not
read in reconciliation, drive loop, commands, queries, or any runtime path. It represents an
aspirational Kubernetes-style desired/observed split that was never wired to a reconciliation
loop that acts on it.

`observed_state + terminal_state` together encode six valid states:

| observed_state | terminal_state | Meaning |
|----------------|----------------|---------|
| `IDLE` | `None` | Ready, available for reuse |
| `RUNNING` | `None` | Agent turn in progress |
| `WAITING` | `None` | Waiting for input |
| `TERMINAL` | `COMPLETED` | Finished successfully |
| `TERMINAL` | `FAILED` | Failed |
| `TERMINAL` | `CANCELLED` | Cancelled |

These six states are already captured by `SessionStatus` (defined in `domain/enums.py:67`), which
has values: `IDLE`, `RUNNING`, `WAITING`, `COMPLETED`, `FAILED`, `CANCELLED`.

`SessionState` already exposes a computed `.status` property that synthesizes these two fields
into a single `SessionStatus` value — but it is not the primary storage. The primary storage
remains the two-field split, with 27 theoretical combinations and only 6 valid ones.

#### 3. `FeatureStatus.READY_FOR_REVIEW` and `FeatureStatus.NEEDS_REWORK` — dead enum values

`FeatureStatus` defines four values: `IN_PROGRESS`, `READY_FOR_REVIEW`, `ACCEPTED`,
`NEEDS_REWORK`.

`READY_FOR_REVIEW` and `NEEDS_REWORK` have zero usages anywhere in the codebase outside
`enums.py`. They are never assigned and never checked. The brain DTO in `dtos/brain.py` carries
`status: FeatureStatus | None` but only `IN_PROGRESS` and `ACCEPTED` are set in practice.

## Decision

### 1. Remove `ObjectiveState.status` sync

`ObjectiveState.status` should be removed. Consumers that need operation status should read
`state.status` directly.

`ObjectiveState` should be retained as a goal-config container (`objective`, `harness_instructions`,
`success_criteria`, `metadata`, `root_task_id`, `summary`) but should not carry a status field.

The sync calls should be removed.

`objective_state` may remain as a convenience accessor on `OperationState` — it is a useful
grouping of goal fields for prompting — but it must not be the authoritative carrier of operation
status.

### 2. Remove `SessionState.desired_state`

`SessionState.desired_state: SessionDesiredState` should be removed entirely.

`SessionDesiredState` enum should be removed from `domain/enums.py`.

`SessionState` lifecycle should be expressed through `observed_state + terminal_state` (current
behavior) or, preferably, migrated to a single `status: SessionStatus` field in a follow-up
simplification pass. The existing `.status` computed property is the right interface; making it
the storage field is the direction.

If a future reconciliation loop needs to express "we want this session to stop", the correct
model is an explicit command or a runtime flag, not a desired-state field on the persisted domain
object.

### 3. Remove `FeatureStatus.READY_FOR_REVIEW` and `FeatureStatus.NEEDS_REWORK`

These two enum values should be removed from `FeatureStatus`. The remaining values
`IN_PROGRESS` and `ACCEPTED` cover the states actually used in runtime.

### What is deferred

**`SessionState` two-field → single `status` migration.** Collapsing `observed_state +
terminal_state` into a single `status: SessionStatus` is the correct direction but requires
migrating all read sites (commands, reconciliation, queries) that pattern-match on
`observed_state` and `terminal_state` separately. This is a follow-up refactor, not part of this
ADR.

**`SchedulerState.PAUSE_REQUESTED` as runtime-only state.** `PAUSE_REQUESTED` is a transient
state in persisted domain — cleaner as a runtime flag. But it is used correctly and causes no
bugs. Deferred.

**`ObjectiveState` goal-config vs `OperationGoal` consolidation.** `ObjectiveState` carries
`objective`, `harness_instructions`, `success_criteria` which overlap with `OperationGoal`.
Full consolidation is a larger refactor. This ADR only removes the status sync; the goal-config
duplication is deferred.

## Alternatives Considered

### Remove `ObjectiveState` entirely

Rejected for now.

`ObjectiveState` is used in 15+ prompting, policy, and rendering call sites as a convenient
accessor. Removing it entirely would require migrating all those sites. Removing the `status`
field and the sync logic provides the main correctness benefit with lower migration cost.

### Keep `desired_state` for future use

Rejected.

Zero usages for an aspirational design is evidence that the concept did not find a home in the
actual architecture. If session-level pause/resume at the desired/observed level is needed in
the future, it should be introduced with an ADR that names the reconciliation loop that acts on
it — not inherited from a dead field.

### Keep `READY_FOR_REVIEW` and `NEEDS_REWORK` for future brain use

Rejected.

Brain DTOs already exist and are not using these values. If the brain needs richer feature
lifecycle tracking in the future, the values can be re-added with explicit behavioral wiring.
Dead code in enums creates false affordance — contributors may believe these states are handled
when they are not.

## Consequences

- `OperationState` loses one redundant status field and its status-mirror hydration.
- The lifecycle, runtime reconciliation, and checkpoint projector paths no longer mirror
  `OperationStatus` into `ObjectiveState`.
- `SessionState` loses one field; `SessionDesiredState` enum is removed.
- `FeatureStatus` shrinks by two values; enum is cleaner.
- Tests that assert `ObjectiveState.status` values must be updated to assert `OperationState.status` directly.
- No behavioral changes — all removed fields were either unread or mirrors of other fields.

## Closure Evidence Matrix

| ADR clause | Repository evidence | Verification |
| --- | --- | --- |
| Remove `ObjectiveState.status` from persisted domain state | `src/agent_operator/domain/operation.py` `ObjectiveState`; `OperationState._hydrate_long_lived_defaults` | `tests/test_runtime.py::test_operation_state_uses_objective_only_for_root_task_goal` |
| Keep `state.status` as the authoritative operation lifecycle status | `src/agent_operator/domain/operation.py` `OperationState.status`; `src/agent_operator/application/operation_lifecycle.py` `OperationLifecycleCoordinator.mark_running`, `mark_completed`, `mark_failed`, `mark_cancelled`, `mark_needs_human` | `uv run pytest tests/test_runtime.py tests/test_operation_projector.py tests/test_operation_entrypoints.py tests/test_operation_runtime_reconciliation_service.py -q` |
| Remove objective-status mirror writes from projection/reconciliation paths | `src/agent_operator/projectors/operation.py` `DefaultOperationProjector._apply_operation_slice`; `src/agent_operator/application/runtime/operation_runtime_reconciliation.py` `OperationRuntimeReconciliationService.reconcile_state` | `tests/test_operation_projector.py::test_operation_projector_projects_operation_and_task_slices` |
| Retain `ObjectiveState` as a goal-config convenience accessor with summary/root-task support | `src/agent_operator/domain/operation.py` `ObjectiveState`; `OperationState.objective_state`; `src/agent_operator/application/loaded_operation.py` | `tests/test_runtime.py::test_operation_state_uses_objective_only_for_root_task_goal` |
| Remove `SessionState.desired_state` and `SessionDesiredState` | `src/agent_operator/domain/operation.py` `SessionState`; `src/agent_operator/domain/enums.py`; `src/agent_operator/domain/__init__.py` | `tests/test_runtime.py::test_legacy_session_status_upgrades_without_desired_state` |
| Preserve the computed `SessionState.status` interface over `observed_state + terminal_state` | `src/agent_operator/domain/operation.py` `SessionState.status` | `tests/test_runtime.py::test_legacy_session_status_upgrades_without_desired_state`; `tests/test_operation_projector.py::test_operation_projector_coordinates_execution_and_session_slices` |
| Remove dead `FeatureStatus.READY_FOR_REVIEW` and `FeatureStatus.NEEDS_REWORK` values | `src/agent_operator/domain/enums.py` `FeatureStatus` | `tests/test_runtime.py::test_feature_status_exposes_only_runtime_values` |
| Event-sourced birth and replay remain grounded in the simplified objective/session models | `src/agent_operator/application/event_sourcing/event_sourced_birth.py` `EventSourcedOperationBirthService.birth`; `src/agent_operator/projectors/operation.py`; `src/agent_operator/application/operation_entrypoints.py` `OperationEntrypointService._load_event_sourced` | `tests/test_operation_entrypoints.py::test_operation_entrypoint_service_replays_event_sourced_run_state`; `tests/test_operation_entrypoints.py::test_operation_entrypoint_service_replays_event_sourced_resume_state` |
| ADR closure is verified against the current repository state | changed implementation under `src/agent_operator/...`; this ADR document | `uv run pytest tests/test_runtime.py tests/test_operation_projector.py tests/test_operation_entrypoints.py tests/test_operation_runtime_reconciliation_service.py -q`; `uv run pytest` |

## Implementation Notes

1. `SessionState` still stores `observed_state + terminal_state`; only the dead desired-state field
   is removed in this ADR.
2. `ObjectiveState` still duplicates goal-config fields from `OperationGoal`; only the redundant
   operation-status mirror is removed here.
3. The follow-up simplification remains the same: migrate `SessionState` to a single stored
   `status: SessionStatus` field in a separate ADR/PR.

## Related

- [ADR 0144](./0144-event-sourcing-write-path-contract-and-rfc-0009-closure.md) — dual-write debt; `active_session`, `SessionState` fields as resume failure sources
- [design/ARCHITECTURE.md](../ARCHITECTURE.md) — Known Technical Debt section
- [BACKLOG.md](../BACKLOG.md)
