from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from agent_operator.application.event_sourcing.event_sourced_commands import (
    EventSourcedCommandApplicationService,
)
from agent_operator.domain import (
    AttentionStatus,
    AttentionType,
    CommandTargetScope,
    InvolvementLevel,
    ObjectiveState,
    OperationCommand,
    OperationCommandType,
    OperationDomainEventDraft,
    OperationStatus,
)
from agent_operator.projectors import DefaultOperationProjector
from agent_operator.runtime import FileOperationCheckpointStore, FileOperationEventStore


async def _seed_created_operation(
    service: EventSourcedCommandApplicationService,
    operation_id: str,
) -> None:
    """Seed one canonical event-sourced operation for command-application tests."""
    objective = ObjectiveState(
        objective="Initial objective",
        harness_instructions="Initial harness",
        success_criteria=["Done"],
    )
    await service._event_store.append(  # noqa: SLF001 - test fixture setup
        operation_id,
        0,
        [
            OperationDomainEventDraft(
                event_type="operation.created",
                payload={
                    **objective.model_dump(mode="json"),
                    "involvement_level": InvolvementLevel.AUTO.value,
                    "created_at": datetime(2026, 4, 3, tzinfo=UTC).isoformat(),
                },
            )
        ],
    )


async def _append_operation_status(
    service: EventSourcedCommandApplicationService,
    operation_id: str,
    status: OperationStatus,
    *,
    final_summary: str,
) -> None:
    """Append one terminal status event for command-application tests."""
    await service._event_store.append(  # noqa: SLF001 - test fixture setup
        operation_id,
        1,
        [
            OperationDomainEventDraft(
                event_type="operation.status.changed",
                payload={
                    "status": status.value,
                    "final_summary": final_summary,
                },
            )
        ],
    )


async def _append_open_attention_request(
    service: EventSourcedCommandApplicationService,
    operation_id: str,
    *,
    attention_id: str,
) -> None:
    """Append one blocking open attention request for command-application tests."""
    await service._event_store.append(  # noqa: SLF001 - test fixture setup
        operation_id,
        1,
        [
            OperationDomainEventDraft(
                event_type="operation.status.changed",
                payload={"status": OperationStatus.NEEDS_HUMAN.value},
            ),
            OperationDomainEventDraft(
                event_type="attention.request.created",
                payload={
                    "attention_id": attention_id,
                    "operation_id": operation_id,
                        "attention_type": AttentionType.QUESTION.value,
                    "target_scope": CommandTargetScope.OPERATION.value,
                    "target_id": operation_id,
                    "title": "Need direction",
                    "question": "Which path should the operator take?",
                    "blocking": True,
                    "status": AttentionStatus.OPEN.value,
                },
            ),
        ],
    )


@pytest.mark.anyio
async def test_event_sourced_command_application_appends_acceptance_and_updates_checkpoint(
    tmp_path: Path,
) -> None:
    event_store = FileOperationEventStore(tmp_path / "events")
    checkpoint_store = FileOperationCheckpointStore(tmp_path / "checkpoints")
    projector = DefaultOperationProjector()
    service = EventSourcedCommandApplicationService(
        event_store=event_store,
        checkpoint_store=checkpoint_store,
        projector=projector,
    )
    operation_id = "op-1"
    await _seed_created_operation(service, operation_id)
    command = OperationCommand(
        operation_id=operation_id,
        command_type=OperationCommandType.PATCH_OBJECTIVE,
        target_scope=CommandTargetScope.OPERATION,
        payload={"text": "Updated objective"},
    )

    result = await service.apply(command)

    assert result.applied is True
    assert result.rejection_reason is None
    assert [event.event_type for event in result.stored_events] == [
        "command.accepted",
        "objective.updated",
    ]
    assert result.checkpoint.objective is not None
    assert result.checkpoint.objective.objective == "Updated objective"

    persisted = await checkpoint_store.load_latest(operation_id)
    assert persisted is not None
    assert persisted.last_applied_sequence == 3


