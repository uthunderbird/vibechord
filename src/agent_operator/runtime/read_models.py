from __future__ import annotations

import json
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

from agent_operator.domain import PersistedReadModelProjection
from agent_operator.runtime.files import atomic_write_text, read_text_with_retry


class FileReadModelProjectionStore:
    """File-backed persisted read-model projection store.

    Projections are derived from canonical events and carry the source event
    sequence they represent. The store does not make projections authoritative.
    """

    def __init__(self, root: Path) -> None:
        self._root = root
        self._root.mkdir(parents=True, exist_ok=True)

    async def save(self, projection: PersistedReadModelProjection) -> None:
        """Persist one projection snapshot."""

        atomic_write_text(
            self._projection_path(projection.operation_id, projection.projection_type),
            f"{json.dumps(self._serialize(projection), sort_keys=True)}\n",
        )

    async def load(
        self,
        operation_id: str,
        projection_type: str,
    ) -> PersistedReadModelProjection | None:
        """Load one projection snapshot."""

        path = self._projection_path(operation_id, projection_type)
        if not path.exists():
            return None
        payload = read_text_with_retry(path)
        if not payload.strip():
            return None
        return self._deserialize(json.loads(payload))

    async def load_source_event_sequence(
        self,
        operation_id: str,
        projection_type: str,
    ) -> int | None:
        """Return the canonical event sequence represented by a projection."""

        projection = await self.load(operation_id, projection_type)
        if projection is None:
            return None
        return projection.source_event_sequence

    def projection_lag(
        self,
        *,
        canonical_sequence: int,
        projection_sequence: int | None,
    ) -> int | None:
        """Compute projection lag relative to canonical event sequence."""

        if canonical_sequence < 0:
            raise ValueError("canonical_sequence must be non-negative.")
        if projection_sequence is None:
            return None
        if projection_sequence < 0:
            raise ValueError("projection_sequence must be non-negative.")
        return max(canonical_sequence - projection_sequence, 0)

    def _projection_path(self, operation_id: str, projection_type: str) -> Path:
        safe_projection_type = projection_type.replace("/", "__")
        return self._root / safe_projection_type / f"{operation_id}.json"

    def _serialize(self, projection: PersistedReadModelProjection) -> dict[str, object]:
        payload = asdict(projection)
        projected_at = payload.get("projected_at")
        if isinstance(projected_at, datetime):
            payload["projected_at"] = projected_at.isoformat()
        return payload

    def _deserialize(self, payload: object) -> PersistedReadModelProjection:
        if not isinstance(payload, dict):
            raise ValueError("Persisted read-model projection must be a JSON object.")
        projected_at = payload.get("projected_at")
        if isinstance(projected_at, str):
            payload = {**payload, "projected_at": datetime.fromisoformat(projected_at)}
        elif projected_at is None:
            payload = {**payload, "projected_at": datetime.now(UTC)}
        return PersistedReadModelProjection(**payload)
