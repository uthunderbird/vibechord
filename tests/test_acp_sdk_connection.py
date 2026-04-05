from __future__ import annotations

import asyncio
import json
from contextlib import AbstractAsyncContextManager
from pathlib import Path
from typing import Any

import pytest
from acp.schema import PermissionOption, ToolCallUpdate

from agent_operator.acp.sdk_client import AcpSdkConnection


class _FakeModel:
    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload

    def model_dump(
        self, *, by_alias: bool = True, exclude_none: bool = True
    ) -> dict[str, Any]:
        return dict(self._payload)


class _FakeSdkClientConnection:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.cancelled_session_id: str | None = None
        self.closed = False

    async def initialize(
        self,
        protocol_version: int,
        client_capabilities=None,
        client_info=None,
        **kwargs: Any,
    ) -> _FakeModel:
        self.calls.append(
            (
                "initialize",
                {
                    "protocol_version": protocol_version,
                    "client_capabilities": client_capabilities,
                    "client_info": client_info,
                },
            )
        )
        return _FakeModel({"protocolVersion": protocol_version})

    async def new_session(self, cwd: str, mcp_servers=None, **kwargs: Any) -> _FakeModel:
        self.calls.append(("new_session", {"cwd": cwd, "mcp_servers": mcp_servers or []}))
        return _FakeModel({"sessionId": "sess-1"})

    async def load_session(
        self,
        cwd: str,
        session_id: str,
        mcp_servers=None,
        **kwargs: Any,
    ) -> _FakeModel:
        self.calls.append(
            (
                "load_session",
                {
                    "cwd": cwd,
                    "session_id": session_id,
                    "mcp_servers": mcp_servers or [],
                },
            )
        )
        return _FakeModel({})

    async def list_sessions(
        self,
        cursor: str | None = None,
        cwd: str | None = None,
        **kwargs: Any,
    ) -> _FakeModel:
        self.calls.append(("list_sessions", {"cursor": cursor, "cwd": cwd}))
        return _FakeModel({"sessions": [{"sessionId": "sess-1"}]})

    async def set_session_mode(self, mode_id: str, session_id: str, **kwargs: Any) -> _FakeModel:
        self.calls.append(("set_session_mode", {"mode_id": mode_id, "session_id": session_id}))
        return _FakeModel({})

    async def set_session_model(self, model_id: str, session_id: str, **kwargs: Any) -> _FakeModel:
        self.calls.append(("set_session_model", {"model_id": model_id, "session_id": session_id}))
        return _FakeModel({})

    async def set_config_option(
        self,
        config_id: str,
        session_id: str,
        value: str | bool,
        **kwargs: Any,
    ) -> _FakeModel:
        self.calls.append(
            (
                "set_config_option",
                {
                    "config_id": config_id,
                    "session_id": session_id,
                    "value": value,
                },
            )
        )
        return _FakeModel({"configOptions": []})

    async def prompt(
        self,
        prompt: list[Any],
        session_id: str,
        message_id: str | None = None,
        **kwargs: Any,
    ) -> _FakeModel:
        rendered = [block.model_dump(by_alias=True, exclude_none=True) for block in prompt]
        self.calls.append(
            ("prompt", {"prompt": rendered, "session_id": session_id, "message_id": message_id})
        )
        return _FakeModel({"stopReason": "end_turn"})

    async def fork_session(
        self,
        cwd: str,
        session_id: str,
        mcp_servers=None,
        **kwargs: Any,
    ) -> _FakeModel:
        self.calls.append(
            (
                "fork_session",
                {
                    "cwd": cwd,
                    "session_id": session_id,
                    "mcp_servers": mcp_servers or [],
                },
            )
        )
        return _FakeModel({"sessionId": "sess-2"})

    async def resume_session(
        self,
        cwd: str,
        session_id: str,
        mcp_servers=None,
        **kwargs: Any,
    ) -> _FakeModel:
        self.calls.append(
            (
                "resume_session",
                {
                    "cwd": cwd,
                    "session_id": session_id,
                    "mcp_servers": mcp_servers or [],
                },
            )
        )
        return _FakeModel({"configOptions": []})

    async def close_session(self, session_id: str, **kwargs: Any) -> _FakeModel:
        self.calls.append(("close_session", {"session_id": session_id}))
        return _FakeModel({})

    async def authenticate(self, method_id: str, **kwargs: Any) -> _FakeModel:
        self.calls.append(("authenticate", {"method_id": method_id}))
        return _FakeModel({})

    async def cancel(self, session_id: str, **kwargs: Any) -> None:
        self.cancelled_session_id = session_id

    async def close(self) -> None:
        self.closed = True


