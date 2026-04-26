from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from agent_operator.acp.adapter_runtime import AcpAdapterRuntime
from agent_operator.acp.client import AcpJsonRpcError
from agent_operator.acp.permissions import AcpPermissionDecision, PermissionEvaluationResult
from agent_operator.acp.session_runtime import AcpAgentSessionRuntime
from agent_operator.adapters.codex_acp import CodexAcpAgentAdapter
from agent_operator.adapters.opencode_acp import OpencodeAcpAgentAdapter
from agent_operator.domain import (
    AgentSessionCommand,
    AgentSessionCommandType,
)


class FakeAcpConnection:
    """Minimal ACP connection double for session-runtime tests."""

    def __init__(self) -> None:
        self.started = False
        self.closed = False
        self.requests: list[tuple[str, dict]] = []
        self.notifications: list[tuple[str, dict]] = []
        self.responses: list[tuple[int, dict | None, dict | None]] = []
        self.drained_notifications: list[dict] = []
        self.next_session_id = "sess-1"

    async def start(self) -> None:
        self.started = True

    async def request(self, method: str, params: dict | None = None) -> dict:
        payload = params or {}
        self.requests.append((method, payload))
        if method == "session/new":
            return {"sessionId": self.next_session_id}
        if method == "session/fork":
            return {"sessionId": "sess-2"}
        if method == "session/load":
            return {"sessionId": payload.get("sessionId", self.next_session_id)}
        if method == "session/prompt":
            await asyncio.sleep(0.05)
            return {"stopReason": "completed"}
        return {"ok": True}

    async def respond(self, request_id: int, *, result=None, error=None) -> None:
        self.responses.append((request_id, result, error))

    async def notify(self, method: str, params: dict | None = None) -> None:
        self.notifications.append((method, params or {}))

    def drain_notifications(self) -> list[dict]:
        items = list(self.drained_notifications)
        self.drained_notifications.clear()
        return items

    def stderr_text(self, limit: int = 4000) -> str:
        return ""

    async def close(self) -> None:
        self.closed = True


class RejectPermissionEvaluator:
    """Permission evaluator double that rejects every permission request.

    Example:
        evaluator = RejectPermissionEvaluator()
        result = await evaluator.evaluate(
            operation_id="op-1",
            working_directory=Path.cwd(),
            request={},
        )
        assert result.decision is AcpPermissionDecision.REJECT
    """

    async def evaluate(self, **_: object) -> PermissionEvaluationResult:
        return PermissionEvaluationResult(
            decision=AcpPermissionDecision.REJECT,
            rationale="Outside harness scope.",
            decision_source="brain",
        )


@pytest.mark.anyio
async def test_acp_agent_session_runtime_starts_single_live_session() -> None:
    connection = FakeAcpConnection()
    adapter_runtime = AcpAdapterRuntime(
        adapter_key="codex_acp",
        working_directory=Path.cwd(),
        connection=connection,
        poll_interval_seconds=0.01,
    )
    runtime = AcpAgentSessionRuntime(
        adapter_runtime=adapter_runtime,
        working_directory=Path.cwd(),
    )

    async with runtime:
        stream = runtime.events()
        await runtime.send(
            AgentSessionCommand(
                command_type=AgentSessionCommandType.START_SESSION,
                instruction="Inspect the repository",
            )
        )
        started = await asyncio.wait_for(anext(stream), timeout=1.0)
        await asyncio.sleep(0.02)

    assert (
        ("session/new", {"cwd": str(Path.cwd().resolve()), "mcpServers": []})
        in connection.requests
    )
    assert any(
        method == "session/prompt" and payload["sessionId"] == "sess-1"
        for method, payload in connection.requests
    )
    assert started.fact_type == "session.started"
    assert started.session_id == "sess-1"
    assert not any(method == "session/cancel" for method, _payload in connection.notifications)


