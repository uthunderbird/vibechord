from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest

from agent_operator.acp.session_runner import (
    AcpCollectErrorClassification,
    AcpSessionRunner,
    AcpSessionState,
)
from agent_operator.domain import AgentError, AgentProgressState, AgentResultStatus
from agent_operator.dtos import AgentRunRequest

JsonObject = dict[str, Any]


class FakeAcpConnection:
    def __init__(self, session_id: str = "sess-1") -> None:
        self.session_id = session_id
        self.notifications: list[JsonObject] = []
        self.requests: list[tuple[str, JsonObject]] = []
        self.notifies: list[tuple[str, JsonObject]] = []
        self.responses: list[tuple[int, JsonObject | None, JsonObject | None]] = []
        self.closed = False
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
        if method == "session/prompt":
            return await self.prompt_future
        if method == "session/set_model":
            return {}
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


class FakeHooks:
    adapter_key = "fake_acp"
    running_message = "Fake ACP turn is running."
    completed_message = "Fake ACP turn completed."
    follow_up_running_error = "Cannot send a follow-up while a Fake ACP turn is still running."

    def __init__(
        self,
        *,
        reuse_live_connection: bool = False,
        keep_after_collect: bool = False,
    ) -> None:
        self.reuse_live_connection = reuse_live_connection
        self.keep_after_collect = keep_after_collect

    async def configure_new_session(self, connection, session_id: str) -> None:
        await connection.request("session/set_model", {"sessionId": session_id, "modelId": "fake"})

    async def configure_loaded_session(self, connection, session_id: str) -> None:
        await connection.request("session/set_model", {"sessionId": session_id, "modelId": "fake"})

    async def handle_server_request(self, session: AcpSessionState, payload: JsonObject) -> None:
        request_id = payload.get("id")
        method = payload.get("method")
        if method == "session/request_permission" and isinstance(request_id, int):
            session.pending_input_message = "Fake ACP turn is waiting for approval."
            session.pending_input_raw = payload
            if session.connection is not None:
                await session.connection.respond(
                    request_id,
                    result={"outcome": {"outcome": "selected", "optionId": "reject"}},
                )
            if session.active_prompt is not None and not session.active_prompt.done():
                session.active_prompt.cancel()
            if session.connection is not None:
                await session.connection.close()
                session.connection = None

    def classify_collect_exception(
        self,
        exc: Exception,
        stderr: str,
    ) -> AcpCollectErrorClassification:
        return AcpCollectErrorClassification(
            status=AgentResultStatus.FAILED,
            error=AgentError(code="fake_failed", message=str(exc), retryable=False),
        )

    def should_reuse_live_connection(self, session: AcpSessionState) -> bool:
        return self.reuse_live_connection

    def should_keep_connection_after_collect(self, handle) -> bool:
        return self.keep_after_collect

    def unknown_session_error(self, session_id: str) -> str:
        return f"Unknown Fake ACP session: {session_id}"


class PermissionRecordingHooks(FakeHooks):
    async def handle_server_request(self, session: AcpSessionState, payload: JsonObject) -> None:
        request_id = payload.get("id")
        method = payload.get("method")
        if method != "session/request_permission" or not isinstance(request_id, int):
            return
        session.permission_event_payloads.extend(
            [
                {
                    "event_type": "permission.request.observed",
                    "adapter_key": self.adapter_key,
                    "session_id": session.acp_session_id,
                    "request": {"method": method},
                    "signature": {"adapter_key": self.adapter_key},
                },
                {
                    "event_type": "permission.request.decided",
                    "adapter_key": self.adapter_key,
                    "session_id": session.acp_session_id,
                    "request": {"method": method},
                    "signature": {"adapter_key": self.adapter_key},
                    "decision": "approve",
                    "decision_source": "deterministic_rule",
                },
            ]
        )


def _update(session_id: str, text: str) -> JsonObject:
    return {
        "jsonrpc": "2.0",
        "method": "session/update",
        "params": {
            "sessionId": session_id,
            "update": {
                "sessionUpdate": "agent_message_chunk",
                "content": {"type": "text", "text": text},
            },
        },
    }


@pytest.mark.anyio
async def test_session_runner_start_poll_collect_success() -> None:
    connection = FakeAcpConnection()
    runner = AcpSessionRunner(
        adapter_key="fake_acp",
        working_directory=Path.cwd(),
        connection_factory=lambda _cwd, _log: connection,
        hooks=FakeHooks(),
    )
    handle = await runner.start(AgentRunRequest(goal="goal", instruction="hello"))
    connection.notifications.append(_update("sess-1", "hi "))

    progress = await runner.poll(handle)
    assert progress.state is AgentProgressState.RUNNING
    assert progress.partial_output == "hi "

    connection.notifications.append(_update("sess-1", "there"))
    connection.prompt_future.set_result({"stopReason": "end_turn"})
    result = await runner.collect(handle)

    assert result.status is AgentResultStatus.SUCCESS
    assert result.output_text == "hi there"
    assert connection.closed is True


