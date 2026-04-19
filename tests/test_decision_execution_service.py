from __future__ import annotations

import pytest

from agent_operator.domain import (
    AgentResult,
    AttentionType,
    BrainActionType,
    BrainDecision,
    Evaluation,
    FocusKind,
    InvolvementLevel,
    OperationGoal,
    OperationStatus,
    ProgressSummary,
    RunMode,
    RunOptions,
)
from agent_operator.testing.operator_service_support import (
    FakeAgent,
    MemoryEventSink,
    MemoryStore,
    MemoryTraceStore,
    StartThenFailBrain,
    make_service,
    run_settings,
)
from agent_operator.testing.runtime_bindings import build_test_runtime_bindings


class ClarificationBrain:
    async def decide_next_action(self, state) -> BrainDecision:
        return BrainDecision(
            action_type=BrainActionType.REQUEST_CLARIFICATION,
            rationale="Which deployment target should the operator use?",
        )

    async def evaluate_result(self, state) -> Evaluation:
        raise AssertionError

    async def summarize_progress(self, state) -> ProgressSummary:
        return ProgressSummary(summary="summary")

    async def normalize_artifact(self, goal, result):
        return result


class BadAdapterBrain:
    async def decide_next_action(self, state) -> BrainDecision:
        return BrainDecision(
            action_type=BrainActionType.START_AGENT,
            target_agent="missing_agent",
            instruction="do the task",
            rationale="try a missing agent",
        )

    async def evaluate_result(self, state) -> Evaluation:
        return Evaluation(goal_satisfied=False, should_continue=True, summary="continue")

    async def summarize_progress(self, state) -> ProgressSummary:
        return ProgressSummary(summary="summary")

    async def normalize_artifact(self, goal, result):
        return result


class UnattendedClarificationThenStopBrain:
    def __init__(self) -> None:
        self.calls = 0

    async def decide_next_action(self, state) -> BrainDecision:
        self.calls += 1
        if self.calls == 1:
            return BrainDecision(
                action_type=BrainActionType.REQUEST_CLARIFICATION,
                rationale="Which environment should be used?",
            )
        return BrainDecision(
            action_type=BrainActionType.STOP,
            rationale="Recorded the unattended attention request and stopped this run.",
        )

    async def evaluate_result(self, state) -> Evaluation:
        return Evaluation(goal_satisfied=False, should_continue=True, summary="Continue.")

    async def summarize_progress(self, state) -> ProgressSummary:
        return ProgressSummary(summary="summary")

    async def normalize_artifact(self, goal, result) -> AgentResult:
        return result


class PolicyGapBrain:
    async def decide_next_action(self, state) -> BrainDecision:
        return BrainDecision(
            action_type=BrainActionType.REQUEST_CLARIFICATION,
            rationale=(
                "Should manual-only verification always be recorded in "
                "MANUAL_TESTING_REQUIRED.md before completion?"
            ),
            metadata={
                "attention_type": "policy_gap",
                "attention_title": "Testing policy is missing",
                "attention_context": "No active testing policy covers manual-only verification.",
                "attention_options": [
                    "Always record manual-only checks in MANUAL_TESTING_REQUIRED.md.",
                    "Only record them for release-affecting work.",
                ],
            },
        )

    async def evaluate_result(self, state) -> Evaluation:
        raise AssertionError("evaluate_result should not be called for clarification")

    async def summarize_progress(self, state) -> ProgressSummary:
        return ProgressSummary(summary="summary")

    async def normalize_artifact(self, goal, result) -> AgentResult:
        return result


class PolicyGuardrailBrain:
    def __init__(self) -> None:
        self.calls = 0

    async def decide_next_action(self, state) -> BrainDecision:
        self.calls += 1
        if self.calls == 1:
            return BrainDecision(
                action_type=BrainActionType.START_AGENT,
                target_agent="claude_acp",
                instruction="Update the release workflow.",
                rationale=(
                    "What release approval policy should the operator apply before changing "
                    "the workflow?"
                ),
                metadata={
                    "requires_policy_decision": True,
                    "attention_title": "Release policy is missing",
                    "attention_context": (
                        "This operation has project policy scope, but no active policy covers "
                        "release approval expectations."
                    ),
                    "attention_options": [
                        "Always ask before release workflow changes.",
                        "Allow routine release workflow changes without asking.",
                    ],
                },
            )
        return BrainDecision(
            action_type=BrainActionType.STOP,
            rationale="Stopped after surfacing the policy boundary.",
        )

    async def evaluate_result(self, state) -> Evaluation:
        return Evaluation(goal_satisfied=False, should_continue=True, summary="Continue.")

    async def summarize_progress(self, state) -> ProgressSummary:
        return ProgressSummary(summary="summary")

    async def normalize_artifact(self, goal, result) -> AgentResult:
        return result


