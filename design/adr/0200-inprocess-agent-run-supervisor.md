# ADR 0200: InProcessAgentRunSupervisor — asyncio-in-process Background Run Management

- Date: 2026-04-21

## Decision Status

Accepted

## Implementation Status

Verified

Skim-safe status on 2026-04-23:

- `implemented`: `AgentRunSupervisorV2` is the centralized in-process background-task registry for
  v2 drive/runtime code
- `implemented`: supervisor state is keyed by operation/session identity, rejects new spawns while
  draining, and exposes active-task plus tracked-session views needed by shutdown and orphan
  detection
- `implemented`: `OperatorServiceV2` now maintains `_drive_tasks`, requests drain on active drive
  contexts first, then marks the supervisor draining, waits for drive tasks to finish, and only
  then cancels remaining background tasks
- `verified`: dedicated supervisor and `OperatorServiceV2` shutdown-order regression tests cover
  spawn/track/cancel/drain behavior and the load-bearing shutdown sequence
- `verified`: full repository suite passed on 2026-04-23 via `uv run pytest`

## Context

When brain decides to start a background agent (`START_BACKGROUND_AGENT`), the agent run must:
1. Execute independently of the drive loop (the drive loop must not block on it)
2. Notify the drive loop when it completes (so the loop can reconcile the result)
3. Be cancellable if the operation is cancelled or the process is draining
4. Be observable (the drive loop needs to poll its status)

In v1, background runs are managed via a combination of `LoadedOperation` background run tracking and direct asyncio task creation in `DecisionExecutionService`. The task handle is not centrally tracked; cancellation during shutdown is ad-hoc.

### Options for background run execution

**Option A — asyncio Tasks in-process (chosen):** Create an `asyncio.Task` per background run. The task runs in the same event loop as the drive loop. Communication via a shared `WakeupInbox` (task completion posts a wakeup).

**Option B — Separate OS process per run.** Spawn a subprocess for each agent run. Communicate via IPC (pipe, socket). Supervisor manages process lifecycle.

**Option C — External task queue (Celery, ARQ, etc.).** Enqueue tasks to a broker. Workers pick up and execute. Operator polls for completion.

**Option D — Thread pool.** Run agent calls in a thread pool. asyncio `run_in_executor` bridges sync and async.

## Decision

Use **Option A — asyncio Tasks in-process** via a centralized `InProcessAgentRunSupervisor`.

### Why asyncio in-process

**Simplicity**: The operator is already an asyncio application. Agent adapter calls (`start()`, `collect()`) are already async. No process boundary, no IPC, no serialization.

**Cancellation**: asyncio task cancellation is first-class. On drain/cancel, `supervisor.cancel_all()` cancels all running tasks. The tasks handle `asyncio.CancelledError` and post a `SessionCancelled` wakeup.

**Observability**: `supervisor.get_tasks_for_operation(operation_id)` returns live task handles. `RuntimeReconciler` polls these each drive cycle to detect completions.

**Resource model**: Agent runs are network-bound (waiting for ACP responses). asyncio cooperative scheduling handles many concurrent runs efficiently. A thread pool would add unnecessary overhead for I/O-bound work.

### Why not Option B (subprocess)

Subprocess-per-run adds process spawn latency (~100ms), requires IPC protocol design, and complicates cancellation (SIGTERM handling per child process). The operator is not CPU-bound; subprocesses provide no concurrency benefit.

### Why not Option C (external queue)

An external task queue adds a broker dependency, deployment complexity, and at-least-once delivery semantics that require idempotent task handlers. For a pre-production project with a single operator process, this is pure overhead.

### InProcessAgentRunSupervisor interface

```python
class InProcessAgentRunSupervisor:
    def spawn(self, coro: Coroutine, *, operation_id: str, session_id: str) -> asyncio.Task
    def get_tasks_for_operation(self, operation_id: str) -> list[asyncio.Task]
    def get_active_tasks(self) -> list[asyncio.Task]            # all operations; used by shutdown
    def get_all_tracked_session_ids(self, operation_id: str) -> set[str]  # full registry incl. done tasks; used by orphan detection (ADR 0201)
    def cancel_all(self) -> None                                # graceful drain
    def mark_draining(self) -> None
```

`spawn()` creates an asyncio Task, registers it by `(operation_id, session_id)`, and posts a `WakeupRef` to `WakeupInbox` when the task completes. The drive loop's `RuntimeReconciler` polls `get_tasks_for_operation()` each cycle.

### Shutdown sequence

On SIGTERM, `OperatorServiceV2._on_sigterm()` executes the following steps in order:

