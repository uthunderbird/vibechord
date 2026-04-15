from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from agent_operator.application.attached_turns import AttachedTurnService
from agent_operator.domain import (
    AgentProgress,
    AgentProgressState,
    AgentResult,
    AgentResultStatus,
    AgentSessionHandle,
    BackgroundRuntimeMode,
    BrainActionType,
    BrainDecision,
    Evaluation,
    ExecutionProfileOverride,
    IterationState,
    OperationGoal,
    OperationPolicy,
    OperationState,
    OperationStatus,
    ProgressSummary,
    RunMode,
    RunOptions,
    SessionRecord,
    SessionRecordStatus,
    SessionStatus,
)
from agent_operator.testing.operator_service_support import (
    EventfulAttachedAgent,
    FakeAgent,
    FakeSupervisor,
    HangingAttachedAgent,
    HangingClaudeAcpAgentWithLog,
    MemoryEventSink,
    MemoryStore,
    MemoryTraceStore,
    MemoryWakeupInbox,
    RecoverableDisconnectAgent,
    StartThenStopBrain,
    make_service,
    run_settings,
)
from agent_operator.testing.runtime_bindings import build_test_runtime_bindings


async def _async_noop(*args, **kwargs) -> None:
    del args, kwargs


async def _async_drain_noop(*args, **kwargs) -> None:
    del args, kwargs


async def _async_signal_noop(*args, **kwargs) -> None:
    del args, kwargs


async def _unexpected_timeout_reconcile(*args, **kwargs) -> AgentResult:
    del args, kwargs
    raise AssertionError("timeout reconciliation should not run in this test")


class NamedSessionBrain(StartThenStopBrain):
    async def decide_next_action(self, state) -> BrainDecision:
        self.calls += 1
        if self.calls == 1:
            return BrainDecision(
                action_type=BrainActionType.START_AGENT,
                target_agent="claude_acp",
                session_name="alignment note",
                instruction="do the task",
                rationale="Use Claude for the task.",
            )
        return BrainDecision(action_type=BrainActionType.STOP, rationale="The task is complete.")


class NamedMixedSessionBrain(StartThenStopBrain):
    async def decide_next_action(self, state) -> BrainDecision:
        self.calls += 1
        if self.calls == 1:
            return BrainDecision(
                action_type=BrainActionType.START_AGENT,
                target_agent="codex_acp",
                session_name="repo audit",
                instruction="inspect repo",
                rationale="Use Codex for the task.",
            )
        return BrainDecision(action_type=BrainActionType.STOP, rationale="The task is complete.")


class OneShotBrain(StartThenStopBrain):
    async def decide_next_action(self, state) -> BrainDecision:
        self.calls += 1
        if self.calls == 1:
            return BrainDecision(
                action_type=BrainActionType.START_AGENT,
                target_agent="claude_acp",
                one_shot=True,
                instruction="do the task once",
                rationale="Use a disposable one-shot session.",
            )
        return BrainDecision(
            action_type=BrainActionType.STOP,
            rationale="The one-shot run already finished.",
        )


class NamedOneShotBrain(StartThenStopBrain):
    async def decide_next_action(self, state) -> BrainDecision:
        self.calls += 1
        if self.calls == 1:
            return BrainDecision(
                action_type=BrainActionType.START_AGENT,
                target_agent="claude_acp",
                session_name="swarm phase 1",
                one_shot=True,
                instruction="/swarm do phase 1",
                rationale="Use a one-shot swarm run for this phase.",
            )
        return BrainDecision(action_type=BrainActionType.STOP, rationale="Done.")


