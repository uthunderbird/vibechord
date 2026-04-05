from __future__ import annotations

from datetime import UTC, datetime

from agent_operator.domain import (
    AttentionRequest,
    AttentionStatus,
    AttentionType,
    CommandTargetScope,
    ExecutionLaunchKind,
    ExecutionMode,
    ExecutionObservedState,
    ExecutionState,
    ObjectiveState,
    OperationCheckpoint,
    OperationStatus,
    OperatorMessage,
    PolicyCoverage,
    SchedulerState,
    SessionObservedState,
    SessionState,
    SessionTerminalState,
    StoredOperationDomainEvent,
    TaskState,
)
from agent_operator.projectors import DefaultOperationProjector


def _event(
    event_type: str,
    *,
    sequence: int,
    payload: dict[str, object],
) -> StoredOperationDomainEvent:
    return StoredOperationDomainEvent(
        operation_id="op-1",
        sequence=sequence,
        event_type=event_type,
        payload=payload,
        timestamp=datetime(2026, 4, 3, 12, 0, sequence, tzinfo=UTC),
    )


def test_operation_projector_projects_operation_and_task_slices() -> None:
    projector = DefaultOperationProjector()
    checkpoint = OperationCheckpoint.initial("op-1")
    objective = ObjectiveState(
        objective="Ship the feature",
    )
    task = TaskState(
        task_id="task-1",
        title="Primary objective",
        goal="Ship the feature",
        definition_of_done="Done",
    )

    projected = projector.project(
        checkpoint,
        [
            _event("operation.created", sequence=1, payload=objective.model_dump()),
            _event("task.created", sequence=2, payload=task.model_dump()),
            _event(
                "task.updated",
                sequence=3,
                payload={
                    "task_id": "task-1",
                    "status": "running",
                    "assigned_agent": "codex_acp",
                },
            ),
            _event(
                "operation.status.changed",
                sequence=4,
                payload={"status": "completed", "final_summary": "done"},
            ),
        ],
    )

    assert projected.objective is not None
    assert projected.objective.objective == "Ship the feature"
    assert projected.status is OperationStatus.COMPLETED
    assert projected.final_summary == "done"
    assert projected.tasks[0].status.value == "running"
    assert projected.tasks[0].assigned_agent == "codex_acp"


def test_operation_projector_coordinates_execution_and_session_slices() -> None:
    projector = DefaultOperationProjector()
    checkpoint = OperationCheckpoint.initial("op-1")
    session = SessionState.model_validate(
        {
            "handle": {
                "adapter_key": "codex_acp",
                "session_id": "session-1",
            }
        }
    )
    execution = ExecutionState(
        execution_id="execution-1",
        operation_id="op-1",
        adapter_key="codex_acp",
        session_id="session-1",
        mode=ExecutionMode.BACKGROUND,
        launch_kind=ExecutionLaunchKind.NEW,
    )

    projected = projector.project(
        checkpoint,
        [
            _event("session.created", sequence=1, payload=session.model_dump()),
            _event("execution.registered", sequence=2, payload=execution.model_dump()),
            _event(
                "execution.observed_state.changed",
                sequence=3,
                payload={
                    "execution_id": "execution-1",
                    "observed_state": "running",
                },
            ),
            _event(
                "execution.observed_state.changed",
                sequence=4,
                payload={
                    "execution_id": "execution-1",
                    "observed_state": "completed",
                    "completed_at": "2026-04-03T12:00:04+00:00",
                },
            ),
        ],
    )

    assert projected.executions[0].observed_state is ExecutionObservedState.COMPLETED
    assert projected.sessions[0].current_execution_id is None
    assert projected.sessions[0].last_terminal_execution_id == "execution-1"
    assert projected.sessions[0].observed_state is SessionObservedState.TERMINAL
    assert projected.sessions[0].terminal_state is SessionTerminalState.COMPLETED


def test_operation_projector_updates_attention_scheduler_and_optional_subslices() -> None:
    projector = DefaultOperationProjector()
    checkpoint = OperationCheckpoint.initial("op-1")
    attention = AttentionRequest(
        attention_id="attention-1",
        operation_id="op-1",
        attention_type=AttentionType.QUESTION,
        target_scope=CommandTargetScope.OPERATION,
        title="Clarify",
        question="Which path?",
        blocking=True,
    )
    operator_message = OperatorMessage(message_id="msg-1", text="Replan around the blocker.")
    policy_coverage = PolicyCoverage(
        status="covered",
        project_scope="project-1",
        scoped_policy_count=1,
        active_policy_count=1,
        summary="1 active policy entry applies now.",
    )

    projected = projector.project(
        checkpoint,
        [
            _event("attention.request.created", sequence=1, payload=attention.model_dump()),
            _event(
                "scheduler.state.changed",
                sequence=2,
                payload={"scheduler_state": "paused"},
            ),
            _event("operator_message.received", sequence=3, payload=operator_message.model_dump()),
            _event("policy.coverage.updated", sequence=4, payload=policy_coverage.model_dump()),
            _event(
                "attention.request.resolved",
                sequence=5,
                payload={"attention_id": "attention-1", "status": "resolved"},
            ),
            _event(
                "operator_message.dropped_from_context",
                sequence=6,
                payload={"message_id": "msg-1"},
            ),
        ],
    )

    assert projected.scheduler_state is SchedulerState.PAUSED
    assert projected.policy_coverage.project_scope == "project-1"
    assert projected.attention_requests[0].status is AttentionStatus.RESOLVED
    assert projected.status is OperationStatus.RUNNING
    assert projected.operator_messages == []


def test_operation_projector_is_deterministic_for_same_input_suffix() -> None:
    projector = DefaultOperationProjector()
    checkpoint = OperationCheckpoint.initial("op-1")
    events = [
        _event(
            "operation.status.changed",
            sequence=1,
            payload={"status": "running"},
        ),
        _event(
            "scheduler.state.changed",
            sequence=2,
            payload={"scheduler_state": "pause_requested"},
        ),
    ]

    first = projector.project(checkpoint, events)
    second = projector.project(checkpoint, events)

    assert first == second
