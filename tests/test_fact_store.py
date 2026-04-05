from __future__ import annotations

import threading
import time
from datetime import UTC, datetime
from pathlib import Path

import anyio
import pytest

import agent_operator.runtime.facts as runtime_facts
from agent_operator.domain import (
    AdapterFactDraft,
    FactFamily,
    FactStoreAppendConflict,
    TechnicalFactDraft,
)
from agent_operator.runtime import FileFactStore


def _adapter_fact(*, value: int) -> AdapterFactDraft:
    return AdapterFactDraft(
        fact_type="acp.notification.received",
        payload={"value": value},
        observed_at=datetime(2026, 4, 3, tzinfo=UTC),
        adapter_key="codex_acp",
        session_id="session-1",
    )


def _technical_fact(*, value: int, source_fact_ids: list[str]) -> TechnicalFactDraft:
    return TechnicalFactDraft(
        fact_type="execution.start_observed",
        payload={"value": value},
        observed_at=datetime(2026, 4, 3, tzinfo=UTC),
        source_fact_ids=source_fact_ids,
        session_id="session-1",
        execution_id="execution-1",
    )


@pytest.mark.anyio
async def test_fact_store_assigns_shared_operation_sequences_across_fact_families(
    tmp_path: Path,
) -> None:
    store = FileFactStore(tmp_path / "facts")

    adapter_facts = await store.append_adapter_facts("op-1", 0, [_adapter_fact(value=1)])
    technical_facts = await store.append_technical_facts(
        "op-1",
        1,
        [_technical_fact(value=2, source_fact_ids=[adapter_facts[0].fact_id])],
    )

    assert [fact.sequence for fact in adapter_facts] == [1]
    assert [fact.sequence for fact in technical_facts] == [2]
    assert technical_facts[0].source_fact_ids == [adapter_facts[0].fact_id]


@pytest.mark.anyio
async def test_fact_store_load_after_filters_by_family(tmp_path: Path) -> None:
    store = FileFactStore(tmp_path / "facts")
    adapter_facts = await store.append_adapter_facts("op-1", 0, [_adapter_fact(value=1)])
    await store.append_technical_facts(
        "op-1",
        1,
        [_technical_fact(value=2, source_fact_ids=[adapter_facts[0].fact_id])],
    )

    adapter_only = await store.load_after("op-1", family=FactFamily.ADAPTER)
    technical_only = await store.load_after("op-1", family=FactFamily.TECHNICAL)

    assert [fact.family for fact in adapter_only] == [FactFamily.ADAPTER]
    assert [fact.family for fact in technical_only] == [FactFamily.TECHNICAL]


@pytest.mark.anyio
async def test_fact_store_load_by_fact_ids_returns_matching_facts(tmp_path: Path) -> None:
    store = FileFactStore(tmp_path / "facts")
    first = await store.append_adapter_facts("op-1", 0, [_adapter_fact(value=1)])
    second = await store.append_adapter_facts("op-1", 1, [_adapter_fact(value=2)])

    loaded = await store.load_by_fact_ids("op-1", [second[0].fact_id, first[0].fact_id])

    assert [fact.fact_id for fact in loaded] == [first[0].fact_id, second[0].fact_id]


@pytest.mark.anyio
async def test_fact_store_rejects_stale_expected_sequence(tmp_path: Path) -> None:
    store = FileFactStore(tmp_path / "facts")
    await store.append_adapter_facts("op-1", 0, [_adapter_fact(value=1)])

    with pytest.raises(FactStoreAppendConflict):
        await store.append_technical_facts(
            "op-1",
            0,
            [_technical_fact(value=2, source_fact_ids=["fact-1"])],
        )


@pytest.mark.anyio
async def test_fact_store_atomic_batch_failure_leaves_existing_stream_unchanged(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = FileFactStore(tmp_path / "facts")
    await store.append_adapter_facts("op-1", 0, [_adapter_fact(value=1)])

    def _raise_atomic_write(path: Path, content: str, *, encoding: str = "utf-8") -> None:
        raise RuntimeError("simulated fact write failure")

    monkeypatch.setattr(
        "agent_operator.runtime.facts.atomic_write_text",
        _raise_atomic_write,
    )

    with pytest.raises(RuntimeError, match="simulated fact write failure"):
        await store.append_technical_facts(
            "op-1",
            1,
            [_technical_fact(value=2, source_fact_ids=["fact-1"])],
        )

    loaded = await store.load_after("op-1")
    assert [fact.sequence for fact in loaded] == [1]


def test_fact_store_serializes_same_operation_appends_with_lock(tmp_path: Path) -> None:
    store = FileFactStore(tmp_path / "facts")
    results: list[list[int]] = []
    errors: list[BaseException] = []
    original_atomic_write_text = runtime_facts.atomic_write_text

    def delayed_atomic_write_text(path: Path, content: str, *, encoding: str = "utf-8") -> None:
        time.sleep(0.05)
        original_atomic_write_text(path, content, encoding=encoding)

    def append_in_thread(value: int) -> None:
        try:
            stored = anyio.run(
                store.append_adapter_facts,
                "op-1",
                0,
                [_adapter_fact(value=value)],
            )
            results.append([fact.sequence for fact in stored])
        except BaseException as exc:  # pragma: no cover
            errors.append(exc)

    runtime_facts.atomic_write_text = delayed_atomic_write_text
    try:
        first = threading.Thread(target=append_in_thread, args=(1,))
        second = threading.Thread(target=append_in_thread, args=(2,))
        first.start()
        time.sleep(0.01)
        second.start()
        first.join(timeout=2)
        second.join(timeout=2)
    finally:
        runtime_facts.atomic_write_text = original_atomic_write_text

    assert len(results) == 1
    assert results[0] == [1]
    assert len(errors) == 1
    assert isinstance(errors[0], FactStoreAppendConflict)


@pytest.mark.anyio
async def test_fact_store_isolates_different_operations(tmp_path: Path) -> None:
    store = FileFactStore(tmp_path / "facts")

    await store.append_adapter_facts("op-1", 0, [_adapter_fact(value=1)])
    await store.append_adapter_facts("op-2", 0, [_adapter_fact(value=2)])

    loaded_one = await store.load_after("op-1")
    loaded_two = await store.load_after("op-2")

    assert [fact.payload["value"] for fact in loaded_one] == [1]
    assert [fact.payload["value"] for fact in loaded_two] == [2]