@pytest.mark.anyio
async def test_acp_agent_session_runtime_exit_does_not_emit_session_cancel_notification() -> None:
    connection = FakeAcpConnection()
    adapter_runtime = AcpAdapterRuntime(
        adapter_key="codex_acp",
        working_directory=Path.cwd(),
        connection=connection,
        poll_interval_seconds=0.01,
    )
    runtime = AcpAgentSessionRuntime(
        adapter_runtime=adapter_runtime,
        working_directory=Path.cwd(),
    )

    async with runtime:
        await runtime.send(
            AgentSessionCommand(
                command_type=AgentSessionCommandType.START_SESSION,
                instruction="Inspect the repository",
            )
        )
        await asyncio.sleep(0.02)

    assert not any(method == "session/cancel" for method, _payload in connection.notifications)


@pytest.mark.anyio
async def test_acp_agent_session_runtime_rejects_second_live_session_start() -> None:
    connection = FakeAcpConnection()
    adapter_runtime = AcpAdapterRuntime(
        adapter_key="codex_acp",
        working_directory=Path.cwd(),
        connection=connection,
        poll_interval_seconds=0.01,
    )
    runtime = AcpAgentSessionRuntime(
        adapter_runtime=adapter_runtime,
        working_directory=Path.cwd(),
    )

    async with runtime:
        await runtime.send(
            AgentSessionCommand(
                command_type=AgentSessionCommandType.START_SESSION,
                instruction="First instruction",
            )
        )
        with pytest.raises(RuntimeError, match="already has a live session"):
            await runtime.send(
                AgentSessionCommand(
                    command_type=AgentSessionCommandType.START_SESSION,
                    instruction="Second instruction",
                )
            )


@pytest.mark.anyio
async def test_acp_agent_session_runtime_emits_technical_fact_for_progress_notification() -> None:
    connection = FakeAcpConnection()
    adapter_runtime = AcpAdapterRuntime(
        adapter_key="claude_acp",
        working_directory=Path.cwd(),
        connection=connection,
        poll_interval_seconds=0.01,
    )
    runtime = AcpAgentSessionRuntime(
        adapter_runtime=adapter_runtime,
        working_directory=Path.cwd(),
    )

    async with runtime:
        stream = runtime.events()
        await runtime.send(
            AgentSessionCommand(
                command_type=AgentSessionCommandType.START_SESSION,
                instruction="Inspect the repository",
            )
        )
        _started = await asyncio.wait_for(anext(stream), timeout=1.0)
        next_fact_task = asyncio.create_task(anext(stream))
        await asyncio.sleep(0.02)
        connection.drained_notifications.append(
            {
                "method": "session/update",
                "params": {
                    "sessionId": "sess-1",
                    "update": {
                        "sessionUpdate": "agent_message_chunk",
                        "content": {"type": "text", "text": "hello"},
                    },
                },
            }
        )
        fact = await asyncio.wait_for(next_fact_task, timeout=1.0)

    assert fact.fact_type == "session.output_chunk_observed"
    assert fact.session_id == "sess-1"
    assert fact.payload["text"] == "hello"


@pytest.mark.anyio
async def test_acp_agent_session_runtime_emits_discontinuity_fact_on_replace() -> None:
    connection = FakeAcpConnection()
    adapter_runtime = AcpAdapterRuntime(
        adapter_key="claude_acp",
        working_directory=Path.cwd(),
        connection=connection,
        poll_interval_seconds=0.01,
    )
    runtime = AcpAgentSessionRuntime(
        adapter_runtime=adapter_runtime,
        working_directory=Path.cwd(),
    )

    async with runtime:
        stream = runtime.events()
        await runtime.send(
            AgentSessionCommand(
                command_type=AgentSessionCommandType.START_SESSION,
                instruction="Inspect the repository",
            )
        )
        first_started = await asyncio.wait_for(anext(stream), timeout=1.0)
        _completed = await asyncio.wait_for(anext(stream), timeout=1.0)
        connection.next_session_id = "sess-2"
        await runtime.send(
            AgentSessionCommand(
                command_type=AgentSessionCommandType.REPLACE_SESSION,
                instruction="Start over with a fresh session",
            )
        )
        started = await asyncio.wait_for(anext(stream), timeout=1.0)
        fact = await asyncio.wait_for(anext(stream), timeout=1.0)

    assert first_started.fact_type == "session.started"
    assert started.fact_type == "session.started"
    assert fact.fact_type == "session.discontinuity_observed"
    assert fact.session_id == "sess-2"
    assert fact.payload["previous_session_id"] == "sess-1"
    assert fact.payload["new_session_id"] == "sess-2"