@pytest.mark.anyio
async def test_event_sourced_command_application_rejects_invalid_command_via_domain_event(
    tmp_path: Path,
) -> None:
    event_store = FileOperationEventStore(tmp_path / "events")
    checkpoint_store = FileOperationCheckpointStore(tmp_path / "checkpoints")
    projector = DefaultOperationProjector()
    service = EventSourcedCommandApplicationService(
        event_store=event_store,
        checkpoint_store=checkpoint_store,
        projector=projector,
    )
    operation_id = "op-2"
    await _seed_created_operation(service, operation_id)
    command = OperationCommand(
        operation_id=operation_id,
        command_type=OperationCommandType.PATCH_OBJECTIVE,
        target_scope=CommandTargetScope.OPERATION,
        payload={"text": ""},
    )

    result = await service.apply(command)

    assert result.applied is False
    assert (
        result.rejection_reason
        == "invalid_payload: PATCH_OBJECTIVE requires non-empty payload.text."
    )
    assert [event.event_type for event in result.stored_events] == ["command.rejected"]
    assert result.checkpoint.objective is not None
    assert result.checkpoint.objective.objective == "Initial objective"


@pytest.mark.anyio
async def test_event_sourced_command_application_rejects_patch_command_for_terminal_operation(
    tmp_path: Path,
) -> None:
    event_store = FileOperationEventStore(tmp_path / "events")
    checkpoint_store = FileOperationCheckpointStore(tmp_path / "checkpoints")
    projector = DefaultOperationProjector()
    service = EventSourcedCommandApplicationService(
        event_store=event_store,
        checkpoint_store=checkpoint_store,
        projector=projector,
    )
    operation_id = "op-terminal-patch"
    await _seed_created_operation(service, operation_id)
    await _append_operation_status(
        service,
        operation_id,
        OperationStatus.COMPLETED,
        final_summary="done",
    )
    command = OperationCommand(
        operation_id=operation_id,
        command_type=OperationCommandType.PATCH_HARNESS,
        target_scope=CommandTargetScope.OPERATION,
        payload={"text": "Try to patch a completed operation."},
    )

    result = await service.apply(command)

    assert result.applied is False
    assert result.rejection_reason == "operation_terminal: operation is already completed."
    assert [event.event_type for event in result.stored_events] == ["command.rejected"]
    assert result.checkpoint.status is OperationStatus.COMPLETED
    assert result.checkpoint.objective is not None
    assert result.checkpoint.objective.harness_instructions == "Initial harness"


@pytest.mark.anyio
async def test_event_sourced_command_application_updates_success_criteria(
    tmp_path: Path,
) -> None:
    event_store = FileOperationEventStore(tmp_path / "events")
    checkpoint_store = FileOperationCheckpointStore(tmp_path / "checkpoints")
    projector = DefaultOperationProjector()
    service = EventSourcedCommandApplicationService(
        event_store=event_store,
        checkpoint_store=checkpoint_store,
        projector=projector,
    )
    operation_id = "op-success-criteria"
    await _seed_created_operation(service, operation_id)
    command = OperationCommand(
        operation_id=operation_id,
        command_type=OperationCommandType.PATCH_SUCCESS_CRITERIA,
        target_scope=CommandTargetScope.OPERATION,
        payload={"success_criteria": ["Ship it", "", "Verify it"]},
    )

    result = await service.apply(command)

    assert result.applied is True
    assert [event.event_type for event in result.stored_events] == [
        "command.accepted",
        "objective.updated",
    ]
    assert result.checkpoint.objective is not None
    assert result.checkpoint.objective.success_criteria == ["Ship it", "Verify it"]


