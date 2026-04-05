from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest

from agent_operator.adapters.codex_acp import (
    CodexAcpAgentAdapter,
    _build_codex_acp_command,
    _classify_codex_acp_error,
)
from agent_operator.domain import AgentProgressState, AgentResultStatus
from agent_operator.dtos import AgentRunRequest

JsonObject = dict[str, Any]


class FakeAcpConnection:
    def __init__(self, session_id: str, prompt_response: JsonObject) -> None:
        self.session_id = session_id
        self.prompt_response = prompt_response
        self.started = False
        self.closed = False
        self.notifications: list[JsonObject] = []
        self.requests: list[tuple[str, JsonObject]] = []
        self.notifies: list[tuple[str, JsonObject]] = []
        self.responses: list[tuple[int, JsonObject | None, JsonObject | None]] = []
        self.prompt_future: asyncio.Future[JsonObject] = asyncio.get_running_loop().create_future()

    async def start(self) -> None:
        self.started = True

    async def request(self, method: str, params: JsonObject | None = None) -> JsonObject:
        payload = params or {}
        self.requests.append((method, payload))
        if method == "initialize":
            return {
                "protocolVersion": 1,
                "agentCapabilities": {},
            }
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


def _update(session_id: str, text: str) -> JsonObject:
    return {
        "jsonrpc": "2.0",
        "method": "session/update",
        "params": {
            "sessionId": session_id,
            "update": {
                "sessionUpdate": "agent_message_chunk",
                "content": {
                    "type": "text",
                    "text": text,
                },
            },
        },
    }


def _approval_request() -> JsonObject:
    return {
        "jsonrpc": "2.0",
        "id": 7,
        "method": "item/commandExecution/requestApproval",
        "params": {
            "command": "python3",
            "reason": "outside writable root",
        },
    }


def _session_permission_request(*, command: list[str]) -> JsonObject:
    return {
        "jsonrpc": "2.0",
        "id": 11,
        "method": "session/request_permission",
        "params": {
            "sessionId": "sess-1",
            "toolCall": {
                "toolCallId": "call-1",
                "kind": "execute",
                "status": "pending",
                "title": "Run git add",
                "rawInput": {
                    "command": ["/bin/zsh", "-lc", "ignored"],
                    "proposed_execpolicy_amendment": command,
                },
            },
            "options": [
                {"optionId": "approved", "kind": "allow_once"},
                {"optionId": "approved-execpolicy-amendment", "kind": "allow_always"},
                {"optionId": "abort", "kind": "reject_once"},
            ],
        },
    }


def test_classify_codex_acp_error_detects_recoverable_disconnect() -> None:
    status, code, retryable, raw = _classify_codex_acp_error(
        "Separator is found, but chunk is longer than limit",
        "",
    )

    assert status is AgentResultStatus.DISCONNECTED
    assert code == "codex_acp_disconnected"
    assert retryable is True
    assert raw == {"recovery_mode": "same_session"}


@pytest.mark.anyio
async def test_codex_acp_adapter_collects_output_and_closes_connection() -> None:
    connection = FakeAcpConnection("sess-1", {"stopReason": "end_turn"})

    def factory(_: Path, __: Path):
        return connection

    adapter = CodexAcpAgentAdapter(connection_factory=factory)
    handle = await adapter.start(
        AgentRunRequest(
            goal="goal",
            instruction="do it",
        )
    )
    connection.notifications.append(_update("sess-1", "hello "))

    progress = await adapter.poll(handle)
    assert progress.state is AgentProgressState.RUNNING
    assert progress.partial_output == "hello "

    connection.notifications.append(_update("sess-1", "world"))
    connection.prompt_future.set_result({"stopReason": "end_turn"})

    result = await adapter.collect(handle)

    assert result.status is AgentResultStatus.SUCCESS
    assert result.output_text == "hello world"
    assert connection.closed is True


@pytest.mark.anyio
async def test_codex_acp_adapter_reloads_session_for_follow_up() -> None:
    first = FakeAcpConnection("sess-1", {"stopReason": "end_turn"})
    second = FakeAcpConnection("sess-1", {"stopReason": "end_turn"})
    connections = [first, second]

    def factory(_: Path, __: Path):
        return connections.pop(0)

    adapter = CodexAcpAgentAdapter(connection_factory=factory)
    handle = await adapter.start(AgentRunRequest(goal="goal", instruction="phase 1"))
    first.notifications.append(_update("sess-1", "first"))
    first.prompt_future.set_result({"stopReason": "end_turn"})
    first_result = await adapter.collect(handle)

    assert first_result.output_text == "first"

    await adapter.send(handle, "phase 2")
    second.notifications.append(_update("sess-1", "second"))
    second.prompt_future.set_result({"stopReason": "end_turn"})
    second_result = await adapter.collect(handle)

    assert [method for method, _ in second.requests] == [
        "initialize",
        "session/load",
        "session/prompt",
    ]
    assert second_result.output_text == "second"


