from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from agent_operator.domain import PersistedReadModelProjection
from agent_operator.runtime import FileReadModelProjectionStore


@pytest.mark.anyio
async def test_read_model_projection_store_round_trips_projection_cursor(
    tmp_path: Path,
) -> None:
    """Catches dropping source_event_sequence while persisting a cached projection."""
    store = FileReadModelProjectionStore(tmp_path / "read_models")
    projection = PersistedReadModelProjection(
        operation_id="op-1",
        projection_type="status",
        source_event_sequence=7,
        projection_payload={"status": "running"},
        projected_at=datetime(2026, 5, 2, tzinfo=UTC),
    )

    await store.save(projection)
    loaded = await store.load("op-1", "status")

    assert loaded is not None
    assert loaded.operation_id == "op-1"
    assert loaded.projection_type == "status"
    assert loaded.source_event_sequence == 7
    assert loaded.projection_payload == {"status": "running"}
    assert await store.load_source_event_sequence("op-1", "status") == 7


@pytest.mark.anyio
async def test_read_model_projection_store_isolates_projection_types(
    tmp_path: Path,
) -> None:
    """Catches overwriting dashboard and status projections for one operation."""
    store = FileReadModelProjectionStore(tmp_path / "read_models")

    await store.save(
        PersistedReadModelProjection(
            operation_id="op-1",
            projection_type="status",
            source_event_sequence=3,
            projection_payload={"surface": "status"},
        )
    )
    await store.save(
        PersistedReadModelProjection(
            operation_id="op-1",
            projection_type="dashboard",
            source_event_sequence=5,
            projection_payload={"surface": "dashboard"},
        )
    )

    status = await store.load("op-1", "status")
    dashboard = await store.load("op-1", "dashboard")

    assert status is not None
    assert dashboard is not None
    assert status.source_event_sequence == 3
    assert dashboard.source_event_sequence == 5


def test_read_model_projection_store_reports_projection_lag(tmp_path: Path) -> None:
    """Catches stale persisted projections being reported as current."""
    store = FileReadModelProjectionStore(tmp_path / "read_models")

    assert store.projection_lag(canonical_sequence=10, projection_sequence=7) == 3
    assert store.projection_lag(canonical_sequence=10, projection_sequence=10) == 0
    assert store.projection_lag(canonical_sequence=10, projection_sequence=None) is None


def test_persisted_read_model_projection_rejects_invalid_cursor() -> None:
    """Catches invalid negative projection cursors entering the store."""
    with pytest.raises(ValueError, match="source_event_sequence"):
        PersistedReadModelProjection(
            operation_id="op-1",
            projection_type="status",
            source_event_sequence=-1,
        )
