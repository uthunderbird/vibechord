from __future__ import annotations

import threading
import time
from datetime import UTC, datetime
from pathlib import Path

import anyio
import pytest

import agent_operator.runtime.event_sourcing as event_sourcing_runtime
from agent_operator.domain import (
    OperationCheckpointRecord,
    OperationDomainEventDraft,
    OperationEventStoreAppendConflict,
)
from agent_operator.domain.event_sourcing import StaleEpochError
from agent_operator.runtime import FileOperationCheckpointStore, FileOperationEventStore


def _make_event(event_type: str, *, value: int) -> OperationDomainEventDraft:
    return OperationDomainEventDraft(
        event_type=event_type,
        payload={"value": value},
        timestamp=datetime(2026, 4, 3, tzinfo=UTC),
    )


@pytest.mark.anyio
async def test_event_store_append_on_empty_stream_assigns_one_based_sequences(
    tmp_path: Path,
) -> None:
    store = FileOperationEventStore(tmp_path / "operation_events")

    stored = await store.append("op-1", 0, [_make_event("task.created", value=1)])

    assert [event.sequence for event in stored] == [1]
    assert await store.load_last_sequence("op-1") == 1
    loaded = await store.load_after("op-1")
    assert [event.sequence for event in loaded] == [1]


@pytest.mark.anyio
async def test_event_store_append_on_existing_stream_assigns_contiguous_sequences(
    tmp_path: Path,
) -> None:
    store = FileOperationEventStore(tmp_path / "operation_events")

    await store.append("op-1", 0, [_make_event("task.created", value=1)])
    stored = await store.append(
        "op-1",
        1,
        [
            _make_event("task.updated", value=2),
            _make_event("task.completed", value=3),
        ],
    )

    assert [event.sequence for event in stored] == [2, 3]
    loaded = await store.load_after("op-1")
    assert [event.sequence for event in loaded] == [1, 2, 3]


@pytest.mark.anyio
async def test_event_store_append_rejects_stale_expected_sequence(tmp_path: Path) -> None:
    store = FileOperationEventStore(tmp_path / "operation_events")
    await store.append("op-1", 0, [_make_event("task.created", value=1)])

    with pytest.raises(OperationEventStoreAppendConflict):
        await store.append("op-1", 0, [_make_event("task.updated", value=2)])


@pytest.mark.anyio
async def test_checkpoint_store_roundtrip(tmp_path: Path) -> None:
    store = FileOperationCheckpointStore(tmp_path / "operation_checkpoints")
    record = OperationCheckpointRecord(
        operation_id="op-1",
        checkpoint_payload={"status": "running"},
        last_applied_sequence=2,
        checkpoint_format_version=1,
        created_at=datetime(2026, 4, 3, tzinfo=UTC),
    )

    await store.save(record)
    loaded = await store.load_latest("op-1")

    assert loaded == record


@pytest.mark.anyio
async def test_checkpoint_store_load_returns_epoch_with_record(tmp_path: Path) -> None:
    store = FileOperationCheckpointStore(tmp_path / "operation_checkpoints")
    record = OperationCheckpointRecord(
        operation_id="op-1",
        checkpoint_payload={"status": "running"},
        last_applied_sequence=2,
        checkpoint_format_version=1,
        created_at=datetime(2026, 4, 3, tzinfo=UTC),
    )

    await store.save(record)

    loaded, epoch_id = await store.load("op-1")

    assert loaded == record
    assert epoch_id == 0


@pytest.mark.anyio
async def test_checkpoint_store_save_with_epoch_rejects_stale_epoch(tmp_path: Path) -> None:
    store = FileOperationCheckpointStore(tmp_path / "operation_checkpoints")
    record = OperationCheckpointRecord(
        operation_id="op-1",
        checkpoint_payload={"status": "running"},
        last_applied_sequence=2,
        checkpoint_format_version=1,
        created_at=datetime(2026, 4, 3, tzinfo=UTC),
    )

    await store.save(record)
    new_epoch = await store.advance_epoch("op-1")

    with pytest.raises(StaleEpochError):
        await store.save_with_epoch(record, epoch_id=0)

    loaded, epoch_id = await store.load("op-1")
    assert loaded == record
    assert epoch_id == new_epoch


