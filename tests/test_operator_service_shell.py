from __future__ import annotations

import pytest

from agent_operator.domain import (
    AgentResult,
    BrainActionType,
    BrainDecision,
    CanonicalPersistenceMode,
    Evaluation,
    ExecutionBudget,
    OperationGoal,
    OperationPolicy,
    OperationStatus,
    PolicyApplicability,
    PolicyCategory,
    PolicyEntry,
    ProgressSummary,
    RunMode,
    RunOptions,
    RuntimeHints,
)
from agent_operator.testing.operator_service_support import (
    FakeAgent,
    MemoryEventSink,
    MemoryHistoryLedger,
    MemoryPolicyStore,
    MemoryStore,
    MemoryTraceStore,
    StartThenStopBrain,
    make_service,
    run_settings,
)
from agent_operator.testing.runtime_bindings import build_test_runtime_bindings


class StopImmediatelyBrain:
    async def decide_next_action(self, state) -> BrainDecision:
        return BrainDecision(
            action_type=BrainActionType.STOP,
            rationale="The operator has enough context to continue after replanning.",
        )

    async def evaluate_result(self, state) -> Evaluation:
        return Evaluation(
            goal_satisfied=True,
            should_continue=False,
            summary="Goal satisfied after replanning.",
        )

    async def summarize_progress(self, state) -> ProgressSummary:
        return ProgressSummary(summary="summary")

    async def normalize_artifact(self, goal, result) -> AgentResult:
        return result


@pytest.mark.anyio
async def test_run_appends_history_ledger_on_terminal_completion() -> None:
    class StopBrain:
        async def decide_next_action(self, state) -> BrainDecision:
            return BrainDecision(
                action_type=BrainActionType.STOP,
                rationale="Done.",
            )

        async def evaluate_result(self, state) -> Evaluation:
            raise AssertionError("evaluate_result should not run for STOP")

    history = MemoryHistoryLedger()
    service = make_service(
        brain=StopBrain(),
        store=MemoryStore(),
        trace_store=MemoryTraceStore(),
        event_sink=MemoryEventSink(),
        history_ledger=history,
        agent_runtime_bindings={},
    )

    outcome = await service.run(
        OperationGoal(objective="Finish the task."),
        policy=OperationPolicy(),
        budget=ExecutionBudget(max_iterations=5),
        runtime_hints=RuntimeHints(),
        options=RunOptions(run_mode=RunMode.ATTACHED),
    )

    assert outcome.status is OperationStatus.COMPLETED
    assert len(history.entries) == 1
    recorded_state, recorded_outcome = history.entries[0]
    assert recorded_state.operation_id == outcome.operation_id
    assert recorded_outcome.summary == "Done."


@pytest.mark.anyio
async def test_run_refreshes_active_policy_context_from_scope() -> None:
    store = MemoryStore()
    policy_store = MemoryPolicyStore()
    await policy_store.save(
        PolicyEntry(
            policy_id="policy-1",
            project_scope="profile:femtobot",
            title="Manual testing debt",
            category=PolicyCategory.TESTING,
            rule_text="Document manual-only verification in MANUAL_TESTING_REQUIRED.md.",
        )
    )
    service = make_service(
        brain=StartThenStopBrain(),
        store=store,
        trace_store=MemoryTraceStore(),
        event_sink=MemoryEventSink(),
        agent_runtime_bindings=build_test_runtime_bindings({"claude_acp": FakeAgent()}),
        policy_store=policy_store,
    )

    outcome = await service.run(
        OperationGoal(
            objective="Ship the feature",
            metadata={"policy_scope": "profile:femtobot"},
        ),
        **run_settings(max_iterations=4, allowed_agents=["claude_acp"]),
    )
    operation = await store.load_operation(outcome.operation_id)

    assert operation is not None
    assert [item.policy_id for item in operation.active_policies] == ["policy-1"]


@pytest.mark.anyio
async def test_run_refreshes_active_policy_context_with_applicability_filters() -> None:
    store = MemoryStore()
    policy_store = MemoryPolicyStore()
    await policy_store.save(
        PolicyEntry(
            policy_id="policy-release",
            project_scope="profile:femtobot",
            title="Release approvals",
            category=PolicyCategory.RELEASE,
            rule_text="Require release approval before production deploys.",
            applicability=PolicyApplicability(
                objective_keywords=["release"],
                run_modes=[RunMode.ATTACHED],
            ),
        )
    )
    await policy_store.save(
        PolicyEntry(
            policy_id="policy-testing",
            project_scope="profile:femtobot",
            title="Manual testing debt",
            category=PolicyCategory.TESTING,
            rule_text="Document manual-only verification in MANUAL_TESTING_REQUIRED.md.",
            applicability=PolicyApplicability(objective_keywords=["manual testing"]),
        )
    )
    service = make_service(
        brain=StartThenStopBrain(),
        store=store,
        trace_store=MemoryTraceStore(),
        event_sink=MemoryEventSink(),
        agent_runtime_bindings=build_test_runtime_bindings({"claude_acp": FakeAgent()}),
        policy_store=policy_store,
    )

    outcome = await service.run(
        OperationGoal(
            objective="Prepare the release train for production",
            metadata={"policy_scope": "profile:femtobot"},
        ),
        **run_settings(
            max_iterations=4,
            allowed_agents=["claude_acp"],
            metadata={"run_mode": RunMode.ATTACHED.value},
        ),
    )
    operation = await store.load_operation(outcome.operation_id)

    assert operation is not None
    assert [item.policy_id for item in operation.active_policies] == ["policy-release"]


@pytest.mark.anyio
async def test_run_persists_event_sourced_canonical_mode() -> None:
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
    assert operation.canonical_persistence_mode is CanonicalPersistenceMode.EVENT_SOURCED


@pytest.mark.anyio
async def test_resume_accepts_event_sourced_operation_created_by_run() -> None:
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

    resumed = await service.resume(outcome.operation_id)

    assert resumed.operation_id == outcome.operation_id
