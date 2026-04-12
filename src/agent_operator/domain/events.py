from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field, model_validator

from agent_operator.domain.enums import RunEventKind

EVENT_FILE_SCHEMA_VERSION = 1


class EventFileRecord(BaseModel):
    """Stable wire record persisted in `.operator/events/<operation_id>.jsonl`.

    Attributes:
        schema_version: Event-file contract version.
        event_id: Stable unique event identifier.
        event_type: Stable event type identifier for routing.
        kind: Stable runtime event bucket (`trace` or `wakeup`).
        category: Stable trace/domain category when present.
        operation_id: Owning operation identifier.
        iteration: Iteration number associated with the event.
        task_id: Optional task identifier reference.
        session_id: Optional session identifier reference.
        dedupe_key: Optional wakeup dedupe key.
        timestamp: Event timestamp in UTC.
        not_before: Optional wakeup delivery lower bound.
        payload: Event payload object.

    Examples:
        >>> record = EventFileRecord(
        ...     event_id="evt-1",
        ...     event_type="operation.started",
        ...     kind=RunEventKind.TRACE,
        ...     category="trace",
        ...     operation_id="op-1",
        ...     iteration=0,
        ... )
        >>> record.schema_version
        1
    """

    schema_version: int = EVENT_FILE_SCHEMA_VERSION
    event_id: str
    event_type: str
    kind: RunEventKind
    category: Literal["domain", "trace"] | None = None
    operation_id: str
    iteration: int
    task_id: str | None = None
    session_id: str | None = None
    dedupe_key: str | None = None
    timestamp: datetime
    not_before: datetime | None = None
    payload: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def from_run_event(cls, event: RunEvent) -> EventFileRecord:
        """Convert an in-memory run event into the stable event-file wire record."""
        return cls(
            event_id=event.event_id,
            event_type=event.event_type,
            kind=event.kind,
            category=event.category,
            operation_id=event.operation_id,
            iteration=event.iteration,
            task_id=event.task_id,
            session_id=event.session_id,
            dedupe_key=event.dedupe_key,
            timestamp=event.timestamp,
            not_before=event.not_before,
            payload=event.payload,
        )

    def to_run_event(self) -> RunEvent:
        """Convert a persisted event-file wire record back into a `RunEvent`."""
        return RunEvent(
            event_id=self.event_id,
            event_type=self.event_type,
            kind=self.kind,
            category=self.category,
            operation_id=self.operation_id,
            iteration=self.iteration,
            task_id=self.task_id,
            session_id=self.session_id,
            dedupe_key=self.dedupe_key,
            timestamp=self.timestamp,
            not_before=self.not_before,
            payload=self.payload,
        )


class RunEvent(BaseModel):
    event_id: str = Field(default_factory=lambda: str(uuid4()))
    event_type: str
    kind: RunEventKind = RunEventKind.TRACE
    category: Literal["domain", "trace"] | None = None
    operation_id: str
    iteration: int
    task_id: str | None = None
    session_id: str | None = None
    dedupe_key: str | None = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    not_before: datetime | None = None
    payload: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_category(self) -> RunEvent:
        if self.kind is RunEventKind.TRACE and self.category is None:
            raise ValueError(
                f"RunEvent with kind=TRACE must have a category set "
                f"(event_type={self.event_type!r}). "
                "Wakeup events are exempt; use kind=RunEventKind.WAKEUP for those."
            )
        return self

    def to_event_file_record(self) -> EventFileRecord:
        """Return the stable event-file wire record for this run event.

        Examples:
            >>> event = RunEvent(
            ...     event_type="operation.started",
            ...     operation_id="op-1",
            ...     iteration=0,
            ...     category="trace",
            ... )
            >>> event.to_event_file_record().event_type
            'operation.started'
        """

        return EventFileRecord.from_run_event(self)