class StartThenContinueThenStopBrain:
    def __init__(self) -> None:
        self.calls = 0

    async def decide_next_action(self, state) -> BrainDecision:
        self.calls += 1
        if self.calls == 1:
            return BrainDecision(
                action_type=BrainActionType.START_AGENT,
                target_agent="claude_acp",
                instruction="phase 1",
                rationale="Start phase 1.",
            )
        if self.calls == 2:
            return BrainDecision(
                action_type=BrainActionType.CONTINUE_AGENT,
                target_agent="claude_acp",
                instruction="phase 2",
                rationale="Continue with phase 2.",
            )
        return BrainDecision(action_type=BrainActionType.STOP, rationale="Done.")

    async def evaluate_result(self, state) -> Evaluation:
        should_continue = len(state.iterations) < 2
        return Evaluation(
            goal_satisfied=not should_continue,
            should_continue=should_continue,
            summary="ok",
        )

    async def summarize_progress(self, state) -> ProgressSummary:
        return ProgressSummary(summary="summary")

    async def normalize_artifact(self, goal, result) -> AgentResult:
        return result


class StartThenStartAgainThenStopBrain:
    def __init__(self, *, target_agent: str = "codex_acp") -> None:
        self.calls = 0
        self.target_agent = target_agent

    async def decide_next_action(self, state) -> BrainDecision:
        self.calls += 1
        if self.calls <= 2:
            return BrainDecision(
                action_type=BrainActionType.START_AGENT,
                target_agent=self.target_agent,
                instruction="keep going",
                rationale="Reuse the idle session when policy allows it.",
            )
        return BrainDecision(action_type=BrainActionType.STOP, rationale="Done.")

    async def evaluate_result(self, state) -> Evaluation:
        should_continue = len(state.iterations) < 2
        return Evaluation(
            goal_satisfied=not should_continue,
            should_continue=should_continue,
            summary="ok",
        )

    async def summarize_progress(self, state) -> ProgressSummary:
        return ProgressSummary(summary="summary")

    async def normalize_artifact(self, goal, result) -> AgentResult:
        return result


class ContinueAttachedSessionBrain:
    async def decide_next_action(self, state) -> BrainDecision:
        return BrainDecision(
            action_type=BrainActionType.CONTINUE_AGENT,
            target_agent="codex_acp",
            instruction="continue the attached session",
            rationale="Use the already attached external session.",
        )

    async def evaluate_result(self, state) -> Evaluation:
        return Evaluation(
            goal_satisfied=True,
            should_continue=False,
            summary="Attached session completed the task.",
        )

    async def summarize_progress(self, state) -> ProgressSummary:
        return ProgressSummary(summary="summary")

    async def normalize_artifact(self, goal, result) -> AgentResult:
        return result


class RestartAfterFailedAttachedSessionBrain:
    def __init__(self) -> None:
        self.calls = 0

    async def decide_next_action(self, state) -> BrainDecision:
        self.calls += 1
        if self.calls == 1:
            return BrainDecision(
                action_type=BrainActionType.START_AGENT,
                target_agent="codex_acp",
                instruction="recover and continue",
                rationale="Start a replacement session after the attached one failed.",
                session_name="femtobot",
            )
        return BrainDecision(
            action_type=BrainActionType.STOP,
            rationale="Stop after verifying the replacement session was started.",
        )

    async def evaluate_result(self, state) -> Evaluation:
        return Evaluation(
            goal_satisfied=False,
            should_continue=True,
            summary="Need one operator step to verify the started request.",
        )

    async def summarize_progress(self, state) -> ProgressSummary:
        return ProgressSummary(summary="summary")

    async def normalize_artifact(self, goal, result) -> AgentResult:
        return result


class _TerminalPlaceholderRegistry:
    def __init__(self, *, progress: AgentProgress, result: AgentResult) -> None:
        self._progress = progress
        self._result = result

    async def poll(self, handle: AgentSessionHandle) -> AgentProgress:
        return self._progress

    async def collect(self, handle: AgentSessionHandle) -> AgentResult:
        return self._result


@pytest.mark.anyio
async def test_operator_service_stores_short_session_name_for_single_agent_runs() -> None:
    store = MemoryStore()
    service = make_service(
        brain=NamedSessionBrain(),
        store=store,
        trace_store=MemoryTraceStore(),
        event_sink=MemoryEventSink(),
        agent_runtime_bindings=build_test_runtime_bindings({"claude_acp": FakeAgent()}),
    )

    outcome = await service.run(
        OperationGoal(objective="fix the issue"),
        **run_settings(max_iterations=4, allowed_agents=["claude_acp"]),
    )

    operation = await store.load_operation(outcome.operation_id)
    assert operation is not None
    assert operation.iterations[0].session is not None
    assert operation.iterations[0].session.session_name == "alignment note"
    assert operation.iterations[0].session.display_name == "alignment note"
    assert operation.iterations[0].session.metadata["session_display_name"] == "alignment note"