@pytest.mark.anyio
async def test_acp_agent_session_runtime_configures_loaded_session_after_fork() -> None:
    connection = FakeAcpConnection()
    configured_session_ids: list[str] = []
    adapter_runtime = AcpAdapterRuntime(
        adapter_key="codex_acp",
        working_directory=Path.cwd(),
        connection=connection,
        poll_interval_seconds=0.01,
    )
    async def configure_loaded_session(_connection, session_id: str) -> None:
        configured_session_ids.append(session_id)

    runtime = AcpAgentSessionRuntime(
        adapter_runtime=adapter_runtime,
        working_directory=Path.cwd(),
        configure_loaded_session=configure_loaded_session,
    )

    async with runtime:
        stream = runtime.events()
        await runtime.send(
            AgentSessionCommand(
                command_type=AgentSessionCommandType.FORK_SESSION,
                session_id="sess-1",
            )
        )
        started = await asyncio.wait_for(anext(stream), timeout=1.0)

    assert ("session/fork", {"cwd": str(Path.cwd().resolve()), "sessionId": "sess-1"}) in [
        (method, {key: value for key, value in payload.items() if key != "mcpServers"})
        for method, payload in connection.requests
        if method == "session/fork"
    ]
    assert configured_session_ids == ["sess-2"]
    assert started.fact_type == "session.started"
    assert started.session_id == "sess-2"
    assert started.payload["forked_from_session_id"] == "sess-1"


@pytest.mark.anyio
async def test_acp_agent_session_runtime_events_is_single_consumer() -> None:
    connection = FakeAcpConnection()
    adapter_runtime = AcpAdapterRuntime(
        adapter_key="claude_acp",
        working_directory=Path.cwd(),
        connection=connection,
    )
    runtime = AcpAgentSessionRuntime(
        adapter_runtime=adapter_runtime,
        working_directory=Path.cwd(),
    )

    async with runtime:
        first = runtime.events()
        assert first is not None
        with pytest.raises(RuntimeError, match="single-consumer"):
            runtime.events()


@pytest.mark.anyio
async def test_acp_agent_session_runtime_emits_terminal_completed_fact() -> None:
    connection = FakeAcpConnection()
    adapter_runtime = AcpAdapterRuntime(
        adapter_key="claude_acp",
        working_directory=Path.cwd(),
        connection=connection,
        poll_interval_seconds=0.01,
    )
    runtime = AcpAgentSessionRuntime(
        adapter_runtime=adapter_runtime,
        working_directory=Path.cwd(),
    )

    async with runtime:
        stream = runtime.events()
        await runtime.send(
            AgentSessionCommand(
                command_type=AgentSessionCommandType.START_SESSION,
                instruction="Inspect the repository",
            )
        )
        started = await asyncio.wait_for(anext(stream), timeout=1.0)
        completed = await asyncio.wait_for(anext(stream), timeout=1.0)

    assert started.fact_type == "session.started"
    assert completed.fact_type == "session.completed"


@pytest.mark.anyio
async def test_acp_agent_session_runtime_can_resume_follow_up_for_existing_session() -> None:
    connection = FakeAcpConnection()
    adapter_runtime = AcpAdapterRuntime(
        adapter_key="codex_acp",
        working_directory=Path.cwd(),
        connection=connection,
        poll_interval_seconds=0.01,
    )
    runtime = AcpAgentSessionRuntime(
        adapter_runtime=adapter_runtime,
        working_directory=Path.cwd(),
    )

    async with runtime:
        stream = runtime.events()
        await runtime.send(
            AgentSessionCommand(
                command_type=AgentSessionCommandType.SEND_MESSAGE,
                instruction="Continue.",
                session_id="sess-1",
            )
        )
        completed = await asyncio.wait_for(anext(stream), timeout=1.0)

    assert any(
        method == "session/load"
        and payload["sessionId"] == "sess-1"
        and payload.get("mcpServers") == []
        for method, payload in connection.requests
    )
    assert any(
        method == "session/prompt"
        and payload["sessionId"] == "sess-1"
        and payload["prompt"][0]["text"] == "Continue."
        for method, payload in connection.requests
    )
    assert completed.fact_type == "session.completed"


