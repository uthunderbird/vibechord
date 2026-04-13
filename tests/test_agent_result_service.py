from __future__ import annotations

from datetime import UTC, datetime

import pytest

from agent_operator.domain import (
    AgentError,
    AgentResult,
    AgentResultStatus,
    AttentionType,
    BackgroundRuntimeMode,
    BrainActionType,
    BrainDecision,
    Evaluation,
    FocusKind,
    OperationGoal,
    OperationStatus,
    ProgressSummary,
    RunEvent,
    RunEventKind,
    RunMode,
    RunOptions,
    SessionStatus,
)
from agent_operator.testing.operator_service_support import (
    EscalatingAgent,
    FakeAgent,
    FakeSupervisor,
    MemoryDistillingStartThenStopBrain,
    MemoryEventSink,
    MemoryStore,
    MemoryTraceStore,
    MemoryWakeupInbox,
    RateLimitedAgent,
    RecoverableDisconnectAgent,
    StartClaudeAcpThenStopBrain,
    StartThenBlockBrain,
    StartThenStopBrain,
    StartTwiceThenStopBrain,
    WaitingInputAgent,
    make_service,
    run_settings,
)
from agent_operator.testing.runtime_bindings import build_test_runtime_bindings


class SummarizingStartThenStopBrain(StartThenStopBrain):
    async def summarize_agent_turn(
        self,
        state,
        *,
        operator_instruction: str,
        result: AgentResult,
    ):
        from agent_operator.domain import AgentTurnSummary

        return AgentTurnSummary(
            declared_goal=operator_instruction,
            actual_work_done="Completed fake agent turn.",
            state_delta="Persisted turn summary.",
            verification_status="Not verified.",
            recommended_next_step="Stop.",
        )


class StartThenDecisionStopBrain:
    def __init__(self) -> None:
        self.calls = 0

    async def decide_next_action(self, state) -> BrainDecision:
        self.calls += 1
        if self.calls == 1:
            return BrainDecision(
                action_type=BrainActionType.START_AGENT,
                target_agent="claude_acp",
                instruction="produce final artifact",
                rationale="Run the agent first.",
            )
        return BrainDecision(
            action_type=BrainActionType.STOP,
            rationale="Stop after the result already exists.",
        )

    async def evaluate_result(self, state) -> Evaluation:
        return Evaluation(
            goal_satisfied=False,
            should_continue=True,
            summary="Need one more brain decision.",
        )

    async def summarize_progress(self, state) -> ProgressSummary:
        return ProgressSummary(summary="summary")

    async def normalize_artifact(self, goal, result) -> AgentResult:
        return result


class VerboseRawAgent(FakeAgent):
    async def collect(self, handle) -> AgentResult:
        return AgentResult(
            session_id=handle.session_id,
            status=AgentResultStatus.SUCCESS,
            output_text="final concise output",
            transcript="x" * 10_000,
            raw={
                "returncode": 0,
                "parsed_result": {"huge": "y" * 10_000},
                "escalation_detected": False,
            },
            completed_at=datetime.now(UTC),
        )


class WrappedResultAgent(FakeAgent):
    async def collect(self, handle) -> AgentResult:
        return AgentResult(
            session_id=handle.session_id,
            status=AgentResultStatus.SUCCESS,
            output_text=(
                "## Swarm Analysis: Research Plan\n\n"
                "### Phase 1: Problem Definition\nfoo\n\n"
                "1. Working title\n"
                "Helpful Is Not Aligned\n\n"
                "2. Core thesis\n"
                "RLHF is not alignment.\n"
            ),
            completed_at=datetime.now(UTC),
        )


class LLMNormalizationBrain:
    async def decide_next_action(self, state) -> BrainDecision:
        if not state.iterations:
            return BrainDecision(
                action_type=BrainActionType.START_AGENT,
                target_agent="claude_acp",
                instruction="produce plan",
                rationale="Run the agent first.",
            )
        return BrainDecision(
            action_type=BrainActionType.STOP,
            rationale="The normalized research plan is already present.",
        )

    async def evaluate_result(self, state) -> Evaluation:
        latest = state.iterations[-1].result
        has_clean_plan = bool(
            latest
            and latest.output_text.startswith("1. Working title")
            and "## Swarm Analysis" not in latest.output_text
        )
        return Evaluation(
            goal_satisfied=has_clean_plan,
            should_continue=not has_clean_plan,
            summary="Research plan normalized." if has_clean_plan else "Need normalization.",
        )

    async def summarize_progress(self, state) -> ProgressSummary:
        return ProgressSummary(summary="summary")

    async def normalize_artifact(self, goal, result) -> AgentResult:
        return result.model_copy(
            update={
                "output_text": (
                    "1. Working title\nHelpful Is Not Aligned\n\n"
                    "2. Core thesis\nRLHF is not alignment.\n"
                ),
                "raw": {
                    **(result.raw or {}),
                    "normalized_by_operator_brain": True,
                },
            }
        )


