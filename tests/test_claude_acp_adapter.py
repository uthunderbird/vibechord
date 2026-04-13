from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest

from agent_operator.acp.client import AcpProtocolError, AcpSubprocessConnection
from agent_operator.adapters.claude_acp import ClaudeAcpAgentAdapter, _classify_claude_acp_error
from agent_operator.domain import AgentProgressState, AgentResultStatus
from agent_operator.dtos import AgentRunRequest

JsonObject = dict[str, Any]


class FakeAcpConnection:
    def __init__(self, session_id: str) -> None:
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
        if method == "session/set_mode":
            return {}
        if method == "session/set_model":
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


@pytest.mark.anyio
async def test_claude_acp_adapter_collects_output() -> None:
    connection = FakeAcpConnection("sess-1")

    adapter = ClaudeAcpAgentAdapter(connection_factory=lambda _cwd, _log_path: connection)
    handle = await adapter.start(
        AgentRunRequest(goal="goal", instruction="say hi", session_name="draft note")
    )
    connection.notifications.append(_update("sess-1", "hello "))

    progress = await adapter.poll(handle)
    assert progress.state is AgentProgressState.RUNNING
    assert progress.partial_output == "hello "
    assert handle.metadata["log_path"].endswith(".jsonl")
    assert "/.operator/acp/claude_acp/" in handle.metadata["log_path"]
    assert handle.session_name == "draft note"

    connection.notifications.append(_update("sess-1", "world"))
    connection.prompt_future.set_result({"stopReason": "end_turn"})
    result = await adapter.collect(handle)

    assert result.status is AgentResultStatus.SUCCESS
    assert result.output_text == "hello world"
    assert connection.closed is False


@pytest.mark.anyio
async def test_claude_acp_adapter_uses_request_working_directory_and_reload_cwd(
    tmp_path: Path,
) -> None:
    first = FakeAcpConnection("sess-1")
    second = FakeAcpConnection("sess-1")
    connections = [first, second]

    def factory(_: Path, __: Path) -> FakeAcpConnection:
        return connections.pop(0)

    adapter = ClaudeAcpAgentAdapter(connection_factory=factory)
    request_dir = tmp_path / "problem-1"
    request_dir.mkdir()
    handle = await adapter.start(
        AgentRunRequest(
            goal="goal",
            instruction="phase 1",
            session_name="draft note",
            working_directory=request_dir,
        )
    )

    assert handle.metadata["working_directory"] == str(request_dir)
    assert ("session/new", {"cwd": str(request_dir.resolve()), "mcpServers": []}) in first.requests
    assert (
        ("session/set_mode", {"sessionId": "sess-1", "modeId": "bypassPermissions"})
        in first.requests
    )

    first.prompt_future.set_result({"stopReason": "end_turn"})
    await adapter.collect(handle)
    await adapter._close_session_connection(adapter._sessions[handle.session_id])

    await adapter.send(handle, "phase 2")

    assert (
        (
            "session/load",
            {
                "sessionId": "sess-1",
                "cwd": str(request_dir.resolve()),
                "mcpServers": [],
            },
        )
        in second.requests
    )
    assert (
        ("session/set_mode", {"sessionId": "sess-1", "modeId": "bypassPermissions"})
        in second.requests
    )


@pytest.mark.anyio
async def test_claude_acp_adapter_reloads_session_for_follow_up() -> None:
    first = FakeAcpConnection("sess-1")
    second = FakeAcpConnection("sess-1")
    connections = [first, second]

    def factory(_: Path, __: Path) -> FakeAcpConnection:
        return connections.pop(0)

    adapter = ClaudeAcpAgentAdapter(connection_factory=factory)
    handle = await adapter.start(AgentRunRequest(goal="goal", instruction="phase 1"))
    first.notifications.append(_update("sess-1", "first"))
    first.prompt_future.set_result({"stopReason": "end_turn"})
    first_result = await adapter.collect(handle)

    assert first_result.output_text == "first"
    await adapter._close_session_connection(adapter._sessions[handle.session_id])

    await adapter.send(handle, "phase 2")
    second.notifications.append(_update("sess-1", "second"))
    second.prompt_future.set_result({"stopReason": "end_turn"})
    second_result = await adapter.collect(handle)

    assert [method for method, _ in second.requests] == [
        "initialize",
        "session/load",
        "session/set_mode",
        "session/prompt",
    ]
    assert second_result.output_text == "second"