@pytest.mark.anyio
async def test_acp_agent_session_runtime_reports_running_follow_up_error() -> None:
    connection = FakeAcpConnection()
    adapter_runtime = AcpAdapterRuntime(
        adapter_key="codex_acp",
        working_directory=Path.cwd(),
        connection=connection,
        poll_interval_seconds=0.01,
    )
    runtime = AcpAgentSessionRuntime(
        adapter_runtime=adapter_runtime,
        working_directory=Path.cwd(),
    )

    async with runtime:
        await runtime.send(
            AgentSessionCommand(
                command_type=AgentSessionCommandType.START_SESSION,
                instruction="Inspect the repository",
            )
        )
        with pytest.raises(
            RuntimeError,
            match="Cannot send a follow-up while a Codex ACP turn is still running.",
        ):
            await runtime.send(
                AgentSessionCommand(
                    command_type=AgentSessionCommandType.SEND_MESSAGE,
                    instruction="Continue.",
                    session_id="sess-1",
                )
            )


@pytest.mark.anyio
async def test_acp_agent_session_runtime_surfaces_provider_capacity_error_details() -> None:
    connection = FakeAcpConnection()

    async def failing_request(method: str, params: dict | None = None) -> dict:
        payload = params or {}
        connection.requests.append((method, payload))
        if method == "session/new":
            return {"sessionId": connection.next_session_id}
        if method == "session/prompt":
            raise AcpJsonRpcError(
                -32603,
                "Internal error",
                {
                    "message": "Selected model is at capacity. Please try a different model.",
                    "codex_error_info": "server_overloaded",
                },
            )
        return {"ok": True}

    connection.request = failing_request  # type: ignore[method-assign]
    adapter_runtime = AcpAdapterRuntime(
        adapter_key="codex_acp",
        working_directory=Path.cwd(),
        connection=connection,
        poll_interval_seconds=0.01,
    )
    runtime = AcpAgentSessionRuntime(
        adapter_runtime=adapter_runtime,
        working_directory=Path.cwd(),
    )

    async with runtime:
        stream = runtime.events()
        await runtime.send(
            AgentSessionCommand(
                command_type=AgentSessionCommandType.START_SESSION,
                instruction="Inspect the repository",
            )
        )
        started = await asyncio.wait_for(anext(stream), timeout=1.0)
        failed = await asyncio.wait_for(anext(stream), timeout=1.0)

    assert started.fact_type == "session.started"
    assert failed.fact_type == "session.failed"
    assert (
        failed.payload["message"]
        == "Selected model is at capacity. Please try a different model."
    )
    assert failed.payload["error_code"] == "codex_acp_provider_overloaded"
    assert failed.payload["retryable"] is True
    assert failed.payload["raw"] == {
        "rpc_error_code": -32603,
        "rpc_error_data": {
            "message": "Selected model is at capacity. Please try a different model.",
            "codex_error_info": "server_overloaded",
        },
        "failure_kind": "provider_capacity",
        "recovery_mode": "new_session",
        "codex_error_info": "server_overloaded",
    }


@pytest.mark.anyio
async def test_acp_agent_session_runtime_configures_new_session_before_prompt() -> None:
    connection = FakeAcpConnection()
    adapter_runtime = AcpAdapterRuntime(
        adapter_key="claude_acp",
        working_directory=Path.cwd(),
        connection=connection,
        poll_interval_seconds=0.01,
    )
    configured: list[str] = []

    async def configure_new_session(connection_obj, session_id: str) -> None:
        configured.append(session_id)
        await connection_obj.request(
            "session/set_mode",
            {"sessionId": session_id, "modeId": "bypassPermissions"},
        )

    runtime = AcpAgentSessionRuntime(
        adapter_runtime=adapter_runtime,
        working_directory=Path.cwd(),
        configure_new_session=configure_new_session,
    )

    async with runtime:
        stream = runtime.events()
        await runtime.send(
            AgentSessionCommand(
                command_type=AgentSessionCommandType.START_SESSION,
                instruction="Inspect the repository",
            )
        )
        _started = await asyncio.wait_for(anext(stream), timeout=1.0)
        _completed = await asyncio.wait_for(anext(stream), timeout=1.0)

    assert configured == ["sess-1"]
    methods = [method for method, _payload in connection.requests]
    assert methods[:3] == ["session/new", "session/set_mode", "session/prompt"]


