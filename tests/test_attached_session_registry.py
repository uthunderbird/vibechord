from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from agent_operator.adapters.runtime_bindings import AgentRuntimeBinding
from agent_operator.application.attached_session_registry import AttachedSessionRuntimeRegistry
from agent_operator.domain import (
    AgentDescriptor,
    AgentSessionCommand,
    AgentSessionCommandType,
    TechnicalFactDraft,
)
from agent_operator.dtos.requests import AgentRunRequest


class FakeSessionRuntime:
    """Small session-runtime fake that emits deterministic technical facts."""

    def __init__(self) -> None:
        self.commands: list[AgentSessionCommand] = []
        self._queue: asyncio.Queue[TechnicalFactDraft | None] = asyncio.Queue()
        self._closed = False

    async def __aenter__(self) -> FakeSessionRuntime:
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.close()

    async def send(self, command: AgentSessionCommand) -> None:
        self.commands.append(command)
        if command.command_type == AgentSessionCommandType.START_SESSION:
            await self._queue.put(
                TechnicalFactDraft(
                    fact_type="session.started",
                    payload={"session_id": "sess-1"},
                    session_id="sess-1",
                )
            )
            await self._queue.put(
                TechnicalFactDraft(
                    fact_type="session.output_chunk_observed",
                    payload={"text": "hello"},
                    session_id="sess-1",
                )
            )
            await self._queue.put(
                TechnicalFactDraft(
                    fact_type="session.completed",
                    payload={},
                    session_id="sess-1",
                )
            )
            return
        if command.command_type == AgentSessionCommandType.SEND_MESSAGE:
            await self._queue.put(
                TechnicalFactDraft(
                    fact_type="session.output_chunk_observed",
                    payload={"text": "follow-up"},
                    session_id="sess-1",
                )
            )
            await self._queue.put(
                TechnicalFactDraft(
                    fact_type="session.completed",
                    payload={},
                    session_id="sess-1",
                )
            )

    def events(self):
        return self._events()

    async def _events(self):
        while True:
            item = await self._queue.get()
            if item is None:
                return
            yield item

    async def cancel(self, reason: str | None = None) -> None:
        if self._closed:
            return
        self._closed = True
        await self._queue.put(None)

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        await self._queue.put(None)


class CancelTrackingSessionRuntime(FakeSessionRuntime):
    """Fake runtime that exposes cancel/close counts for disposal assertions."""

    def __init__(self) -> None:
        super().__init__()
        self.cancel_calls = 0
        self.close_calls = 0
        self.enter_calls = 0

    async def __aenter__(self) -> CancelTrackingSessionRuntime:
        self.enter_calls += 1
        return self

    async def send(self, command: AgentSessionCommand) -> None:
        self.commands.append(command)
        if command.command_type == AgentSessionCommandType.START_SESSION:
            await self._queue.put(
                TechnicalFactDraft(
                    fact_type="session.started",
                    payload={"session_id": "sess-1"},
                    session_id="sess-1",
                )
            )
            await self._queue.put(
                TechnicalFactDraft(
                    fact_type="session.output_chunk_observed",
                    payload={"text": "hello"},
                    session_id="sess-1",
                )
            )
            return
        await super().send(command)

    async def cancel(self, reason: str | None = None) -> None:
        self.cancel_calls += 1
        await super().cancel(reason=reason)

    async def close(self) -> None:
        self.close_calls += 1
        await super().close()


@pytest.mark.anyio
async def test_attached_session_runtime_registry_synthesizes_start_poll_collect_and_follow_up(
) -> None:
    runtime = FakeSessionRuntime()
    registry = AttachedSessionRuntimeRegistry(
        {
            "fake": AgentRuntimeBinding(
                agent_key="fake",
                descriptor=AgentDescriptor(key="fake", display_name="Fake"),
                build_adapter_runtime=lambda *, working_directory, log_path: None,
                build_session_runtime=lambda *, working_directory, log_path: runtime,
            )
        }
    )

    handle = await registry.start(
        "fake",
        AgentRunRequest(
            goal="goal",
            instruction="inspect",
            working_directory=Path.cwd(),
        ),
    )
    progress = await registry.poll(handle)
    result = await registry.collect(handle)

    assert handle.adapter_key == "fake"
    assert progress.state.value == "completed"
    assert result.output_text == "hello"

    await registry.send(handle, "continue")
    follow_up = await registry.collect(handle)

    assert follow_up.output_text == "follow-up"


@pytest.mark.anyio
async def test_attached_session_runtime_registry_cancel_disposes_runtime_and_keeps_terminal_truth(
) -> None:
    runtime = CancelTrackingSessionRuntime()
    registry = AttachedSessionRuntimeRegistry(
        {
            "fake": AgentRuntimeBinding(
                agent_key="fake",
                descriptor=AgentDescriptor(key="fake", display_name="Fake"),
                build_adapter_runtime=lambda *, working_directory, log_path: None,
                build_session_runtime=lambda *, working_directory, log_path: runtime,
            )
        }
    )

    handle = await registry.start(
        "fake",
        AgentRunRequest(
            goal="goal",
            instruction="inspect",
            working_directory=Path.cwd(),
        ),
    )

    await registry.cancel(handle)
    progress = await registry.poll(handle)
    result = await registry.collect(handle)

    assert runtime.cancel_calls == 1
    assert runtime.close_calls == 1
    assert progress.state.value == "cancelled"
    assert result.status.value == "cancelled"

    with pytest.raises(RuntimeError, match="terminal and cannot continue"):
        await registry.send(handle, "continue")
