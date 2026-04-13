from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from agent_operator.domain import (
    AgentError,
    AgentResult,
    AgentResultStatus,
    AgentSessionHandle,
    BackgroundRunStatus,
    BackgroundRuntimeMode,
    BrainActionType,
    BrainDecision,
    Evaluation,
    ExecutionState,
    FocusKind,
    FocusMode,
    FocusState,
    IterationState,
    OperationGoal,
    OperationState,
    OperationStatus,
    ProgressSummary,
    RunEvent,
    RunEventKind,
    RunMode,
    RunOptions,
    SessionState,
    SessionStatus,
)
from agent_operator.testing.operator_service_support import (
    FakeAgent,
    FakeSupervisor,
    MemoryEventSink,
    MemoryStore,
    MemoryTraceStore,
    MemoryWakeupInbox,
    StartClaudeAcpThenStopBrain,
    StartThenStopBrain,
    make_service,
    run_settings,
    state_settings,
)
from agent_operator.testing.runtime_bindings import build_test_runtime_bindings


class StartWaitStopBrain:
    def __init__(self) -> None:
        self.calls = 0

    async def decide_next_action(self, state) -> BrainDecision:
        self.calls += 1
        if self.calls == 1:
            return BrainDecision(
                action_type=BrainActionType.START_AGENT,
                target_agent="claude_acp",
                instruction="run in background",
                rationale="Dispatch work first.",
            )
        if self.calls == 2:
            session_id = state.sessions[0].session_id
            return BrainDecision(
                action_type=BrainActionType.WAIT_FOR_AGENT,
                target_agent="claude_acp",
                session_id=session_id,
                rationale="Wait on the dependency.",
                blocking_focus={
                    "kind": "session",
                    "target_id": session_id,
                    "blocking_reason": "Need the running session to finish.",
                    "interrupt_policy": "material_wakeup",
                    "resume_policy": "replan",
                },
            )
        return BrainDecision(
            action_type=BrainActionType.STOP,
            rationale="Wakeup delivered the result.",
        )

    async def evaluate_result(self, state) -> Evaluation:
        return Evaluation(goal_satisfied=False, should_continue=True, summary="continue")

    async def summarize_progress(self, state) -> ProgressSummary:
        return ProgressSummary(summary="summary")

    async def normalize_artifact(self, goal, result) -> AgentResult:
        return result


class DelayedCollectSupervisor(FakeSupervisor):
    """Return no collected result on the first terminal wakeup reconciliation attempt."""

    def __init__(self) -> None:
        super().__init__()
        self.collect_calls: dict[str, int] = {}

    async def collect_background_turn(self, run_id: str) -> AgentResult | None:
        calls = self.collect_calls.get(run_id, 0) + 1
        self.collect_calls[run_id] = calls
        if calls == 1:
            return None
        return await super().collect_background_turn(run_id)


@pytest.mark.anyio
async def test_operator_service_reconciles_background_wakeup_on_resume() -> None:
    store = MemoryStore()
    trace_store = MemoryTraceStore()
    inbox = MemoryWakeupInbox()
    supervisor = FakeSupervisor()
    service = make_service(
        brain=StartThenStopBrain(),
        store=store,
        trace_store=trace_store,
        event_sink=MemoryEventSink(),
        agent_runtime_bindings=build_test_runtime_bindings({"claude_acp": FakeAgent()}),
        wakeup_inbox=inbox,
        supervisor=supervisor,
    )

    first = await service.run(
        OperationGoal(objective="background task"),
        **run_settings(max_iterations=4, allowed_agents=["claude_acp"]),
        options=RunOptions(
            run_mode=RunMode.RESUMABLE,
            background_runtime_mode=BackgroundRuntimeMode.RESUMABLE_WAKEUP,
        ),
    )
    operation = await store.load_operation(first.operation_id)
    assert operation is not None
    run_id = operation.background_runs[0].run_id
    await inbox.enqueue(
        RunEvent(
            event_type="background_run.completed",
            kind=RunEventKind.WAKEUP,
            operation_id=operation.operation_id,
            iteration=1,
            task_id=operation.tasks[0].task_id,
            session_id=operation.sessions[0].session_id,
            dedupe_key=f"{run_id}:completed",
            payload={"run_id": run_id},
        )
    )

    resumed = await service.resume(
        operation.operation_id,
        options=RunOptions(
            run_mode=RunMode.RESUMABLE,
            background_runtime_mode=BackgroundRuntimeMode.RESUMABLE_WAKEUP,
        ),
    )
    operation = await store.load_operation(resumed.operation_id)
    assert resumed.status is OperationStatus.COMPLETED
    assert operation is not None
    assert operation.iterations[0].result is not None
    assert operation.iterations[0].result.output_text == "completed by fake background agent"
    assert trace_store.bundle.agent_turn_briefs[0].status == "success"