class _FakeProcess:
    def __init__(self) -> None:
        self.pid = 1234
        self.returncode: int | None = None
        self.stderr = None


class _FakeTransportContext(
    AbstractAsyncContextManager[tuple[asyncio.StreamReader, object, _FakeProcess]]
):
    def __init__(self) -> None:
        self.exited = False
        self.reader = asyncio.StreamReader()
        self.writer = object()
        self.process = _FakeProcess()

    async def __aenter__(self) -> tuple[asyncio.StreamReader, object, _FakeProcess]:
        return self.reader, self.writer, self.process

    async def __aexit__(self, exc_type, exc, tb) -> None:
        self.exited = True


@pytest.mark.anyio
async def test_acp_sdk_connection_passes_stdio_limit_to_transport_factory() -> None:
    seen: dict[str, object] = {}
    transport = _FakeTransportContext()
    sdk_client = _FakeSdkClientConnection()

    def _transport_factory(_cmd, _args, _env, _cwd, limit):
        seen["limit"] = limit
        return transport

    connection = AcpSdkConnection(
        command="dummy-agent",
        stdio_limit_bytes=1_048_576,
        transport_factory=_transport_factory,
        client_factory=lambda _client, _writer, _reader: sdk_client,
    )

    await connection.start()

    assert seen["limit"] == 1_048_576


@pytest.mark.anyio
async def test_acp_sdk_connection_maps_core_request_methods() -> None:
    transport = _FakeTransportContext()
    sdk_client = _FakeSdkClientConnection()
    connection = AcpSdkConnection(
        command="dummy-agent",
        transport_factory=lambda _cmd, _args, _env, _cwd, _limit: transport,
        client_factory=lambda _client, _writer, _reader: sdk_client,
    )

    assert await connection.request("initialize", {"protocolVersion": 1}) == {"protocolVersion": 1}
    assert await connection.request("session/new", {"cwd": "/tmp/work", "mcpServers": []}) == {
        "sessionId": "sess-1"
    }
    assert await connection.request(
        "session/load",
        {"cwd": "/tmp/work", "sessionId": "sess-1", "mcpServers": []},
    ) == {}
    assert await connection.request(
        "session/set_config_option",
        {"configId": "model", "sessionId": "sess-1", "value": "gpt-5.4"},
    ) == {"configOptions": []}
    assert await connection.request(
        "session/prompt",
        {"sessionId": "sess-1", "prompt": [{"type": "text", "text": "hello"}]},
    ) == {"stopReason": "end_turn"}
    assert await connection.request("session/list", {"cwd": "/tmp/work", "cursor": "page-1"}) == {
        "sessions": [{"sessionId": "sess-1"}]
    }
    assert await connection.request(
        "session/fork",
        {"cwd": "/tmp/work", "sessionId": "sess-1", "mcpServers": []},
    ) == {"sessionId": "sess-2"}
    assert await connection.request(
        "session/resume",
        {"cwd": "/tmp/work", "sessionId": "sess-1", "mcpServers": []},
    ) == {"configOptions": []}
    assert await connection.request("session/close", {"sessionId": "sess-1"}) == {}
    assert await connection.request("session/authenticate", {"methodId": "oauth"}) == {}

    await connection.notify("session/cancel", {"sessionId": "sess-1"})
    await connection.close()

    assert sdk_client.cancelled_session_id == "sess-1"
    assert sdk_client.closed is True
    assert transport.exited is True
    assert ("new_session", {"cwd": "/tmp/work", "mcp_servers": []}) in sdk_client.calls
    assert (
        ("load_session", {"cwd": "/tmp/work", "session_id": "sess-1", "mcp_servers": []})
        in sdk_client.calls
    )
    assert ("list_sessions", {"cursor": "page-1", "cwd": "/tmp/work"}) in sdk_client.calls
    assert (
        ("fork_session", {"cwd": "/tmp/work", "session_id": "sess-1", "mcp_servers": []})
        in sdk_client.calls
    )
    assert (
        ("resume_session", {"cwd": "/tmp/work", "session_id": "sess-1", "mcp_servers": []})
        in sdk_client.calls
    )
    assert ("close_session", {"session_id": "sess-1"}) in sdk_client.calls
    assert ("authenticate", {"method_id": "oauth"}) in sdk_client.calls


