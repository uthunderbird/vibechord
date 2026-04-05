from __future__ import annotations

from typing import Protocol

from agent_operator.domain import (
    AdapterFactDraft,
    FactFamily,
    OperationCheckpointRecord,
    OperationDomainEventDraft,
    StoredFact,
    TechnicalFactDraft,
)


class FactStore(Protocol):
    """Non-canonical persisted store for adapter and technical facts.

    Examples:
        Implementations are expected to preserve per-operation append order and
        provide a stable fact identifier for idempotent downstream translation.
    """

    async def append_adapter_facts(
        self,
        operation_id: str,
        expected_last_sequence: int,
        facts: list[AdapterFactDraft],
    ) -> list[StoredFact]: ...

    async def append_technical_facts(
        self,
        operation_id: str,
        expected_last_sequence: int,
        facts: list[TechnicalFactDraft],
    ) -> list[StoredFact]: ...

    async def load_after(
        self,
        operation_id: str,
        *,
        after_sequence: int = 0,
        family: FactFamily | None = None,
    ) -> list[StoredFact]: ...

    async def load_by_fact_ids(
        self,
        operation_id: str,
        fact_ids: list[str],
    ) -> list[StoredFact]: ...

    async def load_last_sequence(self, operation_id: str) -> int: ...


class FactTranslator(Protocol):
    """Deterministic translator from technical facts to domain event drafts.

    Examples:
        Concrete implementations may consult the latest canonical checkpoint,
        but they must not mutate it or bypass the canonical event store.
    """

    async def translate(
        self,
        *,
        checkpoint: OperationCheckpointRecord | None,
        technical_facts: list[StoredFact],
    ) -> list[OperationDomainEventDraft]: ...