@pytest.mark.anyio
async def test_event_sourced_command_application_cancels_operation_via_stop_command(
    tmp_path: Path,
) -> None:
    event_store = FileOperationEventStore(tmp_path / "events")
    checkpoint_store = FileOperationCheckpointStore(tmp_path / "checkpoints")
    projector = DefaultOperationProjector()
    service = EventSourcedCommandApplicationService(
        event_store=event_store,
        checkpoint_store=checkpoint_store,
        projector=projector,
    )
    operation_id = "op-stop"
    await _seed_created_operation(service, operation_id)
    command = OperationCommand(
        operation_id=operation_id,
        command_type=OperationCommandType.STOP_OPERATION,
        target_scope=CommandTargetScope.OPERATION,
        target_id=operation_id,
        payload={"reason": "user requested"},
    )

    result = await service.apply(command)

    assert result.applied is True
    assert [event.event_type for event in result.stored_events] == [
        "command.accepted",
        "operation.status.changed",
        "operation.focus.updated",
        "scheduler.state.changed",
    ]
    assert result.checkpoint.status is OperationStatus.CANCELLED
    assert result.checkpoint.final_summary == "Operation cancelled: user requested."

    persisted = await checkpoint_store.load_latest(operation_id)
    assert persisted is not None
    assert persisted.last_applied_sequence == 5


@pytest.mark.anyio
async def test_event_sourced_command_application_rejects_stop_command_for_terminal_operation(
    tmp_path: Path,
) -> None:
    event_store = FileOperationEventStore(tmp_path / "events")
    checkpoint_store = FileOperationCheckpointStore(tmp_path / "checkpoints")
    projector = DefaultOperationProjector()
    service = EventSourcedCommandApplicationService(
        event_store=event_store,
        checkpoint_store=checkpoint_store,
        projector=projector,
    )
    operation_id = "op-terminal-stop"
    await _seed_created_operation(service, operation_id)
    await _append_operation_status(
        service,
        operation_id,
        OperationStatus.CANCELLED,
        final_summary="already cancelled",
    )
    command = OperationCommand(
        operation_id=operation_id,
        command_type=OperationCommandType.STOP_OPERATION,
        target_scope=CommandTargetScope.OPERATION,
        target_id=operation_id,
    )

    result = await service.apply(command)

    assert result.applied is False
    assert result.rejection_reason == "operation_terminal: operation is already cancelled."
    assert [event.event_type for event in result.stored_events] == ["command.rejected"]
    assert result.checkpoint.status is OperationStatus.CANCELLED


@pytest.mark.anyio
async def test_event_sourced_command_application_projects_operator_message_into_checkpoint(
    tmp_path: Path,
) -> None:
    event_store = FileOperationEventStore(tmp_path / "events")
    checkpoint_store = FileOperationCheckpointStore(tmp_path / "checkpoints")
    projector = DefaultOperationProjector()
    service = EventSourcedCommandApplicationService(
        event_store=event_store,
        checkpoint_store=checkpoint_store,
        projector=projector,
    )
    operation_id = "op-3"
    await _seed_created_operation(service, operation_id)
    command = OperationCommand(
        operation_id=operation_id,
        command_type=OperationCommandType.INJECT_OPERATOR_MESSAGE,
        target_scope=CommandTargetScope.OPERATION,
        payload={"text": "Use swarm before choosing the route."},
    )

    result = await service.apply(command)

    assert result.applied is True
    assert [event.event_type for event in result.stored_events] == [
        "command.accepted",
        "operator_message.received",
    ]
    assert len(result.checkpoint.operator_messages) == 1
    message = result.checkpoint.operator_messages[0]
    assert message.text == "Use swarm before choosing the route."
    assert message.source_command_id == command.command_id
    assert message.applied_at is not None


