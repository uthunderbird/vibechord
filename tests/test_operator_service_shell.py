from __future__ import annotations

import ast
from datetime import UTC, datetime
from pathlib import Path

import pytest

from agent_operator.domain import (
    AgentResult,
    BrainActionType,
    BrainDecision,
    CanonicalPersistenceMode,
    Evaluation,
    ExecutionBudget,
    OperationGoal,
    OperationOutcome,
    OperationPolicy,
    OperationState,
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


def test_operator_service_shell_surface_remains_small_and_delegating() -> None:
    service_path = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "agent_operator"
        / "application"
        / "service.py"
    )
    module = ast.parse(service_path.read_text(encoding="utf-8"))
    service_class = next(
        node
        for node in module.body
        if isinstance(node, ast.ClassDef) and node.name == "OperatorService"
    )

    public_methods: list[str] = []
    private_methods: list[str] = []
    for node in service_class.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if node.name == "__init__":
            continue
        if node.name.startswith("_"):
            private_methods.append(node.name)
        else:
            public_methods.append(node.name)

    assert public_methods == [
        "run",
        "resume",
        "recover",
        "tick",
        "cancel",
        "answer_question",
    ]
    assert private_methods == ["_drive_state", "_merge_runtime_flags"]


class RecordingEntrypointService:
    def __init__(self, state: OperationState) -> None:
        self.state = state
        self.prepare_run_calls: list[dict[str, object]] = []
        self.load_for_resume_calls: list[dict[str, object]] = []
        self.load_for_recover_calls: list[dict[str, object]] = []
        self.tick_options_calls: list[RunOptions | None] = []

    async def prepare_run(self, **kwargs) -> OperationState:
        self.prepare_run_calls.append(kwargs)
        return self.state

    async def load_for_resume(self, **kwargs) -> OperationState:
        self.load_for_resume_calls.append(kwargs)
        return self.state

    async def load_for_recover(self, **kwargs) -> OperationState:
        self.load_for_recover_calls.append(kwargs)
        return self.state

    def build_tick_options(self, options: RunOptions | None = None) -> RunOptions:
        self.tick_options_calls.append(options)
        return RunOptions(max_cycles=1)


class RecordingDriveService:
    def __init__(self, outcome: OperationOutcome) -> None:
        self.outcome = outcome
        self.calls: list[tuple[OperationState, RunOptions]] = []

    async def drive(self, state: OperationState, options: RunOptions) -> OperationOutcome:
        self.calls.append((state, options))
        return self.outcome


class RecordingCancellationService:
    def __init__(self, outcome: OperationOutcome) -> None:
        self.outcome = outcome
        self.calls: list[dict[str, object]] = []

    async def cancel(self, **kwargs) -> OperationOutcome:
        self.calls.append(kwargs)
        return self.outcome


def _service_shell_state() -> OperationState:
    return OperationState(
        operation_id="op-shell",
        goal=OperationGoal(objective="Shell delegation"),
        policy=OperationPolicy(),
        execution_budget=ExecutionBudget(max_iterations=5),
        runtime_hints=RuntimeHints(),
        run_started_at=datetime.now(UTC),
    )


@pytest.mark.anyio
async def test_operator_service_run_resume_recover_tick_and_cancel_delegate_to_shell_collaborators(
) -> None:
    state = _service_shell_state()
    outcome = OperationOutcome(
        operation_id=state.operation_id,
        status=OperationStatus.COMPLETED,
        summary="done",
    )
    entrypoints = RecordingEntrypointService(state)
    drive = RecordingDriveService(outcome)
    cancellation = RecordingCancellationService(outcome)
    store = MemoryStore()
    events = MemoryEventSink()
    service = make_service(
        brain=StopImmediatelyBrain(),
        store=store,
        trace_store=MemoryTraceStore(),
        event_sink=events,
        agent_runtime_bindings={},
        operation_entrypoint_service=entrypoints,
        operation_drive_service=drive,
        operation_cancellation_service=cancellation,
    )

    run_options = RunOptions(run_mode=RunMode.ATTACHED)

    run_outcome = await service.run(
        OperationGoal(objective="Shell delegation"),
        options=run_options,
    )
    resume_outcome = await service.resume(state.operation_id, options=run_options)
    recover_outcome = await service.recover(state.operation_id, options=run_options)
    tick_outcome = await service.tick(state.operation_id)
    cancel_outcome = await service.cancel(
        state.operation_id,
        session_id="session-1",
        run_id="run-1",
        reason="stop",
    )

    assert run_outcome == outcome
    assert resume_outcome == outcome
    assert recover_outcome == outcome
    assert tick_outcome == outcome
    assert cancel_outcome == outcome

    assert len(entrypoints.prepare_run_calls) == 1
    assert entrypoints.prepare_run_calls[0]["goal"].objective_text == "Shell delegation"
    assert len(entrypoints.load_for_resume_calls) == 2
    assert entrypoints.load_for_resume_calls[0]["operation_id"] == state.operation_id
    assert entrypoints.load_for_resume_calls[0]["options"] == run_options
    assert len(entrypoints.load_for_recover_calls) == 1
    assert entrypoints.load_for_recover_calls[0]["operation_id"] == state.operation_id
    assert entrypoints.tick_options_calls == [None]

    assert [call[0] for call in drive.calls] == [state, state, state, state]
    assert drive.calls[0][1] == run_options
    assert drive.calls[1][1] == run_options
    assert drive.calls[2][1] == run_options
    assert drive.calls[3][1].max_cycles == 1

    assert len(cancellation.calls) == 1
    assert cancellation.calls[0]["operation_id"] == state.operation_id
    assert cancellation.calls[0]["session_id"] == "session-1"
    assert cancellation.calls[0]["run_id"] == "run-1"
    assert cancellation.calls[0]["reason"] == "stop"

    saved_state = await store.load_operation(state.operation_id)
    assert saved_state is state
    assert any(event.kind.value == "trace" for event in events.events)


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