class PolicyGuardrailClarificationBrain(PolicyGapBrain):
    async def decide_next_action(self, state) -> BrainDecision:
        return BrainDecision(
            action_type=BrainActionType.REQUEST_CLARIFICATION,
            rationale="Should release workflow changes always require explicit approval?",
            metadata={
                "requires_policy_decision": True,
                "policy_question": (
                    "What approval rule should govern future release workflow changes?"
                ),
                "attention_title": "Release policy is missing",
                "attention_context": (
                    "No active release policy currently covers this project-scoped decision."
                ),
            },
        )


class NovelStrategicForkBrain:
    async def decide_next_action(self, state) -> BrainDecision:
        return BrainDecision(
            action_type=BrainActionType.REQUEST_CLARIFICATION,
            rationale=(
                "Should the repo adopt a staged release train or continue with "
                "continuous deployment for the next quarter?"
            ),
            metadata={
                "attention_type": "novel_strategic_fork",
                "attention_title": "Release strategy fork needs a decision",
                "attention_context": (
                    "Both release strategies are plausible and current project policy does not "
                    "establish a default."
                ),
                "attention_options": [
                    "Adopt a staged release train with explicit cut windows.",
                    "Keep continuous deployment and tighten rollback guardrails instead.",
                ],
            },
        )

    async def evaluate_result(self, state) -> Evaluation:
        raise AssertionError("evaluate_result should not be called for clarification")

    async def summarize_progress(self, state) -> ProgressSummary:
        return ProgressSummary(summary="summary")

    async def normalize_artifact(self, goal, result) -> AgentResult:
        return result


class NovelStrategicForkGuardrailBrain:
    def __init__(self) -> None:
        self.calls = 0

    async def decide_next_action(self, state) -> BrainDecision:
        self.calls += 1
        if self.calls == 1:
            return BrainDecision(
                action_type=BrainActionType.START_AGENT,
                target_agent="claude_acp",
                instruction="Choose and implement the release strategy.",
                rationale=(
                    "Should the repo adopt a staged release train or continue with "
                    "continuous deployment for the next quarter?"
                ),
                metadata={
                    "requires_strategy_decision": True,
                    "attention_title": "Release strategy fork needs a decision",
                    "attention_context": (
                        "Both release strategies are plausible and current context does not "
                        "establish a default."
                    ),
                    "attention_options": [
                        "Adopt a staged release train with explicit cut windows.",
                        "Keep continuous deployment and tighten rollback guardrails instead.",
                    ],
                },
            )
        return BrainDecision(
            action_type=BrainActionType.STOP,
            rationale="Stopped after surfacing the strategic fork.",
        )

    async def evaluate_result(self, state) -> Evaluation:
        return Evaluation(goal_satisfied=False, should_continue=True, summary="Continue.")

    async def summarize_progress(self, state) -> ProgressSummary:
        return ProgressSummary(summary="summary")

    async def normalize_artifact(self, goal, result) -> AgentResult:
        return result


class NovelStrategicForkGuardrailClarificationBrain(NovelStrategicForkBrain):
    async def decide_next_action(self, state) -> BrainDecision:
        return BrainDecision(
            action_type=BrainActionType.REQUEST_CLARIFICATION,
            rationale=(
                "Should the repo adopt a staged release train or continue with "
                "continuous deployment for the next quarter?"
            ),
            metadata={
                "requires_strategy_decision": True,
                "strategy_question": (
                    "Which release strategy should become the default for the next quarter?"
                ),
                "attention_title": "Release strategy fork needs a decision",
                "attention_context": (
                    "Both release strategies are plausible and current context does not "
                    "establish a default."
                ),
            },
        )


