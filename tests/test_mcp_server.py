from __future__ import annotations

import json
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

import pytest

import agent_operator.cli.commands.mcp as mcp_command
from agent_operator.application.queries.operation_status_queries import OperationReadPayload
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
    RuntimeHints,
    SchedulerState,
    SessionRecord,
    SessionRecordStatus,
    TaskState,
    TaskStatus,
)
from agent_operator.mcp.server import OperatorMcpServer
from agent_operator.mcp.service import McpToolError, OperatorMcpService
from agent_operator.runtime import FileOperationStore


def _encode_message(message: dict[str, object]) -> bytes:
    body = json.dumps(message).encode("utf-8")
    return f"Content-Length: {len(body)}\r\n\r\n".encode("ascii") + body


def _decode_messages(payload: bytes) -> list[dict[str, object]]:
    messages: list[dict[str, object]] = []
    buffer = BytesIO(payload)
    while True:
        header = buffer.readline()
        if not header:
            return messages
        content_length = int(header.decode("ascii").split(":", 1)[1].strip())
        assert buffer.readline() == b"\r\n"
        messages.append(json.loads(buffer.read(content_length).decode("utf-8")))


class _FakeMcpService:
    async def list_operations(self, *, status_filter):
        assert status_filter is None
        return [{"operation_id": "op-1", "status": "running"}]

    async def run_operation(self, *, goal, agent, wait, timeout_seconds):
        return {"operation_id": "op-2", "status": "running"}

    async def get_status(self, *, operation_id):
        return {"operation_id": operation_id, "status": "running"}

    async def answer_attention(self, *, operation_id, attention_id, answer):
        return {"attention_id": attention_id or "att-1", "status": "answered"}

    async def cancel_operation(self, *, operation_id, reason):
        return {"operation_id": operation_id, "status": "cancelled"}

    async def interrupt_operation(self, *, operation_id):
        return {"operation_id": operation_id, "acknowledged": True}


def test_mcp_server_handles_initialize_and_tools_list() -> None:
    server = OperatorMcpServer(_FakeMcpService())  # type: ignore[arg-type]
    stdin = BytesIO(
        _encode_message(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {"protocolVersion": "2025-03-26"},
            }
        )
        + _encode_message(
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/list",
                "params": {},
            }
        )
    )
    stdout = BytesIO()

    server.serve(stdin, stdout)

    messages = _decode_messages(stdout.getvalue())
    assert messages[0]["result"]["serverInfo"]["name"] == "operator"
    tools = messages[1]["result"]["tools"]
    tool_names = [tool["name"] for tool in tools]
    assert tool_names == [
        "list_operations",
        "run_operation",
        "get_status",
        "answer_attention",
        "cancel_operation",
        "interrupt_operation",
    ]
    run_operation = next(tool for tool in tools if tool["name"] == "run_operation")
    assert run_operation["inputSchema"]["required"] == ["goal"]


def test_mcp_command_runs_stdio_server(monkeypatch) -> None:
    stdin = BytesIO(
        _encode_message(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {"protocolVersion": "2025-03-26"},
            }
        )
    )
    stdout = BytesIO()
    monkeypatch.setattr(mcp_command, "build_operator_mcp_service", lambda: _FakeMcpService())
    monkeypatch.setattr(
        mcp_command,
        "sys",
        SimpleNamespace(
            stdin=SimpleNamespace(buffer=stdin),
            stdout=SimpleNamespace(buffer=stdout),
        ),
    )

    mcp_command.mcp()

    [message] = _decode_messages(stdout.getvalue())
    assert message["result"]["serverInfo"]["name"] == "operator"


def test_mcp_server_returns_structured_tool_error() -> None:
    class _ErrorService(_FakeMcpService):
        async def get_status(self, *, operation_id):
            raise McpToolError("not_found", "Operation missing.", operation_id=operation_id)

    server = OperatorMcpServer(_ErrorService())  # type: ignore[arg-type]
    stdin = BytesIO(
        _encode_message(
            {
                "jsonrpc": "2.0",
                "id": 7,
                "method": "tools/call",
                "params": {"name": "get_status", "arguments": {"operation_id": "op-missing"}},
            }
        )
    )
    stdout = BytesIO()

    server.serve(stdin, stdout)

    [message] = _decode_messages(stdout.getvalue())
    assert message["error"]["code"] == -32000
    assert message["error"]["data"] == {
        "code": "not_found",
        "operation_id": "op-missing",
    }


