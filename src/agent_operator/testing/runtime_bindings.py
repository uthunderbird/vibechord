from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Mapping
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from agent_operator.adapters.runtime_bindings import AgentRuntimeBinding
from agent_operator.domain import (
    AgentCapability,
    AgentDescriptor,
    AgentProgressState,
    AgentResult,
    AgentResultStatus,
    AgentSessionCommand,
    AgentSessionCommandType,
    AgentSessionHandle,
    TechnicalFactDraft,
    standard_coding_agent_capabilities,
)
from agent_operator.dtos.requests import AgentRunRequest
from agent_operator.protocols import AdapterRuntime, AgentSessionRuntime


class TestAgentFacade(Protocol):
    """Minimal fake-agent shape for building runtime-native test bindings."""

    key: str

    async def describe(self) -> AgentDescriptor: ...

    async def start(self, request: AgentRunRequest) -> AgentSessionHandle: ...

    async def send(self, handle: AgentSessionHandle, message: str) -> None: ...

    async def poll(self, handle: AgentSessionHandle): ...

    async def collect(self, handle: AgentSessionHandle) -> AgentResult: ...

    async def cancel(self, handle: AgentSessionHandle) -> None: ...

    async def close(self, handle: AgentSessionHandle) -> None: ...


class ForkableTestAgentFacade(TestAgentFacade, Protocol):
    """Optional fake-agent extension for honest session-fork support."""

    async def fork(self, handle: AgentSessionHandle) -> AgentSessionHandle: ...


@dataclass(slots=True)
class _TurnPollState:
    """Track last-observed partial output during one synthetic runtime turn."""

    partial_output: str = ""


