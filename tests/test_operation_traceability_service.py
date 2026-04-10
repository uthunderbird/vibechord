from __future__ import annotations

from datetime import UTC, datetime

import pytest

from agent_operator.application.attached_session_registry import AttachedSessionRuntimeRegistry
from agent_operator.application.loaded_operation import LoadedOperation
from agent_operator.application.queries.operation_traceability import OperationTraceabilityService
from agent_operator.application.runtime.operation_runtime_context import OperationRuntimeContext
from agent_operator.domain import (
    AgentResult,
    AgentResultStatus,
    AgentSessionHandle,
    AgentTurnSummary,
    ArtifactRecord,
    AttentionRequest,
    AttentionType,
    BackgroundRunStatus,
    BrainActionType,
    BrainDecision,
    ExecutionState,
    FocusKind,
    FocusMode,
    FocusState,
    IterationState,
    MemoryEntry,
    MemoryFreshness,
    MemoryScope,
    MemorySourceRef,
    OperationGoal,
    OperationState,
    OperationStatus,
    RunMode,
    RunOptions,
    SessionRecord,
    SessionRecordStatus,
    TaskState,
    TaskStatus,
)
from agent_operator.testing.operator_service_support import (
    FakeAgent,
    MemoryEventSink,
    MemoryStore,
    MemoryTraceStore,
    StartThenStopBrain,
    make_service,
    run_settings,
    state_settings,
)
from agent_operator.testing.runtime_bindings import build_test_runtime_bindings


def _build_service(trace_store: MemoryTraceStore) -> OperationTraceabilityService:
    registry = AttachedSessionRuntimeRegistry({})
    loaded_operation = LoadedOperation(attached_session_registry=registry)
    return OperationTraceabilityService(
        loaded_operation=loaded_operation,
        trace_store=trace_store,
        runtime_context=OperationRuntimeContext(
            loaded_operation=loaded_operation,
            attached_session_registry=registry,
        ),
    )


def test_sync_traceability_artifacts_writes_brief_and_report_sections() -> None:
    trace_store = MemoryTraceStore()
    service = _build_service(trace_store)
    state = OperationState(
        goal=OperationGoal(
            objective="Fix the issue",
            harness_instructions="Use swarm when unclear.",
        ),
        **state_settings(),
        status=OperationStatus.COMPLETED,
        final_summary="Completed successfully.",
        tasks=[
            TaskState(
                task_id="task-1",
                title="Primary objective",
                goal="Fix the issue",
                definition_of_done="Return the final report.",
                status=TaskStatus.COMPLETED,
                brain_priority=100,
                effective_priority=100,
                assigned_agent="claude_acp",
                linked_session_id="session-1",
                memory_refs=["memory-1"],
                artifact_refs=["artifact-1"],
            )
        ],
        sessions=[
            SessionRecord(
                handle=AgentSessionHandle(
                    adapter_key="claude_acp",
                    session_id="session-1",
                    session_name="repo-audit",
                )
            )
        ],
        artifacts=[
            ArtifactRecord(
                artifact_id="artifact-1",
                kind="final_note",
                producer="claude_acp",
                task_id="task-1",
                session_id="session-1",
                content="Returned two integration points with a concise final note.",
                raw_ref="/tmp/artifact-1.md",
            )
        ],
        memory_entries=[
            MemoryEntry(
                memory_id="memory-1",
                scope=MemoryScope.TASK,
                scope_id="task-1",
                summary="Durable task memory captured from the final artifact.",
                freshness=MemoryFreshness.CURRENT,
                source_refs=[MemorySourceRef(kind="artifact", ref_id="artifact-1")],
            )
        ],
        attention_requests=[
            AttentionRequest(
                operation_id="op-1",
                attention_type=AttentionType.QUESTION,
                title="Need approval",
                question="Approve the release?",
                blocking=True,
            )
        ],
    )

    import anyio

    anyio.run(service.sync_traceability_artifacts, state)

    assert trace_store.bundle.operation_brief is not None
    assert trace_store.report is not None
    assert "## Tasks" in trace_store.report
    assert "## Memory" in trace_store.report
    assert "## Artifacts" in trace_store.report
    assert "## Open Attention" in trace_store.report
    assert "Durable task memory captured from the final artifact." in trace_store.report


def test_recording_traceability_artifacts_updates_bundle_and_trace_records() -> None:
    trace_store = MemoryTraceStore()
    service = _build_service(trace_store)
    state = OperationState(
        goal=OperationGoal(objective="Fix the issue"),
        **state_settings(),
    )
    iteration = IterationState(
        index=1,
        decision=BrainDecision(
            action_type=BrainActionType.START_AGENT,
            target_agent="claude_acp",
            instruction="inspect the repo",
            rationale="Use Claude for the task.",
            expected_outcome="Return findings.",
        ),
        session=AgentSessionHandle(
            adapter_key="claude_acp",
            session_id="session-1",
            session_name="repo-audit",
        ),
        result=AgentResult(
            session_id="session-1",
            status=AgentResultStatus.SUCCESS,
            output_text="completed by fake agent",
        ),
        turn_summary=AgentTurnSummary(
            declared_goal="Inspect the repo",
            actual_work_done="Reviewed the repository.",
            state_delta="Persisted turn summary.",
            verification_status="Not verified.",
            recommended_next_step="Stop.",
        ),
    )
    state.iterations.append(iteration)
    task = TaskState(
        task_id="task-1",
        title="Inspect repo",
        goal="Inspect the repo",
        definition_of_done="Return findings.",
        status=TaskStatus.COMPLETED,
        brain_priority=100,
        effective_priority=100,
    )
    artifact = ArtifactRecord(
        artifact_id="artifact-1",
        kind="final_note",
        producer="claude_acp",
        task_id="task-1",
        session_id="session-1",
        content="Returned findings.",
    )

    import anyio

    anyio.run(service.record_decision_memo, state, iteration, task)
    anyio.run(
        service.record_agent_turn_brief,
        state,
        iteration,
        task,
        iteration.session,
        iteration.result,
        artifact,
    )
    anyio.run(service.record_iteration_brief, state, iteration, task)

    assert trace_store.memos
    assert trace_store.bundle.agent_turn_briefs
    assert trace_store.bundle.iteration_briefs
    assert any(record.category == "decision" for record in trace_store.trace_records)
    assert any(record.category == "agent_turn" for record in trace_store.trace_records)
    assert any(record.category == "iteration" for record in trace_store.trace_records)