@pytest.mark.anyio
async def test_rate_limited_agent_blocks_operation_for_cooldown_without_retrying() -> None:
    store = MemoryStore()
    trace_store = MemoryTraceStore()
    event_sink = MemoryEventSink()
    agent = RateLimitedAgent(key="claude_acp")
    service = make_service(
        brain=StartClaudeAcpThenStopBrain(),
        store=store,
        trace_store=trace_store,
        event_sink=event_sink,
        agent_runtime_bindings=build_test_runtime_bindings({"claude_acp": agent}),
    )

    outcome = await service.run(
        OperationGoal(objective="hit rate limit"),
        **run_settings(max_iterations=4, allowed_agents=["claude_acp"]),
        options=RunOptions(run_mode=RunMode.ATTACHED),
    )

    operation = await store.load_operation(outcome.operation_id)
    assert operation is not None
    assert outcome.status is OperationStatus.NEEDS_HUMAN
    assert "rate limit" in (outcome.summary or "").lower()
    assert len(agent.started_requests) == 1
    record = operation.sessions[0]
    assert record.status is SessionStatus.WAITING
    assert record.cooldown_until is not None
    assert record.cooldown_reason is not None
    assert operation.current_focus is not None
    assert operation.current_focus.kind is FocusKind.SESSION


@pytest.mark.anyio
async def test_rate_limit_enqueues_delayed_cooldown_wakeup() -> None:
    store = MemoryStore()
    trace_store = MemoryTraceStore()
    inbox = MemoryWakeupInbox()
    service = make_service(
        brain=StartClaudeAcpThenStopBrain(),
        store=store,
        trace_store=trace_store,
        event_sink=MemoryEventSink(),
        agent_runtime_bindings=build_test_runtime_bindings(
            {"claude_acp": RateLimitedAgent(key="claude_acp")}
        ),
        wakeup_inbox=inbox,
    )

    outcome = await service.run(
        OperationGoal(objective="hit rate limit"),
        **run_settings(max_iterations=4, allowed_agents=["claude_acp"]),
        options=RunOptions(run_mode=RunMode.ATTACHED),
    )

    assert outcome.status is OperationStatus.NEEDS_HUMAN
    pending = await inbox.list_pending(outcome.operation_id)
    assert len(pending) == 1
    wakeup = pending[0]
    assert wakeup.event_type == "session.cooldown_expired"
    assert wakeup.session_id is not None
    assert wakeup.not_before is not None


@pytest.mark.anyio
async def test_agent_escalation_request_is_flagged_as_incomplete() -> None:
    store = MemoryStore()
    service = make_service(
        brain=StartThenStopBrain(),
        store=store,
        trace_store=MemoryTraceStore(),
        event_sink=MemoryEventSink(),
        agent_runtime_bindings=build_test_runtime_bindings({"claude_acp": EscalatingAgent()}),
    )

    outcome = await service.run(
        OperationGoal(objective="continue work"),
        **run_settings(max_iterations=2, allowed_agents=["claude_acp"]),
    )
    operation = await store.load_operation(outcome.operation_id)

    assert outcome.final_result is not None
    assert outcome.final_result.status is AgentResultStatus.INCOMPLETE
    assert outcome.final_result.error is not None
    assert outcome.final_result.error.code == "agent_requested_escalation"
    assert operation is not None
    assert len(operation.attention_requests) == 1
    assert operation.attention_requests[0].attention_type is AttentionType.APPROVAL_REQUEST


