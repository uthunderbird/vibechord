# ADR 0201: Session Crash Recovery — RuntimeReconciler Orphan Detection

- Date: 2026-04-21

## Decision Status

Accepted

## Implementation Status

Verified

Skim-safe status on 2026-04-22:

- `implemented`: `RuntimeReconciler.detect_orphaned_sessions()` emits `session.crashed` with
  `reason="ORPHANED_AFTER_RESTART"` for RUNNING/PENDING sessions that the in-process supervisor
  has never registered in the current process
- `implemented`: `AgentRunSupervisorV2` retains per-operation tracked session ids after task
  completion through `get_all_tracked_session_ids()`
- `verified`: orphan detection is gated to run once per drive call through
  `ProcessManagerContext.orphan_check_completed`, matching the ADR wake-cycle contract
- `verified`: unit coverage exists for known-session, unknown-session, and once-per-drive-call
  behavior in `tests/test_runtime_reconciler.py` and `tests/test_agent_run_supervisor.py`
- `verified`: full repository suite passed via `uv run pytest` on 2026-04-22

## Context

`InProcessAgentRunSupervisor` (ADR 0200) manages background agent runs as `asyncio.Task` objects in-process. When the operator process crashes and restarts, the new process creates a fresh `InProcessAgentRunSupervisor` with no registered tasks. However, the `OperationAggregate` replayed from the event log may contain sessions in `RUNNING` or `PENDING` state — sessions that were active at crash time.

Without explicit handling, these sessions are permanently stuck: the aggregate says `RUNNING`, but no task exists. `RuntimeReconciler.reconcile()` calls `supervisor.get_tasks_for_operation(operation_id)` and receives an empty list. With no task and no completion event, the drive loop sees no change and does not call brain. The session waits for a wakeup that will never arrive.

This is not a theoretical scenario: any unclean shutdown (OOM, SIGKILL, power loss) produces orphaned sessions.

### The completed-but-unprocessed case

A session may appear RUNNING in the aggregate even though the background task actually completed before the crash. This happens because `SessionCompleted` is written to the event log by the **drive loop** when it processes the `TASK_COMPLETED` wakeup posted by `InProcessAgentRunSupervisor._on_task_complete()`. If the process crashes after the task posts its wakeup but before the drive loop processes it, the event log contains no `SessionCompleted` event and the aggregate shows the session as RUNNING on restart.

This case is indistinguishable from a genuinely crashed/orphaned session at the infrastructure level: in both cases, the aggregate shows RUNNING and the supervisor has no task. The correct recovery is the same — treat the session as failed, generate `AgentSessionCrashed(reason="ORPHANED_AFTER_RESTART")`, and let the brain decide whether to restart. The brain may discover via external means (user message, ACP state check) that the agent actually completed; the infrastructure cannot safely make this determination without re-attaching to the ACP session, which is not guaranteed to be alive (see Alternatives Considered).

## Decision

`RuntimeReconciler.reconcile()` must perform **orphan detection** at the start of each drive call.

### Orphan detection protocol

A session is **orphaned** if:
- `agg.sessions[session_id].status` is `RUNNING` or `PENDING`, AND
- `supervisor.get_tasks_for_operation(operation_id)` does not include a task registered for that `session_id`

On detecting an orphaned session, `RuntimeReconciler` generates an `AgentSessionCrashed` event with:
```python
AgentSessionCrashed(
    operation_id=operation_id,
    session_id=session_id,
    reason="ORPHANED_AFTER_RESTART",
)
```

The drive loop applies this event normally. `OperationAggregate` transitions the session to `CRASHED` status. Brain sees `CRASHED` in the next `decide()` call and chooses to restart the agent, surface the failure to the user, or take another action — the recovery policy is the brain's responsibility, not the infrastructure's.

### Interface addition: `get_all_tracked_session_ids()`

```python
class InProcessAgentRunSupervisor:
    def get_all_tracked_session_ids(self, operation_id: str) -> set[str]
    # Returns session IDs that have ever been registered for this operation,
    # including completed and cancelled tasks. Used by orphan detection.
```

`get_tasks_for_operation()` returns only *active* (non-done) tasks. `get_all_tracked_session_ids()` returns the full registry including completed entries. This lets the reconciler distinguish:
- Session ID known to supervisor + task done → session completed normally (already processed)
- Session ID known to supervisor + task still running → session active (no orphan)
- Session ID **not known** to supervisor → session was never registered in this process → **orphaned**

### When orphan detection runs

Orphan detection runs once per `drive()` call, during the first `reconcile()` invocation (before the first brain call). It does not re-run between `more_actions` sub-calls within the same wake cycle — the first invocation is sufficient to transition all orphaned sessions to `CRASHED`.

### Scope

Orphan detection covers sessions in `RUNNING` or `PENDING` status only. Sessions in terminal states (`COMPLETED`, `CRASHED`, `CANCELLED`) are not checked — they are already resolved.

## Alternatives Considered

**Heartbeat / liveness timeout.** Background sessions post a heartbeat to the aggregate; if no heartbeat arrives within N seconds, the session is declared crashed. Rejected: adds complexity (heartbeat events, timer management) for a problem that is fully solvable at startup via supervisor registry inspection. Heartbeats are useful for detecting hangs in a *running* process; orphan detection is sufficient for the crash-restart scenario.

**Durable task registry.** Persist the supervisor's task registry to a store (SQLite, file). On restart, the supervisor reads the registry and can determine which sessions were in-flight. Rejected: adds a persistence dependency to a component designed to be ephemeral. The information is derivable from the aggregate state without a separate store.

**ACP session re-attach.** On restart, attempt to re-attach to the ACP session at the remote agent and continue from where it left off. Rejected: ACP sessions are transient; the remote agent session is not guaranteed to be alive after an operator crash. Re-attach requires the ACP protocol to support it, which is not currently the case.

## Consequences

- `InProcessAgentRunSupervisor` gains `get_all_tracked_session_ids(operation_id)` — a pure read method, no behavioral change
- `RuntimeReconciler.reconcile()` runs a startup orphan check on the first call per `drive()` invocation
- In-memory test implementations of `InProcessAgentRunSupervisor` must track registered sessions even after task completion, to support `get_all_tracked_session_ids()`
- Brain prompt must describe `ORPHANED_AFTER_RESTART` crash reason so brain can make an informed restart-vs-surface decision
- No persistent state is required beyond the existing aggregate and supervisor in-memory registry
