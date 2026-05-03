from __future__ import annotations

import asyncio
from collections.abc import Callable, Mapping
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from agent_operator.acp.session_runner import acp_log_path
from agent_operator.domain import (
    AgentDescriptor,
    AgentError,
    AgentProgress,
    AgentProgressState,
    AgentResult,
    AgentResultStatus,
    AgentSessionCommand,
    AgentSessionCommandType,
    AgentSessionHandle,
    RunEvent,
    RunEventKind,
    TechnicalFactDraft,
)
from agent_operator.dtos.requests import AgentRunRequest
from agent_operator.protocols import AgentSessionManager, AgentSessionRuntime, EventSink


class AgentSessionRuntimeFactory(Protocol):
    """Build one session runtime for a concrete working directory and log path.

    Args:
        working_directory: Runtime working directory.
        log_path: Runtime log file path.

    Returns:
        One session runtime instance.
    """

    def __call__(
        self,
        *,
        working_directory: Path,
        log_path: Path,
        session_metadata: dict[str, str] | None = None,
    ) -> AgentSessionRuntime: ...


class AttachedRuntimeBinding(Protocol):
    """Minimal binding view required by attached execution.

    Attributes:
        agent_key: Stable configured agent key.
        descriptor: Static agent descriptor surfaced to planning and CLI.
    """

    agent_key: str
    descriptor: AgentDescriptor
    build_session_runtime: AgentSessionRuntimeFactory


@dataclass(frozen=True, slots=True)
class _AttachedSessionRuntimeSpec:
    """Capture the runtime-facing inputs for one logical attached session."""

    adapter_key: str
    working_directory: Path
    log_path: Path
    session_name: str | None
    one_shot: bool
    metadata: dict[str, str]

    @classmethod
    def for_request(
        cls,
        *,
        adapter_key: str,
        request: AgentRunRequest,
    ) -> _AttachedSessionRuntimeSpec:
        session_name = request.session_name
        return cls(
            adapter_key=adapter_key,
            working_directory=request.working_directory,
            log_path=acp_log_path(
                request.working_directory,
                adapter_key=adapter_key,
                session_token=session_name,
            ),
            session_name=session_name,
            one_shot=request.one_shot,
            metadata={
                key: value
                for key, value in request.metadata.items()
                if isinstance(key, str) and isinstance(value, str)
            },
        )

    @classmethod
    def for_handle(cls, handle: AgentSessionHandle) -> _AttachedSessionRuntimeSpec:
        session_name = handle.session_name or cls._payload_str(handle.metadata.get("session_name"))
        working_directory = Path(
            cls._payload_str(handle.metadata.get("working_directory")) or str(Path.cwd())
        )
        return cls(
            adapter_key=handle.adapter_key,
            working_directory=working_directory,
            log_path=acp_log_path(
                working_directory,
                adapter_key=handle.adapter_key,
                session_token=session_name,
            ),
            session_name=session_name,
            one_shot=handle.one_shot,
            metadata={
                key: value
                for key, value in handle.metadata.items()
                if isinstance(key, str) and isinstance(value, str)
            },
        )

    @staticmethod
    def _payload_str(value: object) -> str | None:
        return value if isinstance(value, str) else None


@dataclass(slots=True)
class _LiveAttachedSession:
    """Own one live session runtime and its derived attached-turn state."""

    binding: AttachedRuntimeBinding
    runtime: AgentSessionRuntime
    working_directory: Path
    log_path: Path
    session_name: str | None
    one_shot: bool
    metadata: dict[str, Any]
    handle: AgentSessionHandle | None = None
    started_event: asyncio.Event = field(default_factory=asyncio.Event)
    terminal_event: asyncio.Event = field(default_factory=asyncio.Event)
    consumer_task: asyncio.Task[None] | None = None
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    last_event_at: datetime | None = None
    progress_message: str = "Agent session is running."
    waiting_reason: str | None = None
    output_chunks: list[str] = field(default_factory=list)
    result: AgentResult | None = None
    active_turn: bool = False

    def reset_for_turn(self) -> None:
        """Reset derived state before a fresh prompt turn."""
        self.updated_at = datetime.now(UTC)
        self.last_event_at = None
        self.progress_message = "Agent session is running."
        self.waiting_reason = None
        self.output_chunks.clear()
        self.result = None
        self.terminal_event = asyncio.Event()
        self.active_turn = True


