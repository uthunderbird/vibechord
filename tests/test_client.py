from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import anyio
import pytest

from agent_operator import OperatorClient
from agent_operator.domain import (
    ExecutionBudget,
    InvolvementLevel,
    OperationGoal,
    OperationOutcome,
    OperationPolicy,
    OperationState,
    OperationStatus,
    RunEvent,
    RuntimeHints,
)
from agent_operator.runtime import FileOperationStore, JsonlEventSink

pytestmark = pytest.mark.anyio


def state_settings(
    *,
    allowed_agents: list[str] | None = None,
    involvement_level: InvolvementLevel = InvolvementLevel.AUTO,
    max_iterations: int = 100,
    timeout_seconds: int | None = None,
    metadata: dict[str, object] | None = None,
    max_task_retries: int = 2,
    operator_message_window: int = 3,
) -> dict[str, object]:
    """Build split operation-state settings for SDK tests."""

    return {
        "policy": OperationPolicy(
            allowed_agents=list(allowed_agents or []),
            involvement_level=involvement_level,
        ),
        "execution_budget": ExecutionBudget(
            max_iterations=max_iterations,
            timeout_seconds=timeout_seconds,
            max_task_retries=max_task_retries,
        ),
        "runtime_hints": RuntimeHints(
            operator_message_window=operator_message_window,
            metadata=dict(metadata or {}),
        ),
    }


@pytest.mark.anyio
async def test_operator_client_requires_context_manager(tmp_path: Path) -> None:
    client = OperatorClient(data_dir=tmp_path)

    with pytest.raises(RuntimeError, match="async with"):
        await client.list_operations()

    async with client:
        assert await client.list_operations() == []

    with pytest.raises(RuntimeError, match="async with"):
        await client.list_operations()


@pytest.mark.anyio
async def test_operator_client_run_returns_operation_id(tmp_path: Path, monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeService:
        def __init__(self, *, event_sink: object | None) -> None:
            captured["event_sink"] = event_sink

        async def run(
            self,
            goal: OperationGoal,
            options,
            *,
            operation_id: str | None = None,
            attached_sessions=None,
            policy=None,
            budget=None,
            runtime_hints=None,
        ) -> OperationOutcome:
            del options, attached_sessions, policy, budget, runtime_hints
            assert operation_id is not None
            captured["goal"] = goal.objective_text
            captured["operation_id"] = operation_id
            return OperationOutcome(
                operation_id=operation_id,
                status=OperationStatus.RUNNING,
                summary="started",
            )

    monkeypatch.setattr(
        "agent_operator.client.build_service",
        lambda settings, event_sink=None: FakeService(event_sink=event_sink),
    )

    async with OperatorClient(data_dir=tmp_path) as client:
        operation_id = await client.run("inspect the repository")

    assert operation_id == captured["operation_id"]
    assert captured["goal"] == "inspect the repository"
    assert captured["event_sink"]._path == tmp_path / "events" / f"{operation_id}.jsonl"


@pytest.mark.anyio
async def test_operator_client_stream_events_terminates_on_cycle_finished(tmp_path: Path) -> None:
    operation_id = "op-sdk-events"
    store = FileOperationStore(tmp_path / "runs")
    sink = JsonlEventSink(tmp_path, operation_id)
    state = OperationState(
        operation_id=operation_id,
        goal=OperationGoal(objective="Inspect the repo"),
        status=OperationStatus.COMPLETED,
        final_summary="done",
        **state_settings(),
    )
    await store.save_operation(state)
    await store.save_outcome(
        OperationOutcome(
            operation_id=operation_id,
            status=OperationStatus.COMPLETED,
            summary="done",
        )
    )
    await sink.emit(
        RunEvent(
            event_type="operation.started",
            operation_id=operation_id,
            iteration=0,
            payload={"objective": "Inspect the repo"},
            category="trace",
        )
    )
    await sink.emit(
        RunEvent(
            event_type="operation.cycle_finished",
            operation_id=operation_id,
            iteration=1,
            payload={"summary": "done"},
            category="trace",
        )
    )

    async with OperatorClient(data_dir=tmp_path) as client:
        event_types: list[str] = []
        with anyio.fail_after(1):
            async for event in client.stream_events(operation_id):
                event_types.append(event.event_type)

    assert event_types == ["operation.started", "operation.cycle_finished"]


@pytest.mark.anyio
async def test_operator_client_resolves_last_operation_reference(tmp_path: Path) -> None:
    store = FileOperationStore(tmp_path / "runs")
    older = OperationState(
        operation_id="op-sdk-older",
        goal=OperationGoal(objective="Older operation"),
        created_at=datetime(2026, 4, 13, tzinfo=UTC),
        **state_settings(),
    )
    newer = OperationState(
        operation_id="op-sdk-newer",
        goal=OperationGoal(objective="Newer operation"),
        created_at=datetime(2026, 4, 14, tzinfo=UTC),
        **state_settings(),
    )
    await store.save_operation(older)
    await store.save_operation(newer)

    async with OperatorClient(data_dir=tmp_path) as client:
        brief = await client.get_status("last")

    assert brief.operation_id == "op-sdk-newer"