@pytest.mark.anyio
async def test_operator_service_appends_agent_type_to_named_session_in_mixed_runs() -> None:
    store = MemoryStore()
    service = make_service(
        brain=NamedMixedSessionBrain(),
        store=store,
        trace_store=MemoryTraceStore(),
        event_sink=MemoryEventSink(),
        agent_runtime_bindings=build_test_runtime_bindings(
            {"claude_acp": FakeAgent(), "codex_acp": FakeAgent(key="codex_acp")}
        ),
    )

    outcome = await service.run(
        OperationGoal(objective="inspect repo"),
        **run_settings(max_iterations=4, allowed_agents=["claude_acp", "codex_acp"]),
    )

    operation = await store.load_operation(outcome.operation_id)
    assert operation is not None
    assert operation.iterations[0].session is not None
    assert operation.iterations[0].session.session_name == "repo audit"
    assert operation.iterations[0].session.display_name == "repo audit [codex_acp]"
    assert (
        operation.iterations[0].session.metadata["session_display_name"]
        == "repo audit [codex_acp]"
    )


@pytest.mark.anyio
async def test_operator_service_does_not_surface_active_session_record_after_one_shot_run() -> None:
    store = MemoryStore()
    agent = FakeAgent()
    service = make_service(
        brain=OneShotBrain(),
        store=store,
        trace_store=MemoryTraceStore(),
        event_sink=MemoryEventSink(),
        agent_runtime_bindings=build_test_runtime_bindings({"claude_acp": agent}),
    )

    outcome = await service.run(
        OperationGoal(objective="one-shot task"),
        **run_settings(max_iterations=4, allowed_agents=["claude_acp"]),
    )

    operation = await store.load_operation(outcome.operation_id)
    assert outcome.status is OperationStatus.COMPLETED
    assert operation is not None
    assert agent.started_requests[0].one_shot is True
    assert operation.iterations[0].session is not None
    assert operation.iterations[0].session.one_shot is True
    assert operation.iterations[0].session.session_name is None
    assert operation.active_session_record is None


@pytest.mark.anyio
async def test_operator_service_preserves_name_for_one_shot_session_when_provided() -> None:
    store = MemoryStore()
    agent = FakeAgent()
    service = make_service(
        brain=NamedOneShotBrain(),
        store=store,
        trace_store=MemoryTraceStore(),
        event_sink=MemoryEventSink(),
        agent_runtime_bindings=build_test_runtime_bindings({"claude_acp": agent}),
    )

    outcome = await service.run(
        OperationGoal(objective="run one-shot swarm phase"),
        **run_settings(max_iterations=4, allowed_agents=["claude_acp"]),
    )

    operation = await store.load_operation(outcome.operation_id)
    assert outcome.status is OperationStatus.COMPLETED
    assert operation is not None
    assert agent.started_requests[0].one_shot is True
    assert agent.started_requests[0].session_name == "swarm phase 1"
    assert operation.iterations[0].session is not None
    assert operation.iterations[0].session.one_shot is True
    assert operation.iterations[0].session.display_name == "swarm phase 1"


@pytest.mark.anyio
async def test_operator_service_restarts_non_follow_up_agent_for_continuation() -> None:
    agent = FakeAgent(supports_follow_up=False)
    service = make_service(
        brain=StartThenContinueThenStopBrain(),
        store=MemoryStore(),
        trace_store=MemoryTraceStore(),
        event_sink=MemoryEventSink(),
        agent_runtime_bindings=build_test_runtime_bindings({"claude_acp": agent}),
    )

    outcome = await service.run(
        OperationGoal(objective="complete two phases"),
        **run_settings(max_iterations=4, allowed_agents=["claude_acp"]),
    )

    assert outcome.status is OperationStatus.COMPLETED
    assert len(agent.started_requests) == 2
    assert agent.sent_messages == []
    assert "phase 2" in agent.started_requests[1].instruction
    assert "completed by fake agent" in agent.started_requests[1].instruction