@pytest.mark.anyio
async def test_session_runner_passes_configured_mcp_servers_to_session_new_and_load() -> None:
    first = FakeAcpConnection()
    second = FakeAcpConnection()
    connections = [first, second]

    def factory(_cwd: Path, _log: Path) -> FakeAcpConnection:
        return connections.pop(0)

    runner = AcpSessionRunner(
        adapter_key="fake_acp",
        working_directory=Path.cwd(),
        mcp_servers=[{"name": "filesystem", "command": "npx"}],
        connection_factory=factory,
        hooks=FakeHooks(),
    )
    handle = await runner.start(AgentRunRequest(goal="goal", instruction="hello"))
    first.prompt_future.set_result({"stopReason": "end_turn"})
    await runner.collect(handle)

    await runner.send(handle, "follow up")

    expected_mcp_servers = [{"name": "filesystem", "command": "npx"}]
    assert (
        "session/new",
        {"cwd": str(Path.cwd().resolve()), "mcpServers": expected_mcp_servers},
    ) in first.requests
    assert (
        "session/load",
        {
            "sessionId": "sess-1",
            "cwd": str(Path.cwd().resolve()),
            "mcpServers": expected_mcp_servers,
        },
    ) in second.requests


@pytest.mark.anyio
async def test_session_runner_tracks_usage_updates_and_prompt_usage() -> None:
    connection = FakeAcpConnection()
    runner = AcpSessionRunner(
        adapter_key="fake_acp",
        working_directory=Path.cwd(),
        connection_factory=lambda _cwd, _log: connection,
        hooks=FakeHooks(),
    )
    handle = await runner.start(AgentRunRequest(goal="goal", instruction="hello"))
    connection.notifications.append(
        {
            "jsonrpc": "2.0",
            "method": "session/update",
            "params": {
                "sessionId": "sess-1",
                "update": {
                    "sessionUpdate": "usage_update",
                    "size": 200000,
                    "used": 1234,
                    "cost": {"amount": 0.42, "currency": "USD"},
                },
            },
        }
    )

    progress = await runner.poll(handle)
    assert progress.usage is not None
    assert progress.usage.context_window_size == 200000
    assert progress.usage.context_tokens_used == 1234
    assert progress.usage.cost_amount == 0.42
    assert progress.usage.cost_currency == "USD"

    connection.prompt_future.set_result(
        {
            "stopReason": "end_turn",
            "usage": {
                "inputTokens": 10,
                "outputTokens": 20,
                "totalTokens": 30,
                "thoughtTokens": 5,
            },
        }
    )
    result = await runner.collect(handle)

    assert result.usage is not None
    assert result.usage.input_tokens == 10
    assert result.usage.output_tokens == 20
    assert result.usage.total_tokens == 30
    assert result.usage.context_window_size == 200000
    assert result.usage.context_tokens_used == 1234
    assert result.usage.metadata["thought_tokens"] == 5


@pytest.mark.anyio
async def test_session_runner_populates_structured_session_snapshot() -> None:
    connection = FakeAcpConnection()
    runner = AcpSessionRunner(
        adapter_key="fake_acp",
        working_directory=Path.cwd(),
        connection_factory=lambda _cwd, _log: connection,
        hooks=FakeHooks(),
    )
    handle = await runner.start(AgentRunRequest(goal="goal", instruction="hello"))
    connection.notifications.append(_update("sess-1", "hello"))

    progress = await runner.poll(handle)

    session = runner.require_session(handle)
    assert session.session_snapshot is not None
    assert len(session.session_snapshot.agent_messages) == 1
    assert progress.raw["session_snapshot_available"] is True
    assert progress.raw["last_event_at"] is not None


@pytest.mark.anyio
async def test_session_runner_collect_can_return_disconnected_status() -> None:
    class DisconnectHooks(FakeHooks):
        def classify_collect_exception(
            self,
            exc: Exception,
            stderr: str,
        ) -> AcpCollectErrorClassification:
            return AcpCollectErrorClassification(
                status=AgentResultStatus.DISCONNECTED,
                error=AgentError(
                    code="fake_disconnected",
                    message=str(exc),
                    retryable=True,
                    raw={"recovery_mode": "same_session"},
                ),
            )

    connection = FakeAcpConnection()
    runner = AcpSessionRunner(
        adapter_key="fake_acp",
        working_directory=Path.cwd(),
        connection_factory=lambda _cwd, _log: connection,
        hooks=DisconnectHooks(),
    )
    handle = await runner.start(AgentRunRequest(goal="goal", instruction="hello"))
    connection.prompt_future.set_exception(
        RuntimeError("ACP subprocess closed before completing all pending requests.")
    )

    result = await runner.collect(handle)

    assert result.status is AgentResultStatus.DISCONNECTED
    assert result.error is not None
    assert result.error.code == "fake_disconnected"


