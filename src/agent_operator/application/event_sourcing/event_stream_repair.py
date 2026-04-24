from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from agent_operator.application.event_sourcing.event_sourced_replay import EventSourcedReplayService
from agent_operator.domain import (
    OperationDomainEventDraft,
    StoredOperationDomainEvent,
)
from agent_operator.protocols import (
    OperationCheckpointStore,
    OperationEventStore,
    OperationProjector,
)


@dataclass(slots=True)
class EventStreamRepairPreview:
    operation_id: str
    current_last_sequence: int
    proposed_events: list[dict[str, object]]
    recognized: bool
    projected_status: str
    warnings: list[str]


@dataclass(slots=True)
class EventStreamRepairResult:
    operation_id: str
    previous_last_sequence: int
    stored_events: list[StoredOperationDomainEvent]
    projected_status: str
    warnings: list[str]


class EventStreamRepairService:
    """Debug-only canonical event-stream repair helper."""

    _ALLOWLIST = {
        "operation.status.changed",
        "session.observed_state.changed",
        "scheduler.state.changed",
        "attention.request.answered",
    }
    _DERIVED_STORE_WARNINGS = {
        "attention.request.answered": (
            "attention answers may require follow-up command-intent or focus-state reconciliation"
        ),
        "operation.status.changed": (
            "terminal status repair bypasses the normal lifecycle command path"
        ),
    }

    def __init__(
        self,
        *,
        event_store: OperationEventStore,
        checkpoint_store: OperationCheckpointStore,
        projector: OperationProjector,
    ) -> None:
        self._event_store = event_store
        self._projector = projector
        self._replay = EventSourcedReplayService(
            event_store=event_store,
            checkpoint_store=checkpoint_store,
            projector=projector,
        )

    async def preview_append(
        self,
        *,
        operation_id: str,
        event_type: str,
        payload: dict[str, Any],
        reason: str | None,
    ) -> EventStreamRepairPreview:
        replay_state = await self._replay.load(operation_id)
        draft = self._build_draft(event_type=event_type, payload=payload, reason=reason)
        projected = self._project_projected_state(replay_state, [draft])
        return EventStreamRepairPreview(
            operation_id=operation_id,
            current_last_sequence=replay_state.last_applied_sequence,
            proposed_events=[self._draft_payload(draft)],
            recognized=event_type in self._ALLOWLIST,
            projected_status=projected.status.value,
            warnings=self._warnings_for(event_type),
        )

    async def append(
        self,
        *,
        operation_id: str,
        event_type: str,
        payload: dict[str, Any],
        reason: str,
        expected_last_sequence: int | None = None,
    ) -> EventStreamRepairResult:
        if not reason.strip():
            raise ValueError("reason must not be empty.")
        replay_state = await self._replay.load(operation_id)
        draft = self._build_draft(event_type=event_type, payload=payload, reason=reason)
        append_sequence = (
            replay_state.last_applied_sequence
            if expected_last_sequence is None
            else expected_last_sequence
        )
        stored_events = await self._event_store.append(
            operation_id,
            append_sequence,
            [draft],
        )
        updated_replay_state = self._replay.advance(replay_state, stored_events)
        await self._replay.materialize(updated_replay_state)
        return EventStreamRepairResult(
            operation_id=operation_id,
            previous_last_sequence=replay_state.last_applied_sequence,
            stored_events=stored_events,
            projected_status=updated_replay_state.checkpoint.status.value,
            warnings=self._warnings_for(event_type),
        )

    def _build_draft(
        self,
        *,
        event_type: str,
        payload: dict[str, Any],
        reason: str | None,
    ) -> OperationDomainEventDraft:
        if event_type not in self._ALLOWLIST:
            raise ValueError(f"Unsupported repair event type: {event_type}.")
        return OperationDomainEventDraft(
            event_type=event_type,
            payload=dict(payload),
            metadata={
                "repair_reason": reason.strip() if isinstance(reason, str) else "",
                "repair_source": "debug.event.append",
            },
        )

    def _project_projected_state(self, replay_state, drafts: list[OperationDomainEventDraft]):
        stored_events = [
            StoredOperationDomainEvent(
                operation_id=replay_state.checkpoint.operation_id,
                sequence=replay_state.last_applied_sequence + index + 1,
                event_type=draft.event_type,
                payload=draft.payload,
                timestamp=draft.timestamp,
                causation_id=draft.causation_id,
                correlation_id=draft.correlation_id,
                metadata=draft.metadata,
            )
            for index, draft in enumerate(drafts)
        ]
        return self._projector.project(replay_state.checkpoint, stored_events)

    def _draft_payload(self, draft: OperationDomainEventDraft) -> dict[str, object]:
        return {
            "event_type": draft.event_type,
            "payload": dict(draft.payload),
            "metadata": dict(draft.metadata),
        }

    def _warnings_for(self, event_type: str) -> list[str]:
        warning = self._DERIVED_STORE_WARNINGS.get(event_type)
        return [warning] if warning is not None else []