def test_mcp_server_rejects_unknown_tool_arguments() -> None:
    server = OperatorMcpServer(_FakeMcpService())  # type: ignore[arg-type]
    stdin = BytesIO(
        _encode_message(
            {
                "jsonrpc": "2.0",
                "id": 8,
                "method": "tools/call",
                "params": {
                    "name": "get_status",
                    "arguments": {"operation_id": "op-1", "unexpected": True},
                },
            }
        )
    )
    stdout = BytesIO()

    server.serve(stdin, stdout)

    [message] = _decode_messages(stdout.getvalue())
    assert message["error"]["code"] == -32000
    assert message["error"]["data"] == {"code": "invalid_state"}
    assert "published schema" in message["error"]["message"]


def test_mcp_server_wraps_unhandled_handler_failure() -> None:
    class _BrokenService(_FakeMcpService):
        async def get_status(self, *, operation_id):
            del operation_id
            raise RuntimeError("boom")

    server = OperatorMcpServer(_BrokenService())  # type: ignore[arg-type]
    stdin = BytesIO(
        _encode_message(
            {
                "jsonrpc": "2.0",
                "id": 9,
                "method": "tools/call",
                "params": {"name": "get_status", "arguments": {"operation_id": "op-1"}},
            }
        )
    )
    stdout = BytesIO()

    server.serve(stdin, stdout)

    [message] = _decode_messages(stdout.getvalue())
    assert message["error"]["code"] == -32000
    assert message["error"]["data"] == {"code": "internal_error"}
    assert "Unhandled MCP server error" in message["error"]["message"]


def _settings_loader_factory(tmp_path: Path):
    class _Settings:
        def __init__(self) -> None:
            self.data_dir = tmp_path

    return _Settings


@pytest.mark.anyio
async def test_operator_mcp_service_lists_and_reports_status(tmp_path: Path) -> None:
    store = FileOperationStore(tmp_path / "runs")
    started_at = datetime(2026, 4, 12, 10, 0, tzinfo=UTC)
    ended_at = datetime(2026, 4, 12, 10, 5, tzinfo=UTC)
    operation = OperationState(
        operation_id="op-1",
        goal=OperationGoal(objective="Inspect repo"),
        policy=OperationPolicy(
            allowed_agents=["codex_acp"],
            involvement_level=InvolvementLevel.AUTO,
        ),
        execution_budget=ExecutionBudget(max_iterations=25),
        runtime_hints=RuntimeHints(metadata={"project_profile_name": "operator"}),
        status=OperationStatus.NEEDS_HUMAN,
        scheduler_state=SchedulerState.ACTIVE,
        run_started_at=started_at,
        created_at=started_at,
        updated_at=ended_at,
        tasks=[
            TaskState(
                task_id="task-1",
                title="Primary objective",
                goal="Inspect repo",
                definition_of_done="Done",
                status=TaskStatus.RUNNING,
                brain_priority=100,
                effective_priority=100,
            ),
            TaskState(
                task_id="task-2",
                title="Blocked task",
                goal="Wait",
                definition_of_done="Done",
                status=TaskStatus.PENDING,
                brain_priority=50,
                effective_priority=50,
            ),
        ],
        sessions=[
            SessionRecord(
                handle=AgentSessionHandle(
                    adapter_key="codex_acp",
                    session_id="session-1",
                    session_name="inspect",
                ),
                status=SessionRecordStatus.RUNNING,
            )
        ],
        attention_requests=[
            AttentionRequest(
                attention_id="att-1",
                operation_id="op-1",
                attention_type=AttentionType.QUESTION,
                title="Need input",
                question="Approve?",
                blocking=True,
                status=AttentionStatus.OPEN,
                target_scope=CommandTargetScope.OPERATION,
                target_id="op-1",
                created_at=started_at,
            )
        ],
    )
    outcome = OperationOutcome(
        operation_id="op-1",
        status=OperationStatus.NEEDS_HUMAN,
        summary="Awaiting answer.",
        ended_at=ended_at,
    )
    await store.save_operation(operation)
    await store.save_outcome(outcome)

    class _StatusService:
        async def build_read_payload(self, operation_id: str) -> OperationReadPayload:
            loaded = await store.load_operation(operation_id)
            loaded_outcome = await store.load_outcome(operation_id)
            return OperationReadPayload(
                operation_id=operation_id,
                operation=loaded,
                outcome=loaded_outcome,
                source="legacy_snapshot",
            )

        async def build_status_payload(self, operation_id: str):
            loaded = await store.load_operation(operation_id)
            loaded_outcome = await store.load_outcome(operation_id)
            return loaded, loaded_outcome, None, None

    class _DeliveryService:
        async def answer_attention(self, *args, **kwargs):  # pragma: no cover - unused here
            raise AssertionError

        async def cancel(self, *args, **kwargs):  # pragma: no cover - unused here
            raise AssertionError

        async def enqueue_stop_turn(self, *args, **kwargs):  # pragma: no cover - unused here
            raise AssertionError

    settings_loader = _settings_loader_factory(tmp_path)
    service = OperatorMcpService(
        status_service_factory=lambda settings: _StatusService(),
        delivery_service_factory=lambda settings: _DeliveryService(),
        settings_loader=settings_loader,
        settings_loader_with_data_dir=lambda: (settings_loader(), "env"),
        service_builder=lambda settings, event_sink=None: None,
        store_builder=lambda settings: store,
        event_sink_builder=lambda settings, operation_id: None,
    )

    listed = await service.list_operations(status_filter=OperationStatus.NEEDS_HUMAN)
    status = await service.get_status(operation_id="op-1")

    assert listed == [
        {
            "operation_id": "op-1",
            "status": "needs_human",
            "goal": "Inspect repo",
            "started_at": started_at.isoformat(),
            "attention_count": 1,
        }
    ]
    assert status["attention_requests"] == [
        {
            "id": "att-1",
            "question": "Approve?",
            "created_at": started_at.isoformat(),
        }
    ]
    assert status["ended_at"] == ended_at.isoformat()
    assert "running=1" in str(status["task_summary"])


