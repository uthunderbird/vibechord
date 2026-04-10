from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from agent_operator.domain import (
    AgentResult,
    BackgroundRuntimeMode,
    BrainActionType,
    BrainDecision,
    Evaluation,
    OperationGoal,
    OperationState,
    OperationStatus,
    ProgressSummary,
    RunMode,
    RunOptions,
)
from agent_operator.testing.operator_service_support import (
    DescriptorCapturingBrain,
    FakeAgent,
    FakeSupervisor,
    MemoryEventSink,
    MemoryStore,
    MemoryTraceStore,
    MemoryWakeupInbox,
    StartClaudeAcpThenStopBrain,
    make_service,
    run_settings,
    state_settings,
)
from agent_operator.testing.runtime_bindings import build_test_runtime_bindings


class StopImmediatelyBrain:
    async def decide_next_action(self, state) -> BrainDecision:
        return BrainDecision(
            action_type=BrainActionType.STOP,
            rationale="The operator has enough context to continue after replanning.",
        )

    async def evaluate_result(self, state) -> Evaluation:
        raise AssertionError("evaluate_result should not run for STOP")


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


class StartThenStopOnlyAfterResultBrain:
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
        latest = state.iterations[-1].result if state.iterations else None
        if latest is None:
            return BrainDecision(
                action_type=BrainActionType.FAIL,
                rationale="Brain re-entered before the background result was reconciled.",
            )
        return BrainDecision(
            action_type=BrainActionType.STOP,
            rationale="Terminal result is now available.",
        )

    async def evaluate_result(self, state) -> Evaluation:
        return Evaluation(goal_satisfied=False, should_continue=True, summary="continue")

    async def summarize_progress(self, state) -> ProgressSummary:
        return ProgressSummary(summary="summary")

    async def normalize_artifact(self, goal, result) -> AgentResult:
        return result


class StartThenContinueBackgroundTurnBrain:
    def __init__(self) -> None:
        self.calls = 0

    async def decide_next_action(self, state) -> BrainDecision:
        self.calls += 1
        if self.calls == 1:
            return BrainDecision(
                action_type=BrainActionType.START_AGENT,
                target_agent="claude_acp",
                instruction="run background turn one",
                rationale="Start the first attached-live background turn.",
            )
        if self.calls == 2:
            return BrainDecision(
                action_type=BrainActionType.CONTINUE_AGENT,
                target_agent="claude_acp",
                session_id=(
                    state.active_session.session_id if state.active_session is not None else None
                ),
                instruction="run background turn two",
                rationale="Continue automatically into the next attached-live turn.",
            )
        return BrainDecision(
            action_type=BrainActionType.STOP,
            rationale="Both attached-live background turns completed without manual resume.",
        )

    async def evaluate_result(self, state) -> Evaluation:
        return Evaluation(
            goal_satisfied=False,
            should_continue=True,
            summary="continue",
        )

    async def summarize_progress(self, state) -> ProgressSummary:
        return ProgressSummary(summary="summary")

    async def normalize_artifact(self, goal, result) -> AgentResult:
        return result


@pytest.mark.anyio
async def test_service_refreshes_available_agent_descriptors_before_decision() -> None:
    brain = DescriptorCapturingBrain()
    service = make_service(
        brain=brain,
        store=MemoryStore(),
        trace_store=MemoryTraceStore(),
        event_sink=MemoryEventSink(),
        agent_runtime_bindings=build_test_runtime_bindings({"claude_acp": FakeAgent()}),
    )

    outcome = await service.run(
        OperationGoal(objective="do the task"),
        **run_settings(max_iterations=4, allowed_agents=["claude_acp"]),
    )

    assert outcome.status is OperationStatus.COMPLETED
    assert brain.descriptors is not None
    assert brain.descriptors[0]["key"] == "claude_acp"
    capability_names = {item["name"] for item in brain.descriptors[0]["capabilities"]}
    assert "read_files" in capability_names
    assert "write_files" in capability_names
    assert "edit_files" in capability_names
    assert "grep_search" in capability_names
    assert "glob_search" in capability_names
    assert "run_shell_commands" in capability_names


@pytest.mark.anyio
async def test_attached_run_mode_live_reconciles_background_turns() -> None:
    supervisor = FakeSupervisor(auto_complete_on_poll=True)
    service = make_service(
        brain=StartClaudeAcpThenStopBrain(),
        store=MemoryStore(),
        trace_store=MemoryTraceStore(),
        event_sink=MemoryEventSink(),
        agent_runtime_bindings=build_test_runtime_bindings(
            {"claude_acp": FakeAgent(key="claude_acp")}
        ),
        wakeup_inbox=MemoryWakeupInbox(),
        supervisor=supervisor,
    )

    outcome = await service.run(
        OperationGoal(objective="do the task"),
        **run_settings(max_iterations=4, allowed_agents=["claude_acp"]),
    )

    assert outcome.status is OperationStatus.COMPLETED
    assert len(supervisor.requests) == 1
    assert supervisor.wakeup_deliveries == ["enqueue"]