class _AttachedSessionRuntimeOwner:
    """Own runtime-specific reconstruction and fact application for one live session."""

    def __init__(self, binding: AttachedRuntimeBinding, spec: _AttachedSessionRuntimeSpec) -> None:
        self._binding = binding
        self._spec = spec

    async def open_live_session(
        self,
        *,
        handle: AgentSessionHandle | None = None,
    ) -> _LiveAttachedSession:
        runtime = self._binding.build_session_runtime(
            working_directory=self._spec.working_directory,
            log_path=self._spec.log_path,
            session_metadata=dict(self._spec.metadata),
        )
        await runtime.__aenter__()
        return _LiveAttachedSession(
            binding=self._binding,
            runtime=runtime,
            working_directory=self._spec.working_directory,
            log_path=self._spec.log_path,
            session_name=self._spec.session_name,
            one_shot=self._spec.one_shot,
            metadata=dict(self._spec.metadata),
            handle=handle.model_copy(deep=True) if handle is not None else None,
        )

    async def consume_runtime_events(
        self,
        live: _LiveAttachedSession,
        *,
        on_handle_bound: Callable[[str], None] | None = None,
    ) -> None:
        try:
            async for fact in live.runtime.events():
                bound_handle = self.apply_fact(live, fact)
                if bound_handle is not None and on_handle_bound is not None:
                    on_handle_bound(bound_handle)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            now = datetime.now(UTC)
            if live.handle is not None and live.result is None:
                live.result = AgentResult(
                    session_id=live.handle.session_id,
                    status=AgentResultStatus.FAILED,
                    completed_at=now,
                    error=AgentError(
                        code="attached_runtime_stream_failed",
                        message=str(exc),
                        retryable=False,
                    ),
                )
                live.updated_at = now
                live.terminal_event.set()

    def apply_fact(
        self,
        live: _LiveAttachedSession,
        fact: TechnicalFactDraft,
    ) -> str | None:
        live.updated_at = fact.observed_at
        live.last_event_at = fact.observed_at
        bound_handle = self._bind_handle_from_fact(live, fact)
        if fact.fact_type == "session.started":
            live.started_event.set()
            return bound_handle
        if fact.fact_type == "session.output_chunk_observed":
            text = fact.payload.get("text")
            if isinstance(text, str) and text:
                live.output_chunks.append(text)
            live.progress_message = "Agent session is running."
            return bound_handle
        if fact.fact_type == "session.waiting_input_observed":
            waiting_reason = fact.payload.get("message")
            live.waiting_reason = (
                waiting_reason
                if isinstance(waiting_reason, str)
                else "Agent is waiting for input."
            )
            live.progress_message = live.waiting_reason
            live.active_turn = False
            assert live.handle is not None
            raw_payload = self._payload_dict(fact.payload.get("raw")) or {
                "fact": fact.model_dump(mode="json")
            }
            live.result = AgentResult(
                session_id=live.handle.session_id,
                status=AgentResultStatus.INCOMPLETE,
                output_text="".join(live.output_chunks),
                completed_at=fact.observed_at,
                error=AgentError(
                    code="agent_waiting_input",
                    message=live.waiting_reason,
                    retryable=False,
                    raw=raw_payload,
                ),
                raw=raw_payload,
            )
            live.terminal_event.set()
            return bound_handle
        terminal_result = self._terminal_result_from_fact(live, fact)
        if terminal_result is None:
            return bound_handle
        live.active_turn = False
        live.waiting_reason = None
        live.result = terminal_result
        live.terminal_event.set()
        return bound_handle

    def _bind_handle_from_fact(
        self,
        live: _LiveAttachedSession,
        fact: TechnicalFactDraft,
    ) -> str | None:
        session_id = fact.session_id or self._payload_str(fact.payload.get("session_id"))
        if not isinstance(session_id, str) or not session_id:
            return None
        payload_log_path = self._payload_str(fact.payload.get("log_path"))
        if live.handle is None:
            live.handle = AgentSessionHandle(
                adapter_key=self._binding.agent_key,
                session_id=session_id,
                session_name=live.session_name,
                display_name=self._binding.descriptor.display_name,
                one_shot=live.one_shot,
                metadata={
                    **live.metadata,
                    "working_directory": str(live.working_directory),
                    "log_path": payload_log_path or str(live.log_path),
                },
            )
            live.started_event.set()
            return live.handle.session_id
        if payload_log_path and live.handle.metadata.get("log_path") != payload_log_path:
            live.handle = live.handle.model_copy(
                update={
                    "metadata": {
                        **live.handle.metadata,
                        "log_path": payload_log_path,
                    }
                }
            )
        return None

    def _terminal_result_from_fact(
        self,
        live: _LiveAttachedSession,
        fact: TechnicalFactDraft,
    ) -> AgentResult | None:
        assert live.handle is not None
        raw_payload = self._payload_dict(fact.payload.get("raw")) or {
            "fact": fact.model_dump(mode="json")
        }
        if fact.fact_type == "session.completed":
            output_text = fact.payload.get("output_text")
            return AgentResult(
                session_id=live.handle.session_id,
                status=AgentResultStatus.SUCCESS,
                output_text=(
                    output_text if isinstance(output_text, str) else "".join(live.output_chunks)
                ),
                completed_at=fact.observed_at,
                raw=raw_payload,
            )
        if fact.fact_type == "session.cancelled":
            return AgentResult(
                session_id=live.handle.session_id,
                status=AgentResultStatus.CANCELLED,
                completed_at=fact.observed_at,
                error=AgentError(
                    code=self._payload_str(fact.payload.get("error_code"))
                    or "agent_session_cancelled",
                    message="Agent session cancelled.",
                    retryable=False,
                    raw=raw_payload,
                ),
                raw=raw_payload,
            )
        if fact.fact_type == "session.failed":
            message = fact.payload.get("message")
            return AgentResult(
                session_id=live.handle.session_id,
                status=AgentResultStatus.FAILED,
                completed_at=fact.observed_at,
                error=AgentError(
                    code=self._payload_str(fact.payload.get("error_code"))
                    or "agent_session_failed",
                    message=message if isinstance(message, str) else "Agent session failed.",
                    retryable=bool(fact.payload.get("retryable")),
                    raw=raw_payload,
                ),
                raw=raw_payload,
            )
        if fact.fact_type == "session.discontinuity_observed":
            message = fact.payload.get("message")
            return AgentResult(
                session_id=live.handle.session_id,
                status=AgentResultStatus.DISCONNECTED,
                completed_at=fact.observed_at,
                error=AgentError(
                    code=self._payload_str(fact.payload.get("error_code"))
                    or "agent_session_disconnected",
                    message=(
                        message if isinstance(message, str) else "Agent session disconnected."
                    ),
                    retryable=True,
                    raw=raw_payload,
                ),
                raw=raw_payload,
            )
        return None

    @staticmethod
    def _payload_dict(value: object) -> dict[str, object]:
        return dict(value) if isinstance(value, dict) else {}

    @staticmethod
    def _payload_str(value: object) -> str | None:
        return value if isinstance(value, str) else None