@pytest.mark.anyio
async def test_duplicate_terminal_wakeups_do_not_refold_same_background_run() -> None:
    store = MemoryStore()
    trace_store = MemoryTraceStore()
    inbox = MemoryWakeupInbox()
    supervisor = FakeSupervisor()
    service = make_service(
        brain=StartThenStopBrain(),
        store=store,
        trace_store=trace_store,
        event_sink=MemoryEventSink(),
        agent_runtime_bindings=build_test_runtime_bindings({"claude_acp": FakeAgent()}),
        wakeup_inbox=inbox,
        supervisor=supervisor,
    )

    first = await service.run(
        OperationGoal(objective="background task"),
        **run_settings(max_iterations=4, allowed_agents=["claude_acp"]),
        options=RunOptions(
            run_mode=RunMode.RESUMABLE,
            background_runtime_mode=BackgroundRuntimeMode.RESUMABLE_WAKEUP,
        ),
    )
    operation = await store.load_operation(first.operation_id)
    assert operation is not None
    run_id = operation.background_runs[0].run_id
    session_id = operation.sessions[0].session_id
    task_id = operation.tasks[0].task_id
    for event_id in ("wakeup-1", "wakeup-2"):
        await inbox.enqueue(
            RunEvent(
                event_type="background_run.completed",
                kind=RunEventKind.WAKEUP,
                operation_id=operation.operation_id,
                iteration=1,
                task_id=task_id,
                session_id=session_id,
                dedupe_key=f"{run_id}:completed",
                event_id=event_id,
                payload={"run_id": run_id},
            )
        )

    resumed = await service.resume(
        operation.operation_id,
        options=RunOptions(
            run_mode=RunMode.RESUMABLE,
            background_runtime_mode=BackgroundRuntimeMode.RESUMABLE_WAKEUP,
        ),
    )
    operation = await store.load_operation(resumed.operation_id)
    assert operation is not None
    assert operation.iterations[0].result is not None
    assert operation.iterations[0].result.output_text == "completed by fake background agent"
    assert len(operation.artifacts) == 1
    assert len(trace_store.bundle.agent_turn_briefs) == 1
    assert operation.sessions[0].last_terminal_execution_id == run_id


@pytest.mark.anyio
async def test_resume_reconciles_completed_background_run_without_wakeup() -> None:
    store = MemoryStore()
    trace_store = MemoryTraceStore()
    event_sink = MemoryEventSink()
    supervisor = FakeSupervisor()
    service = make_service(
        brain=StartThenStopBrain(),
        store=store,
        trace_store=trace_store,
        event_sink=event_sink,
        agent_runtime_bindings=build_test_runtime_bindings({"claude_acp": FakeAgent()}),
        supervisor=supervisor,
    )

    first = await service.run(
        OperationGoal(objective="background task"),
        **run_settings(max_iterations=4, allowed_agents=["claude_acp"]),
        options=RunOptions(
            run_mode=RunMode.RESUMABLE,
            background_runtime_mode=BackgroundRuntimeMode.RESUMABLE_WAKEUP,
        ),
    )
    operation = await store.load_operation(first.operation_id)
    assert operation is not None
    run_id = operation.background_runs[0].run_id
    supervisor.runs[run_id].status = BackgroundRunStatus.COMPLETED
    supervisor.runs[run_id].completed_at = datetime.now(UTC)

    resumed = await service.resume(
        operation.operation_id,
        options=RunOptions(
            run_mode=RunMode.RESUMABLE,
            background_runtime_mode=BackgroundRuntimeMode.RESUMABLE_WAKEUP,
        ),
    )
    operation = await store.load_operation(operation.operation_id)
    assert resumed.status is OperationStatus.COMPLETED
    assert operation is not None
    assert operation.iterations[0].result is not None
    assert any(
        event.event_type == "background_run.reconciled_from_supervisor"
        for event in event_sink.events
    )