@pytest.mark.anyio
async def test_event_sourced_command_application_answers_attention_via_canonical_events(
    tmp_path: Path,
) -> None:
    event_store = FileOperationEventStore(tmp_path / "events")
    checkpoint_store = FileOperationCheckpointStore(tmp_path / "checkpoints")
    projector = DefaultOperationProjector()
    service = EventSourcedCommandApplicationService(
        event_store=event_store,
        checkpoint_store=checkpoint_store,
        projector=projector,
    )
    operation_id = "op-answer-attention"
    await _seed_created_operation(service, operation_id)
    await _append_open_attention_request(
        service,
        operation_id,
        attention_id="attention-1",
    )
    command = OperationCommand(
        operation_id=operation_id,
        command_type=OperationCommandType.ANSWER_ATTENTION_REQUEST,
        target_scope=CommandTargetScope.ATTENTION_REQUEST,
        target_id="attention-1",
        payload={"text": "Use the canonical path."},
    )

    result = await service.apply(command)

    assert result.applied is True
    assert [event.event_type for event in result.stored_events] == [
        "command.accepted",
        "attention.request.answered",
        "operation.status.changed",
    ]
    assert result.checkpoint.status is OperationStatus.RUNNING
    assert len(result.checkpoint.attention_requests) == 1
    attention = result.checkpoint.attention_requests[0]
    assert attention.status is AttentionStatus.ANSWERED
    assert attention.answer_text == "Use the canonical path."


@pytest.mark.anyio
async def test_event_sourced_command_application_updates_involvement_level(
    tmp_path: Path,
) -> None:
    event_store = FileOperationEventStore(tmp_path / "events")
    checkpoint_store = FileOperationCheckpointStore(tmp_path / "checkpoints")
    projector = DefaultOperationProjector()
    service = EventSourcedCommandApplicationService(
        event_store=event_store,
        checkpoint_store=checkpoint_store,
        projector=projector,
    )
    operation_id = "op-4"
    await _seed_created_operation(service, operation_id)
    command = OperationCommand(
        operation_id=operation_id,
        command_type=OperationCommandType.SET_INVOLVEMENT_LEVEL,
        target_scope=CommandTargetScope.OPERATION,
        payload={"level": "approval_heavy"},
    )

    result = await service.apply(command)

    assert result.applied is True
    assert [event.event_type for event in result.stored_events] == [
        "command.accepted",
        "operation.involvement_level.updated",
    ]
    assert result.checkpoint.involvement_level.value == "approval_heavy"


@pytest.mark.anyio
async def test_event_sourced_command_application_updates_allowed_agents(
    tmp_path: Path,
) -> None:
    event_store = FileOperationEventStore(tmp_path / "events")
    checkpoint_store = FileOperationCheckpointStore(tmp_path / "checkpoints")
    projector = DefaultOperationProjector()
    service = EventSourcedCommandApplicationService(
        event_store=event_store,
        checkpoint_store=checkpoint_store,
        projector=projector,
    )
    operation_id = "op-allowed-agents"
    await _seed_created_operation(service, operation_id)
    command = OperationCommand(
        operation_id=operation_id,
        command_type=OperationCommandType.SET_ALLOWED_AGENTS,
        target_scope=CommandTargetScope.OPERATION,
        payload={"allowed_agents": ["claude_acp", "", "codex_acp"]},
    )

    result = await service.apply(command)

    assert result.applied is True
    assert [event.event_type for event in result.stored_events] == [
        "command.accepted",
        "operation.allowed_agents.updated",
    ]
    assert result.checkpoint.allowed_agents == ["claude_acp", "codex_acp"]


