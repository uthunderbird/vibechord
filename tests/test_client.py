from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import anyio
import pytest

from agent_operator import OperatorClient
from agent_operator.domain import (
    AgentSessionHandle,
    AttentionRequest,
    AttentionStatus,
    AttentionType,
    CommandTargetScope,
    ExecutionBudget,
    InvolvementLevel,
    ObjectiveState,
    OperationCheckpoint,
    OperationCheckpointRecord,
    OperationGoal,
    OperationOutcome,
    OperationPolicy,
    OperationState,
    OperationStatus,
    RunEvent,
    RuntimeHints,
    SessionRecord,
    SessionRecordStatus,
)
from agent_operator.runtime import FileOperationCommandInbox, FileOperationStore, JsonlEventSink

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


@pytest.mark.anyio
async def test_operator_client_resolves_v2_only_operation_reference(tmp_path: Path) -> None:
    checkpoint = OperationCheckpoint.initial("op-sdk-v2")
    checkpoint.objective = ObjectiveState(objective="Canonical event-sourced SDK operation")
    checkpoint.created_at = datetime(2026, 4, 24, tzinfo=UTC)
    checkpoint.updated_at = checkpoint.created_at
    checkpoint_record = OperationCheckpointRecord(
        operation_id="op-sdk-v2",
        checkpoint_payload=checkpoint.model_dump(mode="json"),
        last_applied_sequence=0,
        checkpoint_format_version=1,
    )
    checkpoint_path = tmp_path / "operation_checkpoints" / "op-sdk-v2.json"
    checkpoint_path.parent.mkdir(parents=True)
    checkpoint_path.write_text(
        json.dumps({**checkpoint_record.model_dump(mode="json"), "epoch_id": 0}, indent=2),
        encoding="utf-8",
    )
    event_dir = tmp_path / "operation_events"
    event_dir.mkdir()
    (event_dir / "op-sdk-v2.jsonl").write_text("", encoding="utf-8")

    async with OperatorClient(data_dir=tmp_path) as client:
        brief = await client.get_status("op-sdk")

    assert brief.operation_id == "op-sdk-v2"
    assert brief.objective_brief == "Canonical event-sourced SDK operation"


async def test_operator_client_control_methods_use_delivery_command_facade(
    tmp_path: Path,
) -> None:
    """Catches swapping SDK control paths back to direct service/inbox calls."""
    operation_id = "op-sdk-control"
    store = FileOperationStore(tmp_path / "runs")
    operation = OperationState(
        operation_id=operation_id,
        goal=OperationGoal(objective="Control through SDK"),
        sessions=[
            SessionRecord(
                handle=AgentSessionHandle(
                    adapter_key="codex_acp",
                    session_id="session-sdk-control",
                    session_name="sdk",
                ),
                status=SessionRecordStatus.RUNNING,
            )
        ],
        attention_requests=[
            AttentionRequest(
                attention_id="att-sdk-control",
                operation_id=operation_id,
                attention_type=AttentionType.QUESTION,
                title="Need answer",
                question="Proceed?",
                blocking=True,
                status=AttentionStatus.OPEN,
                target_scope=CommandTargetScope.OPERATION,
                target_id=operation_id,
            )
        ],
        **state_settings(),
    )
    await store.save_operation(operation)

    async with OperatorClient(data_dir=tmp_path) as client:
        await client.answer_attention("op-sdk", "att-sdk", "Proceed")
        await client.interrupt("op-sdk")

    commands = await FileOperationCommandInbox(tmp_path / "commands").list(operation_id)
    assert [command.command_type.value for command in commands] == [
        "answer_attention_request",
        "stop_agent_turn",
    ]
    assert commands[0].target_id == "att-sdk-control"
    assert commands[0].payload == {"text": "Proceed"}
    assert commands[1].target_id == "session-sdk-control"


async def test_operator_client_lists_event_only_v2_operation(tmp_path: Path) -> None:
    """Catches the mutation where SDK list uses only FileOperationStore summaries."""
    checkpoint = OperationCheckpoint.initial("op-sdk-list-v2")
    checkpoint.objective = ObjectiveState(objective="Canonical event-sourced SDK list")
    checkpoint.status = OperationStatus.RUNNING
    checkpoint.created_at = datetime(2026, 4, 24, tzinfo=UTC)
    checkpoint.updated_at = checkpoint.created_at
    checkpoint_record = OperationCheckpointRecord(
        operation_id="op-sdk-list-v2",
        checkpoint_payload=checkpoint.model_dump(mode="json"),
        last_applied_sequence=0,
        checkpoint_format_version=1,
    )
    checkpoint_path = tmp_path / "operation_checkpoints" / "op-sdk-list-v2.json"
    checkpoint_path.parent.mkdir(parents=True)
    checkpoint_path.write_text(
        json.dumps({**checkpoint_record.model_dump(mode="json"), "epoch_id": 0}, indent=2),
        encoding="utf-8",
    )
    event_dir = tmp_path / "operation_events"
    event_dir.mkdir()
    (event_dir / "op-sdk-list-v2.jsonl").write_text("", encoding="utf-8")

    async with OperatorClient(data_dir=tmp_path) as client:
        summaries = await client.list_operations()

    assert [summary.operation_id for summary in summaries] == ["op-sdk-list-v2"]
    assert summaries[0].objective_prompt == "Canonical event-sourced SDK list"