class TestAgentSessionRuntime:
    """Adapt one fake test agent to the `AgentSessionRuntime` contract."""

    def __init__(
        self,
        *,
        adapter: TestAgentFacade,
        descriptor: AgentDescriptor,
        working_directory: Path,
        log_path: Path,
    ) -> None:
        self._adapter = adapter
        self._descriptor = descriptor
        self._working_directory = working_directory
        self._log_path = log_path
        self._handle: AgentSessionHandle | None = None
        self._events: asyncio.Queue[TechnicalFactDraft | None] = asyncio.Queue()
        self._events_claimed = False
        self._turn_task: asyncio.Task[None] | None = None
        self._turn_state = _TurnPollState()

    async def __aenter__(self) -> TestAgentSessionRuntime:
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.close()

    async def send(self, command: AgentSessionCommand) -> None:
        """Send one start or follow-up command through the legacy fake adapter."""
        if command.command_type == AgentSessionCommandType.START_SESSION:
            await self._start_session(command)
            return
        if command.command_type == AgentSessionCommandType.FORK_SESSION:
            await self._fork_session(command)
            return
        if command.command_type == AgentSessionCommandType.SEND_MESSAGE:
            await self._send_message(command)
            return
        raise ValueError(f"Unsupported test session command: {command.command_type}.")

    def events(self) -> AsyncIterator[TechnicalFactDraft]:
        """Expose one single-consumer technical-fact stream."""
        if self._events_claimed:
            raise RuntimeError("TestAgentSessionRuntime.events() is single-consumer.")
        self._events_claimed = True
        return self._iterate_events()

    async def cancel(self, reason: str | None = None) -> None:
        """Cancel the current legacy turn and emit one terminal fact."""
        await self._cancel_turn_task()
        handle = self._handle
        if handle is None:
            return
        await self._adapter.cancel(handle)
        await self._emit(
            "session.cancelled",
            session_id=handle.session_id,
            payload={"reason": reason or "cancelled"},
        )

    async def close(self) -> None:
        await self._cancel_turn_task()
        handle = self._handle
        if handle is not None:
            with suppress(Exception):
                await self._adapter.close(handle)
        self._handle = None
        await self._events.put(None)

    async def _iterate_events(self) -> AsyncIterator[TechnicalFactDraft]:
        while True:
            item = await self._events.get()
            if item is None:
                return
            yield item

    async def _start_session(self, command: AgentSessionCommand) -> None:
        await self._cancel_turn_task()
        request = AgentRunRequest(
            goal=command.metadata.get("goal", ""),
            instruction=command.instruction or "",
            session_name=self._coerce_str(command.metadata.get("session_name")),
            one_shot=bool(command.metadata.get("one_shot", False)),
            working_directory=self._working_directory,
            metadata={
                key: value
                for key, value in {
                    str(item_key): self._coerce_str(item_value)
                    for item_key, item_value in command.metadata.items()
                }.items()
                if value is not None
            },
        )
        self._handle = await self._adapter.start(request)
        self._turn_state = _TurnPollState()
        handle_log_path = self._handle.metadata.get("log_path")
        await self._emit(
            "session.started",
            session_id=self._handle.session_id,
            payload={
                "session_id": self._handle.session_id,
                "adapter_key": self._descriptor.key,
                "log_path": (
                    handle_log_path
                    if isinstance(handle_log_path, str)
                    else str(self._log_path)
                ),
            },
        )
        if not await self._run_turn_step(self._handle):
            self._turn_task = asyncio.create_task(self._run_turn(self._handle))

    async def _send_message(self, command: AgentSessionCommand) -> None:
        handle = self._handle
        if handle is None:
            if not isinstance(command.session_id, str) or not command.session_id:
                raise RuntimeError("TestAgentSessionRuntime cannot continue without session_id.")
            handle = AgentSessionHandle(
                adapter_key=self._descriptor.key,
                session_id=command.session_id,
                one_shot=False,
                metadata={
                    "working_directory": str(self._working_directory),
                    "log_path": str(self._log_path),
                },
            )
            self._handle = handle
        await self._cancel_turn_task()
        await self._adapter.send(handle, command.instruction or "")
        self._turn_state = _TurnPollState()
        if not await self._run_turn_step(handle):
            self._turn_task = asyncio.create_task(self._run_turn(handle))

    async def _fork_session(self, command: AgentSessionCommand) -> None:
        await self._cancel_turn_task()
        if not self._descriptor.supports_fork:
            raise RuntimeError(f"Agent {self._descriptor.key!r} does not support session fork.")
        fork = getattr(self._adapter, "fork", None)
        if not callable(fork):
            raise RuntimeError(
                f"Agent {self._descriptor.key!r} does not implement session fork support."
            )
        source_handle = self._handle
        if source_handle is None:
            if not isinstance(command.session_id, str) or not command.session_id:
                raise RuntimeError("TestAgentSessionRuntime cannot fork without session_id.")
            source_handle = AgentSessionHandle(
                adapter_key=self._descriptor.key,
                session_id=command.session_id,
                one_shot=False,
                metadata={
                    "working_directory": str(self._working_directory),
                    "log_path": str(self._log_path),
                },
            )
        self._handle = await fork(source_handle)
        self._turn_state = _TurnPollState()
        handle_log_path = self._handle.metadata.get("log_path")
        await self._emit(
            "session.started",
            session_id=self._handle.session_id,
            payload={
                "session_id": self._handle.session_id,
                "adapter_key": self._descriptor.key,
                "forked_from_session_id": source_handle.session_id,
                "log_path": (
                    handle_log_path
                    if isinstance(handle_log_path, str)
                    else str(self._log_path)
                ),
            },
        )

    async def _run_turn(self, handle: AgentSessionHandle) -> None:
        while True:
            if await self._run_turn_step(handle):
                return
            await asyncio.sleep(0)

    async def _run_turn_step(self, handle: AgentSessionHandle) -> bool:
        progress = await self._adapter.poll(handle)
        partial_output = getattr(progress, "partial_output", None)
        if isinstance(partial_output, str) and partial_output != self._turn_state.partial_output:
            delta = partial_output[len(self._turn_state.partial_output) :]
            if not delta:
                delta = partial_output
            self._turn_state.partial_output = partial_output
            await self._emit(
                "session.output_chunk_observed",
                session_id=handle.session_id,
                observed_at=progress.updated_at,
                payload={"text": delta},
            )
        if progress.state is AgentProgressState.WAITING_INPUT:
            await self._emit(
                "session.waiting_input_observed",
                session_id=handle.session_id,
                observed_at=progress.updated_at,
                payload={
                    "message": progress.message,
                    "partial_output": self._turn_state.partial_output,
                    "raw": self._coerce_payload(getattr(progress, "raw", None)),
                },
            )
            return True
        if progress.state in {
            AgentProgressState.COMPLETED,
            AgentProgressState.FAILED,
            AgentProgressState.CANCELLED,
        }:
            result = await self._adapter.collect(handle)
            await self._emit_result(handle, result)
            return True
        return False

    async def _emit_result(self, handle: AgentSessionHandle, result: AgentResult) -> None:
        if result.status is AgentResultStatus.SUCCESS:
            if result.output_text and result.output_text != self._turn_state.partial_output:
                await self._emit(
                    "session.output_chunk_observed",
                    session_id=handle.session_id,
                    observed_at=result.completed_at or datetime.now(UTC),
                    payload={"text": result.output_text},
                )
            await self._emit(
                "session.completed",
                session_id=handle.session_id,
                observed_at=result.completed_at or datetime.now(UTC),
                payload={
                    "status": result.status.value,
                    "output_text": result.output_text,
                    "raw": self._coerce_payload(result.raw),
                },
            )
            return
        fact_type = (
            "session.cancelled"
            if result.status is AgentResultStatus.CANCELLED
            else "session.failed"
        )
        if result.status is AgentResultStatus.DISCONNECTED:
            fact_type = "session.discontinuity_observed"
        error = result.error
        await self._emit(
            fact_type,
            session_id=handle.session_id,
            observed_at=result.completed_at or datetime.now(UTC),
            payload={
                "status": result.status.value,
                "message": error.message if error is not None else result.status.value,
                "error_code": error.code if error is not None else None,
                "raw": self._coerce_payload(error.raw if error is not None else result.raw),
            },
        )

    async def _cancel_turn_task(self) -> None:
        task = self._turn_task
        self._turn_task = None
        if task is None:
            return
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task

    async def _emit(
        self,
        fact_type: str,
        *,
        session_id: str,
        payload: dict[str, object],
        observed_at: datetime | None = None,
    ) -> None:
        await self._events.put(
            TechnicalFactDraft(
                fact_type=fact_type,
                payload=payload,
                observed_at=observed_at or datetime.now(UTC),
                session_id=session_id,
            )
        )

    def _require_handle(self) -> AgentSessionHandle:
        if self._handle is None:
            raise RuntimeError("TestAgentSessionRuntime has no active session handle.")
        return self._handle

    @staticmethod
    def _coerce_str(value: object) -> str | None:
        return value if isinstance(value, str) else None

    @staticmethod
    def _coerce_payload(value: object) -> dict[str, object]:
        return dict(value) if isinstance(value, dict) else {}