@pytest.mark.anyio
async def test_acp_agent_session_runtime_surfaces_permission_requests_via_hook() -> None:
    connection = FakeAcpConnection()
    adapter_runtime = AcpAdapterRuntime(
        adapter_key="codex_acp",
        working_directory=Path.cwd(),
        connection=connection,
        poll_interval_seconds=0.01,
    )

    async def handle_server_request(session, payload: dict) -> None:
        session.pending_input_message = "Codex ACP turn is waiting for approval."
        session.pending_input_raw = {
            "kind": "permission_escalation",
            "raw_payload": payload,
        }
        if session.connection is not None:
            await session.connection.respond(
                7,
                result={"outcome": {"outcome": "selected", "optionId": "abort"}},
            )

    runtime = AcpAgentSessionRuntime(
        adapter_runtime=adapter_runtime,
        working_directory=Path.cwd(),
        handle_server_request=handle_server_request,
    )

    async with runtime:
        stream = runtime.events()
        await runtime.send(
            AgentSessionCommand(
                command_type=AgentSessionCommandType.START_SESSION,
                instruction="Inspect the repository",
                metadata={"operation_id": "op-1"},
            )
        )
        _started = await asyncio.wait_for(anext(stream), timeout=1.0)
        next_fact_task = asyncio.create_task(anext(stream))
        await asyncio.sleep(0.02)
        connection.drained_notifications.append(
            {
                "jsonrpc": "2.0",
                "id": 7,
                "method": "session/request_permission",
                "params": {
                    "sessionId": "sess-1",
                    "toolCall": {
                        "title": "Edit file",
                        "kind": "edit",
                        "rawInput": {"command": ["git", "status"]},
                    },
                    "options": [
                        {"optionId": "approved", "kind": "allow_once"},
                        {"optionId": "abort", "kind": "reject_once"},
                    ],
                },
            }
        )
        fact = await asyncio.wait_for(next_fact_task, timeout=1.0)

    assert fact.fact_type == "session.waiting_input_observed"
    assert fact.session_id == "sess-1"
    assert fact.payload["message"] == "Codex ACP turn is waiting for approval."
    assert connection.responses == [
        (7, {"outcome": {"outcome": "selected", "optionId": "abort"}}, None)
    ]


@pytest.mark.anyio
async def test_acp_agent_session_runtime_permission_request_requires_request_id() -> None:
    connection = FakeAcpConnection()
    adapter_runtime = AcpAdapterRuntime(
        adapter_key="codex_acp",
        working_directory=Path.cwd(),
        connection=connection,
        poll_interval_seconds=0.01,
    )
    seen_payloads: list[dict] = []

    async def handle_server_request(session, payload: dict) -> None:
        seen_payloads.append(payload)
        session.pending_input_message = "Codex ACP turn is waiting for approval."
        session.pending_input_raw = {"kind": "permission_escalation"}
        if session.connection is not None:
            await session.connection.respond(
                int(payload["id"]),
                result={"outcome": {"outcome": "selected", "optionId": "abort"}},
            )

    runtime = AcpAgentSessionRuntime(
        adapter_runtime=adapter_runtime,
        working_directory=Path.cwd(),
        handle_server_request=handle_server_request,
    )

    async with runtime:
        stream = runtime.events()
        await runtime.send(
            AgentSessionCommand(
                command_type=AgentSessionCommandType.START_SESSION,
                instruction="Inspect the repository",
                metadata={"operation_id": "op-1"},
            )
        )
        _started = await asyncio.wait_for(anext(stream), timeout=1.0)
        next_fact_task = asyncio.create_task(anext(stream))
        await asyncio.sleep(0.02)
        connection.drained_notifications.append(
            {
                "jsonrpc": "2.0",
                "id": 11,
                "method": "session/request_permission",
                "params": {
                    "sessionId": "sess-1",
                    "toolCall": {
                        "title": "Edit file",
                        "kind": "edit",
                        "rawInput": {"command": ["git", "status"]},
                    },
                    "options": [
                        {"optionId": "approved", "kind": "allow_once"},
                        {"optionId": "abort", "kind": "reject_once"},
                    ],
                },
            }
        )
        fact = await asyncio.wait_for(next_fact_task, timeout=1.0)

    assert fact.fact_type == "session.waiting_input_observed"
    assert seen_payloads
    assert seen_payloads[0]["id"] == 11
    assert connection.responses == [
        (11, {"outcome": {"outcome": "selected", "optionId": "abort"}}, None)
    ]