def test_runtime_alert_brief_ignores_terminal_background_run_when_live_run_exists() -> None:
    service = _build_service(MemoryTraceStore())
    state = OperationState(
        goal=OperationGoal(objective="background wait"),
        **state_settings(max_iterations=3, allowed_agents=["claude_acp"]),
        status=OperationStatus.RUNNING,
    )
    state.current_focus = FocusState(
        kind=FocusKind.SESSION,
        target_id="session-1",
        mode=FocusMode.BLOCKING,
        blocking_reason="waiting on background run",
    )
    state.background_runs = [
        ExecutionState(
            run_id="run-old",
            operation_id=state.operation_id,
            adapter_key="claude_acp",
            session_id="session-1",
            status=BackgroundRunStatus.COMPLETED,
        ),
        ExecutionState(
            run_id="run-new",
            operation_id=state.operation_id,
            adapter_key="claude_acp",
            session_id="session-1",
            status=BackgroundRunStatus.RUNNING,
        ),
    ]

    assert service.build_runtime_alert_brief(state) is None


def test_operation_brief_does_not_report_waiting_on_attached_turn_when_run_is_terminal() -> None:
    service = _build_service(MemoryTraceStore())
    session = AgentSessionHandle(
        adapter_key="claude_acp",
        session_id="session-1",
        session_name="main",
    )
    state = OperationState(
        goal=OperationGoal(objective="background wait"),
        **state_settings(max_iterations=3, allowed_agents=["claude_acp"]),
        status=OperationStatus.RUNNING,
        sessions=[
            SessionRecord(
                handle=session,
                status=SessionRecordStatus.RUNNING,
                current_execution_id="run-1",
                latest_iteration=1,
            )
        ],
        iterations=[IterationState(index=1, session=session)],
        background_runs=[
            ExecutionState(
                run_id="run-1",
                operation_id="op-1",
                adapter_key="claude_acp",
                session_id="session-1",
                status=BackgroundRunStatus.FAILED,
            )
        ],
    )

    brief = service.build_operation_brief(state)

    assert brief.blocker_brief != "Waiting on an attached agent turn."


def test_report_surfaces_durable_truth_sections() -> None:
    trace_store = MemoryTraceStore()
    service = _build_service(trace_store)
    state = OperationState(
        goal=OperationGoal(objective="Fix the issue"),
        **state_settings(),
        status=OperationStatus.COMPLETED,
        final_summary="Completed successfully.",
        artifacts=[
            ArtifactRecord(
                artifact_id="artifact-1",
                kind="final_note",
                producer="claude_acp",
                task_id="task-1",
                session_id="session-1",
                content="Returned findings.",
            )
        ],
        memory_entries=[
            MemoryEntry(
                memory_id="memory-1",
                scope=MemoryScope.TASK,
                scope_id="task-1",
                summary="Durable task memory captured from the final artifact.",
                freshness=MemoryFreshness.CURRENT,
                source_refs=[MemorySourceRef(kind="artifact", ref_id="artifact-1")],
            )
        ],
    )

    import anyio

    anyio.run(service.sync_traceability_artifacts, state)

    assert trace_store.report is not None
    assert "## Tasks" in trace_store.report
    assert "## Memory" in trace_store.report
    assert "## Artifacts" in trace_store.report
    assert "Durable task memory captured from the final artifact." in trace_store.report


@pytest.mark.anyio
async def test_attached_run_mode_writes_inflight_briefs_before_terminal_result() -> None:
    trace_store = MemoryTraceStore()
    store = MemoryStore()

    class SlowCollectAgent(FakeAgent):
        async def collect(self, handle) -> AgentResult:
            return AgentResult(
                session_id=handle.session_id,
                status=AgentResultStatus.SUCCESS,
                output_text="completed by slow agent",
                completed_at=datetime.now(UTC),
            )

    service = make_service(
        brain=StartThenStopBrain(),
        store=store,
        trace_store=trace_store,
        event_sink=MemoryEventSink(),
        agent_runtime_bindings=build_test_runtime_bindings({"claude_acp": SlowCollectAgent()}),
    )

    outcome = await service.run(
        OperationGoal(objective="do the task"),
        **run_settings(max_iterations=4, allowed_agents=["claude_acp"]),
        options=RunOptions(run_mode=RunMode.ATTACHED),
    )

    bundle = await trace_store.load_brief_bundle(outcome.operation_id)
    assert bundle is not None
    assert bundle.iteration_briefs
    assert bundle.agent_turn_briefs
    assert bundle.agent_turn_briefs[0].assignment_brief == (
        "Asked claude_acp via session session-1 to do the task"
    )