1. Calls `ctx.request_drain()` on all active `ProcessManagerContext` instances. Each drive loop detects `ctx.draining` at the top of its while-loop iteration and breaks after completing the current cycle, emitting `SchedulerPaused` and saving a final checkpoint.

2. Calls `supervisor.mark_draining()`. Background tasks spawned after this point are not created; the supervisor rejects new `spawn()` calls.

3. Awaits all drive loop tasks: `await asyncio.gather(*self._drive_tasks, return_exceptions=True)`. `self._drive_tasks` is the list of `asyncio.Task` objects created by `OperatorServiceV2` for each active operation's drive loop. This is the synchronization point — `cancel_all()` must not be called until this gather completes.

4. Calls `supervisor.cancel_all()` to cancel any background agent tasks still running after the drive loops have exited. Background tasks handle `asyncio.CancelledError` and post a `SessionCancelled` wakeup, but since the drive loops have already exited, no drive loop will process these wakeups — they are discarded.

5. Awaits remaining background task cancellation: `await asyncio.gather(*supervisor.get_active_tasks(), return_exceptions=True)`.

**Why this ordering matters**: If `cancel_all()` is called before the drive loops exit (step 3), a drive loop that is mid-reconcile may see a task cancelled that it was about to process as a completion. The `SessionCancelled` event would be generated incorrectly. Step 3 ensures no drive loop is running when background tasks are cancelled.

## Consequences

- `OperatorServiceV2` must maintain `_drive_tasks: list[asyncio.Task]` — a list of all active drive loop tasks, one per operation. Each task is appended at creation time (when the drive loop is started for an operation) and used in the shutdown sequence step 3 (`asyncio.gather(*self._drive_tasks, ...)`). Without this list, the shutdown ordering guarantee in the Shutdown Sequence above cannot be enforced.
- Background runs share the same event loop and memory space as the drive loop — a runaway background run can starve other operations. Mitigation: adapter `collect()` calls have timeouts enforced by the ACP session runner.
- `InProcessAgentRunSupervisor` is a shared singleton across all concurrent operations on one operator process — thread-safety is a non-issue (single-threaded asyncio) but the task registry must be keyed by `(operation_id, session_id)` to avoid cross-operation collisions.
- The v1 ad-hoc task management in `DecisionExecutionService` is deleted — see ADR 0194.
- If future scaling requires multi-process agent execution, the `AgentRunStore` protocol (used by `RuntimeReconciler`) is the extension point — a new implementation of `AgentRunStore` backed by an external queue would satisfy the protocol without changing the drive loop.

## Repository Implementation

- `src/agent_operator/application/drive/agent_run_supervisor.py` implements the centralized
  in-process task registry, drain gate, active-task query surface, and retained tracked-session
  registry
- `src/agent_operator/application/operator_service_v2.py` wires the supervisor into shutdown by
  maintaining `_drive_tasks`, requesting drain on all active contexts, awaiting drive-loop exit,
  then cancelling background tasks
- `src/agent_operator/application/drive/policy_executor.py` registers background work with the v2
  supervisor when available

## Closure Evidence Matrix

| ADR line / closure claim | Repository evidence | Verification |
| --- | --- | --- |
| Background runs are managed as centralized in-process asyncio tasks | `src/agent_operator/application/drive/agent_run_supervisor.py` | `tests/test_agent_run_supervisor.py` |
| Supervisor tracks active tasks and retained session ids by operation/session identity | `src/agent_operator/application/drive/agent_run_supervisor.py` | `tests/test_agent_run_supervisor.py::test_get_tasks_for_operation_returns_active_only`; `tests/test_agent_run_supervisor.py::test_get_all_tracked_session_ids_persists_after_completion` |
| Draining rejects new spawns and shutdown cancellation is explicit | `src/agent_operator/application/drive/agent_run_supervisor.py` | `tests/test_agent_run_supervisor.py::test_mark_draining_rejects_new_spawns`; `tests/test_agent_run_supervisor.py::test_cancel_all_cancels_active_tasks` |
| `OperatorServiceV2` waits for drive-loop exit before cancelling background tasks | `src/agent_operator/application/operator_service_v2.py:217-230` | `tests/test_operator_service_v2.py::test_on_sigterm_requests_drain_before_cancelling_supervisor_tasks`; `tests/test_operator_service_v2.py::test_on_sigterm_waits_for_drive_exit_before_cancelling_background_tasks` |
| Current repository state is verified, not inferred | this ADR plus the implementation above | `uv run pytest` |
