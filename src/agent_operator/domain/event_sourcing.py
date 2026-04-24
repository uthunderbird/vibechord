from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator


class OperationDomainEventDraft(BaseModel):
    """Draft event payload before operation-local sequencing is assigned.

    Attributes:
        event_type: Stable domain event type identifier.
        payload: JSON-serializable domain event payload.
        timestamp: Event creation timestamp.
        causation_id: Optional upstream fact or event identifier.
        correlation_id: Optional correlation identifier shared across a flow.

    Examples:
        >>> draft = OperationDomainEventDraft(
        ...     event_type="task.created",
        ...     payload={"task_id": "t1"},
        ... )
        >>> draft.event_type
        'task.created'
    """

    event_type: str
    payload: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    causation_id: str | None = None
    correlation_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class StoredOperationDomainEvent(BaseModel):
    """Persisted operation domain event with assigned stream position.

    Attributes:
        operation_id: Owning operation identifier.
        sequence: One-based event sequence within the operation stream.
        event_type: Stable domain event type identifier.
        payload: JSON-serializable domain event payload.
        timestamp: Event creation timestamp.
        causation_id: Optional upstream fact or event identifier.
        correlation_id: Optional correlation identifier shared across a flow.

    Examples:
        >>> event = StoredOperationDomainEvent(
        ...     operation_id="op-1",
        ...     sequence=1,
        ...     event_type="task.created",
        ...     payload={"task_id": "t1"},
        ... )
        >>> event.sequence
        1
    """

    operation_id: str
    sequence: int
    event_type: str
    payload: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    causation_id: str | None = None
    correlation_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("sequence")
    @classmethod
    def _validate_sequence(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("Stored operation event sequence must be positive.")
        return value


class OperationCheckpointRecord(BaseModel):
    """Persisted checkpoint derived from canonical domain events.

    Attributes:
        operation_id: Owning operation identifier.
        checkpoint_payload: Opaque checkpoint payload for replay acceleration.
        last_applied_sequence: Highest applied event sequence in the checkpoint.
        checkpoint_format_version: Checkpoint payload schema version.
        created_at: Checkpoint creation timestamp.

    Examples:
        >>> checkpoint = OperationCheckpointRecord(
        ...     operation_id="op-1",
        ...     checkpoint_payload={"status": "running"},
        ...     last_applied_sequence=2,
        ...     checkpoint_format_version=1,
        ... )
        >>> checkpoint.last_applied_sequence
        2
    """

    operation_id: str
    checkpoint_payload: dict[str, Any] = Field(default_factory=dict)
    last_applied_sequence: int
    checkpoint_format_version: int
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @field_validator("last_applied_sequence")
    @classmethod
    def _validate_last_applied_sequence(cls, value: int) -> int:
        if value < 0:
            raise ValueError("Checkpoint last_applied_sequence must be non-negative.")
        return value

    @field_validator("checkpoint_format_version")
    @classmethod
    def _validate_checkpoint_format_version(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("Checkpoint format version must be positive.")
        return value


class OperationEventStoreAppendConflict(Exception):
    """Raised when optimistic event append observes a stale stream position."""


class StaleEpochError(Exception):
    """Raised by OperationCheckpointStore.save_with_epoch() when the supplied epoch_id
    does not match the stored epoch — indicating a stale write from a superseded operator
    process (ADR 0197 epoch fencing).
    """