@pytest.mark.anyio
async def test_claude_acp_adapter_reuses_live_connection_for_follow_up() -> None:
    connection = FakeAcpConnection("sess-1")

    adapter = ClaudeAcpAgentAdapter(connection_factory=lambda _cwd, _log_path: connection)
    handle = await adapter.start(AgentRunRequest(goal="goal", instruction="phase 1"))
    connection.notifications.append(_update("sess-1", "first"))
    connection.prompt_future.set_result({"stopReason": "end_turn"})
    first_result = await adapter.collect(handle)

    assert first_result.output_text == "first"
    assert connection.closed is False

    connection.prompt_future = asyncio.get_running_loop().create_future()
    await adapter.send(handle, "phase 2")
    connection.notifications.append(_update("sess-1", "second"))
    connection.prompt_future.set_result({"stopReason": "end_turn"})
    second_result = await adapter.collect(handle)

    assert [method for method, _ in connection.requests] == [
        "initialize",
        "session/new",
        "session/set_mode",
        "session/prompt",
        "session/prompt",
    ]
    assert second_result.output_text == "second"


def test_claude_acp_classifies_subprocess_close_as_disconnected() -> None:
    status, code, retryable, raw = _classify_claude_acp_error(
        "ACP subprocess closed before completing all pending requests.",
        "",
    )

    assert status is AgentResultStatus.DISCONNECTED
    assert code == "claude_acp_disconnected"
    assert retryable is True
    assert raw == {"recovery_mode": "same_session"}


@pytest.mark.anyio
async def test_claude_acp_adapter_applies_model_on_new_and_load(tmp_path: Path) -> None:
    first = FakeAcpConnection("sess-1")
    second = FakeAcpConnection("sess-1")
    connections = [first, second]

    def factory(_: Path, __: Path) -> FakeAcpConnection:
        return connections.pop(0)

    adapter = ClaudeAcpAgentAdapter(
        model="claude-haiku-4-5",
        connection_factory=factory,
    )
    request_dir = tmp_path / "problem-625"
    request_dir.mkdir()
    handle = await adapter.start(
        AgentRunRequest(
            goal="goal",
            instruction="phase 1",
            working_directory=request_dir,
        )
    )

    assert (
        (
            "session/set_model",
            {"sessionId": "sess-1", "modelId": "claude-haiku-4-5"},
        )
        in first.requests
    )

    first.prompt_future.set_result({"stopReason": "end_turn"})
    await adapter.collect(handle)
    await adapter._close_session_connection(adapter._sessions[handle.session_id])
    await adapter.send(handle, "phase 2")

    assert (
        (
            "session/set_model",
            {"sessionId": "sess-1", "modelId": "claude-haiku-4-5"},
        )
        in second.requests
    )


@pytest.mark.anyio
async def test_claude_acp_adapter_handles_session_request_permission() -> None:
    connection = FakeAcpConnection("sess-1")

    adapter = ClaudeAcpAgentAdapter(connection_factory=lambda _cwd, _log_path: connection)
    handle = await adapter.start(AgentRunRequest(goal="goal", instruction="phase 1"))

    connection.notifications.append(
        {
            "jsonrpc": "2.0",
            "id": 7,
            "method": "session/request_permission",
            "params": {
                "sessionId": "sess-1",
                "options": [
                    {"kind": "allow_always", "name": "Always Allow", "optionId": "allow_always"},
                    {"kind": "allow_once", "name": "Allow", "optionId": "allow"},
                    {"kind": "reject_once", "name": "Reject", "optionId": "reject"},
                ],
                "toolCall": {
                    "toolCallId": "tool-1",
                    "title": "run bash",
                    "rawInput": {"command": "echo hi"},
                },
            },
        }
    )

    progress = await adapter.poll(handle)

    assert progress.state is AgentProgressState.WAITING_INPUT
    assert progress.message == "Claude ACP turn is waiting for approval."
    assert connection.responses == [
        (
            7,
            {"outcome": {"outcome": "selected", "optionId": "reject"}},
            None,
        )
    ]


