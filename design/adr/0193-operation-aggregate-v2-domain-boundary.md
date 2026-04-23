# ADR 0193: OperationAggregate v2 — Domain Boundary and Field Classification

- Date: 2026-04-21

## Decision Status

Accepted

## Implementation Status

Verified

## Context

`OperationState` (v1) is a single Pydantic model with 50+ fields serving three distinct roles:

1. **Domain state** — business facts that must survive restarts: `goal`, `tasks`, `features`, `sessions`, `executions`, `memory_entries`, `status`, `final_summary`
2. **Coordination state** — drive-loop bookkeeping that the aggregate owns but that lives at the boundary of domain and process management: `current_focus`, `scheduler_state`, `operator_messages`, `processed_command_ids`, `pending_replan_command_ids`, `pending_attention_resolution_ids`
3. **Read-model / cache** — derived data for query efficiency: `operation_brief`, `iteration_briefs`, `agent_turn_briefs`, `policy_coverage`, `involvement_level`, `active_policies`

This mixing causes three concrete problems:

**Problem 1 — Snapshot drift.** v1 persists all three categories as one blob. When the drive loop mutates read-model fields (e.g. appends to `iteration_briefs`), those mutations must also be snapshotted or they are lost on resume. This forces unnecessary checkpoint writes and creates dual-write risk (see ADR 0144).

**Problem 2 — Testability collapse.** A test that exercises a domain invariant (e.g. "FAILED operations cannot be resumed") must construct a full 50-field model including policy caches and traceability briefs. There is no way to test the domain rule in isolation.