@pytest.mark.anyio
async def test_acp_agent_session_runtime_routes_string_id_permission_request() -> None:
    connection = FakeAcpConnection()
    adapter_runtime = AcpAdapterRuntime(
        adapter_key="codex_acp",
        working_directory=Path.cwd(),
        connection=connection,
        poll_interval_seconds=0.01,
    )
    class EscalatingPermissionEvaluator:
        async def evaluate(self, **_: object) -> PermissionEvaluationResult:
            return PermissionEvaluationResult(
                decision=AcpPermissionDecision.ESCALATE,
                rationale="Brain chose to escalate.",
                suggested_options=("Approve once", "Reject"),
                decision_source="brain",
            )

    adapter = CodexAcpAgentAdapter(
        connection_factory=lambda _cwd, _log_path: connection,
        permission_evaluator=EscalatingPermissionEvaluator(),
    )
    runtime = AcpAgentSessionRuntime(
        adapter_runtime=adapter_runtime,
        working_directory=Path.cwd(),
        handle_server_request=adapter._runner._hooks.handle_server_request,  # type: ignore[attr-defined]
    )

    request_id = "5cba607c-697f-402e-8e84-067f2a432fdb"
    async with runtime:
        stream = runtime.events()
        await runtime.send(
            AgentSessionCommand(
                command_type=AgentSessionCommandType.START_SESSION,
                instruction="Inspect the repository",
                metadata={"operation_id": "op-1"},
            )
        )
        _started = await asyncio.wait_for(anext(stream), timeout=1.0)
        next_fact_task = asyncio.create_task(anext(stream))
        await asyncio.sleep(0.02)
        connection.drained_notifications.append(
            {
                "jsonrpc": "2.0",
                "id": request_id,
                "method": "session/request_permission",
                "params": {
                    "sessionId": "sess-1",
                    "toolCall": {
                        "title": "Tool: codex_apps/github_create_blob",
                        "kind": "mcp",
                        "rawInput": {
                            "server": "codex_apps",
                            "tool": "github_create_blob",
                            "arguments": {
                                "repository_full_name": "uthunderbird/vibechord",
                            },
                        },
                    },
                    "options": [
                        {"optionId": "approved", "kind": "allow_once"},
                        {"optionId": "abort", "kind": "reject_once"},
                    ],
                },
            }
        )
        facts = [await asyncio.wait_for(next_fact_task, timeout=1.0)]
        for _ in range(3):
            facts.append(await asyncio.wait_for(anext(stream), timeout=1.0))

    assert [fact.fact_type for fact in facts] == [
        "permission.request.observed",
        "permission.request.escalated",
        "permission.request.followup_required",
        "session.waiting_input_observed",
    ]
    assert connection.responses == [
        (
            request_id,
            {"outcome": {"outcome": "selected", "optionId": "abort"}},
            None,
        )
    ]