@pytest.mark.anyio
async def test_event_sourced_command_application_updates_execution_profile(
    tmp_path: Path,
) -> None:
    event_store = FileOperationEventStore(tmp_path / "events")
    checkpoint_store = FileOperationCheckpointStore(tmp_path / "checkpoints")
    projector = DefaultOperationProjector()
    service = EventSourcedCommandApplicationService(
        event_store=event_store,
        checkpoint_store=checkpoint_store,
        projector=projector,
    )
    operation_id = "op-execution-profile"
    await _seed_created_operation(service, operation_id)
    command = OperationCommand(
        operation_id=operation_id,
        command_type=OperationCommandType.SET_EXECUTION_PROFILE,
        target_scope=CommandTargetScope.OPERATION,
        payload={
            "adapter_key": "codex_acp",
            "model": "gpt-5.4",
            "effort": "low",
            "approval_policy": "never",
            "sandbox_mode": "workspace-write",
        },
    )

    result = await service.apply(command)

    assert result.applied is True
    assert [event.event_type for event in result.stored_events] == [
        "command.accepted",
        "operation.execution_profile.updated",
    ]
    profile = result.checkpoint.execution_profile_overrides["codex_acp"]
    assert profile.model == "gpt-5.4"
    assert profile.reasoning_effort == "low"
    assert profile.approval_policy == "never"
    assert profile.sandbox_mode == "workspace-write"


@pytest.mark.anyio
async def test_event_sourced_command_application_pauses_scheduler(
    tmp_path: Path,
) -> None:
    event_store = FileOperationEventStore(tmp_path / "events")
    checkpoint_store = FileOperationCheckpointStore(tmp_path / "checkpoints")
    projector = DefaultOperationProjector()
    service = EventSourcedCommandApplicationService(
        event_store=event_store,
        checkpoint_store=checkpoint_store,
        projector=projector,
    )
    operation_id = "op-5"
    await _seed_created_operation(service, operation_id)
    command = OperationCommand(
        operation_id=operation_id,
        command_type=OperationCommandType.PAUSE_OPERATOR,
        target_scope=CommandTargetScope.OPERATION,
    )

    result = await service.apply(command)

    assert result.applied is True
    assert [event.event_type for event in result.stored_events] == [
        "command.accepted",
        "scheduler.state.changed",
    ]
    assert result.checkpoint.scheduler_state.value == "paused"


@pytest.mark.anyio
async def test_event_sourced_command_application_rejects_resume_when_not_paused(
    tmp_path: Path,
) -> None:
    event_store = FileOperationEventStore(tmp_path / "events")
    checkpoint_store = FileOperationCheckpointStore(tmp_path / "checkpoints")
    projector = DefaultOperationProjector()
    service = EventSourcedCommandApplicationService(
        event_store=event_store,
        checkpoint_store=checkpoint_store,
        projector=projector,
    )
    operation_id = "op-6"
    await _seed_created_operation(service, operation_id)
    command = OperationCommand(
        operation_id=operation_id,
        command_type=OperationCommandType.RESUME_OPERATOR,
        target_scope=CommandTargetScope.OPERATION,
    )

    result = await service.apply(command)

    assert result.applied is False
    assert result.rejection_reason == "Operator is not paused."
    assert [event.event_type for event in result.stored_events] == ["command.rejected"]
    assert result.checkpoint.scheduler_state.value == "active"


@pytest.mark.anyio
async def test_event_sourced_command_application_is_idempotent_by_command_id(
    tmp_path: Path,
) -> None:
    event_store = FileOperationEventStore(tmp_path / "events")
    checkpoint_store = FileOperationCheckpointStore(tmp_path / "checkpoints")
    projector = DefaultOperationProjector()
    service = EventSourcedCommandApplicationService(
        event_store=event_store,
        checkpoint_store=checkpoint_store,
        projector=projector,
    )
    operation_id = "op-duplicate-command"
    await _seed_created_operation(service, operation_id)
    command = OperationCommand(
        command_id="cmd-duplicate",
        operation_id=operation_id,
        command_type=OperationCommandType.INJECT_OPERATOR_MESSAGE,
        target_scope=CommandTargetScope.OPERATION,
        payload={"text": "Only apply once."},
    )

    first = await service.apply(command)
    second = await service.apply(command)

    assert first.applied is True
    assert [event.event_type for event in first.stored_events] == [
        "command.accepted",
        "operator_message.received",
    ]
    assert second.applied is True
    assert second.stored_events == []
    assert [message.text for message in second.checkpoint.operator_messages] == [
        "Only apply once."
    ]