**Problem 3 — Coordination state has no clear home.** Fields like `processed_command_ids` and `pending_replan_command_ids` are neither pure domain (they don't represent business facts) nor pure ephemeral (they must survive crashes). Their placement in `OperationState` is accidental, not intentional.

### What ADR 0069 and ADR 0144 already decided

ADR 0069 decided the *storage contract*: `OperationEventStore` is canonical, `OperationCheckpointStore` is a derived acceleration surface.

ADR 0144 decided the *write path*: all state transitions must go through domain events, not direct snapshot mutation.

Neither ADR decided *what is domain state* vs *what is coordination state* vs *what is read model*. That classification is the gap this ADR fills.

## Decision

### 1. Explicit field classification

Every field in the v2 aggregate belongs to exactly one of three categories:

| Category | Definition | Persistence | Location |
|---|---|---|---|
| **Domain canonical** | Business facts; produced by applying domain events | Event log (via events) | `OperationAggregate` |
| **Coordination state** | Drive-loop bookkeeping that must survive restarts; belongs to the aggregate but is not a business fact | Event log (via events) | `OperationAggregate` |
| **Read model** | Derived from events for query efficiency; reconstructible at any time from the event log | Not persisted directly — rebuilt by projectors | `OperationReadModel` (separate object) |

### 2. OperationAggregate canonical fields

Domain canonical:
- `operation_id`, `goal`, `policy`, `status`, `objective`, `tasks`, `features`, `sessions`, `executions`, `artifacts`, `memory_entries`, `final_summary`

Coordination state (aggregate-owned, event-sourced):
- `current_focus`, `scheduler_state`, `operator_messages`, `attention_requests`, `processed_command_ids`, `pending_replan_command_ids`, `pending_attention_resolution_ids`
- Rationale: these fields must survive a crash in the middle of a drive cycle; they are produced by domain events (`SchedulerPaused`, `OperatorMessageReceived`, `AttentionRequestCreated`, etc.)

**Event → field production mapping** (see ARCHITECTURE_v2.md §22 for full event definitions):

| Field | Produced by event(s) |
|---|---|
| `status` | `OperationStarted`, `OperationCompleted`, `OperationFailed`, `OperationCancelled` |
| `sessions` | `SessionRegistered`, `SessionRunning`, `SessionCompleted`, `SessionFailed`, `SessionCancelled` |
| `current_focus` | `FocusSet`, `FocusCleared` |
| `scheduler_state` | `SchedulerPauseRequested`, `SchedulerPaused`, `SchedulerResumed` |
| `operator_messages` | `OperatorMessageReceived` |
| `attention_requests` | `AttentionRequestCreated`, `AttentionRequestAnswered` |
| `processed_command_ids` | `CommandProcessed` |
| `pending_replan_command_ids` | `ReplanScheduled`, `ReplanConsumed` |
| `pending_attention_resolution_ids` | `AttentionAnswerQueued`, `AttentionAnswerConsumed` |
| `tasks`, `features`, `executions` | Domain-specific events; see ARCHITECTURE_v2.md §22 |

### 3. OperationReadModel is a separate object

`OperationReadModel` is not part of `OperationAggregate`. It is a derived projection:
- `operation_brief`, `iteration_briefs`, `decision_records`, `agent_turn_briefs`, `artifacts` (duplicated for query)
- Built by `OperationReadModelProjector` from the event stream
- Appended to directly by `DriveService` for traceability data (`iteration_briefs`, `decision_records`) — see ADR 0196

### 4. Ephemeral-only fields are NOT in the aggregate

The following v1 fields are moved to `ProcessManagerContext` (ephemeral, per-drive-call):
- `policy_coverage`, `active_policies`, `involvement_level` — rebuilt from `PolicyStore` at the start of each drive call
- `pending_wakeups` — drained from `WakeupInbox` by `RuntimeReconciler`; not persisted in the aggregate

This is a breaking change from v1 where these fields lived in `OperationState`.

## Alternatives Considered

**Alternative 1 — Keep one model, add category annotations.** Add a `@domain_field` / `@coordination_field` / `@read_model_field` marker convention. Rejected: annotations are not enforced at runtime or test time; the mixing problem persists.

**Alternative 2 — Split into three separate Pydantic models, all persisted.** Persist `DomainAggregate`, `CoordinationState`, and `ReadModel` separately. Rejected: introduces a three-way atomicity problem on checkpoint writes.

**Alternative 3 — Keep v1 model, fix the dual-write problem only.** Route all mutations through events but keep the monolithic model. This is what ADR 0144 attempted incrementally. Rejected as insufficient: the testability and boundary problems remain even with a correct write path.

## Consequences

- `OperationAggregate` has a clearly bounded interface: `apply_events(events: list[DomainEvent])` is the only write path
- Read model is independently testable (pure projection from events)
- Coordination state fields remain in the aggregate but their event-sourced nature is explicit
- v1 `OperationState` is retired; no migration path — see ADR 0194
- `DriveService.drive()` receives `OperationAggregate` and constructs `ProcessManagerContext` via `build_pm_context()` at call start

## Repository Evidence

- `src/agent_operator/domain/aggregate.py` implements immutable `OperationAggregate.create()` and
  `apply_events()`, and no longer stores `active_policies`, `policy_coverage`, or
  `involvement_level` on the aggregate itself.
- `src/agent_operator/domain/read_model.py` defines the separate `OperationReadModel` and
  `DecisionRecord` types outside the aggregate.
- `src/agent_operator/application/queries/operation_read_model_projector.py` now projects
  `operation.created`, `brain.decision.made`, `agent.turn.completed`, and
  `operation.status.changed` into the read model without using `OperationState`.
- `src/agent_operator/application/drive/process_manager_context.py` rebuilds policy coverage as
  per-drive-call ephemeral state, and `src/agent_operator/application/drive/policy_executor.py`
  now seeds brain-facing `OperationState` bridges from that ephemeral policy context plus
  `agg.policy.involvement_level`.
- `src/agent_operator/application/queries/aggregate_query_adapter.py` provides the temporary
  aggregate-to-v1 query bridge with defaulted policy-cache fields rather than aggregate-owned
  runtime-policy truth.

## Residual Follow-On Work

- The wider query and brain-entry surfaces still use temporary `OperationState` bridges in some
  places, so this ADR is verified for aggregate boundary classification rather than for full
  repository-wide v2 cutover.
- The v1 runtime and service shell remain live beside the v2 tranche; that is tracked by ADR 0194
  and does not block this ADR's aggregate-boundary closure.

## Verification

Verified locally on 2026-04-23 with targeted unit coverage plus the full repository suite:

- `pytest -q tests/test_operation_aggregate.py tests/test_operation_read_model_projector.py tests/test_aggregate_query_adapter.py tests/test_lifecycle_gate.py tests/test_runtime_reconciler.py tests/test_drive_service_v2.py tests/test_operator_service_v2.py`
- `uv run pytest`
