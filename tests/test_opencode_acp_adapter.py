from __future__ import annotations

import asyncio
from typing import Any

import pytest

from agent_operator.adapters.opencode_acp import (
    OpencodeAcpAgentAdapter,
    _build_opencode_acp_command,
    _classify_opencode_acp_error,
)
from agent_operator.domain import AgentProgressState, AgentResultStatus
from agent_operator.dtos import AgentRunRequest

JsonObject = dict[str, Any]


class FakeAcpConnection:
    def __init__(self, session_id: str) -> None:
        self.session_id = session_id
        self.closed = False
        self.notifications: list[JsonObject] = []
        self.requests: list[tuple[str, JsonObject]] = []
        self.notifies: list[tuple[str, JsonObject]] = []
        self.responses: list[tuple[int, JsonObject | None, JsonObject | None]] = []
        self.prompt_future: asyncio.Future[JsonObject] = asyncio.get_running_loop().create_future()

    async def start(self) -> None:
        return None

    async def request(self, method: str, params: JsonObject | None = None) -> JsonObject:
        payload = params or {}
        self.requests.append((method, payload))
        if method == "initialize":
            return {"protocolVersion": 1, "agentCapabilities": {}}
        if method == "session/new":
            return {"sessionId": self.session_id}
        if method == "session/load":
            return {}
        if method == "session/set_config_option":
            return {}
        if method == "session/prompt":
            return await self.prompt_future
        raise AssertionError(f"Unexpected method: {method}")

    async def notify(self, method: str, params: JsonObject | None = None) -> None:
        self.notifies.append((method, params or {}))

    async def respond(
        self,
        request_id: int,
        *,
        result: JsonObject | None = None,
        error: JsonObject | None = None,
    ) -> None:
        self.responses.append((request_id, result, error))

    def drain_notifications(self) -> list[JsonObject]:
        items = list(self.notifications)
        self.notifications.clear()
        return items

    def stderr_text(self, limit: int = 4000) -> str:
        return ""

    async def close(self) -> None:
        self.closed = True


def _session_permission_request() -> JsonObject:
    return {
        "jsonrpc": "2.0",
        "id": 9,
        "method": "session/request_permission",
        "params": {
            "sessionId": "sess-1",
            "toolCall": {
                "toolCallId": "call-1",
                "kind": "execute",
                "status": "pending",
                "title": "Run shell command",
                "rawInput": {"command": ["git", "status"]},
            },
            "options": [
                {"optionId": "approved", "kind": "allow_once"},
                {"optionId": "abort", "kind": "reject_once"},
            ],
        },
    }


def _user_input_request() -> JsonObject:
    return {
        "jsonrpc": "2.0",
        "id": 11,
        "method": "item/tool/requestUserInput",
        "params": {"sessionId": "sess-1"},
    }


def test_build_opencode_acp_command_normalizes_whitespace() -> None:
    assert _build_opencode_acp_command("  opencode   acp  ") == "opencode acp"


def test_classify_opencode_acp_error_detects_recoverable_disconnect() -> None:
    status, code, retryable, raw = _classify_opencode_acp_error(
        "ACP subprocess closed before completing all pending requests.",
        "",
    )
    assert status == AgentResultStatus.DISCONNECTED
    assert code == "opencode_acp_disconnected"
    assert retryable is True
    assert raw == {"recovery_mode": "same_session"}


def test_classify_opencode_acp_error_detects_protocol_mismatch() -> None:
    status, code, retryable, raw = _classify_opencode_acp_error(
        "invalid request: missing field value",
        "",
    )
    assert status == AgentResultStatus.FAILED
    assert code == "opencode_acp_protocol_mismatch"
    assert retryable is True
    assert raw == {"recovery_mode": "new_session"}


def test_classify_opencode_acp_error_falls_back_to_failed_unknown() -> None:
    status, code, retryable, raw = _classify_opencode_acp_error(
        "tool execution failed",
        "",
    )
    assert status == AgentResultStatus.FAILED
    assert code == "opencode_acp_failed"
    assert retryable is False
    assert raw is None


@pytest.mark.anyio
async def test_opencode_acp_adapter_reports_waiting_input_for_permission_requests() -> None:
    connection = FakeAcpConnection("sess-1")
    adapter = OpencodeAcpAgentAdapter(connection_factory=lambda _cwd, _log_path: connection)
    handle = await adapter.start(AgentRunRequest(goal="goal", instruction="do it"))
    connection.notifications.append(_session_permission_request())

    progress = await adapter.poll(handle)

    assert progress.state is AgentProgressState.WAITING_INPUT
    assert progress.message == "ACP turn is waiting for approval."
    assert connection.responses == [
        (
            9,
            {"outcome": {"outcome": "selected", "optionId": "abort"}},
            None,
        )
    ]
    assert connection.closed is True


@pytest.mark.anyio
async def test_opencode_acp_adapter_collects_permission_escalation_as_incomplete() -> None:
    connection = FakeAcpConnection("sess-1")
    adapter = OpencodeAcpAgentAdapter(connection_factory=lambda _cwd, _log_path: connection)
    handle = await adapter.start(AgentRunRequest(goal="goal", instruction="phase 1"))
    connection.notifications.append(_session_permission_request())

    progress = await adapter.poll(handle)
    assert progress.state is AgentProgressState.WAITING_INPUT

    connection.prompt_future.set_exception(RuntimeError("ACP subprocess closed"))
    result = await adapter.collect(handle)

    assert result.status is AgentResultStatus.INCOMPLETE
    assert result.error is not None
    assert result.error.code == "agent_requested_escalation"
    assert result.error.message == "ACP turn is waiting for approval."
    assert isinstance(result.error.raw, dict)
    assert result.error.raw.get("kind") == "permission_escalation"


@pytest.mark.anyio
async def test_opencode_acp_adapter_reports_waiting_input_for_user_input_requests() -> None:
    connection = FakeAcpConnection("sess-1")
    adapter = OpencodeAcpAgentAdapter(connection_factory=lambda _cwd, _log_path: connection)
    handle = await adapter.start(AgentRunRequest(goal="goal", instruction="do it"))
    connection.notifications.append(_user_input_request())

    progress = await adapter.poll(handle)

    assert progress.state is AgentProgressState.WAITING_INPUT
    assert progress.message == "ACP turn requested user input."
    assert progress.raw["pending_input_raw"]["kind"] == "user_input_request"
    assert connection.responses == [(11, {"answers": {}}, None)]
    assert connection.closed is True
