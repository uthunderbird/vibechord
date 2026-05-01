from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from agent_operator.domain import (
    OperationCheckpoint,
    OperationCheckpointRecord,
    OperationDomainEventDraft,
    OperationState,
)
from agent_operator.protocols import (
    OperationCheckpointStore,
    OperationEventStore,
    OperationProjector,
)


class ReadModelProjectionWriterLike(Protocol):
    async def refresh(self, operation_id: str) -> object: ...


@dataclass(slots=True)
class EventSourcedOperationBirthResult:
    """Result of creating the canonical birth state for one operation.

    Attributes:
        checkpoint: Derived checkpoint after the initial birth event.
        checkpoint_record: Persisted checkpoint record for replay acceleration.
        stored_events: Stored canonical birth events.
    """

    checkpoint: OperationCheckpoint
    checkpoint_record: OperationCheckpointRecord
    stored_events: list


class EventSourcedOperationBirthService:
    """Create canonical initial state for a newly born event-sourced operation.

    This service appends the initial operation birth event and materializes the first checkpoint so
    that new operations have canonical event-stream truth from their first persisted write.

    Examples:
        >>> service = EventSourcedOperationBirthService(  # doctest: +SKIP
        ...     event_store=None,
        ...     checkpoint_store=None,
        ...     projector=None,
        ... )
    """

    _CHECKPOINT_FORMAT_VERSION = 1

    def __init__(
        self,
        *,
        event_store: OperationEventStore,
        checkpoint_store: OperationCheckpointStore,
        projector: OperationProjector,
        read_model_projection_writer: ReadModelProjectionWriterLike | None = None,
    ) -> None:
        self._event_store = event_store
        self._checkpoint_store = checkpoint_store
        self._projector = projector
        self._read_model_projection_writer = read_model_projection_writer

    async def birth(
        self,
        state: OperationState,
    ) -> EventSourcedOperationBirthResult:
        """Persist the canonical birth event and first derived checkpoint.

        Args:
            state: Newly created operation state whose canonical birth should be materialized.

        Returns:
            Stored canonical birth artifacts for the operation.
        """
        payload = {
            **state.objective_state.model_dump(mode="json"),
            "allowed_agents": list(state.policy.allowed_agents),
            "involvement_level": state.involvement_level.value,
            "created_at": state.created_at.isoformat(),
        }
        event_drafts = [
            OperationDomainEventDraft(
                event_type="operation.created",
                payload=payload,
            )
        ]
        if state.goal.external_ticket is not None:
            event_drafts.append(
                OperationDomainEventDraft(
                    event_type="operation.ticket_linked",
                    payload=state.goal.external_ticket.model_dump(mode="json"),
                )
            )
        event_drafts.extend(
            OperationDomainEventDraft(
                event_type="session.created",
                payload=session.model_dump(mode="json"),
            )
            for session in state.sessions
        )
        stored_events = await self._event_store.append(
            state.operation_id,
            0,
            event_drafts,
        )
        checkpoint = self._projector.project(
            OperationCheckpoint.initial(state.operation_id, created_at=state.created_at),
            stored_events,
        )
        checkpoint_record = OperationCheckpointRecord(
            operation_id=state.operation_id,
            checkpoint_payload=checkpoint.model_dump(mode="json"),
            last_applied_sequence=stored_events[-1].sequence,
            checkpoint_format_version=self._CHECKPOINT_FORMAT_VERSION,
        )
        await self._checkpoint_store.save(checkpoint_record)
        await self._refresh_read_model_projection(state.operation_id)
        return EventSourcedOperationBirthResult(
            checkpoint=checkpoint,
            checkpoint_record=checkpoint_record,
            stored_events=stored_events,
        )

    async def _refresh_read_model_projection(self, operation_id: str) -> None:
        if self._read_model_projection_writer is None:
            return
        await self._read_model_projection_writer.refresh(operation_id)
