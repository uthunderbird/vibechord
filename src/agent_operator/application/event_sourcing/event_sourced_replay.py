from __future__ import annotations

from contextlib import suppress
from dataclasses import dataclass

from agent_operator.domain import (
    OperationCheckpoint,
    OperationCheckpointRecord,
    StoredOperationDomainEvent,
)
from agent_operator.protocols import (
    OperationCheckpointStore,
    OperationEventStore,
    OperationProjector,
)


@dataclass(slots=True)
class EventSourcedReplayState:
    """Canonical replay result for one operation.

    Attributes:
        operation_id: Owning operation identifier.
        checkpoint: Canonical checkpoint after suffix projection.
        last_applied_sequence: Highest event sequence represented in `checkpoint`.
        suffix_events: Event suffix projected after the stored checkpoint.
        stored_checkpoint: Last persisted checkpoint record, if any.
    """

    operation_id: str
    checkpoint: OperationCheckpoint
    last_applied_sequence: int
    suffix_events: list[StoredOperationDomainEvent]
    stored_checkpoint: OperationCheckpointRecord | None


class EventSourcedReplayService:
    """Canonical live replay and checkpoint materialization authority.

    This service loads live operation truth from the latest stored checkpoint plus the domain-event
    suffix after `last_applied_sequence`. It does not consult mutable snapshot state.

    Examples:
        >>> service = EventSourcedReplayService(  # doctest: +SKIP
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
    ) -> None:
        self._event_store = event_store
        self._checkpoint_store = checkpoint_store
        self._projector = projector

    async def load(self, operation_id: str) -> EventSourcedReplayState:
        """Load canonical live truth from checkpoint plus suffix."""
        stored_checkpoint = await self._checkpoint_store.load_latest(operation_id)
        last_stream_sequence = await self._event_store.load_last_sequence(operation_id)
        checkpoint_sequence = stored_checkpoint.last_applied_sequence if stored_checkpoint else 0
        if checkpoint_sequence > last_stream_sequence:
            raise ValueError(
                f"Checkpoint for operation {operation_id!r} is ahead of stream: "
                f"{checkpoint_sequence} > {last_stream_sequence}."
            )
        checkpoint = self._load_checkpoint(operation_id, stored_checkpoint)
        suffix_events = await self._event_store.load_after(
            operation_id,
            after_sequence=checkpoint_sequence,
        )
        projected = self._projector.project(checkpoint, suffix_events)
        last_applied_sequence = suffix_events[-1].sequence if suffix_events else checkpoint_sequence
        return EventSourcedReplayState(
            operation_id=operation_id,
            checkpoint=projected,
            last_applied_sequence=last_applied_sequence,
            suffix_events=suffix_events,
            stored_checkpoint=stored_checkpoint,
        )

    async def materialize(
        self,
        state: EventSourcedReplayState,
    ) -> OperationCheckpointRecord:
        """Persist the latest derived checkpoint for a replayed state."""
        record = OperationCheckpointRecord(
            operation_id=state.operation_id,
            checkpoint_payload=state.checkpoint.model_dump(mode="json"),
            last_applied_sequence=state.last_applied_sequence,
            checkpoint_format_version=self._CHECKPOINT_FORMAT_VERSION,
        )
        await self._checkpoint_store.save(record)
        return record

    def advance(
        self,
        state: EventSourcedReplayState,
        events: list[StoredOperationDomainEvent],
    ) -> EventSourcedReplayState:
        """Project new stored events onto an already replayed canonical state.

        Args:
            state: Previously replayed canonical state.
            events: Newly stored ordered domain events.

        Returns:
            Updated replay state after projecting `events`.
        """
        if not events:
            return state
        return EventSourcedReplayState(
            operation_id=state.operation_id,
            checkpoint=self._projector.project(state.checkpoint, events),
            last_applied_sequence=events[-1].sequence,
            suffix_events=[*state.suffix_events, *events],
            stored_checkpoint=state.stored_checkpoint,
        )

    async def load_aggregate(
        self,
        operation_id: str,
    ) -> tuple[object, int, int]:
        """Load OperationAggregate for v2 DriveService.

        Returns (aggregate, last_applied_sequence, epoch_id).
        epoch_id is 0 unless checkpoint_store supports the epoch-fenced load() API (ADR 0197).
        """
        from agent_operator.domain.aggregate import OperationAggregate
        from agent_operator.domain.operation import OperationGoal

        replay_state = await self.load(operation_id)
        epoch_id = 0
        with suppress(AttributeError, NotImplementedError):
            _checkpoint, epoch_id = await self._checkpoint_store.load(operation_id)

        checkpoint = replay_state.checkpoint
        goal = getattr(checkpoint, "goal", None) or OperationGoal(objective="")
        agg = OperationAggregate.create(goal=goal, operation_id=operation_id)
        agg = agg.apply_events(replay_state.suffix_events)
        return agg, replay_state.last_applied_sequence, epoch_id

    def _load_checkpoint(
        self,
        operation_id: str,
        record: OperationCheckpointRecord | None,
    ) -> OperationCheckpoint:
        if record is None:
            return OperationCheckpoint.initial(operation_id)
        return OperationCheckpoint.model_validate(record.checkpoint_payload)
