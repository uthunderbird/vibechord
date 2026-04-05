from __future__ import annotations

import pytest

from agent_operator.application.event_sourcing.event_sourced_birth import (
    EventSourcedOperationBirthService,
)
from agent_operator.domain import (
    CanonicalPersistenceMode,
    OperationGoal,
    OperationPolicy,
    OperationState,
)
from agent_operator.projectors import DefaultOperationProjector
from agent_operator.runtime import FileOperationCheckpointStore, FileOperationEventStore


@pytest.mark.anyio
async def test_event_sourced_operation_birth_appends_initial_event_and_checkpoint(
    tmp_path,
) -> None:
    """Newly born operations persist canonical initial event-stream artifacts."""
    operation_id = "op-1"
    event_store = FileOperationEventStore(tmp_path / "events")
    checkpoint_store = FileOperationCheckpointStore(tmp_path / "checkpoints")
    service = EventSourcedOperationBirthService(
        event_store=event_store,
        checkpoint_store=checkpoint_store,
        projector=DefaultOperationProjector(),
    )
    state = OperationState(
        operation_id=operation_id,
        goal=OperationGoal(objective="Inspect the repository."),
        policy=OperationPolicy(),
    )

    result = await service.birth(state)

    assert state.canonical_persistence_mode is CanonicalPersistenceMode.EVENT_SOURCED
    assert [event.event_type for event in result.stored_events] == ["operation.created"]
    assert result.checkpoint.objective is not None
    assert result.checkpoint.objective.objective == "Inspect the repository."
    assert result.checkpoint_record.last_applied_sequence == 1
    persisted = await checkpoint_store.load_latest(operation_id)
    assert persisted is not None
    assert persisted.last_applied_sequence == 1
    stored_events = await event_store.load_after(operation_id, after_sequence=0)
    assert [event.event_type for event in stored_events] == ["operation.created"]