@pytest.mark.anyio
async def test_operator_service_can_start_with_attached_session() -> None:
    store = MemoryStore()
    agent = FakeAgent(key="codex_acp", supports_follow_up=True)
    service = make_service(
        brain=ContinueAttachedSessionBrain(),
        store=store,
        trace_store=MemoryTraceStore(),
        event_sink=MemoryEventSink(),
        agent_runtime_bindings=build_test_runtime_bindings({"codex_acp": agent}),
    )

    outcome = await service.run(
        OperationGoal(objective="continue existing work"),
        **run_settings(max_iterations=3, allowed_agents=["codex_acp"]),
        attached_sessions=[
            AgentSessionHandle(
                adapter_key="codex_acp",
                session_id="attached-1",
                session_name="femtobot",
                metadata={"working_directory": "../femtobot"},
            )
        ],
    )

    operation = await store.load_operation(outcome.operation_id)
    assert outcome.status is OperationStatus.COMPLETED
    assert operation is not None
    assert operation.active_session_record is not None
    assert operation.active_session_record.session_id == "attached-1"
    assert operation.tasks[0].linked_session_id == "attached-1"
    assert agent.sent_messages == ["continue the attached session"]
    assert agent.started_requests == []


@pytest.mark.anyio
async def test_background_replacement_session_preserves_attached_working_directory() -> None:
    supervisor = FakeSupervisor()
    store = MemoryStore()
    service = make_service(
        brain=RestartAfterFailedAttachedSessionBrain(),
        store=store,
        trace_store=MemoryTraceStore(),
        event_sink=MemoryEventSink(),
        agent_runtime_bindings=build_test_runtime_bindings(
            {"codex_acp": FakeAgent(key="codex_acp", supports_follow_up=True)}
        ),
        wakeup_inbox=MemoryWakeupInbox(),
        supervisor=supervisor,
    )

    outcome = await service.run(
        OperationGoal(objective="continue existing work"),
        **run_settings(max_iterations=2, allowed_agents=["codex_acp"]),
        options=RunOptions(
            run_mode=RunMode.RESUMABLE,
            background_runtime_mode=BackgroundRuntimeMode.RESUMABLE_WAKEUP,
        ),
        attached_sessions=[
            AgentSessionHandle(
                adapter_key="codex_acp",
                session_id="attached-1",
                session_name="femtobot",
                metadata={"working_directory": "/Users/thunderbird/Projects/femtobot"},
            )
        ],
    )

    assert outcome.status is OperationStatus.RUNNING
    assert len(supervisor.requests) == 1
    assert supervisor.requests[0].working_directory == Path("/Users/thunderbird/Projects/femtobot")
    assert supervisor.existing_sessions == [None]


@pytest.mark.anyio
async def test_operation_goal_working_directory_fallback_reaches_agent_request() -> None:
    agent = FakeAgent()
    service = make_service(
        brain=StartThenStopBrain(),
        store=MemoryStore(),
        trace_store=MemoryTraceStore(),
        event_sink=MemoryEventSink(),
        agent_runtime_bindings=build_test_runtime_bindings({"claude_acp": agent}),
    )

    outcome = await service.run(
        OperationGoal(
            objective="do the task",
            metadata={"working_directory": "/Users/thunderbird/Projects/hct/trunk"},
        ),
        **run_settings(max_iterations=4, allowed_agents=["claude_acp"]),
    )

    assert outcome.status is OperationStatus.COMPLETED
    assert len(agent.started_requests) == 1
    assert agent.started_requests[0].working_directory == Path(
        "/Users/thunderbird/Projects/hct/trunk"
    )


