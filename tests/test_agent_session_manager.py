from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import pytest

from agent_operator.acp.adapter_runtime import AcpAdapterRuntime
from agent_operator.acp.session_runtime import AcpAgentSessionRuntime
from agent_operator.application.agent_session_manager import AttachedSessionManager
from agent_operator.application.attached_session_registry import AttachedRuntimeBinding
from agent_operator.dtos.requests import AgentRunRequest
from agent_operator.domain import (
    AgentCapability,
    AgentDescriptor,
    AgentSessionCommand,
    AgentSessionCommandType,
    AgentResultStatus,
    AgentSessionHandle,
    TechnicalFactDraft,
)
from agent_operator.testing.operator_service_support import FakeAgent
from agent_operator.testing.runtime_bindings import build_test_runtime_bindings


class _ForkCapableAcpConnection:
    def __init__(self) -> None:
        self.started = False
        self.closed = False
        self.requests: list[tuple[str, dict]] = []
        self.next_session_id = "sess-1"

    async def start(self) -> None:
        self.started = True

    async def request(self, method: str, params: dict | None = None) -> dict:
        payload = params or {}
        self.requests.append((method, payload))
        if method == "session/fork":
            return {"sessionId": "sess-2"}
        if method == "session/load":
            return {"sessionId": payload.get("sessionId", "sess-2")}
        return {"ok": True}

    async def respond(self, request_id: int, *, result=None, error=None) -> None:
        return None

    async def notify(self, method: str, params: dict | None = None) -> None:
        return None

    def drain_notifications(self) -> list[dict]:
        return []

    def stderr_text(self, limit: int = 4000) -> str:
        return ""

    async def close(self) -> None:
        self.closed = True


def _fork_binding() -> AttachedRuntimeBinding:
    descriptor = AgentDescriptor(
        key="codex_acp",
        display_name="Codex via ACP",
        capabilities=[
            AgentCapability(name="acp", description="ACP session over stdio"),
            AgentCapability(name="fork", description="Can fork an existing ACP session"),
        ],
        supports_follow_up=True,
        supports_cancellation=True,
        supports_fork=True,
    )

    def build_runtime(*, working_directory: Path, log_path: Path) -> AcpAgentSessionRuntime:
        connection = _ForkCapableAcpConnection()
        adapter_runtime = AcpAdapterRuntime(
            adapter_key="codex_acp",
            working_directory=working_directory,
            connection=connection,
            poll_interval_seconds=0.01,
        )
        return AcpAgentSessionRuntime(
            adapter_runtime=adapter_runtime,
            working_directory=working_directory,
        )

    @dataclass
    class _Binding:
        agent_key: str
        descriptor: AgentDescriptor

        @staticmethod
        def build_session_runtime(
            *,
            working_directory: Path,
            log_path: Path,
        ) -> AcpAgentSessionRuntime:
            return build_runtime(working_directory=working_directory, log_path=log_path)

    return _Binding(agent_key="codex_acp", descriptor=descriptor)


@pytest.mark.anyio
async def test_agent_session_manager_forks_when_binding_supports_it(tmp_path: Path) -> None:
    manager = AttachedSessionManager.from_bindings({"codex_acp": _fork_binding()})

    handle = await manager.fork(
        AgentSessionHandle(
            adapter_key="codex_acp",
            session_id="sess-1",
            session_name="fork-parent",
            metadata={"working_directory": str(tmp_path)},
        )
    )

    assert handle.adapter_key == "codex_acp"
    assert handle.session_id == "sess-2"
    assert handle.session_name == "fork-parent"
    assert handle.metadata["working_directory"] == str(tmp_path)


@pytest.mark.anyio
async def test_agent_session_manager_rejects_fork_when_binding_does_not_support_it(
    tmp_path: Path,
) -> None:
    fake_agent = FakeAgent(supports_follow_up=True)
    manager = AttachedSessionManager.from_bindings(
        build_test_runtime_bindings({"claude_acp": fake_agent})
    )

    with pytest.raises(RuntimeError, match="does not support session fork"):
        await manager.fork(
            AgentSessionHandle(
                adapter_key="claude_acp",
                session_id="session-1",
                metadata={"working_directory": str(tmp_path)},
            )
        )


class _ForkableFakeAgent(FakeAgent):
    def __init__(self) -> None:
        super().__init__(key="claude_acp", supports_follow_up=True)
        self.supports_fork = True
        self.forked_handles: list[AgentSessionHandle] = []

    async def fork(self, handle: AgentSessionHandle) -> AgentSessionHandle:
        self.forked_handles.append(handle)
        return AgentSessionHandle(
            adapter_key=handle.adapter_key,
            session_id="session-2",
            session_name=handle.session_name,
            metadata={
                **dict(handle.metadata),
                "log_path": str(Path(handle.metadata["working_directory"]) / "fork.jsonl"),
            },
        )