@pytest.mark.anyio
async def test_checkpoint_store_advance_epoch_without_existing_checkpoint(tmp_path: Path) -> None:
    store = FileOperationCheckpointStore(tmp_path / "operation_checkpoints")

    new_epoch = await store.advance_epoch("op-1")
    loaded, epoch_id = await store.load("op-1")

    assert new_epoch == 1
    assert loaded is None
    assert epoch_id == 1


@pytest.mark.anyio
async def test_event_store_load_after_supports_replay_suffix_from_checkpoint(
    tmp_path: Path,
) -> None:
    event_store = FileOperationEventStore(tmp_path / "operation_events")
    checkpoint_store = FileOperationCheckpointStore(tmp_path / "operation_checkpoints")
    await event_store.append(
        "op-1",
        0,
        [
            _make_event("task.created", value=1),
            _make_event("task.updated", value=2),
            _make_event("task.completed", value=3),
        ],
    )
    await checkpoint_store.save(
        OperationCheckpointRecord(
            operation_id="op-1",
            checkpoint_payload={"status": "running"},
            last_applied_sequence=2,
            checkpoint_format_version=1,
            created_at=datetime(2026, 4, 3, tzinfo=UTC),
        )
    )

    checkpoint = await checkpoint_store.load_latest("op-1")

    assert checkpoint is not None
    suffix = await event_store.load_after("op-1", after_sequence=checkpoint.last_applied_sequence)
    assert [event.sequence for event in suffix] == [3]


@pytest.mark.anyio
async def test_event_store_atomic_batch_persistence_keeps_stream_unchanged_on_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = FileOperationEventStore(tmp_path / "operation_events")
    await store.append("op-1", 0, [_make_event("task.created", value=1)])

    def _raise_atomic_write(path: Path, content: str, *, encoding: str = "utf-8") -> None:
        raise RuntimeError("simulated write failure")

    monkeypatch.setattr(
        "agent_operator.runtime.event_sourcing.atomic_write_text",
        _raise_atomic_write,
    )

    with pytest.raises(RuntimeError, match="simulated write failure"):
        await store.append(
            "op-1",
            1,
            [
                _make_event("task.updated", value=2),
                _make_event("task.completed", value=3),
            ],
        )

    loaded = await store.load_after("op-1")
    assert [event.sequence for event in loaded] == [1]


def test_event_store_serializes_same_operation_appends_with_lock(tmp_path: Path) -> None:
    store = FileOperationEventStore(tmp_path / "operation_events")
    results: list[list[int]] = []
    errors: list[BaseException] = []
    original_atomic_write_text = event_sourcing_runtime.atomic_write_text

    def delayed_atomic_write_text(path: Path, content: str, *, encoding: str = "utf-8") -> None:
        time.sleep(0.05)
        original_atomic_write_text(path, content, encoding=encoding)

    def append_in_thread(value: int) -> None:
        try:
            stored = anyio.run(
                store.append,
                "op-1",
                0,
                [_make_event("task.created", value=value)],
            )
            results.append([event.sequence for event in stored])
        except BaseException as exc:  # pragma: no cover - assertion inspects contents.
            errors.append(exc)

    event_sourcing_runtime.atomic_write_text = delayed_atomic_write_text
    try:
        first = threading.Thread(target=append_in_thread, args=(1,))
        second = threading.Thread(target=append_in_thread, args=(2,))
        first.start()
        time.sleep(0.01)
        second.start()
        first.join(timeout=2)
        second.join(timeout=2)
    finally:
        event_sourcing_runtime.atomic_write_text = original_atomic_write_text

    assert len(results) == 1
    assert results[0] == [1]
    assert len(errors) == 1
    assert isinstance(errors[0], OperationEventStoreAppendConflict)
    loaded = anyio.run(store.load_after, "op-1")
    assert [event.sequence for event in loaded] == [1]


@pytest.mark.anyio
async def test_event_store_isolates_different_operations(tmp_path: Path) -> None:
    store = FileOperationEventStore(tmp_path / "operation_events")

    await store.append("op-1", 0, [_make_event("task.created", value=1)])
    await store.append("op-2", 0, [_make_event("task.created", value=2)])

    loaded_one = await store.load_after("op-1")
    loaded_two = await store.load_after("op-2")

    assert [event.payload["value"] for event in loaded_one] == [1]
    assert [event.payload["value"] for event in loaded_two] == [2]