@pytest.mark.anyio
async def test_codex_acp_adapter_sets_model_and_reasoning_effort() -> None:
    connection = FakeAcpConnection("sess-1", {"stopReason": "end_turn"})

    def factory(_: Path, __: Path):
        return connection

    adapter = CodexAcpAgentAdapter(
        model="gpt-5.4",
        reasoning_effort="low",
        connection_factory=factory,
    )
    handle = await adapter.start(
        AgentRunRequest(
            goal="goal",
            instruction="do it",
        )
    )
    connection.notifications.append(_update("sess-1", "done"))
    connection.prompt_future.set_result({"stopReason": "end_turn"})
    await adapter.collect(handle)

    assert [method for method, _ in connection.requests] == [
        "initialize",
        "session/new",
        "session/set_config_option",
        "session/set_config_option",
        "session/prompt",
    ]
    assert connection.requests[2][1]["configId"] == "model"
    assert connection.requests[2][1]["value"] == "gpt-5.4"
    assert connection.requests[3][1]["configId"] == "reasoning_effort"
    assert connection.requests[3][1]["value"] == "low"


@pytest.mark.anyio
async def test_codex_acp_adapter_reports_waiting_input_for_approval_requests() -> None:
    connection = FakeAcpConnection("sess-1", {"stopReason": "end_turn"})

    def factory(_: Path, __: Path):
        return connection

    adapter = CodexAcpAgentAdapter(connection_factory=factory)
    handle = await adapter.start(
        AgentRunRequest(
            goal="goal",
            instruction="do it",
        )
    )
    connection.notifications.append(_approval_request())

    progress = await adapter.poll(handle)

    assert progress.state is AgentProgressState.WAITING_INPUT
    assert progress.message == "Codex ACP turn is waiting for approval."
    assert connection.responses == [(7, {"decision": "decline"}, None)]
    assert connection.closed is True


@pytest.mark.anyio
async def test_codex_acp_adapter_auto_approves_safe_git_add_permission_request(
    tmp_path: Path,
) -> None:
    connection = FakeAcpConnection("sess-1", {"stopReason": "end_turn"})
    repo = tmp_path / "repo"
    repo.mkdir()

    def factory(_: Path, __: Path):
        return connection

    adapter = CodexAcpAgentAdapter(connection_factory=factory)
    handle = await adapter.start(
        AgentRunRequest(
            goal="goal",
            instruction="do it",
            working_directory=repo,
        )
    )
    connection.notifications.append(
        _session_permission_request(
            command=["git", "-C", str(repo), "add", "src/femtobot/plugins/builtin.py"]
        )
    )

    progress = await adapter.poll(handle)

    assert progress.state is AgentProgressState.RUNNING
    assert connection.responses == [
        (
            11,
            {"outcome": {"outcome": "selected", "optionId": "approved"}},
            None,
        )
    ]
    assert connection.closed is False


@pytest.mark.anyio
async def test_codex_acp_adapter_rejects_out_of_repo_git_add_permission_request(
    tmp_path: Path,
) -> None:
    connection = FakeAcpConnection("sess-1", {"stopReason": "end_turn"})
    repo = tmp_path / "repo"
    repo.mkdir()

    def factory(_: Path, __: Path):
        return connection

    adapter = CodexAcpAgentAdapter(connection_factory=factory)
    handle = await adapter.start(
        AgentRunRequest(
            goal="goal",
            instruction="do it",
            working_directory=repo,
        )
    )
    connection.notifications.append(
        _session_permission_request(
            command=["git", "-C", str(repo), "add", "../outside.txt"]
        )
    )

    progress = await adapter.poll(handle)

    assert progress.state is AgentProgressState.WAITING_INPUT
    assert progress.message == "Codex ACP turn is waiting for approval."
    assert connection.responses == [
        (
            11,
            {"outcome": {"outcome": "selected", "optionId": "abort"}},
            None,
        )
    ]
    assert connection.closed is True


@pytest.mark.anyio
async def test_codex_acp_adapter_describe_exposes_standard_coding_tools() -> None:
    adapter = CodexAcpAgentAdapter(
        connection_factory=lambda _cwd, _log_path: FakeAcpConnection("sess", {})
    )

    descriptor = await adapter.describe()
    capability_names = {item.name for item in descriptor.capabilities}

    assert "acp" in capability_names
    assert "follow_up" in capability_names
    assert "read_files" in capability_names
    assert "write_files" in capability_names
    assert "edit_files" in capability_names
    assert "grep_search" in capability_names
    assert "glob_search" in capability_names
    assert "run_shell_commands" in capability_names


def test_build_codex_acp_command_includes_runtime_overrides() -> None:
    command = _build_codex_acp_command(
        "npx @zed-industries/codex-acp",
        approval_policy="never",
        sandbox_mode="danger-full-access",
    )

    assert command == (
        "npx @zed-industries/codex-acp -c 'approval_policy=\"never\"' "
        "-c 'sandbox_mode=\"danger-full-access\"'"
    )