@pytest.mark.anyio
async def test_resume_releases_unhandled_wakeup_for_retry() -> None:
    store = MemoryStore()
    trace_store = MemoryTraceStore()
    inbox = MemoryWakeupInbox()
    supervisor = DelayedCollectSupervisor()
    service = make_service(
        brain=StartThenStopBrain(),
        store=store,
        trace_store=trace_store,
        event_sink=MemoryEventSink(),
        agent_runtime_bindings=build_test_runtime_bindings({"claude_acp": FakeAgent()}),
        wakeup_inbox=inbox,
        supervisor=supervisor,
    )

    first = await service.run(
        OperationGoal(objective="background task"),
        **run_settings(max_iterations=4, allowed_agents=["claude_acp"]),
        options=RunOptions(
            run_mode=RunMode.RESUMABLE,
            background_runtime_mode=BackgroundRuntimeMode.RESUMABLE_WAKEUP,
        ),
    )
    operation = await store.load_operation(first.operation_id)
    assert operation is not None
    run_id = operation.background_runs[0].run_id
    await inbox.enqueue(
        RunEvent(
            event_type="background_run.completed",
            kind=RunEventKind.WAKEUP,
            operation_id=operation.operation_id,
            iteration=1,
            task_id=operation.tasks[0].task_id,
            session_id=operation.sessions[0].session_id,
            dedupe_key=f"{run_id}:completed",
            payload={"run_id": run_id},
        )
    )

    reconciliation = service._operation_runtime_reconciliation_service

    await reconciliation.reconcile_background_wakeups(operation)

    pending_after_first_resume = await inbox.list_pending(operation.operation_id)
    assert operation.iterations[0].result is None
    assert len(pending_after_first_resume) == 1
    assert pending_after_first_resume[0].payload == {"run_id": run_id}
    assert inbox.acked == []

    await reconciliation.reconcile_background_wakeups(operation)

    assert operation.iterations[0].result is not None
    assert operation.iterations[0].result.output_text == "completed by fake background agent"
    assert await inbox.list_pending(operation.operation_id) == []


@pytest.mark.anyio
async def test_resume_cleans_orphaned_background_runs_while_waiting() -> None:
    store = MemoryStore()
    operation = OperationState(
        goal=OperationGoal(objective="background task"),
        **state_settings(max_iterations=4, allowed_agents=["claude_acp"]),
    )
    session = AgentSessionHandle(
        adapter_key="claude_acp",
        session_id="session-1",
        session_name="main",
    )
    operation.sessions.append(
        SessionState(
            handle=session,
            status=SessionStatus.RUNNING,
            current_execution_id="run-current",
        )
    )
    operation.background_runs.extend(
        [
            ExecutionState(
                run_id="run-current",
                operation_id=operation.operation_id,
                adapter_key="claude_acp",
                session_id="session-1",
                status=BackgroundRunStatus.RUNNING,
            ),
            ExecutionState(
                run_id="run-orphan",
                operation_id=operation.operation_id,
                adapter_key="claude_acp",
                session_id="session-1",
                status=BackgroundRunStatus.RUNNING,
            ),
        ]
    )
    operation.current_focus = FocusState(
        kind=FocusKind.SESSION,
        target_id="session-1",
        mode=FocusMode.BLOCKING,
    )
    await store.save_operation(operation)

    supervisor = FakeSupervisor()
    supervisor.runs = {run.run_id: run.model_copy() for run in operation.background_runs}
    service = make_service(
        brain=StartWaitStopBrain(),
        store=store,
        trace_store=MemoryTraceStore(),
        event_sink=MemoryEventSink(),
        agent_runtime_bindings=build_test_runtime_bindings({"claude_acp": FakeAgent()}),
        wakeup_inbox=MemoryWakeupInbox(),
        supervisor=supervisor,
    )

    resumed = await service.resume(
        operation.operation_id,
        options=RunOptions(
            run_mode=RunMode.RESUMABLE,
            background_runtime_mode=BackgroundRuntimeMode.RESUMABLE_WAKEUP,
        ),
    )
    updated = await store.load_operation(operation.operation_id)
    assert resumed.status is OperationStatus.RUNNING
    assert updated is not None
    runs = {run.run_id: run for run in updated.background_runs}
    assert runs["run-orphan"].status is BackgroundRunStatus.CANCELLED
    assert (
        ("run-orphan", BackgroundRunStatus.CANCELLED, "orphaned_background_run")
        in supervisor.finalized
    )