@pytest.mark.anyio
async def test_attached_run_surfaces_waiting_input_as_incomplete_result() -> None:
    store = MemoryStore()
    event_sink = MemoryEventSink()
    service = make_service(
        brain=StartThenBlockBrain(),
        store=store,
        trace_store=MemoryTraceStore(),
        event_sink=event_sink,
        agent_runtime_bindings=build_test_runtime_bindings({"claude_acp": WaitingInputAgent()}),
    )

    outcome = await service.run(
        OperationGoal(objective="continue work"),
        **run_settings(max_iterations=2, allowed_agents=["claude_acp"]),
    )
    operation = await store.load_operation(outcome.operation_id)

    assert outcome.status is OperationStatus.NEEDS_HUMAN
    assert outcome.final_result is not None
    assert outcome.final_result.status is AgentResultStatus.INCOMPLETE
    assert outcome.final_result.error is not None
    assert outcome.final_result.error.code == "agent_requested_escalation"
    assert operation is not None
    assert len(operation.attention_requests) == 1
    assert operation.attention_requests[0].attention_type is AttentionType.APPROVAL_REQUEST
    created = [
        event for event in event_sink.events if event.event_type == "attention.request.created"
    ]
    assert len(created) == 1
    assert created[0].session_id == operation.sessions[0].handle.session_id


@pytest.mark.anyio
async def test_resume_recovers_disconnected_session_without_starting_new_one() -> None:
    store = MemoryStore()
    agent = RecoverableDisconnectAgent()
    service = make_service(
        brain=StartTwiceThenStopBrain(),
        store=store,
        trace_store=MemoryTraceStore(),
        event_sink=MemoryEventSink(),
        agent_runtime_bindings=build_test_runtime_bindings({"claude_acp": agent}),
    )

    first = await service.run(
        OperationGoal(objective="recover claude session after ACP disconnect"),
        **run_settings(max_iterations=4, allowed_agents=["claude_acp"]),
        options=RunOptions(run_mode=RunMode.ATTACHED, max_cycles=1),
    )
    operation = await store.load_operation(first.operation_id)

    assert first.status is OperationStatus.NEEDS_HUMAN
    assert first.final_result is not None
    assert first.final_result.status is AgentResultStatus.DISCONNECTED
    assert operation is not None
    assert len(operation.sessions) == 1
    assert operation.sessions[0].status is SessionStatus.WAITING

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
async def test_result_refreshes_task_memory() -> None:
    store = MemoryStore()
    service = make_service(
        brain=MemoryDistillingStartThenStopBrain(),
        store=store,
        trace_store=MemoryTraceStore(),
        event_sink=MemoryEventSink(),
        agent_runtime_bindings=build_test_runtime_bindings({"claude_acp": FakeAgent()}),
    )

    outcome = await service.run(
        OperationGoal(objective="distill memory"),
        **run_settings(max_iterations=2, allowed_agents=["claude_acp"]),
    )
    operation = await store.load_operation(outcome.operation_id)

    assert operation is not None
    assert operation.memory_entries