def build_test_runtime_bindings(
    agents: Mapping[str, TestAgentFacade],
) -> dict[str, AgentRuntimeBinding]:
    """Build canonical runtime bindings from fake test agents.

    Args:
        agents: Fake test agents keyed by agent key.

    Returns:
        Runtime bindings that expose the same scenario behavior through `AgentSessionRuntime`.
    """

    bindings: dict[str, AgentRuntimeBinding] = {}
    for agent_key, adapter in agents.items():
        bindings[agent_key] = AgentRuntimeBinding(
            agent_key=agent_key,
            descriptor=AgentDescriptor(
                key=agent_key,
                display_name=_coerce_display_name(adapter, agent_key),
                capabilities=_coerce_capabilities(adapter),
                supports_follow_up=_coerce_supports_follow_up(adapter),
                supports_fork=_coerce_supports_fork(adapter),
                metadata=_coerce_metadata(adapter),
            ),
            build_adapter_runtime=_unsupported_adapter_runtime_factory,
            build_session_runtime=_build_test_session_runtime_factory(
                agent_key=agent_key,
                adapter=adapter,
            ),
        )
    return bindings


def _build_test_session_runtime_factory(
    *,
    agent_key: str,
    adapter: TestAgentFacade,
):
    descriptor = AgentDescriptor(
        key=agent_key,
        display_name=_coerce_display_name(adapter, agent_key),
        capabilities=_coerce_capabilities(adapter),
        supports_follow_up=_coerce_supports_follow_up(adapter),
        supports_fork=_coerce_supports_fork(adapter),
        metadata=_coerce_metadata(adapter),
    )

    def factory(*, working_directory: Path, log_path: Path) -> AgentSessionRuntime:
        return TestAgentSessionRuntime(
            adapter=adapter,
            descriptor=descriptor,
            working_directory=working_directory,
            log_path=log_path,
        )

    return factory


def _unsupported_adapter_runtime_factory(
    *,
    working_directory: Path,
    log_path: Path,
) -> AdapterRuntime:
    raise RuntimeError("Test runtime bindings do not provide AdapterRuntime instances.")


def _coerce_display_name(adapter: TestAgentFacade, fallback: str) -> str:
    return getattr(adapter, "display_name", None) or fallback


def _coerce_supports_follow_up(adapter: TestAgentFacade) -> bool:
    return bool(getattr(adapter, "supports_follow_up", True))


def _coerce_supports_fork(adapter: TestAgentFacade) -> bool:
    return bool(getattr(adapter, "supports_fork", False)) and callable(
        getattr(adapter, "fork", None)
    )


def _coerce_capabilities(adapter: TestAgentFacade) -> list[AgentCapability]:
    capabilities = getattr(adapter, "capabilities", None)
    if isinstance(capabilities, list):
        return [item for item in capabilities if isinstance(item, AgentCapability)]
    return standard_coding_agent_capabilities()


def _coerce_metadata(adapter: TestAgentFacade) -> dict[str, object]:
    metadata = getattr(adapter, "metadata", None)
    normalized = dict(metadata) if isinstance(metadata, Mapping) else {}
    permission_resume_mode = getattr(adapter, "permission_resume_mode", None)
    if isinstance(permission_resume_mode, str) and permission_resume_mode:
        normalized["permission_resume_mode"] = permission_resume_mode
    return normalized