@pytest.mark.anyio
async def test_resume_marks_stale_background_run_as_failed() -> None:
    store = MemoryStore()
    operation = OperationState(
        goal=OperationGoal(objective="background task"),
        **state_settings(max_iterations=4, allowed_agents=["claude_acp"]),
    )
    session = AgentSessionHandle(
        adapter_key="claude_acp",
        session_id="session-1",
        session_name="main",
    )
    operation.sessions.append(
        SessionState(
            handle=session,
            status=SessionStatus.RUNNING,
            current_execution_id="run-stale",
            latest_iteration=1,
        )
    )
    operation.iterations.append(IterationState(index=1, task_id=None, session=session))
    operation.background_runs.append(
        ExecutionState(
            run_id="run-stale",
            operation_id=operation.operation_id,
            adapter_key="claude_acp",
            session_id="session-1",
            status=BackgroundRunStatus.RUNNING,
            last_heartbeat_at=datetime.now(UTC) - timedelta(minutes=10),
        )
    )
    operation.current_focus = FocusState(
        kind=FocusKind.SESSION,
        target_id="session-1",
        mode=FocusMode.BLOCKING,
    )
    await store.save_operation(operation)

    supervisor = FakeSupervisor()
    supervisor.runs = {run.run_id: run.model_copy() for run in operation.background_runs}
    service = make_service(
        brain=StartWaitStopBrain(),
        store=store,
        trace_store=MemoryTraceStore(),
        event_sink=MemoryEventSink(),
        agent_runtime_bindings=build_test_runtime_bindings({"claude_acp": FakeAgent()}),
        wakeup_inbox=MemoryWakeupInbox(),
        supervisor=supervisor,
    )

    resumed = await service.resume(
        operation.operation_id,
        options=RunOptions(
            run_mode=RunMode.RESUMABLE,
            background_runtime_mode=BackgroundRuntimeMode.RESUMABLE_WAKEUP,
            max_cycles=1,
        ),
    )
    updated = await store.load_operation(operation.operation_id)
    assert resumed.status is OperationStatus.RUNNING
    assert updated is not None
    assert updated.iterations[0].result is not None
    assert updated.iterations[0].result.error is not None
    assert updated.iterations[0].result.error.code == "background_run_stale"
    assert ("run-stale", BackgroundRunStatus.FAILED, "background_run_stale") in supervisor.finalized


@pytest.mark.anyio
async def test_resume_syncs_terminal_background_run_truth_back_to_supervisor() -> None:
    store = MemoryStore()
    operation = OperationState(
        goal=OperationGoal(objective="background task"),
        **state_settings(max_iterations=4, allowed_agents=["claude_acp"]),
    )
    operation.background_runs.append(
        ExecutionState(
            run_id="run-failed",
            operation_id=operation.operation_id,
            adapter_key="claude_acp",
            session_id="session-1",
            status=BackgroundRunStatus.FAILED,
            completed_at=datetime.now(UTC),
            last_heartbeat_at=datetime.now(UTC),
        )
    )
    await store.save_operation(operation)

    supervisor = FakeSupervisor()
    supervisor.runs["run-failed"] = ExecutionState(
        run_id="run-failed",
        operation_id=operation.operation_id,
        adapter_key="claude_acp",
        session_id="session-1",
        status=BackgroundRunStatus.RUNNING,
    )
    service = make_service(
        brain=StartWaitStopBrain(),
        store=store,
        trace_store=MemoryTraceStore(),
        event_sink=MemoryEventSink(),
        agent_runtime_bindings=build_test_runtime_bindings({"claude_acp": FakeAgent()}),
        wakeup_inbox=MemoryWakeupInbox(),
        supervisor=supervisor,
    )

    resumed = await service.resume(
        operation.operation_id,
        options=RunOptions(
            run_mode=RunMode.RESUMABLE,
            background_runtime_mode=BackgroundRuntimeMode.RESUMABLE_WAKEUP,
            max_cycles=1,
        ),
    )

    assert resumed.status is OperationStatus.RUNNING
    assert supervisor.runs["run-failed"].status is BackgroundRunStatus.FAILED


