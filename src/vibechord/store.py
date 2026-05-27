"""File-backed canonical event store."""

from __future__ import annotations

import json
import uuid
from pathlib import Path

from vibechord.domain import RunEvent
from vibechord.protocols import Clock


class EventStoreError(RuntimeError):
    """Raised when persisted events are corrupt or inconsistent."""


class JsonlEventStore:
    """Append-only JSONL event store.

    Example:
        >>> from tempfile import TemporaryDirectory
        >>> from vibechord.time import FakeClock
        >>> with TemporaryDirectory() as tmp:
        ...     store = JsonlEventStore(Path(tmp) / "events.jsonl", FakeClock())
        ...     event = store.append("op-1", "operation.started", {"goal": "x"})
        ...     store.replay("op-1")[0].event_id == event.event_id
        True
    """

    def __init__(self, path: Path, clock: Clock) -> None:
        """Create a JSONL event store at path."""

        self.path = path
        self.clock = clock
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.touch(exist_ok=True)

    def append(
        self,
        operation_id: str,
        kind: str,
        payload: dict[str, str | int | bool],
        command_id: str | None = None,
    ) -> RunEvent:
        """Append an event, returning prior command-caused event if idempotent."""

        if command_id is not None:
            existing = self._find_command_event(operation_id, command_id, kind)
            if existing is not None:
                return existing
        sequence = self._next_sequence(operation_id)
        event = RunEvent(
            operation_id=operation_id,
            sequence=sequence,
            event_id=str(uuid.uuid4()),
            kind=kind,
            timestamp=self.clock.now(),
            payload=payload,
            command_id=command_id,
        )
        with self.path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(_event_to_record(event), sort_keys=True) + "\n")
        return event

    def replay(self, operation_id: str) -> tuple[RunEvent, ...]:
        """Replay events for one operation and detect sequence gaps."""

        events = tuple(
            event for event in self.all_events() if event.operation_id == operation_id
        )
        expected = 1
        for event in events:
            if event.sequence != expected:
                raise EventStoreError(
                    f"sequence gap in {self.path} for {operation_id}: "
                    f"expected {expected}, got {event.sequence}"
                )
            expected += 1
        return events

    def all_events(self) -> tuple[RunEvent, ...]:
        """Return all events ordered by operation id and sequence."""

        events = []
        with self.path.open("r", encoding="utf-8") as stream:
            for line_number, line in enumerate(stream, start=1):
                stripped = line.strip()
                if not stripped:
                    continue
                try:
                    record = json.loads(stripped)
                    events.append(_event_from_record(record))
                except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
                    raise EventStoreError(
                        f"corrupt event in {self.path} at line {line_number}: {exc}"
                    ) from exc
        return tuple(
            sorted(events, key=lambda event: (event.operation_id, event.sequence))
        )

    def _next_sequence(self, operation_id: str) -> int:
        events = [
            event for event in self.all_events() if event.operation_id == operation_id
        ]
        if not events:
            return 1
        return max(event.sequence for event in events) + 1

    def _find_command_event(
        self, operation_id: str, command_id: str, kind: str
    ) -> RunEvent | None:
        for event in self.all_events():
            if (
                event.operation_id == operation_id
                and event.command_id == command_id
                and event.kind == kind
            ):
                return event
        return None


def _event_to_record(event: RunEvent) -> dict[str, object]:
    return {
        "operation_id": event.operation_id,
        "sequence": event.sequence,
        "event_id": event.event_id,
        "kind": event.kind,
        "timestamp": event.timestamp,
        "payload": event.payload,
        "command_id": event.command_id,
    }


def _event_from_record(record: dict[str, object]) -> RunEvent:
    payload = record["payload"]
    if not isinstance(payload, dict):
        raise TypeError("payload must be object")
    sequence = record["sequence"]
    if not isinstance(sequence, int):
        raise TypeError("sequence must be int")
    return RunEvent(
        operation_id=str(record["operation_id"]),
        sequence=sequence,
        event_id=str(record["event_id"]),
        kind=str(record["kind"]),
        timestamp=str(record["timestamp"]),
        payload={str(key): _payload_value(value) for key, value in payload.items()},
        command_id=None
        if record.get("command_id") is None
        else str(record["command_id"]),
    )


def _payload_value(value: object) -> str | int | bool:
    if isinstance(value, str | int | bool):
        return value
    raise TypeError(f"unsupported payload value {value!r}")
