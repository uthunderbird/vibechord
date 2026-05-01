from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from agent_operator.domain import (
    AdapterFactDraft,
    FactFamily,
    FactStoreAppendConflict,
    StoredFact,
    TechnicalFactDraft,
)
from agent_operator.runtime.event_sourcing import FileOperationEventStore
from agent_operator.runtime.files import atomic_write_text, read_text_with_retry


class FileFactStore:
    """File-backed persisted non-canonical fact store.

    Facts are ordered per operation by a one-based sequence shared across both
    adapter and technical fact families.

    Examples:
        >>> from pathlib import Path
        >>> store = FileFactStore(Path("/tmp/operator-facts"))
        >>> store._fact_path("op-1").name
        'op-1.jsonl'
    """

    def __init__(self, root: Path) -> None:
        self._root = root
        self._root.mkdir(parents=True, exist_ok=True)
        self._lock_helper = FileOperationEventStore(root)

    async def append_adapter_facts(
        self,
        operation_id: str,
        expected_last_sequence: int,
        facts: list[AdapterFactDraft],
    ) -> list[StoredFact]:
        """Persist adapter facts with optimistic per-operation ordering."""

        return self._append(
            operation_id=operation_id,
            expected_last_sequence=expected_last_sequence,
            family=FactFamily.ADAPTER,
            adapter_facts=facts,
            technical_facts=[],
        )

    async def append_technical_facts(
        self,
        operation_id: str,
        expected_last_sequence: int,
        facts: list[TechnicalFactDraft],
    ) -> list[StoredFact]:
        """Persist technical facts with optimistic per-operation ordering."""

        return self._append(
            operation_id=operation_id,
            expected_last_sequence=expected_last_sequence,
            family=FactFamily.TECHNICAL,
            adapter_facts=[],
            technical_facts=facts,
        )

    async def load_after(
        self,
        operation_id: str,
        *,
        after_sequence: int = 0,
        family: FactFamily | None = None,
    ) -> list[StoredFact]:
        """Load persisted facts after a given sequence number."""

        if after_sequence < 0:
            raise ValueError("after_sequence must be non-negative.")
        facts = [
            fact
            for fact in self._load_stream(self._fact_path(operation_id))
            if fact.sequence > after_sequence
        ]
        if family is None:
            return facts
        return [fact for fact in facts if fact.family is family]

    async def load_by_fact_ids(self, operation_id: str, fact_ids: list[str]) -> list[StoredFact]:
        """Load persisted facts by stable fact identifier."""

        wanted = set(fact_ids)
        return [
            fact
            for fact in self._load_stream(self._fact_path(operation_id))
            if fact.fact_id in wanted
        ]

    async def load_last_sequence(self, operation_id: str) -> int:
        """Return the last persisted fact sequence for one operation."""

        facts = self._load_stream(self._fact_path(operation_id))
        if not facts:
            return 0
        return facts[-1].sequence

    async def load_translated_sequence(self, operation_id: str) -> int:
        """Return the highest fact sequence durably translated into canonical events."""

        path = self._translation_cursor_path(operation_id)
        if not path.exists():
            return 0
        payload = read_text_with_retry(path)
        if not payload.strip():
            return 0
        data = json.loads(payload)
        sequence = data.get("translated_sequence", 0)
        if not isinstance(sequence, int) or sequence < 0:
            raise ValueError(
                f"Invalid translated fact sequence for operation {operation_id!r}."
            )
        return sequence

    async def mark_translated_through(self, operation_id: str, sequence: int) -> None:
        """Advance the translated fact cursor after successful canonical materialization."""

        if sequence < 0:
            raise ValueError("translated fact sequence must be non-negative.")
        with self._lock_helper._operation_lock(operation_id):
            last_sequence = await self.load_last_sequence(operation_id)
            if sequence > last_sequence:
                raise ValueError(
                    f"Translated fact sequence {sequence} exceeds persisted sequence "
                    f"{last_sequence} for operation {operation_id!r}."
                )
            current_sequence = await self.load_translated_sequence(operation_id)
            if sequence <= current_sequence:
                return
            payload = json.dumps(
                {
                    "operation_id": operation_id,
                    "translated_sequence": sequence,
                    "updated_at": datetime.now(UTC).isoformat(),
                },
                sort_keys=True,
            )
            atomic_write_text(self._translation_cursor_path(operation_id), f"{payload}\n")

    def _append(
        self,
        *,
        operation_id: str,
        expected_last_sequence: int,
        family: FactFamily,
        adapter_facts: list[AdapterFactDraft],
        technical_facts: list[TechnicalFactDraft],
    ) -> list[StoredFact]:
        if expected_last_sequence < 0:
            raise ValueError("expected_last_sequence must be non-negative.")
        if not adapter_facts and not technical_facts:
            return []
        fact_path = self._fact_path(operation_id)
        with self._lock_helper._operation_lock(operation_id):
            existing_facts = self._load_stream(fact_path)
            current_last_sequence = existing_facts[-1].sequence if existing_facts else 0
            if current_last_sequence != expected_last_sequence:
                raise FactStoreAppendConflict(
                    f"Expected last sequence {expected_last_sequence}, "
                    f"found {current_last_sequence} for operation {operation_id!r}."
                )
            stored_batch = self._build_stored_facts(
                operation_id=operation_id,
                family=family,
                start_sequence=current_last_sequence + 1,
                adapter_facts=adapter_facts,
                technical_facts=technical_facts,
            )
            all_facts = [*existing_facts, *stored_batch]
            serialized = "\n".join(fact.model_dump_json() for fact in all_facts)
            if serialized:
                serialized = f"{serialized}\n"
            atomic_write_text(fact_path, serialized)
        return stored_batch

    def _build_stored_facts(
        self,
        *,
        operation_id: str,
        family: FactFamily,
        start_sequence: int,
        adapter_facts: list[AdapterFactDraft],
        technical_facts: list[TechnicalFactDraft],
    ) -> list[StoredFact]:
        persisted_at = datetime.now(UTC)
        if family is FactFamily.ADAPTER:
            return [
                StoredFact(
                    operation_id=operation_id,
                    sequence=start_sequence + index,
                    family=FactFamily.ADAPTER,
                    fact_type=fact.fact_type,
                    payload=fact.payload,
                    observed_at=fact.observed_at,
                    persisted_at=persisted_at,
                    adapter_key=fact.adapter_key,
                    session_id=fact.session_id,
                    execution_id=fact.execution_id,
                    task_id=fact.task_id,
                )
                for index, fact in enumerate(adapter_facts)
            ]
        return [
            StoredFact(
                operation_id=operation_id,
                sequence=start_sequence + index,
                family=FactFamily.TECHNICAL,
                fact_type=fact.fact_type,
                payload=fact.payload,
                observed_at=fact.observed_at,
                persisted_at=persisted_at,
                session_id=fact.session_id,
                execution_id=fact.execution_id,
                task_id=fact.task_id,
                source_fact_ids=fact.source_fact_ids,
            )
            for index, fact in enumerate(technical_facts)
        ]

    def _fact_path(self, operation_id: str) -> Path:
        return self._root / f"{operation_id}.jsonl"

    def _translation_cursor_path(self, operation_id: str) -> Path:
        cursor_root = self._root / ".translation_cursors"
        cursor_root.mkdir(parents=True, exist_ok=True)
        return cursor_root / f"{operation_id}.json"

    def _load_stream(self, path: Path) -> list[StoredFact]:
        if not path.exists():
            return []
        payload = read_text_with_retry(path)
        if not payload.strip():
            return []
        return [
            StoredFact.model_validate_json(line)
            for line in payload.splitlines()
            if line.strip()
        ]