@pytest.mark.anyio
async def test_acp_agent_session_runtime_known_permission_request_never_silently_noops() -> None:
    connection = FakeAcpConnection()
    adapter_runtime = AcpAdapterRuntime(
        adapter_key="codex_acp",
        working_directory=Path.cwd(),
        connection=connection,
        poll_interval_seconds=0.01,
    )

    async def handle_server_request(_session, _payload: dict) -> None:
        return None

    runtime = AcpAgentSessionRuntime(
        adapter_runtime=adapter_runtime,
        working_directory=Path.cwd(),
        handle_server_request=handle_server_request,
    )

    async with runtime:
        stream = runtime.events()
        await runtime.send(
            AgentSessionCommand(
                command_type=AgentSessionCommandType.START_SESSION,
                instruction="Inspect the repository",
                metadata={"operation_id": "op-1"},
            )
        )
        _started = await asyncio.wait_for(anext(stream), timeout=1.0)
        next_fact_task = asyncio.create_task(anext(stream))
        await asyncio.sleep(0.02)
        connection.drained_notifications.append(
            {
                "jsonrpc": "2.0",
                "id": "known-permission-noop",
                "method": "session/request_permission",
                "params": {
                    "sessionId": "sess-1",
                    "toolCall": {
                        "title": "Tool: codex_apps/github_create_blob",
                        "kind": "mcp",
                        "rawInput": {"server": "codex_apps", "tool": "github_create_blob"},
                    },
                    "options": [
                        {"optionId": "approved", "kind": "allow_once"},
                        {"optionId": "abort", "kind": "reject_once"},
                    ],
                },
            }
        )
        fact = await asyncio.wait_for(next_fact_task, timeout=1.0)

    assert fact.fact_type == "session.failed"
    assert fact.payload["error_code"] == "agent_server_request_unrecognized"


@pytest.mark.anyio
async def test_acp_agent_session_runtime_forwards_opencode_permission_requests_through_shared_hook(
) -> None:
    connection = FakeAcpConnection()
    adapter_runtime = AcpAdapterRuntime(
        adapter_key="opencode_acp",
        working_directory=Path.cwd(),
        connection=connection,
        poll_interval_seconds=0.01,
    )
    adapter = OpencodeAcpAgentAdapter(
        connection_factory=lambda _cwd, _log_path: connection,
    )
    runtime = AcpAgentSessionRuntime(
        adapter_runtime=adapter_runtime,
        working_directory=Path.cwd(),
        handle_server_request=adapter._runner._hooks.handle_server_request,  # type: ignore[attr-defined]
    )

    async with runtime:
        stream = runtime.events()
        await runtime.send(
            AgentSessionCommand(
                command_type=AgentSessionCommandType.START_SESSION,
                instruction="Inspect the repository",
                metadata={"operation_id": "op-1"},
            )
        )
        _started = await asyncio.wait_for(anext(stream), timeout=1.0)
        next_fact_task = asyncio.create_task(anext(stream))
        await asyncio.sleep(0.02)
        connection.drained_notifications.append(
            {
                "jsonrpc": "2.0",
                "id": 7,
                "method": "session/request_permission",
                "params": {
                    "sessionId": "sess-1",
                    "toolCall": {
                        "title": "Edit file",
                        "kind": "edit",
                        "rawInput": {"command": ["git", "status"]},
                    },
                    "options": [
                        {"optionId": "approved", "kind": "allow_once"},
                        {"optionId": "abort", "kind": "reject_once"},
                    ],
                },
            }
        )
        facts = [await asyncio.wait_for(next_fact_task, timeout=1.0)]
        for _ in range(3):
            facts.append(await asyncio.wait_for(anext(stream), timeout=1.0))

    assert [fact.fact_type for fact in facts] == [
        "permission.request.observed",
        "permission.request.escalated",
        "permission.request.followup_required",
        "session.waiting_input_observed",
    ]
    assert all(fact.session_id == "sess-1" for fact in facts)
    assert facts[-1].payload["message"] == "ACP turn is waiting for approval."
    assert connection.responses == [
        (7, {"outcome": {"outcome": "selected", "optionId": "abort"}}, None)
    ]