@pytest.mark.anyio
async def test_session_runner_collect_includes_permission_events_in_raw_result() -> None:
    connection = FakeAcpConnection()
    runner = AcpSessionRunner(
        adapter_key="fake_acp",
        working_directory=Path.cwd(),
        connection_factory=lambda _cwd, _log: connection,
        hooks=PermissionRecordingHooks(),
    )
    handle = await runner.start(AgentRunRequest(goal="goal", instruction="hello"))
    connection.notifications.append(
        {
            "jsonrpc": "2.0",
            "id": 7,
            "method": "session/request_permission",
            "params": {"sessionId": "sess-1"},
        }
    )
    connection.prompt_future.set_result({"stopReason": "end_turn"})

    result = await runner.collect(handle)

    assert result.raw is not None
    assert [event["event_type"] for event in result.raw["permission_events"]] == [
        "permission.request.observed",
        "permission.request.decided",
    ]


@pytest.mark.anyio
async def test_session_runner_send_reuses_live_connection_when_hook_allows() -> None:
    connection = FakeAcpConnection()
    runner = AcpSessionRunner(
        adapter_key="fake_acp",
        working_directory=Path.cwd(),
        connection_factory=lambda _cwd, _log: connection,
        hooks=FakeHooks(reuse_live_connection=True, keep_after_collect=True),
    )
    handle = await runner.start(AgentRunRequest(goal="goal", instruction="one"))
    connection.prompt_future.set_result({"stopReason": "end_turn"})
    await runner.collect(handle)

    connection.prompt_future = asyncio.get_running_loop().create_future()
    await runner.send(handle, "two")
    connection.prompt_future.set_result({"stopReason": "end_turn"})
    await runner.collect(handle)

    assert [method for method, _ in connection.requests] == [
        "initialize",
        "session/new",
        "session/set_model",
        "session/prompt",
        "session/prompt",
    ]


@pytest.mark.anyio
async def test_session_runner_poll_reports_waiting_input_from_permission_request() -> None:
    connection = FakeAcpConnection()
    runner = AcpSessionRunner(
        adapter_key="fake_acp",
        working_directory=Path.cwd(),
        connection_factory=lambda _cwd, _log: connection,
        hooks=FakeHooks(),
    )
    handle = await runner.start(AgentRunRequest(goal="goal", instruction="hello"))
    connection.notifications.append(
        {
            "jsonrpc": "2.0",
            "id": 7,
            "method": "session/request_permission",
            "params": {"sessionId": "sess-1"},
        }
    )

    progress = await runner.poll(handle)

    assert progress.state is AgentProgressState.WAITING_INPUT
    assert progress.message == "Fake ACP turn is waiting for approval."
    assert connection.responses == [
        (7, {"outcome": {"outcome": "selected", "optionId": "reject"}}, None)
    ]


@pytest.mark.anyio
async def test_session_runner_collect_returns_incomplete_for_pending_permission_escalation(
) -> None:
    connection = FakeAcpConnection()
    runner = AcpSessionRunner(
        adapter_key="fake_acp",
        working_directory=Path.cwd(),
        connection_factory=lambda _cwd, _log: connection,
        hooks=FakeHooks(),
    )
    handle = await runner.start(AgentRunRequest(goal="goal", instruction="hello"))
    connection.notifications.append(
        {
            "jsonrpc": "2.0",
            "id": 7,
            "method": "session/request_permission",
            "params": {"sessionId": "sess-1"},
        }
    )

    progress = await runner.poll(handle)
    assert progress.state is AgentProgressState.WAITING_INPUT

    result = await runner.collect(handle)

    assert result.status is AgentResultStatus.INCOMPLETE
    assert result.error is not None
    assert result.error.code == "agent_waiting_input"
    assert result.error.message == "Fake ACP turn is waiting for approval."


@pytest.mark.anyio
async def test_session_runner_cancel_notifies_and_closes() -> None:
    connection = FakeAcpConnection()
    runner = AcpSessionRunner(
        adapter_key="fake_acp",
        working_directory=Path.cwd(),
        connection_factory=lambda _cwd, _log: connection,
        hooks=FakeHooks(),
    )
    handle = await runner.start(AgentRunRequest(goal="goal", instruction="hello"))

    await runner.cancel(handle)

    assert connection.notifies == [("session/cancel", {"sessionId": "sess-1"})]
    assert connection.closed is True


@pytest.mark.anyio
async def test_session_runner_poll_can_reattach_after_in_memory_session_loss() -> None:
    first = FakeAcpConnection("sess-1")
    second = FakeAcpConnection("sess-1")
    connections = [first, second]

    def factory(_cwd: Path, _log: Path) -> FakeAcpConnection:
        return connections.pop(0)

    runner = AcpSessionRunner(
        adapter_key="fake_acp",
        working_directory=Path.cwd(),
        connection_factory=factory,
        hooks=FakeHooks(),
    )
    handle = await runner.start(AgentRunRequest(goal="goal", instruction="hello"))

    # Simulate operator restart: runner loses in-memory session state while
    # handle remains persisted.
    runner.sessions.clear()

    second.notifications.append(_update("sess-1", "still running"))
    progress = await runner.poll(handle)

    assert progress.state is AgentProgressState.RUNNING
    assert progress.partial_output == "still running"
    assert (
        (
            "session/load",
            {
                "sessionId": "sess-1",
                "cwd": str(Path.cwd().resolve()),
                "mcpServers": [],
            },
        )
        in second.requests
    )
