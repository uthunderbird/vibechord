from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest

from agent_operator.acp.adapter_runtime import AcpAdapterRuntime
from agent_operator.domain import (
    AdapterCommand,
    AdapterCommandType,
)


class FakeAcpConnection:
    """Minimal ACP connection double for adapter-runtime tests."""

    def __init__(self) -> None:
        self.started = False
        self.closed = False
        self.requests: list[tuple[str, dict[str, Any]]] = []
        self.notifications: list[tuple[str, dict[str, Any]]] = []
        self.responses: list[tuple[int, dict[str, Any] | None, dict[str, Any] | None]] = []
        self._drained_notifications: list[dict[str, Any]] = []

    async def start(self) -> None:
        self.started = True

    async def request(
        self,
        method: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload = params or {}
        self.requests.append((method, payload))
        return {"ok": True}

    async def respond(
        self,
        request_id: int,
        *,
        result: dict[str, Any] | None = None,
        error: dict[str, Any] | None = None,
    ) -> None:
        self.responses.append((request_id, result, error))

    async def notify(
        self,
        method: str,
        params: dict[str, Any] | None = None,
    ) -> None:
        self.notifications.append((method, params or {}))

    def drain_notifications(self) -> list[dict[str, Any]]:
        items = list(self._drained_notifications)
        self._drained_notifications.clear()
        return items

    def stderr_text(self, limit: int = 4000) -> str:
        return ""

    async def close(self) -> None:
        self.closed = True


@pytest.mark.anyio
async def test_acp_adapter_runtime_starts_and_closes_transport() -> None:
    connection = FakeAcpConnection()
    runtime = AcpAdapterRuntime(
        adapter_key="codex_acp",
        working_directory=Path.cwd(),
        connection=connection,
    )

    async with runtime:
        assert connection.started is True

    assert connection.closed is True


@pytest.mark.anyio
async def test_acp_adapter_runtime_sends_request_notify_and_respond_commands() -> None:
    connection = FakeAcpConnection()
    runtime = AcpAdapterRuntime(
        adapter_key="codex_acp",
        working_directory=Path.cwd(),
        connection=connection,
    )

    async with runtime:
        await runtime.send(
            AdapterCommand(
                command_type=AdapterCommandType.REQUEST,
                method="session/new",
                params={"cwd": str(Path.cwd())},
            )
        )
        await runtime.send(
            AdapterCommand(
                command_type=AdapterCommandType.NOTIFY,
                method="session/prompt",
                params={"sessionId": "session-1", "prompt": "hello"},
            )
        )
        await runtime.send(
            AdapterCommand(
                command_type=AdapterCommandType.RESPOND,
                request_id=7,
                result={"decision": "approve"},
            )
        )

    assert connection.requests == [("session/new", {"cwd": str(Path.cwd())})]
    assert connection.notifications == [
        ("session/prompt", {"sessionId": "session-1", "prompt": "hello"})
    ]
    assert connection.responses == [(7, {"decision": "approve"}, None)]


@pytest.mark.anyio
async def test_acp_adapter_runtime_emits_adapter_facts_from_notifications() -> None:
    connection = FakeAcpConnection()
    runtime = AcpAdapterRuntime(
        adapter_key="claude_acp",
        working_directory=Path.cwd(),
        connection=connection,
        poll_interval_seconds=0.01,
    )

    async with runtime:
        stream = runtime.events()
        task = asyncio.create_task(anext(stream))
        await asyncio.sleep(0.02)
        connection._drained_notifications.append(  # noqa: SLF001 - test fixture injection
            {"method": "session/progress", "params": {"sessionId": "session-1"}}
        )
        fact = await asyncio.wait_for(task, timeout=1.0)

    assert fact.fact_type == "acp.notification.received"
    assert fact.adapter_key == "claude_acp"
    assert fact.payload["method"] == "session/progress"
    assert fact.payload["params"] == {"sessionId": "session-1"}


@pytest.mark.anyio
async def test_acp_adapter_runtime_cancel_closes_stream() -> None:
    connection = FakeAcpConnection()
    runtime = AcpAdapterRuntime(
        adapter_key="claude_acp",
        working_directory=Path.cwd(),
        connection=connection,
        poll_interval_seconds=0.01,
    )

    async with runtime:
        await runtime.cancel(reason="stop transport")
        stream = runtime.events()
        with pytest.raises(StopAsyncIteration):
            await anext(stream)

    assert connection.closed is True


@pytest.mark.anyio
async def test_acp_adapter_runtime_events_is_single_consumer() -> None:
    connection = FakeAcpConnection()
    runtime = AcpAdapterRuntime(
        adapter_key="claude_acp",
        working_directory=Path.cwd(),
        connection=connection,
    )

    async with runtime:
        first = runtime.events()
        assert first is not None
        with pytest.raises(RuntimeError, match="single-consumer"):
            runtime.events()