@pytest.mark.anyio
async def test_claude_acp_adapter_collects_permission_escalation_as_incomplete() -> None:
    connection = FakeAcpConnection("sess-1")

    adapter = ClaudeAcpAgentAdapter(connection_factory=lambda _cwd, _log_path: connection)
    handle = await adapter.start(AgentRunRequest(goal="goal", instruction="phase 1"))

    connection.notifications.append(
        {
            "jsonrpc": "2.0",
            "id": 7,
            "method": "session/request_permission",
            "params": {
                "sessionId": "sess-1",
                "options": [
                    {"kind": "allow_always", "name": "Always Allow", "optionId": "allow_always"},
                    {"kind": "allow_once", "name": "Allow", "optionId": "allow"},
                    {"kind": "reject_once", "name": "Reject", "optionId": "reject"},
                ],
                "toolCall": {
                    "toolCallId": "tool-1",
                    "title": "run bash",
                    "rawInput": {"command": "git status"},
                },
            },
        }
    )

    progress = await adapter.poll(handle)
    assert progress.state is AgentProgressState.WAITING_INPUT

    connection.prompt_future.set_exception(RuntimeError("ACP subprocess closed"))
    result = await adapter.collect(handle)

    assert result.status is AgentResultStatus.INCOMPLETE
    assert result.error is not None
    assert result.error.code == "agent_requested_escalation"
    assert result.error.message == "Claude ACP turn is waiting for approval."
    assert isinstance(result.error.raw, dict)
    assert result.error.raw.get("kind") == "permission_escalation"


@pytest.mark.anyio
async def test_claude_acp_adapter_auto_approves_safe_lake_build_permission_request() -> None:
    connection = FakeAcpConnection("sess-1")

    adapter = ClaudeAcpAgentAdapter(connection_factory=lambda _cwd, _log_path: connection)
    handle = await adapter.start(AgentRunRequest(goal="goal", instruction="phase 1"))

    connection.notifications.append(
        {
            "jsonrpc": "2.0",
            "id": 8,
            "method": "session/request_permission",
            "params": {
                "sessionId": "sess-1",
                "options": [
                    {"kind": "allow_always", "name": "Always Allow", "optionId": "allow_always"},
                    {"kind": "allow_once", "name": "Allow", "optionId": "allow"},
                    {"kind": "reject_once", "name": "Reject", "optionId": "reject"},
                ],
                "toolCall": {
                    "toolCallId": "tool-2",
                    "title": "Run lake build",
                    "rawInput": {"command": ["lake", "build", "Erdosreshala.Problem625"]},
                },
            },
        }
    )

    progress = await adapter.poll(handle)

    assert progress.state is AgentProgressState.RUNNING
    assert progress.message == "Claude ACP turn is running."
    assert progress.raw["pending_input_message"] is None
    assert progress.raw["pending_input_raw"] is None
    assert connection.responses == [
        (
            8,
            {"outcome": {"outcome": "selected", "optionId": "allow_always"}},
            None,
        )
    ]
    assert connection.closed is False