@dataclass(slots=True)
class _TerminalAttachedSession:
    """Retain terminal session truth after live runtime disposal."""

    handle: AgentSessionHandle
    result: AgentResult
    updated_at: datetime
    last_event_at: datetime | None
    log_path: Path


class AttachedSessionManager(AgentSessionManager):
    """Concrete live-session manager for attached and in-process execution.

    This manager owns one `AgentSessionRuntime` instance per live operator session and
    synthesizes the app-facing session lifecycle from runtime facts.

    Examples:
        >>> manager = AttachedSessionManager({})
        >>> manager.keys()
        []
    """

    def __init__(
        self,
        bindings: Mapping[str, AttachedRuntimeBinding],
        *,
        startup_timeout_seconds: float = 60.0,
        event_sink: EventSink | None = None,
    ) -> None:
        self._bindings = dict(bindings)
        self._startup_timeout_seconds = startup_timeout_seconds
        self._event_sink = event_sink
        self._sessions: dict[str, _LiveAttachedSession] = {}
        self._terminal_sessions: dict[str, _TerminalAttachedSession] = {}

    @classmethod
    def from_bindings(
        cls,
        bindings: Mapping[str, AttachedRuntimeBinding],
    ) -> AttachedSessionManager:
        """Build one concrete session manager from attached runtime bindings."""
        return cls(bindings)

    def keys(self) -> list[str]:
        """Return configured agent keys."""
        return sorted(self._bindings)

    def has(self, adapter_key: str) -> bool:
        """Return whether one configured binding exists."""
        return adapter_key in self._bindings

    async def describe(self, adapter_key: str) -> AgentDescriptor:
        """Return one configured descriptor."""
        return self._bindings[adapter_key].descriptor.model_copy(deep=True)

    async def start(
        self,
        adapter_key: str,
        request: AgentRunRequest,
    ) -> AgentSessionHandle:
        """Start one attached session through `AgentSessionRuntime`.

        Args:
            adapter_key: Selected agent key.
            request: New run request.

        Returns:
            Live attached session handle.
        """

        binding = self._bindings[adapter_key]
        owner = _AttachedSessionRuntimeOwner(
            binding,
            _AttachedSessionRuntimeSpec.for_request(
                adapter_key=adapter_key,
                request=request,
            ),
        )
        live = await owner.open_live_session()
        live.reset_for_turn()
        live.consumer_task = asyncio.create_task(self._consume_runtime_events(live, owner))
        try:
            await live.runtime.send(
                AgentSessionCommand(
                    command_type=AgentSessionCommandType.START_SESSION,
                    instruction=request.instruction,
                    metadata={
                        **dict(request.metadata),
                        "goal": request.goal,
                        "session_name": request.session_name,
                        "one_shot": request.one_shot,
                    },
                )
            )
            await asyncio.wait_for(
                live.started_event.wait(),
                timeout=self._startup_timeout_seconds,
            )
            assert live.handle is not None
            return live.handle.model_copy(deep=True)
        except Exception:
            await self._dispose_runtime(live)
            raise

    async def fork(self, handle: AgentSessionHandle) -> AgentSessionHandle:
        """Fork one existing session when the configured adapter supports it."""
        binding = self._bindings.get(handle.adapter_key)
        if binding is None:
            raise RuntimeError(f"Unknown attached session: {handle.session_id}")
        if not binding.descriptor.supports_fork:
            raise RuntimeError(
                f"Agent {binding.descriptor.key!r} does not support session fork."
            )
        owner = _AttachedSessionRuntimeOwner(
            binding,
            _AttachedSessionRuntimeSpec.for_handle(handle),
        )
        live = await owner.open_live_session()
        live.progress_message = "Agent session forked and waiting for the next message."
        live.waiting_reason = live.progress_message
        live.consumer_task = asyncio.create_task(self._consume_runtime_events(live, owner))
        try:
            await live.runtime.send(
                AgentSessionCommand(
                    command_type=AgentSessionCommandType.FORK_SESSION,
                    session_id=handle.session_id,
                    metadata={
                        **live.metadata,
                        "session_name": live.session_name,
                        "one_shot": live.one_shot,
                    },
                )
            )
            await asyncio.wait_for(
                live.started_event.wait(),
                timeout=self._startup_timeout_seconds,
            )
            assert live.handle is not None
            return live.handle.model_copy(deep=True)
        except Exception:
            await self._dispose_runtime(live)
            raise

    async def send(self, handle: AgentSessionHandle, message: str) -> None:
        """Send one follow-up prompt to a live attached session."""
        live = await self._ensure_live_session(handle)
        live.reset_for_turn()
        await live.runtime.send(
            AgentSessionCommand(
                command_type=AgentSessionCommandType.SEND_MESSAGE,
                instruction=message,
                session_id=handle.session_id,
            )
        )

    async def poll(self, handle: AgentSessionHandle) -> AgentProgress:
        """Return the latest synthesized progress snapshot for one session."""
        terminal = self._terminal_sessions.get(handle.session_id)
        if terminal is not None:
            return self._progress_from_terminal_session(terminal)
        live = await self._ensure_live_session(handle)
        state = AgentProgressState.RUNNING
        message = live.progress_message
        if live.waiting_reason is not None:
            state = AgentProgressState.WAITING_INPUT
            message = live.waiting_reason
        elif live.result is not None:
            state = {
                AgentResultStatus.SUCCESS: AgentProgressState.COMPLETED,
                AgentResultStatus.INCOMPLETE: AgentProgressState.WAITING_INPUT,
                AgentResultStatus.FAILED: AgentProgressState.FAILED,
                AgentResultStatus.CANCELLED: AgentProgressState.CANCELLED,
                AgentResultStatus.DISCONNECTED: AgentProgressState.FAILED,
            }[live.result.status]
            if live.result.error is not None:
                message = live.result.error.message
            elif state is AgentProgressState.COMPLETED:
                message = "Agent session completed."
        return AgentProgress(
            session_id=handle.session_id,
            state=state,
            message=message,
            updated_at=live.updated_at,
            partial_output="".join(live.output_chunks)[-2000:],
            raw={
                "last_event_at": (
                    live.last_event_at.isoformat()
                    if live.last_event_at is not None
                    else None
                ),
                "log_path": str(live.log_path),
            },
        )

    async def collect(self, handle: AgentSessionHandle) -> AgentResult:
        """Wait for one terminal result and return it."""
        terminal = self._terminal_sessions.get(handle.session_id)
        if terminal is not None:
            return terminal.result.model_copy(deep=True)
        live = await self._ensure_live_session(handle)
        await live.terminal_event.wait()
        assert live.result is not None
        result = live.result.model_copy(deep=True)
        if self._should_retire_terminal_session(live):
            await self._retire_terminal_session(live)
        return result

    async def cancel(self, handle: AgentSessionHandle) -> None:
        """Cancel one live session and dispose its runtime."""
        live = await self._ensure_live_session(handle)
        try:
            if not (
                live.result is not None
                and live.result.status is AgentResultStatus.INCOMPLETE
            ):
                await live.runtime.cancel(reason="attached_session_cancelled")
        finally:
            if live.result is None:
                now = datetime.now(UTC)
                live.result = AgentResult(
                    session_id=handle.session_id,
                    status=AgentResultStatus.CANCELLED,
                    completed_at=now,
                    error=AgentError(
                        code="agent_session_cancelled",
                        message="Agent session cancelled.",
                        retryable=False,
                    ),
                )
                live.updated_at = now
                live.last_event_at = now
                live.terminal_event.set()
            await self._retire_terminal_session(live)

    async def close(self, handle: AgentSessionHandle) -> None:
        """Dispose one runtime instance without surfacing a cancellation."""
        self._terminal_sessions.pop(handle.session_id, None)
        await self._dispose_by_session_id(handle.session_id)

    async def _ensure_live_session(self, handle: AgentSessionHandle) -> _LiveAttachedSession:
        if handle.session_id in self._terminal_sessions:
            raise RuntimeError(
                f"Attached session {handle.session_id!r} is terminal and cannot continue."
            )
        live = self._sessions.get(handle.session_id)
        if live is not None:
            if self._should_reattach_live_session(live):
                await self._dispose_by_session_id(handle.session_id)
            else:
                return live
        binding = self._bindings.get(handle.adapter_key)
        if binding is None:
            raise RuntimeError(f"Unknown attached session: {handle.session_id}")
        owner = _AttachedSessionRuntimeOwner(
            binding,
            _AttachedSessionRuntimeSpec.for_handle(handle),
        )
        live = await owner.open_live_session(handle=handle)
        live.consumer_task = asyncio.create_task(self._consume_runtime_events(live, owner))
        self._sessions[handle.session_id] = live
        return live

    def _should_reattach_live_session(self, live: _LiveAttachedSession) -> bool:
        task = live.consumer_task
        if task is None or not task.done():
            return False
        return (
            live.result is not None
            and live.result.status is AgentResultStatus.SUCCESS
            and not live.active_turn
        )

    async def _dispose_by_session_id(self, session_id: str) -> None:
        live = self._sessions.pop(session_id, None)
        if live is None:
            return
        await self._dispose_runtime(live)

    async def _dispose_runtime(self, live: _LiveAttachedSession) -> None:
        with suppress(Exception):
            await live.runtime.close()
        task = live.consumer_task
        if task is not None:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task

    async def _consume_runtime_events(
        self,
        live: _LiveAttachedSession,
        owner: _AttachedSessionRuntimeOwner,
    ) -> None:
        try:
            async for fact in live.runtime.events():
                bound_handle = owner.apply_fact(live, fact)
                if bound_handle is not None:
                    self._sessions[bound_handle] = live
                await self._emit_fact_event(live, fact)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            now = datetime.now(UTC)
            if live.handle is not None and live.result is None:
                live.result = AgentResult(
                    session_id=live.handle.session_id,
                    status=AgentResultStatus.FAILED,
                    completed_at=now,
                    error=AgentError(
                        code="attached_runtime_stream_failed",
                        message=str(exc),
                        retryable=False,
                    ),
                )
                live.updated_at = now
                live.terminal_event.set()

    def _progress_from_terminal_session(
        self,
        terminal: _TerminalAttachedSession,
    ) -> AgentProgress:
        result = terminal.result
        state = {
            AgentResultStatus.SUCCESS: AgentProgressState.COMPLETED,
            AgentResultStatus.INCOMPLETE: AgentProgressState.WAITING_INPUT,
            AgentResultStatus.FAILED: AgentProgressState.FAILED,
            AgentResultStatus.CANCELLED: AgentProgressState.CANCELLED,
            AgentResultStatus.DISCONNECTED: AgentProgressState.FAILED,
        }[result.status]
        message = "Agent session completed."
        if result.error is not None:
            message = result.error.message
        return AgentProgress(
            session_id=terminal.handle.session_id,
            state=state,
            message=message,
            updated_at=terminal.updated_at,
            partial_output=(result.output_text or "")[-2000:],
            raw={
                "last_event_at": (
                    terminal.last_event_at.isoformat()
                    if terminal.last_event_at is not None
                    else None
                ),
                "log_path": str(terminal.log_path),
            },
        )

    def _should_retire_terminal_session(self, live: _LiveAttachedSession) -> bool:
        result = live.result
        if result is None:
            return False
        if live.one_shot:
            return True
        return result.status in {
            AgentResultStatus.CANCELLED,
            AgentResultStatus.FAILED,
        }

    async def _retire_terminal_session(self, live: _LiveAttachedSession) -> None:
        assert live.handle is not None
        assert live.result is not None
        self._terminal_sessions[live.handle.session_id] = _TerminalAttachedSession(
            handle=live.handle.model_copy(deep=True),
            result=live.result.model_copy(deep=True),
            updated_at=live.updated_at,
            last_event_at=live.last_event_at,
            log_path=live.log_path,
        )
        await self._dispose_by_session_id(live.handle.session_id)

    async def _emit_fact_event(
        self,
        live: _LiveAttachedSession,
        fact: TechnicalFactDraft,
    ) -> None:
        if self._event_sink is None:
            return
        operation_id = live.metadata.get("operation_id")
        if not isinstance(operation_id, str) or not operation_id:
            return
        session_id = (
            fact.session_id
            or (live.handle.session_id if live.handle is not None else None)
            or self._payload_str(fact.payload.get("session_id"))
        )
        await self._event_sink.emit(
            RunEvent(
                event_type=fact.fact_type,
                kind=RunEventKind.TRACE,
                category="trace",
                operation_id=operation_id,
                iteration=0,
                task_id=fact.task_id if isinstance(fact.task_id, str) else None,
                session_id=session_id if isinstance(session_id, str) else None,
                timestamp=fact.observed_at,
                payload={
                    **dict(fact.payload),
                    "observed_at": fact.observed_at.isoformat(),
                },
            )
        )

    @staticmethod
    def _payload_str(value: object) -> str | None:
        return value if isinstance(value, str) else None