@pytest.mark.anyio
async def test_request_clarification_creates_blocking_attention_request() -> None:
    store = MemoryStore()
    event_sink = MemoryEventSink()
    service = make_service(
        brain=ClarificationBrain(),
        store=store,
        trace_store=MemoryTraceStore(),
        event_sink=event_sink,
        agent_runtime_bindings=build_test_runtime_bindings({"claude_acp": FakeAgent()}),
    )

    outcome = await service.run(
        OperationGoal(objective="pick a deployment target"),
        **run_settings(max_iterations=2, allowed_agents=["claude_acp"]),
        options=RunOptions(run_mode=RunMode.RESUMABLE),
    )
    operation = await store.load_operation(outcome.operation_id)

    assert outcome.status is OperationStatus.NEEDS_HUMAN
    assert operation is not None
    assert operation.attention_requests[0].blocking is True
    assert operation.current_focus is not None
    assert operation.current_focus.kind is FocusKind.ATTENTION_REQUEST
    created = [
        event for event in event_sink.events if event.event_type == "attention.request.created"
    ]
    assert len(created) == 1
    assert created[0].payload["attention_id"] == operation.attention_requests[0].attention_id
    assert created[0].payload["attention_type"] == AttentionType.QUESTION.value
    assert created[0].payload["status"] == "open"


@pytest.mark.anyio
async def test_missing_target_agent_fails_operation() -> None:
    store = MemoryStore()
    service = make_service(
        brain=BadAdapterBrain(),
        store=store,
        trace_store=MemoryTraceStore(),
        event_sink=MemoryEventSink(),
        agent_runtime_bindings=build_test_runtime_bindings({"claude_acp": FakeAgent()}),
    )

    outcome = await service.run(
        OperationGoal(objective="do work"),
        **run_settings(
            max_iterations=2,
            allowed_agents=["claude_acp"],
            involvement_level=InvolvementLevel.AUTO,
        ),
    )

    assert outcome.status is OperationStatus.FAILED
    assert "unavailable or not allowed" in (outcome.summary or "")


@pytest.mark.anyio
async def test_unattended_clarification_creates_non_blocking_attention_request() -> None:
    store = MemoryStore()
    service = make_service(
        brain=UnattendedClarificationThenStopBrain(),
        store=store,
        trace_store=MemoryTraceStore(),
        event_sink=MemoryEventSink(),
        agent_runtime_bindings=build_test_runtime_bindings({"claude_acp": FakeAgent()}),
    )

    outcome = await service.run(
        OperationGoal(objective="pick a deployment target"),
        **run_settings(
            max_iterations=3,
            allowed_agents=["claude_acp"],
            involvement_level=InvolvementLevel.UNATTENDED,
        ),
    )
    operation = await store.load_operation(outcome.operation_id)

    assert operation is not None
    assert outcome.status is OperationStatus.COMPLETED
    attention = operation.attention_requests[0]
    assert attention.attention_type is AttentionType.QUESTION
    assert attention.blocking is False
    assert operation.involvement_level is InvolvementLevel.UNATTENDED


@pytest.mark.anyio
async def test_request_clarification_can_create_policy_gap_attention() -> None:
    store = MemoryStore()
    service = make_service(
        brain=PolicyGapBrain(),
        store=store,
        trace_store=MemoryTraceStore(),
        event_sink=MemoryEventSink(),
        agent_runtime_bindings=build_test_runtime_bindings({"claude_acp": FakeAgent()}),
    )

    outcome = await service.run(
        OperationGoal(objective="set the testing workflow"),
        **run_settings(max_iterations=2, allowed_agents=["claude_acp"]),
        options=RunOptions(run_mode=RunMode.RESUMABLE),
    )
    operation = await store.load_operation(outcome.operation_id)

    assert outcome.status is OperationStatus.NEEDS_HUMAN
    assert operation is not None
    attention = operation.attention_requests[0]
    assert attention.attention_type is AttentionType.POLICY_GAP
    assert attention.title == "Testing policy is missing"
    assert attention.context_brief == "No active testing policy covers manual-only verification."
    assert attention.suggested_options == [
        "Always record manual-only checks in MANUAL_TESTING_REQUIRED.md.",
        "Only record them for release-affecting work.",
    ]