@pytest.mark.anyio
async def test_resumable_run_mode_uses_enqueue_delivery_for_background_turns() -> None:
    supervisor = FakeSupervisor()
    service = make_service(
        brain=StartClaudeAcpThenStopBrain(),
        store=MemoryStore(),
        trace_store=MemoryTraceStore(),
        event_sink=MemoryEventSink(),
        agent_runtime_bindings=build_test_runtime_bindings(
            {"claude_acp": FakeAgent(key="claude_acp")}
        ),
        wakeup_inbox=MemoryWakeupInbox(),
        supervisor=supervisor,
    )

    outcome = await service.run(
        OperationGoal(objective="do the task"),
        **run_settings(max_iterations=4, allowed_agents=["claude_acp"]),
        options=RunOptions(
            run_mode=RunMode.RESUMABLE,
            background_runtime_mode=BackgroundRuntimeMode.RESUMABLE_WAKEUP,
        ),
    )

    assert outcome.status is OperationStatus.RUNNING
    assert supervisor.wakeup_deliveries == ["enqueue"]


@pytest.mark.anyio
async def test_wait_for_agent_is_supported_with_background_runtime() -> None:
    store = MemoryStore()
    inbox = MemoryWakeupInbox()
    supervisor = FakeSupervisor()
    service = make_service(
        brain=StartWaitStopBrain(),
        store=store,
        trace_store=MemoryTraceStore(),
        event_sink=MemoryEventSink(),
        agent_runtime_bindings=build_test_runtime_bindings({"claude_acp": FakeAgent()}),
        wakeup_inbox=inbox,
        supervisor=supervisor,
    )

    first = await service.run(
        OperationGoal(objective="waitable task"),
        **run_settings(max_iterations=5, allowed_agents=["claude_acp"]),
        options=RunOptions(
            run_mode=RunMode.RESUMABLE,
            background_runtime_mode=BackgroundRuntimeMode.RESUMABLE_WAKEUP,
        ),
    )
    second = await service.resume(
        first.operation_id,
        options=RunOptions(
            run_mode=RunMode.RESUMABLE,
            background_runtime_mode=BackgroundRuntimeMode.RESUMABLE_WAKEUP,
        ),
    )
    operation = await store.load_operation(second.operation_id)
    assert operation is not None
    assert second.status is OperationStatus.RUNNING
    assert operation.current_focus is not None
    assert operation.current_focus.mode.value == "blocking"


@pytest.mark.anyio
async def test_wait_for_agent_is_supported_in_attached_mode_with_wakeup_runtime() -> None:
    store = MemoryStore()
    supervisor = FakeSupervisor(auto_complete_on_poll=True)
    agent = FakeAgent()
    service = make_service(
        brain=StartWaitStopBrain(),
        store=store,
        trace_store=MemoryTraceStore(),
        event_sink=MemoryEventSink(),
        agent_runtime_bindings=build_test_runtime_bindings({"claude_acp": agent}),
        wakeup_inbox=MemoryWakeupInbox(),
        supervisor=supervisor,
    )

    outcome = await service.run(
        OperationGoal(objective="waitable attached task"),
        **run_settings(max_iterations=5, allowed_agents=["claude_acp"]),
    )

    operation = await store.load_operation(outcome.operation_id)
    assert operation is not None
    assert outcome.status is OperationStatus.COMPLETED
    assert supervisor.wakeup_deliveries == ["enqueue"]
    assert operation.iterations[1].result is not None
    assert "WAIT_FOR_AGENT ignored because the target session already has a collected" in (
        operation.iterations[1].notes[0]
    )


@pytest.mark.anyio
async def test_attached_background_wait_does_not_spin_brain_iterations() -> None:
    store = MemoryStore()
    supervisor = FakeSupervisor(complete_after_polls=3)
    brain = StartThenStopOnlyAfterResultBrain()
    service = make_service(
        brain=brain,
        store=store,
        trace_store=MemoryTraceStore(),
        event_sink=MemoryEventSink(),
        agent_runtime_bindings=build_test_runtime_bindings({"claude_acp": FakeAgent()}),
        wakeup_inbox=MemoryWakeupInbox(),
        supervisor=supervisor,
    )

    outcome = await service.run(
        OperationGoal(objective="waitable attached task"),
        **run_settings(max_iterations=5, allowed_agents=["claude_acp"]),
    )

    operation = await store.load_operation(outcome.operation_id)
    assert operation is not None
    assert outcome.status is OperationStatus.COMPLETED
    assert len(operation.iterations) == 2
    assert brain.calls == 2
    assert supervisor.poll_counts["run-1"] >= 3
    assert operation.iterations[0].result is not None