@pytest.mark.anyio
async def test_acp_agent_session_runtime_streams_codex_rejection_followup_required() -> None:
    """Catches dropping Codex follow-up-required permission facts from the live stream."""
    connection = FakeAcpConnection()
    adapter_runtime = AcpAdapterRuntime(
        adapter_key="codex_acp",
        working_directory=Path.cwd(),
        connection=connection,
        poll_interval_seconds=0.01,
    )
    adapter = CodexAcpAgentAdapter(
        connection_factory=lambda _cwd, _log_path: connection,
        permission_evaluator=RejectPermissionEvaluator(),
    )
    runtime = AcpAgentSessionRuntime(
        adapter_runtime=adapter_runtime,
        working_directory=Path.cwd(),
        handle_server_request=adapter._runner._hooks.handle_server_request,  # type: ignore[attr-defined]
    )

    async with runtime:
        stream = runtime.events()
        await runtime.send(
            AgentSessionCommand(
                command_type=AgentSessionCommandType.START_SESSION,
                instruction="Inspect the repository",
                metadata={"operation_id": "op-1"},
            )
        )
        _started = await asyncio.wait_for(anext(stream), timeout=1.0)
        next_fact_task = asyncio.create_task(anext(stream))
        await asyncio.sleep(0.02)
        connection.drained_notifications.append(
            {
                "jsonrpc": "2.0",
                "id": 7,
                "method": "session/request_permission",
                "params": {
                    "sessionId": "sess-1",
                    "toolCall": {
                        "title": "Run external e2e",
                        "kind": "execute",
                        "rawInput": {"command": ["uv", "run", "operator"]},
                    },
                    "options": [
                        {"optionId": "approved", "kind": "allow_once"},
                        {"optionId": "abort", "kind": "reject_once"},
                    ],
                },
            }
        )
        facts = [await asyncio.wait_for(next_fact_task, timeout=1.0)]
        for _ in range(3):
            facts.append(await asyncio.wait_for(anext(stream), timeout=1.0))

    assert [fact.fact_type for fact in facts] == [
        "permission.request.observed",
        "permission.request.decided",
        "permission.request.followup_required",
        "session.failed",
    ]
    assert all(fact.session_id == "sess-1" for fact in facts)
    assert facts[1].payload["decision"] == "reject"
    assert facts[1].payload["decision_source"] == "brain"
    assert (
        facts[2].payload["required_followup_reason"]
        == "codex_acp requires explicit replacement instructions after a rejected "
        "or escalated permission request."
    )
    assert facts[3].payload["error_code"] == "agent_permission_rejected"
    assert connection.responses == [
        (7, {"outcome": {"outcome": "selected", "optionId": "abort"}}, None)
    ]


@pytest.mark.anyio
async def test_acp_agent_session_runtime_scopes_permission_events_to_one_prompt_turn() -> None:
    """Catches stale permission events leaking from a prior prompt into a later result."""
    connection = FakeAcpConnection()
    adapter_runtime = AcpAdapterRuntime(
        adapter_key="opencode_acp",
        working_directory=Path.cwd(),
        connection=connection,
        poll_interval_seconds=0.01,
    )
    adapter = OpencodeAcpAgentAdapter(
        connection_factory=lambda _cwd, _log_path: connection,
    )
    runtime = AcpAgentSessionRuntime(
        adapter_runtime=adapter_runtime,
        working_directory=Path.cwd(),
        handle_server_request=adapter._runner._hooks.handle_server_request,  # type: ignore[attr-defined]
    )

    async with runtime:
        stream = runtime.events()
        await runtime.send(
            AgentSessionCommand(
                command_type=AgentSessionCommandType.START_SESSION,
                instruction="Inspect the repository",
                metadata={"operation_id": "op-1"},
            )
        )
        _started = await asyncio.wait_for(anext(stream), timeout=1.0)
        next_fact_task = asyncio.create_task(anext(stream))
        await asyncio.sleep(0.02)
        connection.drained_notifications.append(
            {
                "jsonrpc": "2.0",
                "id": 7,
                "method": "session/request_permission",
                "params": {
                    "sessionId": "sess-1",
                    "toolCall": {
                        "title": "Edit file",
                        "kind": "edit",
                        "rawInput": {"command": ["git", "status"]},
                    },
                    "options": [
                        {"optionId": "approved", "kind": "allow_once"},
                        {"optionId": "abort", "kind": "reject_once"},
                    ],
                },
            }
        )
        _permission_observed = await asyncio.wait_for(next_fact_task, timeout=1.0)
        for _ in range(3):
            await asyncio.wait_for(anext(stream), timeout=1.0)

        await runtime.send(
            AgentSessionCommand(
                command_type=AgentSessionCommandType.SEND_MESSAGE,
                session_id="sess-1",
                instruction="Continue with read-only inspection",
                metadata={"operation_id": "op-1"},
            )
        )
        completed = await asyncio.wait_for(anext(stream), timeout=1.0)

    assert completed.fact_type == "session.completed"
    raw_payload = completed.payload.get("raw")
    assert isinstance(raw_payload, dict)
    assert raw_payload["permission_events"] == []
