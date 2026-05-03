from __future__ import annotations

from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, model_validator

from agent_operator.domain import RunEvent, StoredOperationDomainEvent
from agent_operator.runtime.events import parse_event_file_line

LiveFeedLayer = Literal["canonical", "overlay", "forensic"]
LiveFeedRecordType = Literal["event", "warning"]


class LiveFeedEnvelope(BaseModel):
    """Shared typed live-feed record for supervisory surfaces.

    Examples:
        ```python
        envelope = LiveFeedEnvelope.from_event(
            operation_id="op-1",
            layer="canonical",
            sequence=1,
            event=RunEvent(
                event_type="operation.created",
                operation_id="op-1",
                iteration=0,
                category="domain",
            ),
        )
        assert envelope.record_type == "event"
        ```
    """

    record_id: str
    operation_id: str
    layer: LiveFeedLayer
    record_type: LiveFeedRecordType
    event: RunEvent | None = None
    sequence: int | None = None
    warning_code: str | None = None
    message: str | None = None

    @classmethod
    def from_event(
        cls,
        *,
        operation_id: str,
        layer: LiveFeedLayer,
        event: RunEvent,
        sequence: int | None = None,
    ) -> LiveFeedEnvelope:
        """Build an event envelope."""

        return cls(
            record_id=event.event_id,
            operation_id=operation_id,
            layer=layer,
            record_type="event",
            event=event,
            sequence=sequence,
        )

    @classmethod
    def warning(
        cls,
        *,
        operation_id: str,
        layer: LiveFeedLayer,
        warning_code: str,
        message: str,
        record_suffix: str,
        sequence: int | None = None,
    ) -> LiveFeedEnvelope:
        """Build a warning envelope."""

        return cls(
            record_id=f"{operation_id}:{record_suffix}",
            operation_id=operation_id,
            layer=layer,
            record_type="warning",
            warning_code=warning_code,
            message=message,
            sequence=sequence,
        )

    @model_validator(mode="after")
    def _validate_shape(self) -> LiveFeedEnvelope:
        if self.record_type == "event":
            if self.event is None:
                raise ValueError("LiveFeedEnvelope(event) requires event.")
            if self.warning_code is not None or self.message is not None:
                raise ValueError("LiveFeedEnvelope(event) cannot carry warning fields.")
            return self
        if self.message is None or self.warning_code is None:
            raise ValueError("LiveFeedEnvelope(warning) requires warning_code and message.")
        if self.event is not None:
            raise ValueError("LiveFeedEnvelope(warning) cannot carry event.")
        return self


def parse_canonical_live_feed_line(operation_id: str, raw_line: str) -> LiveFeedEnvelope:
    """Parse one canonical operation-event line into a live-feed envelope."""

    stored_event = StoredOperationDomainEvent.model_validate_json(raw_line)
    payload = dict(stored_event.payload)
    iteration = payload.get("iteration")
    if not isinstance(iteration, int) or iteration < 0:
        iteration = 0
    task_id = payload.get("task_id")
    session_id = payload.get("session_id")
    event = RunEvent(
        event_id=f"{operation_id}:{stored_event.sequence}",
        event_type=stored_event.event_type,
        kind="trace",
        category="domain",
        operation_id=operation_id,
        iteration=iteration,
        task_id=task_id if isinstance(task_id, str) else None,
        session_id=session_id if isinstance(session_id, str) else None,
        timestamp=stored_event.timestamp,
        payload=payload,
    )
    return LiveFeedEnvelope.from_event(
        operation_id=operation_id,
        layer="canonical",
        event=event,
        sequence=stored_event.sequence,
    )


def parse_legacy_live_feed_line(operation_id: str, raw_line: str) -> LiveFeedEnvelope:
    """Parse one legacy runtime-event line into a live-feed envelope."""

    event = parse_event_file_line(raw_line)
    return LiveFeedEnvelope.from_event(
        operation_id=operation_id,
        layer="forensic",
        event=event,
    )


def build_sequence_gap_warning(
    *,
    operation_id: str,
    previous_sequence: int,
    next_sequence: int,
) -> LiveFeedEnvelope | None:
    """Build a canonical sequence-gap warning when an envelope skips records."""

    if next_sequence <= previous_sequence + 1:
        return None
    missing_from = previous_sequence + 1
    missing_to = next_sequence - 1
    missing_range = (
        str(missing_from) if missing_from == missing_to else f"{missing_from}-{missing_to}"
    )
    return LiveFeedEnvelope.warning(
        operation_id=operation_id,
        layer="canonical",
        warning_code="sequence_gap",
        message=(
            "Canonical live stream is missing sequence "
            f"{missing_range}; replayed status may be ahead of visible events."
        ),
        record_suffix=f"sequence-gap:{missing_range}",
        sequence=missing_from,
    )


def iter_live_feed(
    path: Path,
    *,
    operation_id: str,
    parser: Callable[[str, str], LiveFeedEnvelope],
) -> Iterator[LiveFeedEnvelope]:
    """Iterate persisted live-feed envelopes from one stream path."""

    if not path.exists():
        return iter(())

    def _records() -> Iterator[LiveFeedEnvelope]:
        previous_sequence: int | None = None
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                envelope = parser(operation_id, line)
                if (
                    envelope.layer == "canonical"
                    and envelope.sequence is not None
                    and previous_sequence is not None
                ):
                    warning = build_sequence_gap_warning(
                        operation_id=operation_id,
                        previous_sequence=previous_sequence,
                        next_sequence=envelope.sequence,
                    )
                    if warning is not None:
                        yield warning
                if envelope.sequence is not None:
                    previous_sequence = envelope.sequence
                yield envelope

    return _records()