@pytest.mark.anyio
async def test_attached_live_progresses_across_repeated_background_turns_without_resume() -> None:
    store = MemoryStore()
    inbox = MemoryWakeupInbox()
    supervisor = FakeSupervisor(auto_complete_on_poll=True)
    brain = StartThenContinueBackgroundTurnBrain()
    service = make_service(
        brain=brain,
        store=store,
        trace_store=MemoryTraceStore(),
        event_sink=MemoryEventSink(),
        agent_runtime_bindings=build_test_runtime_bindings({"claude_acp": FakeAgent()}),
        wakeup_inbox=inbox,
        supervisor=supervisor,
    )

    outcome = await service.run(
        OperationGoal(objective="advance across repeated attached-live background turns"),
        **run_settings(max_iterations=6, allowed_agents=["claude_acp"]),
    )

    operation = await store.load_operation(outcome.operation_id)
    assert operation is not None
    assert outcome.status is OperationStatus.COMPLETED
    assert brain.calls == 3
    assert len(operation.iterations) == 3
    assert operation.iterations[0].result is not None
    assert operation.iterations[1].result is not None
    assert operation.iterations[2].result is None
    assert len(supervisor.requests) == 2
    assert supervisor.wakeup_deliveries == ["enqueue", "enqueue"]
    assert supervisor.existing_sessions[0] is None
    assert supervisor.existing_sessions[1] is not None
    assert supervisor.existing_sessions[1].session_id == operation.iterations[0].session.session_id
    assert operation.pending_wakeups == []
    assert await inbox.list_pending(outcome.operation_id) == []


@pytest.mark.anyio
async def test_timeout_seconds_fires_failed_when_elapsed() -> None:
    store = MemoryStore()
    event_sink = MemoryEventSink()
    service = make_service(
        brain=StopImmediatelyBrain(),
        store=store,
        trace_store=MemoryTraceStore(),
        event_sink=event_sink,
        agent_runtime_bindings=build_test_runtime_bindings({"claude_acp": FakeAgent()}),
    )
    state = OperationState(
        goal=OperationGoal(objective="do something"),
        **state_settings(timeout_seconds=1, allowed_agents=["claude_acp"]),
        run_started_at=datetime.now(UTC) - timedelta(seconds=3600),
    )
    await store.save_operation(state)

    outcome = await service.resume(state.operation_id)

    assert outcome.status is OperationStatus.FAILED
    assert "Time limit" in (outcome.summary or "")
    status_events = [
        e
        for e in event_sink.events
        if e.event_type == "operation.status.changed"
        and e.payload.get("new_status") == "failed"
    ]
    assert status_events


@pytest.mark.anyio
async def test_timeout_seconds_none_does_not_fire() -> None:
    service = make_service(
        brain=StopImmediatelyBrain(),
        store=MemoryStore(),
        trace_store=MemoryTraceStore(),
        event_sink=MemoryEventSink(),
        agent_runtime_bindings=build_test_runtime_bindings({"claude_acp": FakeAgent()}),
    )
    outcome = await service.run(
        OperationGoal(objective="do something"),
        **run_settings(allowed_agents=["claude_acp"]),
    )
    assert outcome.status is OperationStatus.COMPLETED


@pytest.mark.anyio
async def test_run_started_at_is_set_on_first_run_and_preserved_on_resume() -> None:
    store = MemoryStore()
    service = make_service(
        brain=StopImmediatelyBrain(),
        store=store,
        trace_store=MemoryTraceStore(),
        event_sink=MemoryEventSink(),
        agent_runtime_bindings=build_test_runtime_bindings({"claude_acp": FakeAgent()}),
    )
    outcome = await service.run(
        OperationGoal(objective="do something"),
        **run_settings(allowed_agents=["claude_acp"]),
    )
    operation = await store.load_operation(outcome.operation_id)
    assert operation is not None
    assert operation.run_started_at is not None
    original_started_at = operation.run_started_at

    await service.resume(outcome.operation_id)
    operation = await store.load_operation(outcome.operation_id)
    assert operation is not None
    assert operation.run_started_at == original_started_at
