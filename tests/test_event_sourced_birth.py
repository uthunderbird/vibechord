from __future__ import annotations

import pytest

from agent_operator.application.event_sourcing.event_sourced_birth import (
    EventSourcedOperationBirthService,
)
from agent_operator.application.queries import (
    OperationReadModelProjectionWriter,
    OperationReadModelProjector,
)
from agent_operator.domain import (
    AgentSessionHandle,
    CanonicalPersistenceMode,
    ExternalTicketLink,
    OperationGoal,
    OperationPolicy,
    OperationState,
    SessionState,
)
from agent_operator.projectors import DefaultOperationProjector
from agent_operator.runtime import (
    FileOperationCheckpointStore,
    FileOperationEventStore,
    FileReadModelProjectionStore,
)


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
        goal=OperationGoal(
            objective="Inspect the repository.",
            external_ticket=ExternalTicketLink(
                provider="github_issues",
                project_key="owner/repo",
                ticket_id="123",
                url="https://github.com/owner/repo/issues/123",
                title="Inspect the repository",
            ),
        ),
        policy=OperationPolicy(),
    )
    session = AgentSessionHandle(adapter_key="claude_acp", session_id="session-1")
    state.sessions.append(SessionState(handle=session))

    result = await service.birth(state)

    assert state.canonical_persistence_mode is CanonicalPersistenceMode.EVENT_SOURCED
    assert [event.event_type for event in result.stored_events] == [
        "operation.created",
        "operation.ticket_linked",
        "session.created",
    ]
    assert result.checkpoint.objective is not None
    assert result.checkpoint.objective.objective == "Inspect the repository."
    assert result.checkpoint.external_ticket is not None
    assert result.checkpoint.external_ticket.ticket_id == "123"
    assert len(result.checkpoint.sessions) == 1
    assert result.checkpoint.sessions[0].session_id == "session-1"
    assert result.checkpoint_record.last_applied_sequence == 3
    persisted = await checkpoint_store.load_latest(operation_id)
    assert persisted is not None
    assert persisted.last_applied_sequence == 3
    stored_events = await event_store.load_after(operation_id, after_sequence=0)
    assert [event.event_type for event in stored_events] == [
        "operation.created",
        "operation.ticket_linked",
        "session.created",
    ]


@pytest.mark.anyio
async def test_event_sourced_operation_birth_refreshes_read_model_projection(
    tmp_path,
) -> None:
    """Catches newly born operations missing the initial persisted read model cursor."""
    operation_id = "op-birth-projection"
    event_store = FileOperationEventStore(tmp_path / "events")
    checkpoint_store = FileOperationCheckpointStore(tmp_path / "checkpoints")
    projection_store = FileReadModelProjectionStore(tmp_path / "read_models")
    service = EventSourcedOperationBirthService(
        event_store=event_store,
        checkpoint_store=checkpoint_store,
        projector=DefaultOperationProjector(),
        read_model_projection_writer=OperationReadModelProjectionWriter(
            event_store=event_store,
            projection_store=projection_store,
            projector=OperationReadModelProjector(),
        ),
    )
    state = OperationState(
        operation_id=operation_id,
        goal=OperationGoal(objective="Create initial persisted projection."),
        policy=OperationPolicy(),
    )

    result = await service.birth(state)

    projection = await projection_store.load(operation_id, "status")
    assert projection is not None
    assert projection.source_event_sequence == result.stored_events[-1].sequence
    assert projection.projection_payload["operation_brief"]["objective_brief"] == (
        "Create initial persisted projection."
    )
