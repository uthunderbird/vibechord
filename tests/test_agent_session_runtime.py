from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from agent_operator.acp.adapter_runtime import AcpAdapterRuntime
from agent_operator.acp.session_runtime import AcpAgentSessionRuntime
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
