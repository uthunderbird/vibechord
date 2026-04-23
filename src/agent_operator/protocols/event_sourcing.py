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

    v2 epoch fencing (ADR 0197): load() returns the current epoch alongside the checkpoint.
    save() requires the epoch captured at load() time — a mismatch raises StaleEpochError.
    advance_epoch() is called by Commander on operation reassignment.

    Examples:
        Implementations are expected to store only derived checkpoint state and
        never become the source of truth ahead of the canonical event stream.
    """

    async def save(self, record: OperationCheckpointRecord) -> None: ...

    async def load_latest(self, operation_id: str) -> OperationCheckpointRecord | None: ...

    # ── v2 epoch-fenced API (ADR 0197) ────────────────────────────────────────

    async def load(self, operation_id: str) -> tuple[OperationCheckpointRecord | None, int]:
        """Load checkpoint and current epoch_id together.

        DriveService.drive() captures epoch_id from this return value at the start of each
        drive call and uses it for all subsequent save_with_epoch() calls.
        Returns (None, 0) if no checkpoint exists yet.
        """
        ...

    async def save_with_epoch(
        self, record: OperationCheckpointRecord, *, epoch_id: int
    ) -> None:
        """Persist checkpoint only if epoch_id matches the stored epoch (exact equality).

        Raises StaleEpochError if epoch_id != stored_epoch_id.
        """
        ...

    async def advance_epoch(self, operation_id: str) -> int:
        """Atomically increment and return the new epoch_id.

        Called by Commander when reassigning an operation to a new operator process.
        After this call, any save_with_epoch() with the old epoch_id will raise StaleEpochError.
        """
        ...
