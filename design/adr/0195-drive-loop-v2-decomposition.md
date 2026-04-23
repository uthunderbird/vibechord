# ADR 0195: Drive Loop v2 Decomposition — LifecycleGate / RuntimeReconciler / PolicyExecutor

- Date: 2026-04-21

## Decision Status

Accepted

## Implementation Status

Verified

Skim-safe status on 2026-04-23:

- `implemented`: the v2 drive loop is now decomposed into explicit `LifecycleGate`,
  `RuntimeReconciler`, `PolicyExecutor`, and `DriveService` classes under
  `src/agent_operator/application/drive/`
- `implemented`: `DriveService` owns the loop, checkpoint writes, wake-cycle continuation, and
  aggregate event application; sub-services communicate only through returned domain-event drafts
- `implemented`: `LifecycleGate` is pure/stateless, `RuntimeReconciler` is event-returning over
  runtime inputs, and `PolicyExecutor` records and executes brain decisions without directly
  mutating the aggregate
- `verified`: dedicated unit slices exist for `LifecycleGate`, `RuntimeReconciler`,
  `PolicyExecutor`, and `DriveService`
- `verified`: full repository suite passed on 2026-04-23 via `uv run pytest`

## Context

The v1 drive loop is implemented as a single class `OperationDriveService` that inherits from 25+ mixin classes via multiple inheritance:

```
OperationDriveService
  ├── OperationDriveRuntimeService   (reconciliation, background run management)
  ├── OperationDriveControlService   (commands, planning triggers)
  ├── OperationDriveDecisionExecutorService (brain calls, decision execution)
  ├── OperationDriveTraceService     (event emission, traceability)
  └── (more mixins...)
```

`operation_drive.py` alone is ~500 lines. The full service graph required to construct `OperationDriveService` requires 15+ collaborators injected at construction time into the top-level `OperatorService`.

### Concrete problems with the mixin architecture

**Problem 1 — No unit testability.** Every test of any drive loop behavior must construct the full 25-mixin `OperationDriveService`. There is no way to test "LifecycleGate should exit when budget is exceeded" without providing adapters, brain, event store, checkpoint store, policy store, wakeup inbox, command inbox, supervisor, etc.

**Problem 2 — No clear ownership of invariants.** The question "who is responsible for checking whether the operation should continue?" has no clear answer. `OperationDriveService._should_continue()` delegates to `OperationDriveRuntimeService._is_scheduler_paused()` which checks a field on `OperationState`. In v2 this field is on the aggregate — but with the mixin architecture, the field access path is opaque.

**Problem 3 — Implicit ordering.** The drive loop calls `_refresh_policy_context`, `_cleanup_orphaned_background_runs`, `_clear_expired_session_cooldowns`, `_migrate_legacy_rate_limit_failures`, `_sync_terminal_background_runs`, `_reconcile_stale_background_runs`, `_reconcile_background_wakeups` in a specific order. This order is not documented; it is implicit in the call sequence in `operation_drive.py`. Changing any step requires understanding the full call graph.

**Problem 4 — Brain has side effects.** `DecisionExecutionService` (called from the drive loop) can directly mutate fields on `OperationState` as part of executing a brain decision. In v2, brain decisions must produce only domain events — the aggregate is mutated only via `apply_events()`.

## Decision

Decompose the drive loop into four explicitly bounded services with documented responsibilities:

### 1. LifecycleGate
- **Contract:** Pure functions. No I/O. No mutations. All inputs via method parameters.
- **Responsibilities:** `should_continue(agg, ctx, config) -> bool`, `should_pause(agg, ctx) -> bool`, `check_pre_run(agg, config) -> LifecycleGateResult | None`
- **Testable:** A test of "budget exceeded → should_continue returns False" needs only an `OperationAggregate` with the right field values and an `OperationConfig`. No mocks.

### 2. RuntimeReconciler
- **Contract:** Async. Reads runtime state (wakeup inbox, command inbox, adapter registry, agent run store). Returns domain events. Never mutates aggregate directly.
- **Responsibilities:** Drain wakeup inbox → events, drain command inbox → events, poll background run status → events, detect stale sessions → events
- **Testable:** Mock `WakeupInbox` with predetermined wakeup signals; assert on the returned event list.

### 3. PolicyExecutor
- **Contract:** Async. Calls brain, executes decision. Returns `(decision, events, agent_result, iteration_brief)`. Never mutates aggregate directly.
- **Responsibilities:** Build `BrainContext`, call `brain.decide()`, optionally call `brain.plan()` on planning trigger, execute decision (start session, send message, collect result), return events
- **Testable:** Mock brain with predetermined decisions; assert that the returned events match the expected domain transitions.

