from __future__ import annotations

from datetime import UTC, datetime, timedelta

import anyio
import pytest

from agent_operator.domain import (
    AgentResult,
    AttentionStatus,
    BackgroundRuntimeMode,
    BrainActionType,
    BrainDecision,
    CommandTargetScope,
    Evaluation,
    FocusKind,
    OperationCommand,
    OperationCommandType,
    OperationGoal,
    OperationState,
    OperationStatus,
    OperatorMessage,
    ProgressSummary,
    RunMode,
    RunOptions,
)
from agent_operator.testing.operator_service_support import (
    AnswerThenStopBrain,
    DescriptorCapturingBrain,
    FakeAgent,
    FakeSupervisor,
    MemoryCommandInbox,
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


class WaitForAgentThenStopBrain:
    """Brain that issues WAIT_FOR_AGENT and stops when result is ready.

    evaluate_result returns should_continue=False if the latest iteration has no
    result — modelling the real LLM which sees result_status=null and concludes
    nothing happened.  The drive loop must NOT call evaluate_result after a
    WAIT_FOR_AGENT iteration whose result slot is still empty.
    """

    def __init__(self) -> None:
        self.calls = 0
        self.eval_calls = 0

    async def decide_next_action(self, state) -> BrainDecision:
        self.calls += 1
        if self.calls == 1:
            return BrainDecision(
                action_type=BrainActionType.START_AGENT,
                target_agent="claude_acp",
                instruction="start background work",
                rationale="Kick off the long-running task.",
            )
        if self.calls == 2:
            session_id = state.sessions[0].session_id
            return BrainDecision(
                action_type=BrainActionType.WAIT_FOR_AGENT,
                target_agent="claude_acp",
                session_id=session_id,
                rationale="Block on the session result.",
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
            rationale="Result is in, task done.",
        )

    async def evaluate_result(self, state) -> Evaluation:
        self.eval_calls += 1
        latest = state.iterations[-1].result if state.iterations else None
        if latest is None:
            # Real LLM behaviour: "I see no result, nothing to evaluate → stop"
            return Evaluation(
                goal_satisfied=False,
                should_continue=False,
                summary="No result available yet — stopping.",
            )
        return Evaluation(goal_satisfied=False, should_continue=True, summary="keep going")

    async def summarize_progress(self, state) -> ProgressSummary:
        return ProgressSummary(summary="summary")

    async def normalize_artifact(self, goal, result) -> AgentResult:
        return result


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
            active_session = state.active_session_record
            return BrainDecision(
                action_type=BrainActionType.CONTINUE_AGENT,
                target_agent="claude_acp",
                session_id=(active_session.session_id if active_session is not None else None),
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


class CapturingStartThenStopBrain:
    def __init__(self) -> None:
        self.calls = 0
        self.seen_messages: list[list[str]] = []

    async def decide_next_action(self, state) -> BrainDecision:
        self.calls += 1
        self.seen_messages.append([message.text for message in state.operator_messages])
        if self.calls == 1:
            return BrainDecision(
                action_type=BrainActionType.START_AGENT,
                target_agent="claude_acp",
                instruction="run one turn",
                rationale="Need one execution cycle before stopping.",
            )
        return BrainDecision(
            action_type=BrainActionType.STOP,
            rationale="Captured enough planning cycles.",
        )

    async def evaluate_result(self, state) -> Evaluation:
        return Evaluation(goal_satisfied=False, should_continue=True, summary="continue")

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


@pytest.mark.anyio
async def test_operator_message_window_drops_message_before_next_cycle() -> None:
    brain = CapturingStartThenStopBrain()
    store = MemoryStore()
    event_sink = MemoryEventSink()
    service = make_service(
        brain=brain,
        store=store,
        trace_store=MemoryTraceStore(),
        event_sink=event_sink,
        agent_runtime_bindings=build_test_runtime_bindings({"claude_acp": FakeAgent()}),
    )
    operation = OperationState(
        operation_id="op-message-window-1",
        goal=OperationGoal(objective="Do the task"),
        operator_messages=[OperatorMessage(text="Use the smaller safe slice.")],
        **state_settings(allowed_agents=["claude_acp"], operator_message_window=1),
    )
    await store.save_operation(operation)

    outcome = await service.resume(
        operation.operation_id,
        options=RunOptions(run_mode=RunMode.ATTACHED, max_cycles=3),
    )
    updated = await store.load_operation(operation.operation_id)

    assert outcome.status is OperationStatus.COMPLETED
    assert brain.seen_messages == [["Use the smaller safe slice."], []]
    assert updated is not None
    assert updated.operator_messages[0].dropped_from_context is True
    assert updated.operator_messages[0].planning_cycles_active == 1
    drop_events = [
        event
        for event in event_sink.events
        if event.event_type == "operator_message.dropped_from_context"
    ]
    assert len(drop_events) == 1
    assert drop_events[0].payload["text_preview"] == "Use the smaller safe slice."
    assert drop_events[0].payload["operator_message_window"] == 1


@pytest.mark.anyio
async def test_operator_message_window_zero_keeps_message_for_first_cycle_only() -> None:
    brain = CapturingStartThenStopBrain()
    store = MemoryStore()
    service = make_service(
        brain=brain,
        store=store,
        trace_store=MemoryTraceStore(),
        event_sink=MemoryEventSink(),
        agent_runtime_bindings=build_test_runtime_bindings({"claude_acp": FakeAgent()}),
    )
    operation = OperationState(
        operation_id="op-message-window-0",
        goal=OperationGoal(objective="Do the task"),
        operator_messages=[OperatorMessage(text="Only use this once.")],
        **state_settings(allowed_agents=["claude_acp"], operator_message_window=0),
    )
    await store.save_operation(operation)

    outcome = await service.resume(
        operation.operation_id,
        options=RunOptions(run_mode=RunMode.ATTACHED, max_cycles=3),
    )
    updated = await store.load_operation(operation.operation_id)

    assert outcome.status is OperationStatus.COMPLETED
    assert brain.seen_messages == [["Only use this once."], []]
    assert updated is not None
    assert updated.operator_messages[0].dropped_from_context is True
    assert updated.operator_messages[0].planning_cycles_active == 1


@pytest.mark.anyio
async def test_attached_mode_inline_waits_on_blocking_attention_until_answered() -> None:
    """Attached drive loop stays alive on NEEDS_HUMAN+ATTENTION_REQUEST and continues once answered.
    """
    store = MemoryStore()
    event_sink = MemoryEventSink()
    inbox = MemoryCommandInbox()
    brain = AnswerThenStopBrain()
    service = make_service(
        brain=brain,
        store=store,
        trace_store=MemoryTraceStore(),
        event_sink=event_sink,
        agent_runtime_bindings=build_test_runtime_bindings({"claude_acp": FakeAgent()}),
        command_inbox=inbox,
    )

    outcome_holder: list[object] = []

    async def run_service() -> None:
        outcome = await service.run(
            OperationGoal(objective="need clarification then continue"),
            **run_settings(max_iterations=5, allowed_agents=["claude_acp"]),
        )
        outcome_holder.append(outcome)

    async def answer_when_blocked() -> None:
        # Poll store.operations directly (shared dict) until an attention request appears.
        while True:
            for op_state in list(store.operations.values()):
                if op_state.attention_requests:
                    attention = op_state.attention_requests[0]
                    command = OperationCommand(
                        operation_id=op_state.operation_id,
                        command_type=OperationCommandType.ANSWER_ATTENTION_REQUEST,
                        target_scope=CommandTargetScope.ATTENTION_REQUEST,
                        target_id=attention.attention_id,
                        payload={"text": "Use staging first."},
                    )
                    await inbox.enqueue(command)
                    return
            await anyio.sleep(0.05)

    async with anyio.create_task_group() as tg:
        tg.start_soon(run_service)
        tg.start_soon(answer_when_blocked)

    assert len(outcome_holder) == 1
    outcome = outcome_holder[0]
    assert outcome.status is OperationStatus.COMPLETED  # type: ignore[union-attr]

    operation = await store.load_operation(outcome.operation_id)  # type: ignore[union-attr]
    assert operation is not None
    assert operation.attention_requests[0].status is AttentionStatus.RESOLVED
    assert operation.attention_requests[0].answer_text == "Use staging first."
    assert (
        operation.current_focus is None
        or operation.current_focus.kind is not FocusKind.ATTENTION_REQUEST
    )


@pytest.mark.anyio
async def test_evaluate_result_is_not_called_after_wait_for_agent_with_no_result_yet() -> None:
    """evaluate_result must be skipped when the current iteration has no result yet.

    When evaluate_result IS called with result_status=null (the iteration hasn't
    been folded yet), a real LLM brain will likely return should_continue=False — causing the
    operation to exit as needs_human even though nothing went wrong.

    The fix: skip evaluate_result when iteration.decision.action_type is WAIT_FOR_AGENT.
    """
    store = MemoryStore()
    brain = WaitForAgentThenStopBrain()
    supervisor = FakeSupervisor(auto_complete_on_poll=True)
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
        OperationGoal(objective="background task"),
        **run_settings(max_iterations=6, allowed_agents=["claude_acp"]),
    )

    # The operation should complete normally, NOT exit as needs_human.
    assert outcome.status is OperationStatus.COMPLETED, (
        f"Expected COMPLETED but got {outcome.status}. "
        "evaluate_result was likely called after WAIT_FOR_AGENT with no result, "
        "causing premature needs_human exit."
    )
    # evaluate_result should never have seen a null-result iteration.
    # If it did AND returned should_continue=False, the outcome would be needs_human above.
    # But we also assert it wasn't called spuriously on the empty WAIT_FOR_AGENT iteration.
    operation = await store.load_operation(outcome.operation_id)
    assert operation is not None
    wait_for_agent_iterations = [
        it for it in operation.iterations
        if it.decision is not None and it.decision.action_type is BrainActionType.WAIT_FOR_AGENT
    ]
    assert len(wait_for_agent_iterations) == 1
    # The key invariant: evaluate_result was never called with result=None.
    # If it had been, the brain returns should_continue=False → needs_human
    # (asserted COMPLETED above).
    # Also verify the brain advanced past call 2 (WAIT_FOR_AGENT) to call 3 (STOP).
    assert brain.calls == 3