@pytest.mark.anyio
async def test_operator_mcp_service_answer_cancel_interrupt_and_timeout_validation(
    tmp_path: Path,
    monkeypatch,
) -> None:
    settings_loader = _settings_loader_factory(tmp_path)
    store = FileOperationStore(tmp_path / "runs")
    operation = OperationState(
        operation_id="op-1",
        goal=OperationGoal(objective="Inspect repo"),
        policy=OperationPolicy(),
        execution_budget=ExecutionBudget(),
        runtime_hints=RuntimeHints(),
    )
    await store.save_operation(operation)
    monkeypatch.chdir(tmp_path)
    (tmp_path / "operator-profile.yaml").write_text("name: operator\ncwd: .\n", encoding="utf-8")

    class _DeliveryService:
        async def answer_attention(
            self,
            operation_id,
            *,
            attention_id,
            text,
            promote,
            policy_payload,
        ):
            class _Command:
                target_id = attention_id or "att-oldest"

            return _Command(), None, None

        async def cancel(self, operation_id, *, session_id, run_id, reason=None):
            return OperationOutcome(
                operation_id=operation_id,
                status=OperationStatus.CANCELLED,
                summary=f"Operation cancelled: {reason}." if reason else "Operation cancelled.",
            )

        async def enqueue_stop_turn(self, operation_id, *, task_id=None):
            return None

    service = OperatorMcpService(
        status_service_factory=lambda settings: None,
        delivery_service_factory=lambda settings: _DeliveryService(),
        settings_loader=settings_loader,
        settings_loader_with_data_dir=lambda: (settings_loader(), "env"),
        service_builder=lambda settings, event_sink=None: None,
        store_builder=lambda settings: store,
        event_sink_builder=lambda settings, operation_id: None,
    )

    answered = await service.answer_attention(
        operation_id="op-1",
        attention_id=None,
        answer="Proceed",
    )
    cancelled = await service.cancel_operation(operation_id="op-1", reason="user-requested")
    interrupted = await service.interrupt_operation(operation_id="op-1")

    assert answered == {"attention_id": "att-oldest", "status": "answered"}
    assert cancelled == {"operation_id": "op-1", "status": "cancelled"}
    assert interrupted == {"operation_id": "op-1", "acknowledged": True}

    with pytest.raises(McpToolError, match="timeout_seconds is supported only when wait=true."):
        await service.run_operation(
            goal="Inspect repo",
            agent=None,
            wait=False,
            timeout_seconds=5,
        )


@pytest.mark.anyio
async def test_operator_mcp_service_resolves_v2_only_operation_reference(tmp_path: Path) -> None:
    settings_loader = _settings_loader_factory(tmp_path)
    store = FileOperationStore(tmp_path / "runs")
    checkpoint = OperationCheckpoint.initial("op-mcp-v2")
    checkpoint.objective = ObjectiveState(objective="Canonical MCP operation")
    checkpoint.created_at = datetime(2026, 4, 24, tzinfo=UTC)
    checkpoint.updated_at = checkpoint.created_at
    checkpoint_record = OperationCheckpointRecord(
        operation_id="op-mcp-v2",
        checkpoint_payload=checkpoint.model_dump(mode="json"),
        last_applied_sequence=0,
        checkpoint_format_version=1,
    )
    checkpoint_path = tmp_path / "operation_checkpoints" / "op-mcp-v2.json"
    checkpoint_path.parent.mkdir(parents=True)
    checkpoint_path.write_text(
        json.dumps({**checkpoint_record.model_dump(mode="json"), "epoch_id": 0}, indent=2),
        encoding="utf-8",
    )
    event_dir = tmp_path / "operation_events"
    event_dir.mkdir()
    (event_dir / "op-mcp-v2.jsonl").write_text("", encoding="utf-8")

    service = OperatorMcpService(
        status_service_factory=lambda settings: None,
        delivery_service_factory=lambda settings: None,
        settings_loader=settings_loader,
        settings_loader_with_data_dir=lambda: (settings_loader(), "env"),
        service_builder=lambda settings, event_sink=None: None,
        store_builder=lambda settings: store,
        event_sink_builder=lambda settings, operation_id: None,
    )

    resolved = await service._resolve_operation_id("op-mcp")  # noqa: SLF001

    assert resolved == "op-mcp-v2"