@pytest.mark.anyio
async def test_resume_migrates_legacy_rate_limit_failure_into_cooldown_block() -> None:
    store = MemoryStore()
    operation = OperationState(
        goal=OperationGoal(objective="legacy rate limit"),
        **state_settings(max_iterations=4, allowed_agents=["claude_acp"]),
        status=OperationStatus.FAILED,
        final_summary="Unable to continue because the worker hit a hard reset limit.",
    )
    session = AgentSessionHandle(
        adapter_key="claude_acp",
        session_id="session-legacy-rate-limit",
        session_name="legacy",
    )
    operation.sessions.append(
        SessionState(
            handle=session,
            status=SessionStatus.FAILED,
            last_result_iteration=1,
            latest_iteration=1,
        )
    )
    operation.iterations.append(
        IterationState(
            index=1,
            result=AgentResult(
                session_id=session.session_id,
                status=AgentResultStatus.FAILED,
                output_text="",
                error=AgentError(
                    code="claude_acp_failed",
                    message="Internal error: You've hit your limit · resets 1am (Asia/Almaty)",
                    retryable=False,
                ),
                completed_at=datetime.now(UTC),
            ),
        )
    )
    await store.save_operation(operation)

    service = make_service(
        brain=StartClaudeAcpThenStopBrain(),
        store=store,
        trace_store=MemoryTraceStore(),
        event_sink=MemoryEventSink(),
        agent_runtime_bindings=build_test_runtime_bindings(
            {"claude_acp": FakeAgent(key="claude_acp")}
        ),
    )

    resumed = await service.resume(
        operation.operation_id,
        options=RunOptions(run_mode=RunMode.ATTACHED),
    )
    updated = await store.load_operation(operation.operation_id)
    assert resumed.status is OperationStatus.NEEDS_HUMAN
    assert updated is not None
    assert updated.sessions[0].status is SessionStatus.WAITING
    assert updated.sessions[0].cooldown_until is not None


@pytest.mark.anyio
async def test_resume_reconciles_disconnected_background_run_without_session_id() -> None:
    store = MemoryStore()
    supervisor = FakeSupervisor()
    service = make_service(
        brain=StartWaitStopBrain(),
        store=store,
        trace_store=MemoryTraceStore(),
        event_sink=MemoryEventSink(),
        agent_runtime_bindings=build_test_runtime_bindings({"claude_acp": FakeAgent()}),
        wakeup_inbox=MemoryWakeupInbox(),
        supervisor=supervisor,
    )

    first = await service.run(
        OperationGoal(objective="recover early disconnected background run"),
        **run_settings(max_iterations=5, allowed_agents=["claude_acp"]),
        options=RunOptions(
            run_mode=RunMode.RESUMABLE,
            max_cycles=1,
            background_runtime_mode=BackgroundRuntimeMode.RESUMABLE_WAKEUP,
        ),
    )
    assert first.status is OperationStatus.RUNNING

    run = supervisor.runs["run-1"]
    run.status = BackgroundRunStatus.DISCONNECTED
    run.session_id = None
    run.completed_at = datetime.now(UTC)
    run.last_heartbeat_at = run.completed_at
    supervisor.results["run-1"] = AgentResult(
        session_id="background-run-1",
        status=AgentResultStatus.DISCONNECTED,
        output_text="",
        error=AgentError(
            code="codex_acp_disconnected",
            message="ACP subprocess closed before completing all pending requests.",
            retryable=True,
            raw={"recovery_mode": "same_session"},
        ),
        completed_at=run.completed_at,
    )

    resumed = await service.resume(
        first.operation_id,
        options=RunOptions(
            run_mode=RunMode.RESUMABLE,
            max_cycles=3,
            background_runtime_mode=BackgroundRuntimeMode.RESUMABLE_WAKEUP,
        ),
    )
    operation = await store.load_operation(first.operation_id)

    assert resumed.status is OperationStatus.COMPLETED
    assert resumed.final_result is not None
    assert resumed.final_result.status is AgentResultStatus.DISCONNECTED
    assert operation is not None
    assert operation.iterations[1].result is not None
    assert operation.iterations[1].result.status is AgentResultStatus.DISCONNECTED
    assert "WAIT_FOR_AGENT ignored" in operation.iterations[1].notes[0]
    assert operation.sessions[0].current_execution_id is None


