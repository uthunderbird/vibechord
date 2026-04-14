from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from agent_operator.application.event_sourcing.event_sourced_birth import (
    EventSourcedOperationBirthService,
)
from agent_operator.application.event_sourcing.event_sourced_replay import (
    EventSourcedReplayService,
)
from agent_operator.application.operation_lifecycle import OperationLifecycleCoordinator
from agent_operator.domain import (
    AgentResult,
    AgentResultStatus,
    AgentSessionHandle,
    ExecutionObservedState,
    ExecutionState,
    FocusKind,
    FocusMode,
    FocusState,
    IterationState,
    OperationGoal,
    OperationPolicy,
    OperationState,
    OperationStatus,
    SessionObservedState,
    SessionState,
    TaskState,
)
from agent_operator.projectors import DefaultOperationProjector
from agent_operator.runtime import (
    FileOperationCheckpointStore,
    FileOperationEventStore,
    FileOperationStore,
)
from agent_operator.testing.operator_service_support import MemoryStore


async def _build_event_sourced_lifecycle(tmp_path: Path):
    store = FileOperationStore(tmp_path / "operations")
    event_store = FileOperationEventStore(tmp_path / "operation_events")
    checkpoint_store = FileOperationCheckpointStore(tmp_path / "operation_checkpoints")
    projector = DefaultOperationProjector()
    birth = EventSourcedOperationBirthService(
        event_store=event_store,
        checkpoint_store=checkpoint_store,
        projector=projector,
    )
    replay = EventSourcedReplayService(
        event_store=event_store,
        checkpoint_store=checkpoint_store,
        projector=projector,
    )
    lifecycle = OperationLifecycleCoordinator(
        store=store,
        event_store=event_store,
        replay_service=replay,
    )
    return store, event_store, birth, replay, lifecycle


@pytest.mark.anyio
async def test_finalize_outcome_persists_terminal_status_via_lifecycle_coordinator(
    tmp_path: Path,
) -> None:
    store, event_store, birth, replay, lifecycle = await _build_event_sourced_lifecycle(
        tmp_path
    )
    state = OperationState(
        operation_id="op-lifecycle-terminal",
        goal=OperationGoal(objective="Finish cleanly."),
        policy=OperationPolicy(),
    )
    await birth.birth(state)
    await store.save_operation(state)

    lifecycle.mark_completed(state, summary="Task completed canonically.")
    outcome = await lifecycle.finalize_outcome(state)

    snapshot_state = await store.load_operation(state.operation_id)
    replay_state = await replay.load(state.operation_id)
    stored_events = await event_store.load_after(state.operation_id, after_sequence=0)
    persisted_outcome = await store.load_outcome(state.operation_id)

    assert outcome.status is OperationStatus.COMPLETED
    assert outcome.summary == "Task completed canonically."
    assert snapshot_state is not None
    assert snapshot_state.status is OperationStatus.RUNNING
    assert replay_state.checkpoint.status is OperationStatus.COMPLETED
    assert replay_state.checkpoint.final_summary == "Task completed canonically."
    assert [event.event_type for event in stored_events][-1] == "operation.status.changed"
    assert persisted_outcome is not None
    assert persisted_outcome.status is OperationStatus.COMPLETED


@pytest.mark.anyio
async def test_cancel_operation_persists_event_sourced_cancellation_and_outcome(
    tmp_path: Path,
) -> None:
    store, event_store, birth, replay, lifecycle = await _build_event_sourced_lifecycle(
        tmp_path
    )
    session = AgentSessionHandle(adapter_key="claude_acp", session_id="session-1")
    state = OperationState(
        operation_id="op-lifecycle-cancel",
        goal=OperationGoal(objective="Cancel cleanly."),
        policy=OperationPolicy(),
        sessions=[
            SessionState(
                handle=session,
                observed_state=SessionObservedState.RUNNING,
                current_execution_id="run-1",
            )
        ],
        executions=[
            ExecutionState(
                execution_id="run-1",
                operation_id="op-lifecycle-cancel",
                adapter_key="claude_acp",
                session_id="session-1",
                observed_state=ExecutionObservedState.RUNNING,
            )
        ],
    )
    await birth.birth(state)
    await store.save_operation(state)

    outcome = await lifecycle.cancel_operation(
        state,
        summary="Operation cancelled by lifecycle coordinator.",
    )

    replay_state = await replay.load(state.operation_id)
    stored_events = await event_store.load_after(state.operation_id, after_sequence=0)
    persisted_outcome = await store.load_outcome(state.operation_id)

    assert outcome.status is OperationStatus.CANCELLED
    assert outcome.summary == "Operation cancelled by lifecycle coordinator."
    assert replay_state.checkpoint.status is OperationStatus.CANCELLED
    assert replay_state.checkpoint.final_summary == "Operation cancelled by lifecycle coordinator."
    assert replay_state.checkpoint.current_focus is None
    assert replay_state.checkpoint.sessions[0].status.value == "cancelled"
    assert replay_state.checkpoint.executions[0].status.value == "cancelled"
    assert persisted_outcome is not None
    assert persisted_outcome.status is OperationStatus.CANCELLED
    event_types = [event.event_type for event in stored_events]
    assert "session.waiting_reason.updated" in event_types
    assert "session.observed_state.changed" in event_types
    assert "execution.observed_state.changed" in event_types
    assert event_types[-1] == "operation.status.changed"


@pytest.mark.anyio
async def test_fold_reconciled_terminal_result_clears_blocking_focus_after_result() -> None:
    lifecycle = OperationLifecycleCoordinator(store=MemoryStore())
    session = AgentSessionHandle(adapter_key="claude_acp", session_id="session-1")
    task = TaskState(
        task_id="task-1",
        title="Inspect the repo",
        goal="Inspect the repo",
        definition_of_done="Result returned",
    )
    iteration = IterationState(index=1, task_id=task.task_id, session=session)
    state = OperationState(
        operation_id="op-lifecycle-fold",
        goal=OperationGoal(objective="Fold the reconciled result."),
        policy=OperationPolicy(),
        status=OperationStatus.RUNNING,
        current_focus=FocusState(
            kind=FocusKind.SESSION,
            target_id=session.session_id,
            mode=FocusMode.BLOCKING,
            blocking_reason="Waiting on the active agent turn.",
        ),
        iterations=[iteration],
    )
    result = AgentResult(
        session_id=session.session_id,
        status=AgentResultStatus.SUCCESS,
        output_text="Done.",
        completed_at=datetime.now(UTC),
    )
    calls: list[str] = []

    async def handle_agent_result(*args, **kwargs) -> None:  # type: ignore[no-untyped-def]
        calls.append("handle")
        args[0].iterations[0].result = result

    async def record_iteration_brief(*args, **kwargs) -> None:  # type: ignore[no-untyped-def]
        calls.append("brief")

    await lifecycle.fold_reconciled_terminal_result(
        state,
        iteration=iteration,
        task=task,
        session=session,
        result=result,
        handle_agent_result=handle_agent_result,
        record_iteration_brief=record_iteration_brief,
        clear_blocking_focus=True,
        wakeup_event_id="wakeup-1",
    )

    assert calls == ["handle", "brief"]
    assert state.iterations[0].result == result
    assert state.current_focus is None