@pytest.mark.anyio
async def test_attached_turn_timeout_recovers_and_replans() -> None:
    store = MemoryStore()
    trace_store = MemoryTraceStore()
    event_sink = MemoryEventSink()
    service = make_service(
        brain=StartThenStopBrain(),
        store=store,
        trace_store=trace_store,
        event_sink=event_sink,
        agent_runtime_bindings=build_test_runtime_bindings(
            {"claude_acp": HangingAttachedAgent()}
        ),
        attached_turn_timeout=timedelta(seconds=0),
    )

    outcome = await service.run(
        OperationGoal(objective="recover from attached-turn timeout"),
        **run_settings(max_iterations=2, allowed_agents=["claude_acp"]),
    )

    assert outcome.status is OperationStatus.COMPLETED
    assert outcome.final_result is not None
    assert "Latest partial theorem state" in outcome.final_result.output_text
    assert outcome.final_result.raw is not None
    assert outcome.final_result.raw["attached_turn_recovered"] is True
    operation = await store.load_operation(outcome.operation_id)
    assert operation is not None
    record = operation.sessions[0]
    assert record.recovery_count == 1
    assert record.last_recovered_at is not None
    assert trace_store.bundle.operation_brief is not None
    assert "timed out" in (trace_store.bundle.operation_brief.runtime_alert_brief or "")
    assert any(event.event_type == "attached_turn.recovered" for event in event_sink.events)


@pytest.mark.anyio
async def test_attached_turn_timeout_prefers_log_tail_recovery(tmp_path: Path) -> None:
    log_path = tmp_path / "claude-acp.jsonl"
    log_path.write_text(
        "\n".join(
            [
                (
                    '{"timestamp":"2026-03-31T10:00:00Z","type":"assistant",'
                    '"message":{"content":[{"type":"text","text":"Old completed text."}]}}'
                ),
                (
                    '{"timestamp":"2026-03-31T10:00:05Z","type":"tool_use",'
                    '"name":"Bash","input":{"command":"echo old"}}'
                ),
                (
                    '{"timestamp":"2026-03-31T10:01:00Z","type":"assistant","message":'
                    '{"content":[{"type":"text","text":"Latest theorem audit. '
                    'I will run the build now."}]}}'
                ),
                (
                    '{"timestamp":"2026-03-31T10:01:10Z","type":"tool_use",'
                    '"name":"Bash","input":{"command":"lake build Erdosreshala.P1"}}'
                ),
                (
                    '{"timestamp":"2026-03-31T10:01:20Z","type":"result","subtype":"success",'
                    '"result":"Build passed; theorem still has 2 sorry."}'
                ),
            ]
        ),
        encoding="utf-8",
    )

    service = make_service(
        brain=StartThenStopBrain(),
        store=MemoryStore(),
        trace_store=MemoryTraceStore(),
        event_sink=MemoryEventSink(),
        agent_runtime_bindings=build_test_runtime_bindings(
            {"claude_acp": HangingClaudeAcpAgentWithLog(log_path)}
        ),
        attached_turn_timeout=timedelta(seconds=0),
    )

    outcome = await service.run(
        OperationGoal(objective="recover from attached-turn timeout using ACP log tail"),
        **run_settings(max_iterations=2, allowed_agents=["claude_acp"]),
    )

    assert outcome.status is OperationStatus.COMPLETED
    assert outcome.final_result is not None
    assert "Latest theorem audit. I will run the build now." in outcome.final_result.output_text
    assert "lake build Erdosreshala.P1" in outcome.final_result.output_text
    assert "Build passed; theorem still has 2 sorry." in outcome.final_result.output_text
    assert (
        "Latest partial theorem state from the hanging turn."
        not in outcome.final_result.output_text
    )
    assert outcome.final_result.raw is not None
    assert outcome.final_result.raw["used_log_tail_recovery"] is True