@pytest.mark.anyio
async def test_policy_guardrail_blocks_policy_shaped_agent_action_in_auto_mode() -> None:
    store = MemoryStore()
    agent = FakeAgent()
    service = make_service(
        brain=PolicyGuardrailBrain(),
        store=store,
        trace_store=MemoryTraceStore(),
        event_sink=MemoryEventSink(),
        agent_runtime_bindings=build_test_runtime_bindings({"claude_acp": agent}),
    )

    outcome = await service.run(
        OperationGoal(
            objective="Update the release workflow",
            metadata={"policy_scope": "profile:femtobot"},
        ),
        **run_settings(
            max_iterations=2,
            allowed_agents=["claude_acp"],
            involvement_level=InvolvementLevel.AUTO,
        ),
        options=RunOptions(run_mode=RunMode.RESUMABLE),
    )
    operation = await store.load_operation(outcome.operation_id)

    assert outcome.status is OperationStatus.NEEDS_HUMAN
    assert operation is not None
    assert agent.started_requests == []
    attention = operation.attention_requests[0]
    assert attention.attention_type is AttentionType.POLICY_GAP
    assert attention.blocking is True
    assert attention.title == "Release policy is missing"
    assert operation.current_focus is not None
    assert operation.current_focus.kind is FocusKind.ATTENTION_REQUEST


@pytest.mark.anyio
async def test_policy_guardrail_defers_policy_shaped_agent_action_in_unattended_mode() -> None:
    store = MemoryStore()
    agent = FakeAgent()
    service = make_service(
        brain=PolicyGuardrailBrain(),
        store=store,
        trace_store=MemoryTraceStore(),
        event_sink=MemoryEventSink(),
        agent_runtime_bindings=build_test_runtime_bindings({"claude_acp": agent}),
    )

    outcome = await service.run(
        OperationGoal(
            objective="Update the release workflow",
            metadata={"policy_scope": "profile:femtobot"},
        ),
        **run_settings(
            max_iterations=3,
            allowed_agents=["claude_acp"],
            involvement_level=InvolvementLevel.UNATTENDED,
        ),
    )
    operation = await store.load_operation(outcome.operation_id)

    assert outcome.status is OperationStatus.COMPLETED
    assert operation is not None
    assert agent.started_requests == []
    attention = operation.attention_requests[0]
    assert attention.attention_type is AttentionType.POLICY_GAP
    assert attention.blocking is False
    assert any("Deferred policy-shaped action" in note for note in operation.iterations[0].notes)


@pytest.mark.anyio
async def test_policy_guardrail_forces_policy_gap_type_for_clarification() -> None:
    store = MemoryStore()
    service = make_service(
        brain=PolicyGuardrailClarificationBrain(),
        store=store,
        trace_store=MemoryTraceStore(),
        event_sink=MemoryEventSink(),
        agent_runtime_bindings=build_test_runtime_bindings({"claude_acp": FakeAgent()}),
    )

    outcome = await service.run(
        OperationGoal(
            objective="Update the release workflow",
            metadata={"policy_scope": "profile:femtobot"},
        ),
        **run_settings(
            max_iterations=2,
            allowed_agents=["claude_acp"],
            involvement_level=InvolvementLevel.AUTO,
        ),
        options=RunOptions(run_mode=RunMode.RESUMABLE),
    )
    operation = await store.load_operation(outcome.operation_id)

    assert outcome.status is OperationStatus.NEEDS_HUMAN
    assert operation is not None
    attention = operation.attention_requests[0]
    assert attention.attention_type is AttentionType.POLICY_GAP
    assert attention.title == "Release policy is missing"
    assert attention.question == "What approval rule should govern future release workflow changes?"


@pytest.mark.anyio
async def test_request_clarification_can_create_novel_strategic_fork_attention() -> None:
    store = MemoryStore()
    service = make_service(
        brain=NovelStrategicForkBrain(),
        store=store,
        trace_store=MemoryTraceStore(),
        event_sink=MemoryEventSink(),
        agent_runtime_bindings=build_test_runtime_bindings({"claude_acp": FakeAgent()}),
    )

    outcome = await service.run(
        OperationGoal(objective="choose a release strategy"),
        **run_settings(
            max_iterations=2,
            allowed_agents=["claude_acp"],
            involvement_level=InvolvementLevel.AUTO,
        ),
        options=RunOptions(run_mode=RunMode.RESUMABLE),
    )
    operation = await store.load_operation(outcome.operation_id)

    assert outcome.status is OperationStatus.NEEDS_HUMAN
    assert operation is not None
    attention = operation.attention_requests[0]
    assert attention.attention_type is AttentionType.NOVEL_STRATEGIC_FORK
    assert attention.title == "Release strategy fork needs a decision"
    assert attention.suggested_options == [
        "Adopt a staged release train with explicit cut windows.",
        "Keep continuous deployment and tighten rollback guardrails instead.",
    ]