@pytest.mark.anyio
async def test_background_rate_limit_blocks_operation_without_launching_new_run() -> None:
    store = MemoryStore()
    trace_store = MemoryTraceStore()
    inbox = MemoryWakeupInbox()
    supervisor = FakeSupervisor()
    service = make_service(
        brain=StartClaudeAcpThenStopBrain(),
        store=store,
        trace_store=trace_store,
        event_sink=MemoryEventSink(),
        agent_runtime_bindings=build_test_runtime_bindings({"claude_acp": FakeAgent()}),
        wakeup_inbox=inbox,
        supervisor=supervisor,
    )

    first = await service.run(
        OperationGoal(objective="background rate limit"),
        **run_settings(max_iterations=4, allowed_agents=["claude_acp"]),
        options=RunOptions(
            run_mode=RunMode.RESUMABLE,
            background_runtime_mode=BackgroundRuntimeMode.RESUMABLE_WAKEUP,
        ),
    )

    operation = await store.load_operation(first.operation_id)
    assert operation is not None
    run_id = operation.background_runs[0].run_id
    supervisor.results[run_id] = supervisor.results[run_id].model_copy(
        update={
            "status": AgentResultStatus.FAILED,
            "output_text": "",
            "error": AgentError(
                code="claude_acp_rate_limited",
                message="Claude rate limit hit. Try again in 60 minutes.",
                retryable=True,
                raw={"retry_after_seconds": 3600, "rate_limit_detected": True},
            ),
            "completed_at": datetime.now(UTC),
        }
    )
    await inbox.enqueue(
        RunEvent(
            event_type="background_run.failed",
            kind=RunEventKind.WAKEUP,
            operation_id=operation.operation_id,
            iteration=1,
            task_id=operation.tasks[0].task_id,
            session_id=operation.sessions[0].session_id,
            dedupe_key=f"{run_id}:failed",
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
    updated = await store.load_operation(operation.operation_id)

    assert resumed.status is OperationStatus.NEEDS_HUMAN
    assert updated is not None
    assert updated.sessions[0].status is SessionStatus.WAITING
    assert updated.sessions[0].cooldown_until is not None


@pytest.mark.anyio
async def test_completed_agent_turn_persists_turn_summary() -> None:
    store = MemoryStore()
    trace_store = MemoryTraceStore()
    service = make_service(
        brain=SummarizingStartThenStopBrain(),
        store=store,
        trace_store=trace_store,
        event_sink=MemoryEventSink(),
        agent_runtime_bindings=build_test_runtime_bindings({"claude_acp": FakeAgent()}),
    )

    outcome = await service.run(
        OperationGoal(objective="complete one fake turn"),
        **run_settings(max_iterations=3, allowed_agents=["claude_acp"]),
    )
    state = await store.load_operation(outcome.operation_id)

    assert state is not None
    completed_iterations = [item for item in state.iterations if item.result is not None]
    assert completed_iterations
    assert completed_iterations[0].turn_summary is not None
    assert completed_iterations[0].turn_summary.actual_work_done == "Completed fake agent turn."
    assert trace_store.bundle.agent_turn_briefs
    assert trace_store.bundle.agent_turn_briefs[0].turn_summary is not None
    assert "Persisted turn summary." in (trace_store.bundle.agent_turn_briefs[0].result_brief or "")


@pytest.mark.anyio
async def test_operator_service_preserves_latest_result_when_stopping() -> None:
    service = make_service(
        brain=StartThenDecisionStopBrain(),
        store=MemoryStore(),
        trace_store=MemoryTraceStore(),
        event_sink=MemoryEventSink(),
        agent_runtime_bindings=build_test_runtime_bindings({"claude_acp": FakeAgent()}),
    )

    outcome = await service.run(
        OperationGoal(objective="complete and stop"),
        **run_settings(max_iterations=4, allowed_agents=["claude_acp"]),
    )

    assert outcome.status is OperationStatus.COMPLETED
    assert outcome.final_result is not None
    assert outcome.final_result.output_text == "completed by fake agent"


@pytest.mark.anyio
async def test_operator_service_compacts_persisted_iteration_result() -> None:
    store = MemoryStore()
    service = make_service(
        brain=StartThenStopBrain(),
        store=store,
        trace_store=MemoryTraceStore(),
        event_sink=MemoryEventSink(),
        agent_runtime_bindings=build_test_runtime_bindings({"claude_acp": VerboseRawAgent()}),
    )

    outcome = await service.run(
        OperationGoal(objective="complete the task"),
        **run_settings(max_iterations=3, allowed_agents=["claude_acp"]),
    )

    operation = await store.load_operation(outcome.operation_id)
    assert operation is not None
    persisted_result = operation.iterations[-1].result
    assert persisted_result is not None
    assert persisted_result.output_text == "final concise output"
    assert persisted_result.transcript is None
    assert persisted_result.raw == {
        "returncode": 0,
        "escalation_detected": False,
    }


@pytest.mark.anyio
async def test_operator_service_normalizes_result_with_brain_before_evaluation() -> None:
    service = make_service(
        brain=LLMNormalizationBrain(),
        store=MemoryStore(),
        trace_store=MemoryTraceStore(),
        event_sink=MemoryEventSink(),
        agent_runtime_bindings=build_test_runtime_bindings({"claude_acp": WrappedResultAgent()}),
    )

    outcome = await service.run(
        OperationGoal(
            objective="produce a research plan",
            metadata={"result_normalization_instruction": "Return only the research plan."},
        ),
        **run_settings(max_iterations=4, allowed_agents=["claude_acp"]),
    )

    assert outcome.status is OperationStatus.COMPLETED
    assert outcome.final_result is not None
    assert outcome.final_result.output_text.startswith("1. Working title")
    assert "## Swarm Analysis" not in outcome.final_result.output_text