@pytest.mark.anyio
async def test_operator_mcp_service_maps_ambiguous_prefix_without_message_sniffing(
    tmp_path: Path,
) -> None:
    settings_loader = _settings_loader_factory(tmp_path)
    store = FileOperationStore(tmp_path / "runs")
    for operation_id in ("op-mcp-ambiguous-a", "op-mcp-ambiguous-b"):
        checkpoint = OperationCheckpoint.initial(operation_id)
        checkpoint.objective = ObjectiveState(objective=f"Canonical {operation_id}")
        checkpoint.created_at = datetime(2026, 4, 24, tzinfo=UTC)
        checkpoint.updated_at = checkpoint.created_at
        checkpoint_record = OperationCheckpointRecord(
            operation_id=operation_id,
            checkpoint_payload=checkpoint.model_dump(mode="json"),
            last_applied_sequence=0,
            checkpoint_format_version=1,
        )
        checkpoint_path = tmp_path / "operation_checkpoints" / f"{operation_id}.json"
        checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
        checkpoint_path.write_text(
            json.dumps({**checkpoint_record.model_dump(mode="json"), "epoch_id": 0}, indent=2),
            encoding="utf-8",
        )
        event_dir = tmp_path / "operation_events"
        event_dir.mkdir(exist_ok=True)
        (event_dir / f"{operation_id}.jsonl").write_text("", encoding="utf-8")

    service = OperatorMcpService(
        status_service_factory=lambda settings: None,
        delivery_service_factory=lambda settings: None,
        settings_loader=settings_loader,
        settings_loader_with_data_dir=lambda: (settings_loader(), "env"),
        service_builder=lambda settings, event_sink=None: None,
        store_builder=lambda settings: store,
        event_sink_builder=lambda settings, operation_id: None,
    )

    with pytest.raises(McpToolError) as exc_info:
        await service._resolve_operation_id("op-mcp-ambiguous")  # noqa: SLF001

    assert exc_info.value.code == "invalid_state"
    assert "op-mcp-ambiguous-a" in exc_info.value.message
    assert "op-mcp-ambiguous-b" in exc_info.value.message


@pytest.mark.anyio
async def test_operator_mcp_service_lists_event_only_v2_operation(tmp_path: Path) -> None:
    """Catches the mutation where MCP list enumerates only FileOperationStore snapshots."""
    settings_loader = _settings_loader_factory(tmp_path)
    store = FileOperationStore(tmp_path / "runs")
    checkpoint = OperationCheckpoint.initial("op-mcp-list-v2")
    checkpoint.objective = ObjectiveState(objective="Canonical MCP list operation")
    checkpoint.status = OperationStatus.RUNNING
    checkpoint.created_at = datetime(2026, 4, 24, tzinfo=UTC)
    checkpoint.updated_at = checkpoint.created_at
    checkpoint_record = OperationCheckpointRecord(
        operation_id="op-mcp-list-v2",
        checkpoint_payload=checkpoint.model_dump(mode="json"),
        last_applied_sequence=0,
        checkpoint_format_version=1,
    )
    checkpoint_path = tmp_path / "operation_checkpoints" / "op-mcp-list-v2.json"
    checkpoint_path.parent.mkdir(parents=True)
    checkpoint_path.write_text(
        json.dumps({**checkpoint_record.model_dump(mode="json"), "epoch_id": 0}, indent=2),
        encoding="utf-8",
    )
    event_dir = tmp_path / "operation_events"
    event_dir.mkdir()
    (event_dir / "op-mcp-list-v2.jsonl").write_text("", encoding="utf-8")
    service = OperatorMcpService(
        status_service_factory=lambda settings: None,
        delivery_service_factory=lambda settings: None,
        settings_loader=settings_loader,
        settings_loader_with_data_dir=lambda: (settings_loader(), "env"),
        service_builder=lambda settings, event_sink=None: None,
        store_builder=lambda settings: store,
        event_sink_builder=lambda settings, operation_id: None,
    )

    listed = await service.list_operations(status_filter=None)

    assert listed == [
        {
            "operation_id": "op-mcp-list-v2",
            "status": "running",
            "goal": "Canonical MCP list operation",
            "started_at": "2026-04-24T00:00:00+00:00",
            "attention_count": 0,
        }
    ]