### 4. DriveService
- **Contract:** Owns the while loop. Owns checkpoint writes. Coordinates the three services above. Returns `OperationOutcome`.
- **Responsibilities:** Call `build_pm_context()` once at start. Run while loop: `LifecycleGate.should_continue()` → `RuntimeReconciler.reconcile()` → `PolicyExecutor.decide_and_execute()` → `apply_events()` → `event_log.append()` → `checkpoint_store.save()`. Handle `more_actions` continuation. Handle drain exit.

### Interface contract: events as the only communication channel

Services communicate only through domain events returned to the drive loop:
- No service directly calls another service's methods
- No service writes to `OperationAggregate` fields directly
- The aggregate is mutated only via `agg.apply_events(events)` in the drive loop body

This is enforceable: `OperationAggregate` exposes no public setters.

## Alternatives Considered

**Keep mixin architecture, fix individual problems.** Make `OperationState` fields read-only; add types for the event return. Rejected: the root problem (no unit testability, implicit ordering) remains with mixins regardless of field mutability.

**Single-class rewrite without mixins.** Collapse all 25 mixins into one `DriveService` class with private methods. Rejected: still results in a 1000+ line class with the same testability problem — you cannot test `LifecycleGate` logic without constructing the full `DriveService`.

**Protocol-based injection without the four-service split.** Define a `ReconcilerProtocol` and inject it into a monolithic `DriveService`. This is identical to the chosen approach — the difference is whether the four services are named and documented as the architecture, or treated as implementation choices. We name them explicitly so they appear in tests, dependency injection, and future documentation.

## Consequences

- `LifecycleGate` has pure-function tests: ~10 lines per test, no mocks
- `RuntimeReconciler` tests mock only the inbox and run store protocols
- `PolicyExecutor` tests mock only the brain protocol
- `DriveService` integration tests can use real sub-services with in-memory implementations
- v1 mixin services (`OperationDriveRuntimeService`, `OperationDriveControlService`, etc.) are deleted — see ADR 0194
- The `OperationDriveService` class is deleted; replaced by `DriveService` with a different constructor surface (see ARCHITECTURE_v2.md §11.3)

## Repository Implementation

- `src/agent_operator/application/drive/lifecycle_gate.py` is the pure predicate boundary for
  continuation, pause materialization, timeout, budget, and background-wait gating
- `src/agent_operator/application/drive/runtime_reconciler.py` drains wakeups/commands, polls
  runtime state, and returns domain-event drafts without mutating the aggregate
- `src/agent_operator/application/drive/policy_executor.py` calls the brain, emits
  `brain.decision.made`, and translates execution into domain-event drafts
- `src/agent_operator/application/drive/drive_service.py` is the orchestration shell that applies
  events, appends them to the event log, writes checkpoints, and enforces `more_actions`
  continuation bounds

## Closure Evidence Matrix

| ADR line / closure claim | Repository evidence | Verification |
| --- | --- | --- |
| Drive loop is decomposed into four explicit services | `src/agent_operator/application/drive/lifecycle_gate.py`; `src/agent_operator/application/drive/runtime_reconciler.py`; `src/agent_operator/application/drive/policy_executor.py`; `src/agent_operator/application/drive/drive_service.py` | `tests/test_lifecycle_gate.py`; `tests/test_runtime_reconciler.py`; `tests/test_policy_executor.py`; `tests/test_drive_service_v2.py` |
| `LifecycleGate` is pure/stateless and independently testable | `src/agent_operator/application/drive/lifecycle_gate.py` | `tests/test_lifecycle_gate.py` |
| `RuntimeReconciler` reads runtime state and returns domain events without direct aggregate mutation | `src/agent_operator/application/drive/runtime_reconciler.py` | `tests/test_runtime_reconciler.py` |
| `PolicyExecutor` records and executes brain decisions via returned events | `src/agent_operator/application/drive/policy_executor.py` | `tests/test_policy_executor.py` |
| `DriveService` owns the loop, applies events, persists them, and handles bounded `more_actions` continuation | `src/agent_operator/application/drive/drive_service.py` | `tests/test_drive_service_v2.py::test_drive_service_reuses_wake_cycle_and_skips_intermediate_checkpoint_for_more_actions`; `tests/test_drive_service_v2.py::test_drive_service_uses_epoch_loaded_from_checkpoint_store` |
| Current repository state is verified, not inferred | this ADR plus the implementation above | `uv run pytest` |