@pytest.mark.anyio
async def test_duplicate_background_wakeup_does_not_duplicate_result_or_briefs() -> None:
    store = MemoryStore()
    trace_store = MemoryTraceStore()
    inbox = MemoryWakeupInbox()
    supervisor = FakeSupervisor()
    service = make_service(
        brain=StartThenStopBrain(),
        store=store,
        trace_store=trace_store,
        event_sink=MemoryEventSink(),
        agent_runtime_bindings=build_test_runtime_bindings({"claude_acp": FakeAgent()}),
        wakeup_inbox=inbox,
        supervisor=supervisor,
    )

    first = await service.run(
        OperationGoal(objective="background task"),
        **run_settings(max_iterations=4, allowed_agents=["claude_acp"]),
        options=RunOptions(
            run_mode=RunMode.RESUMABLE,
            background_runtime_mode=BackgroundRuntimeMode.RESUMABLE_WAKEUP,
        ),
    )
    operation = await store.load_operation(first.operation_id)
    assert operation is not None
    run_id = operation.background_runs[0].run_id
    for dedupe_key in (f"{run_id}:completed", f"{run_id}:completed-duplicate"):
        await inbox.enqueue(
            RunEvent(
                event_type="background_run.completed",
                kind=RunEventKind.WAKEUP,
                operation_id=operation.operation_id,
                iteration=1,
                task_id=operation.tasks[0].task_id,
                session_id=operation.sessions[0].session_id,
                dedupe_key=dedupe_key,
                payload={"run_id": run_id},
            )
        )

    resumed = await service.resume(
        operation.operation_id,
        options=RunOptions(
            run_mode=RunMode.RESUMABLE,
            background_runtime_mode=BackgroundRuntimeMode.RESUMABLE_WAKEUP,
        ),
    )

    operation = await store.load_operation(resumed.operation_id)
    assert resumed.status is OperationStatus.COMPLETED
    assert operation is not None
    assert operation.iterations[0].result is not None
    operation_briefs = [
        item for item in operation.agent_turn_briefs if item.session_id == "session-1"
    ]
    trace_briefs = [
        item for item in trace_store.bundle.agent_turn_briefs if item.session_id == "session-1"
    ]
    assert len(operation_briefs) == 1
    assert len(trace_briefs) == 1


@pytest.mark.anyio
async def test_cancelled_background_run_produces_cancelled_session_state() -> None:
    store = MemoryStore()
    trace_store = MemoryTraceStore()
    inbox = MemoryWakeupInbox()
    supervisor = FakeSupervisor()
    service = make_service(
        brain=StartWaitStopBrain(),
        store=store,
        trace_store=trace_store,
        event_sink=MemoryEventSink(),
        agent_runtime_bindings=build_test_runtime_bindings({"claude_acp": FakeAgent()}),
        wakeup_inbox=inbox,
        supervisor=supervisor,
    )

    first = await service.run(
        OperationGoal(objective="cancel background task"),
        **run_settings(max_iterations=5, allowed_agents=["claude_acp"]),
        options=RunOptions(
            run_mode=RunMode.RESUMABLE,
            background_runtime_mode=BackgroundRuntimeMode.RESUMABLE_WAKEUP,
        ),
    )
    operation = await store.load_operation(first.operation_id)
    assert operation is not None
    run_id = operation.background_runs[0].run_id

    cancel_outcome = await service.cancel(operation.operation_id, run_id=run_id)
    assert cancel_outcome.summary == "Cancellation requested."

    resumed = await service.resume(
        operation.operation_id,
        options=RunOptions(
            run_mode=RunMode.RESUMABLE,
            background_runtime_mode=BackgroundRuntimeMode.RESUMABLE_WAKEUP,
        ),
    )
    operation = await store.load_operation(resumed.operation_id)
    assert operation is not None
    assert operation.sessions[0].status.value == "cancelled"
    assert run_id in {run.run_id for run in operation.background_runs}
    assert any(brief.status == "cancelled" for brief in trace_store.bundle.agent_turn_briefs)
