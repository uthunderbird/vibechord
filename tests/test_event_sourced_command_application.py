from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from agent_operator.application.event_sourcing.event_sourced_commands import (
    EventSourcedCommandApplicationService,
)
from agent_operator.domain import (
    CommandTargetScope,
    InvolvementLevel,
    ObjectiveState,
    OperationCommand,
    OperationCommandType,
    OperationDomainEventDraft,
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
    assert result.rejection_reason == "PATCH_OBJECTIVE requires non-empty payload.text."
    assert [event.event_type for event in result.stored_events] == ["command.rejected"]
    assert result.checkpoint.objective is not None
    assert result.checkpoint.objective.objective == "Initial objective"


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