@pytest.mark.anyio
async def test_claude_acp_adapter_describe_exposes_standard_coding_tools() -> None:
    adapter = ClaudeAcpAgentAdapter(
        connection_factory=lambda _cwd, _log_path: FakeAcpConnection("sess")
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


@pytest.mark.anyio
async def test_acp_subprocess_connection_reports_env_var_hint_for_missing_command(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_create_subprocess_exec(*args, **kwargs):
        raise FileNotFoundError(2, "No such file or directory", "claude-code-acp")

    monkeypatch.setattr(
        "agent_operator.acp.client.asyncio.create_subprocess_exec",
        fake_create_subprocess_exec,
    )

    connection = AcpSubprocessConnection(
        command="claude-code-acp",
        cwd=tmp_path,
        log_path=tmp_path / "acp.log",
        env_var_hint="OPERATOR_CLAUDE_ACP__COMMAND",
    )

    with pytest.raises(AcpProtocolError, match="OPERATOR_CLAUDE_ACP__COMMAND"):
        await connection.start()


@pytest.mark.anyio
async def test_acp_subprocess_connection_writes_raw_log_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class DummyStdin:
        def __init__(self) -> None:
            self.closed = False
            self.writes: list[bytes] = []

        def write(self, data: bytes) -> None:
            self.writes.append(data)

        async def drain(self) -> None:
            return None

        def close(self) -> None:
            self.closed = True

        def is_closing(self) -> bool:
            return self.closed

    class DummyProcess:
        def __init__(self) -> None:
            self.stdin = DummyStdin()
            self.stdout = asyncio.StreamReader()
            self.stderr = asyncio.StreamReader()
            self.pid = 4321
            self.returncode: int | None = None

        async def wait(self) -> int:
            while self.returncode is None:
                await asyncio.sleep(0)
            return self.returncode

        def terminate(self) -> None:
            self.returncode = 0

        def kill(self) -> None:
            self.returncode = -9

    process = DummyProcess()

    async def fake_create_subprocess_exec(*args, **kwargs):
        return process

    monkeypatch.setattr(
        "agent_operator.acp.client.asyncio.create_subprocess_exec",
        fake_create_subprocess_exec,
    )

    log_path = tmp_path / "acp" / "claude_acp" / "session.jsonl"
    connection = AcpSubprocessConnection(
        command="claude-code-acp",
        cwd=tmp_path,
        log_path=log_path,
    )

    await connection.start()
    await connection.notify("session/ping", {"value": 1})
    process.stdout.feed_data(
        
            b'{"jsonrpc":"2.0","method":"session/update","params":{"sessionId":"sess-1",'
            b'"update":{"sessionUpdate":"agent_message_chunk","content":{"type":"text",'
            b'"text":"hello"}}}}\n'
        
    )
    process.stderr.feed_data(b"warn-line\n")
    process.stdout.feed_eof()
    process.stderr.feed_eof()
    await asyncio.sleep(0)
    await connection.close()

    lines = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()]
    events = [line["event"] for line in lines]

    assert "subprocess.start" in events
    assert "subprocess.started" in events
    assert "jsonrpc.send" in events
    assert "jsonrpc.stdout" in events
    assert "subprocess.stderr" in events
    assert "subprocess.close" in events


@pytest.mark.anyio
async def test_claude_acp_adapter_sets_permission_mode_env_for_subprocess(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class DummyStdin:
        def __init__(self) -> None:
            self.closed = False

        def write(self, data: bytes) -> None:
            return None

        async def drain(self) -> None:
            return None

        def close(self) -> None:
            self.closed = True

        def is_closing(self) -> bool:
            return self.closed

    class DummyProcess:
        def __init__(self) -> None:
            self.stdin = DummyStdin()
            self.stdout = asyncio.StreamReader()
            self.stderr = asyncio.StreamReader()
            self.pid = 4321
            self.returncode: int | None = 0

        async def wait(self) -> int:
            self.stdout.feed_eof()
            self.stderr.feed_eof()
            return 0

        def terminate(self) -> None:
            self.returncode = 0

        def kill(self) -> None:
            self.returncode = -9

    captured: dict[str, object] = {}

    async def fake_create_subprocess_exec(*args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        return DummyProcess()

    monkeypatch.setattr(
        "agent_operator.acp.client.asyncio.create_subprocess_exec",
        fake_create_subprocess_exec,
    )

    adapter = ClaudeAcpAgentAdapter(
        command="npm exec --yes --package=@zed-industries/claude-code-acp -- claude-code-acp",
        permission_mode="bypassPermissions",
    )
    connection = adapter._default_connection_factory(tmp_path, tmp_path / "acp.log")
    await connection.start()
    await connection.close()

    env = captured["kwargs"]["env"]
    assert isinstance(env, dict)
    assert env["CLAUDE_PERMISSION_MODE"] == "bypassPermissions"


@pytest.mark.anyio
async def test_claude_acp_adapter_maps_effort_to_thinking_tokens_env(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class DummyStdin:
        def __init__(self) -> None:
            self.closed = False

        def write(self, data: bytes) -> None:
            return None

        async def drain(self) -> None:
            return None

        def close(self) -> None:
            self.closed = True

        def is_closing(self) -> bool:
            return self.closed

    class DummyProcess:
        def __init__(self) -> None:
            self.stdin = DummyStdin()
            self.stdout = asyncio.StreamReader()
            self.stderr = asyncio.StreamReader()
            self.pid = 4321
            self.returncode: int | None = 0

        async def wait(self) -> int:
            self.stdout.feed_eof()
            self.stderr.feed_eof()
            return 0

        def terminate(self) -> None:
            self.returncode = 0

        def kill(self) -> None:
            self.returncode = -9

    captured: dict[str, object] = {}

    async def fake_create_subprocess_exec(*args, **kwargs):
        captured["kwargs"] = kwargs
        return DummyProcess()

    monkeypatch.setattr(
        "agent_operator.acp.client.asyncio.create_subprocess_exec",
        fake_create_subprocess_exec,
    )

    adapter = ClaudeAcpAgentAdapter(
        command="npm exec --yes --package=@zed-industries/claude-code-acp -- claude-code-acp",
        effort="medium",
    )
    connection = adapter._default_connection_factory(tmp_path, tmp_path / "acp.log")
    await connection.start()
    await connection.close()

    env = captured["kwargs"]["env"]
    assert isinstance(env, dict)
    assert env["MAX_THINKING_TOKENS"] == "4096"


@pytest.mark.anyio
async def test_claude_acp_adapter_maps_none_effort_to_zero_thinking_tokens(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class DummyStdin:
        def __init__(self) -> None:
            self.closed = False

        def write(self, data: bytes) -> None:
            return None

        async def drain(self) -> None:
            return None

        def close(self) -> None:
            self.closed = True

        def is_closing(self) -> bool:
            return self.closed

    class DummyProcess:
        def __init__(self) -> None:
            self.stdin = DummyStdin()
            self.stdout = asyncio.StreamReader()
            self.stderr = asyncio.StreamReader()
            self.pid = 4321
            self.returncode: int | None = 0

        async def wait(self) -> int:
            self.stdout.feed_eof()
            self.stderr.feed_eof()
            return 0

        def terminate(self) -> None:
            self.returncode = 0

        def kill(self) -> None:
            self.returncode = -9

    captured: dict[str, object] = {}

    async def fake_create_subprocess_exec(*args, **kwargs):
        captured["kwargs"] = kwargs
        return DummyProcess()

    monkeypatch.setattr(
        "agent_operator.acp.client.asyncio.create_subprocess_exec",
        fake_create_subprocess_exec,
    )

    adapter = ClaudeAcpAgentAdapter(
        command="npm exec --yes --package=@zed-industries/claude-code-acp -- claude-code-acp",
        effort="none",
    )
    connection = adapter._default_connection_factory(tmp_path, tmp_path / "acp.log")
    await connection.start()
    await connection.close()

    env = captured["kwargs"]["env"]
    assert isinstance(env, dict)
    assert env["MAX_THINKING_TOKENS"] == "0"


def test_classify_claude_acp_error_detects_real_limit_message() -> None:
    status, code, retryable, raw = _classify_claude_acp_error(
        "Internal error: You've hit your limit · resets 1am (Asia/Almaty)",
        (
            'Error handling request ... message: "Internal error: '
            "You've hit your limit · resets 1am (Asia/Almaty)\""
        ),
    )

    assert status is AgentResultStatus.FAILED
    assert code == "claude_acp_rate_limited"
    assert retryable is True
    assert raw == {"rate_limit_detected": True}