@pytest.mark.anyio
async def test_collect_turn_does_not_persist_terminal_placeholder_waiting_reason() -> None:
    service = AttachedTurnService(attached_turn_timeout=timedelta(seconds=30))
    session = AgentSessionHandle(adapter_key="codex_acp", session_id="session-1")
    progress = AgentProgress(
        session_id=session.session_id,
        state=AgentProgressState.COMPLETED,
        message="Agent session completed.",
        updated_at=datetime.now(UTC),
    )
    result = AgentResult(
        session_id=session.session_id,
        status=AgentResultStatus.SUCCESS,
        output_text="done",
        completed_at=datetime.now(UTC),
    )
    registry = _TerminalPlaceholderRegistry(progress=progress, result=result)
    state = OperationState(
        goal=OperationGoal(objective="check attached waiting reason"),
        policy=OperationPolicy(),
        iterations=[IterationState(index=1)],
    )
    iteration = state.iterations[0]
    record = SessionRecord(
        handle=session,
        status=SessionRecordStatus.RUNNING,
        waiting_reason="Still working through the current slice.",
    )
    state.sessions.append(record)

    collected = await service.collect_turn(
        state=state,
        iteration=iteration,
        task=None,
        registry=registry,  # type: ignore[arg-type]
        session=session,
        ensure_session_record=lambda current_state, current_session: record,
        sync_traceability_artifacts=_async_noop,
        drain_commands=_async_drain_noop,
        reconcile_timeout=_unexpected_timeout_reconcile,
        dispatch_process_manager_signal=_async_signal_noop,
        scheduler_is_draining=False,
    )

    assert collected is result
    assert record.status is SessionRecordStatus.RUNNING
    assert record.waiting_reason == "Still working through the current slice."


@pytest.mark.anyio
async def test_attached_turn_timeout_uses_last_acp_event_activity() -> None:
    service = make_service(
        brain=StartThenStopBrain(),
        store=MemoryStore(),
        trace_store=MemoryTraceStore(),
        event_sink=MemoryEventSink(),
        agent_runtime_bindings=build_test_runtime_bindings({"claude_acp": EventfulAttachedAgent()}),
        attached_turn_timeout=timedelta(seconds=2),
    )

    outcome = await service.run(
        OperationGoal(objective="do not timeout while ACP events are still arriving"),
        **run_settings(max_iterations=2, allowed_agents=["claude_acp"]),
    )

    assert outcome.status is OperationStatus.COMPLETED
    assert outcome.final_result is not None
    assert outcome.final_result.output_text == "completed after fresh ACP activity"


@pytest.mark.anyio
async def test_resume_recovers_disconnected_codex_session_without_starting_new_one() -> None:
    store = MemoryStore()
    agent = RecoverableDisconnectAgent(
        key="codex_acp",
        error_code="codex_acp_disconnected",
    )
    service = make_service(
        brain=StartThenStartAgainThenStopBrain(target_agent="codex_acp"),
        store=store,
        trace_store=MemoryTraceStore(),
        event_sink=MemoryEventSink(),
        agent_runtime_bindings=build_test_runtime_bindings({"codex_acp": agent}),
    )

    first = await service.run(
        OperationGoal(objective="recover codex session after ACP disconnect"),
        **run_settings(max_iterations=4, allowed_agents=["codex_acp"]),
        options=RunOptions(run_mode=RunMode.ATTACHED, max_cycles=1),
    )
    operation = await store.load_operation(first.operation_id)

    assert first.status is OperationStatus.NEEDS_HUMAN
    assert first.final_result is not None
    assert first.final_result.status is AgentResultStatus.DISCONNECTED
    assert operation is not None
    assert len(operation.sessions) == 1
    assert operation.sessions[0].status is SessionStatus.WAITING
    assert operation.sessions[0].current_execution_id is None
    assert "Recovering agent connection after ACP disconnect." in (
        operation.sessions[0].waiting_reason or ""
    )

    resumed = await service.resume(
        first.operation_id,
        options=RunOptions(run_mode=RunMode.ATTACHED, max_cycles=2),
    )
    updated = await store.load_operation(first.operation_id)

    assert resumed.status is OperationStatus.COMPLETED
    assert resumed.final_result is not None
    assert resumed.final_result.status is AgentResultStatus.SUCCESS
    assert updated is not None
    assert len(updated.sessions) == 1
    assert agent.sent_messages == ["keep going"]
    assert len(agent.started_requests) == 1


