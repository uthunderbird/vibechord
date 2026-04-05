from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator

from agent_operator.domain.enums import FactFamily


class AdapterFactDraft(BaseModel):
    """Raw adapter-facing observation prior to persistence ordering.

    Attributes:
        fact_type: Stable adapter fact subtype.
        payload: Adapter-specific fact payload.
        observed_at: Observation timestamp.
        adapter_key: Producing adapter identifier.
        session_id: Optional linked session identifier.
        execution_id: Optional linked execution identifier.
        task_id: Optional linked task identifier.

    Examples:
        >>> draft = AdapterFactDraft(
        ...     fact_type="acp.notification.received",
        ...     payload={"method": "session/progress"},
        ...     adapter_key="codex_acp",
        ... )
        >>> draft.fact_type
        'acp.notification.received'
    """

    fact_type: str
    payload: dict[str, object] = Field(default_factory=dict)
    observed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    adapter_key: str
    session_id: str | None = None
    execution_id: str | None = None
    task_id: str | None = None


class TechnicalFactDraft(BaseModel):
    """Normalized operator-runtime observation prior to persistence ordering.

    Attributes:
        fact_type: Stable technical fact subtype.
        payload: Adapter-agnostic technical fact payload.
        observed_at: Observation timestamp.
        source_fact_ids: Source adapter or technical fact identifiers.
        session_id: Optional linked session identifier.
        execution_id: Optional linked execution identifier.
        task_id: Optional linked task identifier.

    Examples:
        >>> draft = TechnicalFactDraft(
        ...     fact_type="execution.start_observed",
        ...     payload={"launch_kind": "new"},
        ...     source_fact_ids=["fact-1"],
        ... )
        >>> draft.source_fact_ids
        ['fact-1']
    """

    fact_type: str
    payload: dict[str, object] = Field(default_factory=dict)
    observed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    source_fact_ids: list[str] = Field(default_factory=list)
    session_id: str | None = None
    execution_id: str | None = None
    task_id: str | None = None

    @field_validator("source_fact_ids")
    @classmethod
    def _validate_source_fact_ids(cls, value: list[str]) -> list[str]:
        if any(not fact_id for fact_id in value):
            raise ValueError("Technical fact source_fact_ids must not contain empty values.")
        return value


class StoredFact(BaseModel):
    """Persisted non-canonical fact ordered within one operation stream.

    Attributes:
        fact_id: Stable fact identifier.
        operation_id: Owning operation identifier.
        sequence: One-based persisted arrival sequence within the operation.
        family: Fact family discriminator.
        fact_type: Stable fact subtype.
        payload: Persisted fact payload.
        observed_at: Observation timestamp.
        persisted_at: Persistence timestamp.
        adapter_key: Optional producing adapter identifier.
        session_id: Optional linked session identifier.
        execution_id: Optional linked execution identifier.
        task_id: Optional linked task identifier.
        source_fact_ids: Optional causal source fact identifiers.

    Examples:
        >>> fact = StoredFact(
        ...     fact_id="fact-1",
        ...     operation_id="op-1",
        ...     sequence=1,
        ...     family=FactFamily.ADAPTER,
        ...     fact_type="acp.notification.received",
        ...     payload={"method": "session/progress"},
        ...     observed_at=datetime(2026, 4, 3, tzinfo=UTC),
        ...     persisted_at=datetime(2026, 4, 3, tzinfo=UTC),
        ...     adapter_key="codex_acp",
        ... )
        >>> fact.family
        <FactFamily.ADAPTER: 'adapter'>
    """

    fact_id: str = Field(default_factory=lambda: str(uuid4()))
    operation_id: str
    sequence: int
    family: FactFamily
    fact_type: str
    payload: dict[str, object] = Field(default_factory=dict)
    observed_at: datetime
    persisted_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    adapter_key: str | None = None
    session_id: str | None = None
    execution_id: str | None = None
    task_id: str | None = None
    source_fact_ids: list[str] = Field(default_factory=list)

    @field_validator("sequence")
    @classmethod
    def _validate_sequence(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("Stored fact sequence must be positive.")
        return value

    @field_validator("source_fact_ids")
    @classmethod
    def _validate_stored_source_fact_ids(cls, value: list[str]) -> list[str]:
        if any(not fact_id for fact_id in value):
            raise ValueError("Stored fact source_fact_ids must not contain empty values.")
        return value


class FactStoreAppendConflict(Exception):
    """Raised when optimistic fact append observes a stale stream position."""