@pytest.mark.anyio
async def test_agent_session_manager_forks_through_test_runtime_binding_when_agent_implements_it(
    tmp_path: Path,
) -> None:
    fake_agent = _ForkableFakeAgent()
    manager = AttachedSessionManager.from_bindings(
        build_test_runtime_bindings({"claude_acp": fake_agent})
    )

    handle = await manager.fork(
        AgentSessionHandle(
            adapter_key="claude_acp",
            session_id="session-1",
            session_name="fork-parent",
            metadata={"working_directory": str(tmp_path)},
        )
    )

    assert handle.session_id == "session-2"
    assert fake_agent.forked_handles[0].session_id == "session-1"
    assert handle.metadata["log_path"] == str(tmp_path / "fork.jsonl")


class _ReattachAfterTerminalRuntime:
    def __init__(self, *, instance_id: int, working_directory: Path) -> None:
        self.instance_id = instance_id
        self.working_directory = working_directory
        self._events: asyncio.Queue[TechnicalFactDraft | None] = asyncio.Queue()
        self._events_claimed = False
        self._handle = AgentSessionHandle(
            adapter_key="codex_acp",
            session_id="sess-1",
            session_name="reattachable",
            metadata={"working_directory": str(working_directory)},
        )
        self._emit_task: asyncio.Task[None] | None = None

    async def __aenter__(self) -> _ReattachAfterTerminalRuntime:
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.close()

    async def send(self, command: AgentSessionCommand) -> None:
        if command.command_type == AgentSessionCommandType.START_SESSION:
            self._emit_task = asyncio.create_task(
                self._emit_start_sequence(f"completed via runtime-{self.instance_id}")
            )
            return
        if command.command_type == AgentSessionCommandType.SEND_MESSAGE:
            self._emit_task = asyncio.create_task(
                self._emit_follow_up_sequence(f"follow-up via runtime-{self.instance_id}")
            )
            return
        raise AssertionError(f"Unexpected command type: {command.command_type}")

    def events(self):
        if self._events_claimed:
            raise RuntimeError("events already claimed")
        self._events_claimed = True
        return self._iterate()

    async def _iterate(self):
        while True:
            item = await self._events.get()
            if item is None:
                return
            yield item

    async def _emit_start_sequence(self, output_text: str) -> None:
        started_at = datetime.now(UTC)
        await self._events.put(
            TechnicalFactDraft(
                fact_type="session.started",
                payload={
                    "session_id": self._handle.session_id,
                    "working_directory": str(self.working_directory),
                },
                observed_at=started_at,
                session_id=self._handle.session_id,
            )
        )
        await asyncio.sleep(0)
        await self._events.put(
            TechnicalFactDraft(
                fact_type="session.completed",
                payload={"output_text": output_text},
                observed_at=datetime.now(UTC),
                session_id=self._handle.session_id,
            )
        )
        await self._events.put(None)

    async def _emit_follow_up_sequence(self, output_text: str) -> None:
        await asyncio.sleep(0)
        await self._events.put(
            TechnicalFactDraft(
                fact_type="session.completed",
                payload={"output_text": output_text},
                observed_at=datetime.now(UTC),
                session_id=self._handle.session_id,
            )
        )
        await self._events.put(None)

    async def cancel(self, reason: str | None = None) -> None:
        await self.close()

    async def close(self) -> None:
        if self._emit_task is not None:
            self._emit_task.cancel()
        await self._events.put(None)


@pytest.mark.anyio
async def test_agent_session_manager_reattaches_after_successful_turn_runtime_exits(
    tmp_path: Path,
) -> None:
    descriptor = AgentDescriptor(
        key="codex_acp",
        display_name="Codex via ACP",
        capabilities=[AgentCapability(name="acp", description="ACP session over stdio")],
        supports_follow_up=True,
        supports_cancellation=True,
        supports_fork=False,
    )
    built_runtime_ids: list[int] = []

    @dataclass
    class _Binding:
        agent_key: str
        descriptor: AgentDescriptor

        @staticmethod
        def build_session_runtime(*, working_directory: Path, log_path: Path):
            runtime_id = len(built_runtime_ids) + 1
            built_runtime_ids.append(runtime_id)
            return _ReattachAfterTerminalRuntime(
                instance_id=runtime_id,
                working_directory=working_directory,
            )

    manager = AttachedSessionManager.from_bindings({"codex_acp": _Binding("codex_acp", descriptor)})

    handle = await manager.start(
        "codex_acp",
        AgentRunRequest(
            goal="goal",
            instruction="start",
            session_name="reattachable",
            one_shot=False,
            working_directory=tmp_path,
            metadata={"working_directory": str(tmp_path)},
        ),
    )
    first = await asyncio.wait_for(manager.collect(handle), timeout=1.0)
    assert first.status is AgentResultStatus.SUCCESS
    assert first.output_text == "completed via runtime-1"

    await asyncio.sleep(0)

    await manager.send(handle, "follow up")
    second = await asyncio.wait_for(manager.collect(handle), timeout=1.0)

    assert second.status is AgentResultStatus.SUCCESS
    assert second.output_text == "follow-up via runtime-2"
    assert built_runtime_ids == [1, 2]