@pytest.mark.anyio
async def test_start_agent_reuses_idle_session_when_profile_requests_reuse_if_idle() -> None:
    store = MemoryStore()
    agent = FakeAgent(key="codex_acp")
    service = make_service(
        brain=StartThenStartAgainThenStopBrain(target_agent="codex_acp"),
        store=store,
        trace_store=MemoryTraceStore(),
        event_sink=MemoryEventSink(),
        agent_runtime_bindings=build_test_runtime_bindings({"codex_acp": agent}),
    )

    outcome = await service.run(
        OperationGoal(
            objective="reuse the same codex session",
            metadata={
                "resolved_project_profile": {
                    "session_reuse_policy": "reuse_if_idle",
                }
            },
        ),
        **run_settings(max_iterations=4, allowed_agents=["codex_acp"]),
    )
    operation = await store.load_operation(outcome.operation_id)

    assert outcome.status is OperationStatus.COMPLETED
    assert operation is not None
    assert len(agent.started_requests) == 1
    assert agent.sent_messages == ["keep going"]
    assert len(operation.sessions) == 1


@pytest.mark.anyio
async def test_start_agent_does_not_reuse_idle_session_when_execution_profile_mismatches() -> None:
    store = MemoryStore()
    agent = FakeAgent(key="codex_acp")
    service = make_service(
        brain=StartThenStartAgainThenStopBrain(target_agent="codex_acp"),
        store=store,
        trace_store=MemoryTraceStore(),
        event_sink=MemoryEventSink(),
        agent_runtime_bindings=build_test_runtime_bindings({"codex_acp": agent}),
    )

    outcome = await service.run(
        OperationGoal(
            objective="do not reuse mismatched codex session",
            metadata={
                "resolved_project_profile": {
                    "session_reuse_policy": "reuse_if_idle",
                },
                "effective_adapter_settings": {
                    "codex_acp": {"model": "gpt-5.4", "reasoning_effort": "low"}
                },
            },
        ),
        **run_settings(max_iterations=4, allowed_agents=["codex_acp"]),
        options=RunOptions(run_mode=RunMode.ATTACHED, max_cycles=1),
    )
    operation = await store.load_operation(outcome.operation_id)
    assert operation is not None
    operation.execution_profile_overrides["codex_acp"] = ExecutionProfileOverride(
        adapter_key="codex_acp",
        model="gpt-5.4-mini",
        reasoning_effort="medium",
    )
    await store.save_operation(operation)

    resumed = await service.resume(
        outcome.operation_id,
        options=RunOptions(run_mode=RunMode.ATTACHED, max_cycles=4),
    )
    updated = await store.load_operation(outcome.operation_id)

    assert outcome.status is OperationStatus.RUNNING
    assert resumed.status is OperationStatus.COMPLETED
    assert updated is not None
    assert len(agent.started_requests) == 2


@pytest.mark.anyio
async def test_background_request_metadata_includes_project_profile_path() -> None:
    store = MemoryStore()
    supervisor = FakeSupervisor()
    service = make_service(
        brain=StartThenStartAgainThenStopBrain(target_agent="codex_acp"),
        store=store,
        trace_store=MemoryTraceStore(),
        event_sink=MemoryEventSink(),
        agent_runtime_bindings=build_test_runtime_bindings(
            {"codex_acp": FakeAgent(key="codex_acp")}
        ),
        supervisor=supervisor,
    )

    outcome = await service.run(
        OperationGoal(
            objective="close all BR cards",
            metadata={
                "project_profile_name": "femtobot",
                "project_profile_path": "/tmp/femtobot/operator-profile.yaml",
                "policy_scope": "profile:femtobot",
            },
        ),
        **run_settings(max_iterations=2, allowed_agents=["codex_acp"]),
        options=RunOptions(
            run_mode=RunMode.RESUMABLE,
            max_cycles=1,
            background_runtime_mode=BackgroundRuntimeMode.RESUMABLE_WAKEUP,
        ),
    )

    assert outcome.status is OperationStatus.RUNNING
    assert supervisor.requests
    assert supervisor.requests[0].metadata["project_profile_name"] == "femtobot"
    assert (
        supervisor.requests[0].metadata["project_profile_path"]
        == "/tmp/femtobot/operator-profile.yaml"
    )
