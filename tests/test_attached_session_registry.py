from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path

import pytest

from agent_operator.adapters.runtime_bindings import AgentRuntimeBinding
from agent_operator.application.attached_session_registry import AttachedSessionManager
from agent_operator.domain import (
    AgentDescriptor,
    AgentError,
    AgentResult,
    AgentResultStatus,
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


class TerminalTrackingSessionRuntime(FakeSessionRuntime):
    """Fake runtime that emits one chosen terminal fact and records disposal."""

    def __init__(
        self,
        *,
        terminal_fact_type: str,
        terminal_payload: dict[str, object] | None = None,
    ) -> None:
        super().__init__()
        self.terminal_fact_type = terminal_fact_type
        self.terminal_payload = terminal_payload or {}
        self.close_calls = 0

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
                    fact_type=self.terminal_fact_type,
                    payload=self.terminal_payload,
                    session_id="sess-1",
                )
            )
            return
        await super().send(command)

    async def close(self) -> None:
        self.close_calls += 1
        await super().close()


class ReattachableSessionRuntime(FakeSessionRuntime):
    """Fake runtime factory product used to verify reattachment via session metadata."""

    def __init__(self, *, label: str) -> None:
        super().__init__()
        self.label = label

    async def send(self, command: AgentSessionCommand) -> None:
        self.commands.append(command)
        if command.command_type == AgentSessionCommandType.START_SESSION:
            await self._queue.put(
                TechnicalFactDraft(
                    fact_type="session.started",
                    payload={
                        "session_id": "sess-1",
                        "log_path": f"/tmp/{self.label}.jsonl",
                    },
                    session_id="sess-1",
                )
            )
            await self._queue.put(
                TechnicalFactDraft(
                    fact_type="session.waiting_input_observed",
                    payload={"message": f"{self.label} waiting"},
                    session_id="sess-1",
                )
            )
            return
        if command.command_type == AgentSessionCommandType.SEND_MESSAGE:
            await self._queue.put(
                TechnicalFactDraft(
                    fact_type="session.output_chunk_observed",
                    payload={"text": f"{self.label}:follow-up"},
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
        await super().send(command)


@pytest.mark.anyio
async def test_attached_session_runtime_registry_synthesizes_start_poll_collect_and_follow_up(
) -> None:
    runtime = FakeSessionRuntime()
    registry = AttachedSessionManager(
        {
            "fake": AgentRuntimeBinding(
                agent_key="fake",
                descriptor=AgentDescriptor(key="fake", display_name="Fake"),
                build_adapter_runtime=lambda *, working_directory, log_path: None,
                build_session_runtime=lambda *,
                working_directory,
                log_path,
                session_metadata=None: runtime,
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
    registry = AttachedSessionManager(
        {
            "fake": AgentRuntimeBinding(
                agent_key="fake",
                descriptor=AgentDescriptor(key="fake", display_name="Fake"),
                build_adapter_runtime=lambda *, working_directory, log_path: None,
                build_session_runtime=lambda *,
                working_directory,
                log_path,
                session_metadata=None: runtime,
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


@pytest.mark.anyio
async def test_attached_session_runtime_registry_cancel_preserves_waiting_input_truth(
) -> None:
    runtime = CancelTrackingSessionRuntime()
    registry = AttachedSessionManager(
        {
            "fake": AgentRuntimeBinding(
                agent_key="fake",
                descriptor=AgentDescriptor(key="fake", display_name="Fake"),
                build_adapter_runtime=lambda *, working_directory, log_path: None,
                build_session_runtime=lambda *,
                working_directory,
                log_path,
                session_metadata=None: runtime,
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

    live = registry._sessions[handle.session_id]  # noqa: SLF001 - regression check
    live.waiting_reason = "Agent is waiting for approval."
    live.result = AgentResult(
        session_id=handle.session_id,
        status=AgentResultStatus.INCOMPLETE,
        completed_at=datetime.now(UTC),
        output_text="hello",
        error=AgentError(
            code="agent_waiting_input",
            message="Agent is waiting for approval.",
            retryable=False,
        ),
    )
    live.terminal_event.set()

    await registry.cancel(handle)
    progress = await registry.poll(handle)
    result = await registry.collect(handle)

    assert runtime.cancel_calls == 0
    assert runtime.close_calls == 1
    assert progress.state.value == "waiting_input"
    assert result.status.value == "incomplete"
    assert result.error is not None
    assert result.error.code == "agent_waiting_input"


@pytest.mark.anyio
async def test_attached_session_runtime_registry_rehydrates_runtime_from_handle_metadata(
) -> None:
    runtimes: list[ReattachableSessionRuntime] = []

    def build_runtime(*, working_directory, log_path, session_metadata=None):
        del working_directory, log_path, session_metadata
        runtime = ReattachableSessionRuntime(label=f"runtime-{len(runtimes) + 1}")
        runtimes.append(runtime)
        return runtime

    registry = AttachedSessionManager(
        {
            "fake": AgentRuntimeBinding(
                agent_key="fake",
                descriptor=AgentDescriptor(key="fake", display_name="Fake"),
                build_adapter_runtime=lambda *, working_directory, log_path: None,
                build_session_runtime=build_runtime,
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
    initial_result = await registry.collect(handle)

    assert initial_result.status.value == "incomplete"
    assert handle.metadata["log_path"] == "/tmp/runtime-1.jsonl"

    await registry.close(handle)
    await registry.send(handle, "continue")
    follow_up = await registry.collect(handle)

    assert len(runtimes) == 2
    assert runtimes[1].commands[-1].command_type is AgentSessionCommandType.SEND_MESSAGE
    assert runtimes[1].commands[-1].session_id == "sess-1"
    assert follow_up.output_text == "runtime-2:follow-up"


@pytest.mark.anyio
async def test_attached_session_runtime_registry_collect_retires_completed_one_shot_session(
) -> None:
    runtime = TerminalTrackingSessionRuntime(terminal_fact_type="session.completed")
    registry = AttachedSessionManager(
        {
            "fake": AgentRuntimeBinding(
                agent_key="fake",
                descriptor=AgentDescriptor(key="fake", display_name="Fake"),
                build_adapter_runtime=lambda *, working_directory, log_path: None,
                build_session_runtime=lambda *,
                working_directory,
                log_path,
                session_metadata=None: runtime,
            )
        }
    )

    handle = await registry.start(
        "fake",
        AgentRunRequest(
            goal="goal",
            instruction="inspect",
            one_shot=True,
            working_directory=Path.cwd(),
        ),
    )

    result = await registry.collect(handle)
    progress = await registry.poll(handle)

    assert result.status.value == "success"
    assert runtime.close_calls == 1
    assert progress.state.value == "completed"

    with pytest.raises(RuntimeError, match="terminal and cannot continue"):
        await registry.send(handle, "continue")


@pytest.mark.anyio
async def test_attached_session_runtime_registry_collect_retires_failed_session(
) -> None:
    runtime = TerminalTrackingSessionRuntime(
        terminal_fact_type="session.failed",
        terminal_payload={"message": "boom"},
    )
    registry = AttachedSessionManager(
        {
            "fake": AgentRuntimeBinding(
                agent_key="fake",
                descriptor=AgentDescriptor(key="fake", display_name="Fake"),
                build_adapter_runtime=lambda *, working_directory, log_path: None,
                build_session_runtime=lambda *,
                working_directory,
                log_path,
                session_metadata=None: runtime,
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

    result = await registry.collect(handle)
    progress = await registry.poll(handle)

    assert result.status.value == "failed"
    assert progress.state.value == "failed"
    assert runtime.close_calls == 1

    with pytest.raises(RuntimeError, match="terminal and cannot continue"):
        await registry.send(handle, "continue")


@pytest.mark.anyio
async def test_attached_session_runtime_registry_preserves_retryable_provider_capacity_error(
) -> None:
    runtime = TerminalTrackingSessionRuntime(
        terminal_fact_type="session.failed",
        terminal_payload={
            "message": "Selected model is at capacity. Please try a different model.",
            "error_code": "codex_acp_provider_overloaded",
            "retryable": True,
            "raw": {
                "failure_kind": "provider_capacity",
                "recovery_mode": "new_session",
                "codex_error_info": "server_overloaded",
            },
        },
    )
    registry = AttachedSessionManager(
        {
            "fake": AgentRuntimeBinding(
                agent_key="fake",
                descriptor=AgentDescriptor(key="fake", display_name="Fake"),
                build_adapter_runtime=lambda *, working_directory, log_path: None,
                build_session_runtime=lambda *,
                working_directory,
                log_path,
                session_metadata=None: runtime,
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

    result = await registry.collect(handle)

    assert result.status.value == "failed"
    assert result.error is not None
    assert result.error.code == "codex_acp_provider_overloaded"
    assert result.error.message == "Selected model is at capacity. Please try a different model."
    assert result.error.retryable is True
    assert result.error.raw == {
        "failure_kind": "provider_capacity",
        "recovery_mode": "new_session",
        "codex_error_info": "server_overloaded",
    }
