from __future__ import annotations

import json
import time
from collections.abc import Callable
from pathlib import Path

from agent_operator.domain import EVENT_FILE_SCHEMA_VERSION, EventFileRecord, RunEvent
from agent_operator.protocols import EventSink


class JsonlEventSink:
    def __init__(self, data_dir: Path, operation_id: str | None = None) -> None:
        """
        Backward compatible constructor.

        New form:
        - JsonlEventSink(data_dir, operation_id) writes to data_dir/events/<operation_id>.jsonl

        Legacy test form:
        - JsonlEventSink(path_to_jsonl) writes directly to that file.
        """

        if operation_id is None:
            # Legacy: caller passed an explicit .jsonl path.
            self._path = data_dir
        else:
            self._path = data_dir / "events" / f"{operation_id}.jsonl"
        self._path.parent.mkdir(parents=True, exist_ok=True)

    async def emit(self, event: RunEvent) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("a", encoding="utf-8") as handle:
            handle.write(event.to_event_file_record().model_dump_json())
            handle.write("\n")

    def read_events(self, operation_id: str | None = None) -> list[RunEvent]:
        if not self._path.exists():
            return []
        events: list[RunEvent] = []
        with self._path.open(encoding="utf-8") as handle:
            for line in handle:
                raw = line.strip()
                if not raw:
                    continue
                events.append(parse_event_file_line(raw))
        return events

    def iter_events(
        self,
        operation_id: str | None = None,
        *,
        follow: bool = False,
        poll_interval: float = 0.5,
    ):
        handle = None
        try:
            while True:
                if handle is None:
                    if not self._path.exists():
                        if not follow:
                            return
                        time.sleep(poll_interval)
                        continue
                    handle = self._path.open(encoding="utf-8")
                position = handle.tell()
                line = handle.readline()
                if not line:
                    if not follow:
                        return
                    time.sleep(poll_interval)
                    continue
                if not line.endswith("\n"):
                    handle.seek(position)
                    time.sleep(poll_interval)
                    continue
                yield parse_event_file_line(line)
        finally:
            if handle is not None:
                handle.close()


class ProjectingEventSink:
    def __init__(self, sink: EventSink, on_event: Callable[[RunEvent], None]) -> None:
        self._sink = sink
        self._on_event = on_event

    async def emit(self, event: RunEvent) -> None:
        await self._sink.emit(event)
        self._on_event(event)


def parse_event_file_line(raw_line: str) -> RunEvent:
    """Parse one persisted event-file line into a `RunEvent`.

    The parser accepts both the current stable event-file wire schema and
    legacy raw `RunEvent` lines written before the contract serializer existed.
    """

    payload = json.loads(raw_line)
    if isinstance(payload, dict) and payload.get("schema_version") == EVENT_FILE_SCHEMA_VERSION:
        return EventFileRecord.model_validate(payload).to_run_event()
    return RunEvent.model_validate(payload)