@pytest.mark.anyio
async def test_acp_sdk_connection_bridges_permission_requests_to_raw_notifications() -> None:
    transport = _FakeTransportContext()
    sdk_client = _FakeSdkClientConnection()
    connection = AcpSdkConnection(
        command="dummy-agent",
        transport_factory=lambda _cmd, _args, _env, _cwd, _limit: transport,
        client_factory=lambda _client, _writer, _reader: sdk_client,
    )
    await connection.start()

    request_task = asyncio.create_task(
        connection._request_permission(
            options=[
                PermissionOption.model_validate(
                    {"optionId": "approved", "name": "Yes", "kind": "allow_once"}
                )
            ],
            session_id="sess-1",
            tool_call=ToolCallUpdate.model_validate(
                {
                    "toolCallId": "call-1",
                    "title": "Edit file",
                    "status": "pending",
                    "kind": "edit",
                    "rawInput": {"path": "demo.txt"},
                }
            ),
            meta=None,
        )
    )
    await asyncio.sleep(0)

    notifications = connection.drain_notifications()
    assert len(notifications) == 1
    assert notifications[0]["method"] == "session/request_permission"
    assert notifications[0]["params"]["sessionId"] == "sess-1"
    assert notifications[0]["params"]["toolCall"]["toolCallId"] == "call-1"

    await connection.respond(
        notifications[0]["id"],
        result={"outcome": {"outcome": "selected", "optionId": "approved"}},
    )
    response = await request_task

    assert response.model_dump(by_alias=True, exclude_none=True) == {
        "outcome": {"outcome": "selected", "optionId": "approved"}
    }


@pytest.mark.anyio
async def test_acp_sdk_connection_logs_incoming_session_updates(tmp_path: Path) -> None:
    transport = _FakeTransportContext()
    sdk_client = _FakeSdkClientConnection()
    log_path = tmp_path / "acp.jsonl"
    connection = AcpSdkConnection(
        command="dummy-agent",
        log_path=log_path,
        transport_factory=lambda _cmd, _args, _env, _cwd, _limit: transport,
        client_factory=lambda client, _writer, _reader: sdk_client,
    )
    await connection.start()

    from agent_operator.acp.sdk_client import _SdkBridgeClient

    bridge = _SdkBridgeClient(connection)
    update = _FakeModel(
        {
            "sessionUpdate": "agent_message_chunk",
            "content": {"type": "text", "text": "hello"},
        }
    )

    await bridge.session_update("sess-1", update)

    notifications = connection.drain_notifications()
    assert len(notifications) == 1
    lines = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()]
    stdout_events = [line for line in lines if line["event"] == "jsonrpc.stdout"]
    assert stdout_events
    payload = json.loads(stdout_events[-1]["line"])
    assert payload["method"] == "session/update"
    assert payload["params"]["sessionId"] == "sess-1"
    assert payload["params"]["update"]["content"]["text"] == "hello"
