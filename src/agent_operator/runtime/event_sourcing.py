from __future__ import annotations

import os
import time
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from pathlib import Path

from agent_operator.domain import (
    OperationCheckpointRecord,
    OperationDomainEventDraft,
    OperationEventStoreAppendConflict,
    StoredOperationDomainEvent,
)
from agent_operator.runtime.files import atomic_write_text, read_text_with_retry


class FileOperationEventStore:
    """File-backed canonical domain event store with optimistic append semantics.

    Attributes:
        _root: Directory holding per-operation JSONL event streams.
        _lock_root: Directory holding per-operation lock files.

    Examples:
        >>> from pathlib import Path
        >>> store = FileOperationEventStore(Path("/tmp/operator-events"))
        >>> store._stream_path("op-1").name
        'op-1.jsonl'
    """

    def __init__(self, root: Path) -> None:
        self._root = root
        self._root.mkdir(parents=True, exist_ok=True)
        self._lock_root = self._root / ".locks"
        self._lock_root.mkdir(parents=True, exist_ok=True)

    async def append(
        self,
        operation_id: str,
        expected_last_sequence: int,
        events: list[OperationDomainEventDraft],
    ) -> list[StoredOperationDomainEvent]:
        """Append a batch of events atomically for one operation.

        Args:
            operation_id: Owning operation identifier.
            expected_last_sequence: Optimistic concurrency precondition.
            events: Domain event drafts to persist.

        Returns:
            Persisted events with assigned stream positions.

        Raises:
            OperationEventStoreAppendConflict: If the stream tail does not match
                `expected_last_sequence`.
        """

        if expected_last_sequence < 0:
            raise ValueError("expected_last_sequence must be non-negative.")
        if not events:
            return []
        stream_path = self._stream_path(operation_id)
        with self._operation_lock(operation_id):
            existing_events = self._load_stream(stream_path)
            current_last_sequence = existing_events[-1].sequence if existing_events else 0
            if current_last_sequence != expected_last_sequence:
                raise OperationEventStoreAppendConflict(
                    f"Expected last sequence {expected_last_sequence}, "
                    f"found {current_last_sequence} for operation {operation_id!r}."
                )
            next_sequence = current_last_sequence + 1
            stored_batch = [
                StoredOperationDomainEvent(
                    operation_id=operation_id,
                    sequence=next_sequence + index,
                    event_type=event.event_type,
                    payload=event.payload,
                    timestamp=event.timestamp,
                    causation_id=event.causation_id,
                    correlation_id=event.correlation_id,
                )
                for index, event in enumerate(events)
            ]
            all_events = [*existing_events, *stored_batch]
            serialized = "\n".join(event.model_dump_json() for event in all_events)
            if serialized:
                serialized = f"{serialized}\n"
            atomic_write_text(stream_path, serialized)
        return stored_batch

    async def load_after(
        self,
        operation_id: str,
        *,
        after_sequence: int = 0,
    ) -> list[StoredOperationDomainEvent]:
        """Load persisted events after a given sequence number.

        Args:
            operation_id: Owning operation identifier.
            after_sequence: Highest already-applied sequence number.

        Returns:
            Ordered suffix of persisted events.
        """

        if after_sequence < 0:
            raise ValueError("after_sequence must be non-negative.")
        return [
            event
            for event in self._load_stream(self._stream_path(operation_id))
            if event.sequence > after_sequence
        ]

    async def load_last_sequence(self, operation_id: str) -> int:
        """Return the last persisted sequence for an operation stream.

        Args:
            operation_id: Owning operation identifier.

        Returns:
            Zero for an empty stream, otherwise the last assigned sequence.
        """

        events = self._load_stream(self._stream_path(operation_id))
        if not events:
            return 0
        return events[-1].sequence

    def _stream_path(self, operation_id: str) -> Path:
        return self._root / f"{operation_id}.jsonl"

    def _lock_path(self, operation_id: str) -> Path:
        return self._lock_root / f"{operation_id}.lock"

    def _load_stream(self, path: Path) -> list[StoredOperationDomainEvent]:
        if not path.exists():
            return []
        payload = read_text_with_retry(path)
        if not payload.strip():
            return []
        lines = [line for line in payload.splitlines() if line.strip()]
        return [StoredOperationDomainEvent.model_validate_json(line) for line in lines]

    @contextmanager
    def _operation_lock(
        self,
        operation_id: str,
        *,
        timeout_seconds: float = 2.0,
        retry_delay_seconds: float = 0.01,
    ) -> Iterator[None]:
        lock_path = self._lock_path(operation_id)
        deadline = time.monotonic() + timeout_seconds
        while True:
            try:
                file_descriptor = os.open(
                    lock_path,
                    os.O_CREAT | os.O_EXCL | os.O_WRONLY,
                    0o600,
                )
                break
            except FileExistsError:
                if time.monotonic() >= deadline:
                    raise TimeoutError(f"Timed out waiting for lock {lock_path}.") from None
                time.sleep(retry_delay_seconds)
        try:
            os.close(file_descriptor)
            yield
        finally:
            with suppress(FileNotFoundError):
                lock_path.unlink()


class FileOperationCheckpointStore:
    """File-backed derived checkpoint store for operation replay acceleration.

    Examples:
        >>> from pathlib import Path
        >>> store = FileOperationCheckpointStore(Path("/tmp/operator-checkpoints"))
        >>> store._checkpoint_path("op-1").name
        'op-1.json'
    """

    def __init__(self, root: Path) -> None:
        self._root = root
        self._root.mkdir(parents=True, exist_ok=True)

    async def save(self, record: OperationCheckpointRecord) -> None:
        """Persist the latest derived checkpoint for one operation.

        Args:
            record: Checkpoint record to store.
        """

        atomic_write_text(
            self._checkpoint_path(record.operation_id),
            record.model_dump_json(indent=2),
        )

    async def load_latest(self, operation_id: str) -> OperationCheckpointRecord | None:
        """Load the latest checkpoint for one operation.

        Args:
            operation_id: Owning operation identifier.

        Returns:
            The latest checkpoint record, if present.
        """

        path = self._checkpoint_path(operation_id)
        if not path.exists():
            return None
        return OperationCheckpointRecord.model_validate_json(read_text_with_retry(path))

    def _checkpoint_path(self, operation_id: str) -> Path:
        return self._root / f"{operation_id}.json"