@pytest.mark.anyio
async def test_novel_guardrail_blocks_strategic_agent_action_in_auto_mode() -> None:
    store = MemoryStore()
    agent = FakeAgent()
    service = make_service(
        brain=NovelStrategicForkGuardrailBrain(),
        store=store,
        trace_store=MemoryTraceStore(),
        event_sink=MemoryEventSink(),
        agent_runtime_bindings=build_test_runtime_bindings({"claude_acp": agent}),
    )

    outcome = await service.run(
        OperationGoal(objective="choose a release strategy"),
        **run_settings(
            max_iterations=2,
            allowed_agents=["claude_acp"],
            involvement_level=InvolvementLevel.AUTO,
        ),
        options=RunOptions(run_mode=RunMode.RESUMABLE),
    )
    operation = await store.load_operation(outcome.operation_id)

    assert outcome.status is OperationStatus.NEEDS_HUMAN
    assert operation is not None
    assert agent.started_requests == []
    attention = operation.attention_requests[0]
    assert attention.attention_type is AttentionType.NOVEL_STRATEGIC_FORK
    assert attention.blocking is True
    assert operation.current_focus is not None
    assert operation.current_focus.kind is FocusKind.ATTENTION_REQUEST


@pytest.mark.anyio
async def test_novel_guardrail_defers_strategic_agent_action_in_unattended_mode() -> None:
    store = MemoryStore()
    agent = FakeAgent()
    service = make_service(
        brain=NovelStrategicForkGuardrailBrain(),
        store=store,
        trace_store=MemoryTraceStore(),
        event_sink=MemoryEventSink(),
        agent_runtime_bindings=build_test_runtime_bindings({"claude_acp": agent}),
    )

    outcome = await service.run(
        OperationGoal(objective="choose a release strategy"),
        **run_settings(
            max_iterations=3,
            allowed_agents=["claude_acp"],
            involvement_level=InvolvementLevel.UNATTENDED,
        ),
    )
    operation = await store.load_operation(outcome.operation_id)

    assert outcome.status is OperationStatus.COMPLETED
    assert operation is not None
    assert agent.started_requests == []
    attention = operation.attention_requests[0]
    assert attention.attention_type is AttentionType.NOVEL_STRATEGIC_FORK
    assert attention.blocking is False
    assert any("Deferred strategic fork" in note for note in operation.iterations[0].notes)


@pytest.mark.anyio
async def test_novel_guardrail_forces_strategic_fork_type_for_clarification() -> None:
    store = MemoryStore()
    service = make_service(
        brain=NovelStrategicForkGuardrailClarificationBrain(),
        store=store,
        trace_store=MemoryTraceStore(),
        event_sink=MemoryEventSink(),
        agent_runtime_bindings=build_test_runtime_bindings({"claude_acp": FakeAgent()}),
    )

    outcome = await service.run(
        OperationGoal(objective="choose a release strategy"),
        **run_settings(
            max_iterations=2,
            allowed_agents=["claude_acp"],
            involvement_level=InvolvementLevel.AUTO,
        ),
        options=RunOptions(run_mode=RunMode.RESUMABLE),
    )
    operation = await store.load_operation(outcome.operation_id)

    assert outcome.status is OperationStatus.NEEDS_HUMAN
    assert operation is not None
    attention = operation.attention_requests[0]
    assert attention.attention_type is AttentionType.NOVEL_STRATEGIC_FORK
    assert attention.title == "Release strategy fork needs a decision"


@pytest.mark.anyio
async def test_fail_action_marks_operation_and_root_task_failed() -> None:
    store = MemoryStore()
    service = make_service(
        brain=StartThenFailBrain(),
        store=store,
        trace_store=MemoryTraceStore(),
        event_sink=MemoryEventSink(),
        agent_runtime_bindings=build_test_runtime_bindings({"claude_acp": FakeAgent()}),
    )

    outcome = await service.run(
        OperationGoal(objective="continue work"),
        **run_settings(max_iterations=3, allowed_agents=["claude_acp"]),
    )
    operation = await store.load_operation(outcome.operation_id)

    assert outcome.status is OperationStatus.FAILED
    assert outcome.summary == "The agent surfaced an external blocker that makes this goal fail."
    assert operation is not None
    assert operation.tasks[0].status.name == "FAILED"
