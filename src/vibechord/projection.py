"""Projection service for status, fleet, and live-feed envelopes."""

from __future__ import annotations

from vibechord.domain import (
    AgentTurnDTO,
    FleetRowDTO,
    LiveFeedEnvelope,
    OperationSnapshot,
    OperationStatus,
    RunEvent,
    StatusDTO,
)
from vibechord.protocols import EventStore

TERMINAL_STATUSES = {
    OperationStatus.COMPLETED,
    OperationStatus.FAILED,
    OperationStatus.CANCELLED,
    OperationStatus.INTERRUPTED,
}


class ProjectionError(RuntimeError):
    """Raised when projections cannot be built from canonical events."""


class ProjectionService:
    """Build derived read models from canonical events."""

    def __init__(self, event_store: EventStore) -> None:
        """Create a projection service over one event store."""

        self.event_store = event_store

    def snapshot(self, operation_id: str) -> OperationSnapshot:
        """Replay one operation into canonical state."""

        events = self.event_store.replay(operation_id)
        if not events:
            raise ProjectionError(f"operation not found: {operation_id}")
        return snapshot_from_events(events)

    def status(self, operation_id: str) -> StatusDTO:
        """Build a shared status DTO."""

        snapshot = self.snapshot(operation_id)
        return StatusDTO(
            operation_id=snapshot.operation_id,
            status=snapshot.status.value,
            goal=snapshot.goal,
            source_sequence=snapshot.source_sequence,
            stale=False,
            stop_reason=snapshot.stop_reason,
            attention_id=snapshot.open_attention_id,
            attention_prompt=snapshot.open_attention_prompt,
            recent_messages=snapshot.recent_messages,
            last_agent_output=snapshot.last_agent_output,
            agent_outputs=snapshot.agent_outputs,
        )

    def fleet(self) -> tuple[FleetRowDTO, ...]:
        """Build a shared fleet snapshot."""

        operation_ids = sorted(
            {event.operation_id for event in self.event_store.all_events()}
        )
        rows = []
        for operation_id in operation_ids:
            snapshot = self.snapshot(operation_id)
            rows.append(
                FleetRowDTO(
                    operation_id=operation_id,
                    status=snapshot.status.value,
                    label=snapshot.goal[:80],
                    attention=snapshot.open_attention_prompt,
                    live_chat=snapshot.recent_messages[-1]
                    if snapshot.recent_messages
                    else None,
                    source_sequence=snapshot.source_sequence,
                    stale=False,
                )
            )
        return tuple(rows)

    def live_feed(self, operation_id: str) -> tuple[LiveFeedEnvelope, ...]:
        """Build live-feed envelopes from canonical events."""

        envelopes = []
        for event in self.event_store.replay(operation_id):
            envelopes.append(
                LiveFeedEnvelope(
                    operation_id=operation_id,
                    sequence=event.sequence,
                    kind="canonical_event",
                    payload_kind=event.kind,
                    payload={
                        "event_id": event.event_id,
                        "command_id": event.command_id,
                        **event.payload,
                    },
                    stale=False,
                )
            )
        return tuple(envelopes)


def snapshot_from_events(events: tuple[RunEvent, ...]) -> OperationSnapshot:
    """Replay canonical events into an OperationSnapshot."""

    first = events[0]
    goal = ""
    status = OperationStatus.RUNNING
    stop_reason: str | None = None
    open_attention_id: str | None = None
    open_attention_prompt: str | None = None
    messages: list[str] = []
    iterations = 0
    agent_calls = 0
    last_agent_output: str | None = None
    agent_outputs: list[AgentTurnDTO] = []

    for event in events:
        if event.kind == "operation.started":
            goal = str(event.payload["goal"])
            status = OperationStatus.RUNNING
        elif event.kind == "operation.iteration":
            iterations += 1
        elif event.kind == "attention.requested":
            status = OperationStatus.BLOCKED
            open_attention_id = str(event.payload["attention_id"])
            open_attention_prompt = str(event.payload["prompt"])
        elif event.kind == "attention.answered":
            open_attention_id = None
            open_attention_prompt = None
            status = OperationStatus.RUNNING
        elif event.kind == "operator.message.posted":
            messages.append(str(event.payload["text"]))
        elif event.kind == "operator.message.expired":
            if messages:
                messages.pop(0)
        elif event.kind == "agent.invocation.finished":
            agent_calls += 1
            agent_name = str(event.payload["agent_name"])
            output = str(event.payload["output"])
            last_agent_output = output
            agent_outputs.append(
                AgentTurnDTO(agent_name=agent_name, status="completed", output=output)
            )
        elif event.kind == "agent.invocation.failed":
            agent_calls += 1
            agent_name = str(event.payload["agent_name"])
            error = str(event.payload["error"])
            agent_outputs.append(
                AgentTurnDTO(agent_name=agent_name, status="failed", error=error)
            )
            status = OperationStatus.FAILED
            stop_reason = error
        elif event.kind == "operation.paused":
            status = OperationStatus.PAUSED
        elif event.kind == "operation.resumed":
            status = OperationStatus.RUNNING
        elif event.kind == "operation.cancelled":
            status = OperationStatus.CANCELLED
            stop_reason = str(event.payload.get("reason", "cancelled"))
        elif event.kind == "operation.interrupted":
            status = OperationStatus.INTERRUPTED
            stop_reason = str(event.payload.get("reason", "interrupted"))
        elif event.kind == "operation.completed":
            status = OperationStatus.COMPLETED
            stop_reason = str(event.payload.get("reason", "completed"))
        elif event.kind == "operation.failed":
            status = OperationStatus.FAILED
            stop_reason = str(event.payload.get("reason", "failed"))

    if goal == "":
        raise ProjectionError("operation has no operation.started event")
    return OperationSnapshot(
        operation_id=first.operation_id,
        goal=goal,
        status=status,
        source_sequence=events[-1].sequence,
        iterations=iterations,
        agent_calls=agent_calls,
        stop_reason=stop_reason,
        open_attention_id=open_attention_id,
        open_attention_prompt=open_attention_prompt,
        recent_messages=tuple(messages[-5:]),
        last_agent_output=last_agent_output,
        agent_outputs=tuple(agent_outputs),
    )
