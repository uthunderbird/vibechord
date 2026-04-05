from __future__ import annotations

from typing import Protocol

from agent_operator.domain import (
    OperationCheckpointRecord,
    OperationDomainEventDraft,
    StoredOperationDomainEvent,
)


class OperationEventStore(Protocol):
    """Canonical domain event persistence contract for one operation stream.

    Examples:
        Implementations are expected to assign contiguous one-based sequences and
        reject stale appends via optimistic concurrency checks.
    """

    async def append(
        self,
        operation_id: str,
        expected_last_sequence: int,
        events: list[OperationDomainEventDraft],
    ) -> list[StoredOperationDomainEvent]: ...

    async def load_after(
        self,
        operation_id: str,
        *,
        after_sequence: int = 0,
    ) -> list[StoredOperationDomainEvent]: ...

    async def load_last_sequence(self, operation_id: str) -> int: ...


class OperationCheckpointStore(Protocol):
    """Derived checkpoint persistence contract for operation replay acceleration.

    Examples:
        Implementations are expected to store only derived checkpoint state and
        never become the source of truth ahead of the canonical event stream.
    """

    async def save(self, record: OperationCheckpointRecord) -> None: ...

    async def load_latest(self, operation_id: str) -> OperationCheckpointRecord | None: ...
