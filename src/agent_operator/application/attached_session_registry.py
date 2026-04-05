from __future__ import annotations

import asyncio
from collections.abc import Mapping
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
    TechnicalFactDraft,
)
from agent_operator.dtos.requests import AgentRunRequest
from agent_operator.protocols import AgentSessionRuntime


class AgentSessionRuntimeFactory(Protocol):
    """Build one session runtime for a concrete working directory and log path.

    Args:
        working_directory: Runtime working directory.
        log_path: Runtime log file path.

    Returns:
        One session runtime instance.
    """

    def __call__(self, *, working_directory: Path, log_path: Path) -> AgentSessionRuntime: ...


class AttachedRuntimeBinding(Protocol):
    """Minimal binding view required by attached execution.

    Attributes:
        agent_key: Stable configured agent key.
        descriptor: Static agent descriptor surfaced to planning and CLI.
    """

    agent_key: str
    descriptor: AgentDescriptor
    build_session_runtime: AgentSessionRuntimeFactory


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


class AttachedSessionRuntimeRegistry:
    """Runtime-backed registry for attached and in-process session execution.

    The registry owns one `AgentSessionRuntime` instance per live operator session and
    synthesizes the old `start/send/poll/collect/cancel` surface from runtime facts.

    Examples:
        >>> registry = AttachedSessionRuntimeRegistry({})
        >>> registry.keys()
        []
    """

    def __init__(self, bindings: Mapping[str, AttachedRuntimeBinding]) -> None:
        self._bindings = dict(bindings)
        self._sessions: dict[str, _LiveAttachedSession] = {}

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
        log_path = acp_log_path(
            request.working_directory,
            adapter_key=adapter_key,
            session_token=request.session_name,
        )
        runtime = binding.build_session_runtime(
            working_directory=request.working_directory,
            log_path=log_path,
        )
        await runtime.__aenter__()
        live = _LiveAttachedSession(
            binding=binding,
            runtime=runtime,
            working_directory=request.working_directory,
            log_path=log_path,
            session_name=request.session_name,
            one_shot=request.one_shot,
            metadata=dict(request.metadata),
        )
        live.reset_for_turn()
        live.consumer_task = asyncio.create_task(self._consume_runtime_events(live))
        try:
            await runtime.send(
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
            await asyncio.wait_for(live.started_event.wait(), timeout=10.0)
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
        live = await self._ensure_live_session(handle)
        await live.terminal_event.wait()
        assert live.result is not None
        return live.result.model_copy(deep=True)

    async def cancel(self, handle: AgentSessionHandle) -> None:
        """Cancel one live session and dispose its runtime."""
        live = await self._ensure_live_session(handle)
        await live.runtime.cancel(reason="attached_session_cancelled")
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
            live.terminal_event.set()

    async def close(self, handle: AgentSessionHandle) -> None:
        """Dispose one runtime instance without surfacing a cancellation."""
        await self._dispose_by_session_id(handle.session_id)

    def _require_session(self, handle: AgentSessionHandle) -> _LiveAttachedSession:
        try:
            return self._sessions[handle.session_id]
        except KeyError as exc:
            raise RuntimeError(f"Unknown attached session: {handle.session_id}") from exc

    async def _ensure_live_session(self, handle: AgentSessionHandle) -> _LiveAttachedSession:
        live = self._sessions.get(handle.session_id)
        if live is not None:
            return live
        binding = self._bindings.get(handle.adapter_key)
        if binding is None:
            raise RuntimeError(f"Unknown attached session: {handle.session_id}")
        working_directory = Path(
            str(handle.metadata.get("working_directory", Path.cwd()))
        )
        session_name = handle.session_name or handle.metadata.get("session_name")
        log_path = acp_log_path(
            working_directory,
            adapter_key=handle.adapter_key,
            session_token=session_name if isinstance(session_name, str) else None,
        )
        runtime = binding.build_session_runtime(
            working_directory=working_directory,
            log_path=log_path,
        )
        await runtime.__aenter__()
        live = _LiveAttachedSession(
            binding=binding,
            runtime=runtime,
            working_directory=working_directory,
            log_path=log_path,
            session_name=session_name if isinstance(session_name, str) else None,
            one_shot=handle.one_shot,
            metadata={
                key: value
                for key, value in handle.metadata.items()
                if isinstance(key, str) and isinstance(value, str)
            },
            handle=handle.model_copy(deep=True),
        )
        live.consumer_task = asyncio.create_task(self._consume_runtime_events(live))
        self._sessions[handle.session_id] = live
        return live

    async def _dispose_by_session_id(self, session_id: str) -> None:
        live = self._sessions.pop(session_id, None)
        if live is None:
            return
        await self._dispose_runtime(live)

    async def _dispose_runtime(self, live: _LiveAttachedSession) -> None:
        with suppress(Exception):
            await live.runtime.__aexit__(None, None, None)
        task = live.consumer_task
        if task is not None:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task

    async def _consume_runtime_events(self, live: _LiveAttachedSession) -> None:
        try:
            async for fact in live.runtime.events():
                self._apply_fact(live, fact)
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

    def _apply_fact(self, live: _LiveAttachedSession, fact: TechnicalFactDraft) -> None:
        live.updated_at = fact.observed_at
        live.last_event_at = fact.observed_at
        if fact.fact_type == "session.started":
            payload_log_path = self._payload_str(fact.payload.get("log_path"))
            handle = AgentSessionHandle(
                adapter_key=live.binding.agent_key,
                session_id=str(fact.payload["session_id"]),
                session_name=live.session_name,
                display_name=live.binding.descriptor.display_name,
                one_shot=live.one_shot,
                metadata={
                    **live.metadata,
                    "working_directory": str(live.working_directory),
                    "log_path": payload_log_path or str(live.log_path),
                },
            )
            live.handle = handle
            self._sessions[handle.session_id] = live
            live.started_event.set()
            return
        if fact.fact_type == "session.output_chunk_observed":
            text = fact.payload.get("text")
            if isinstance(text, str) and text:
                live.output_chunks.append(text)
            live.progress_message = "Agent session is running."
            return
        if fact.fact_type == "session.waiting_input_observed":
            message = fact.payload.get("message")
            live.waiting_reason = (
                message if isinstance(message, str) else "Agent is waiting for input."
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
            return
        if fact.fact_type == "session.completed":
            assert live.handle is not None
            live.active_turn = False
            live.waiting_reason = None
            output_text = fact.payload.get("output_text")
            raw_payload = self._payload_dict(fact.payload.get("raw")) or {
                "fact": fact.model_dump(mode="json")
            }
            live.result = AgentResult(
                session_id=live.handle.session_id,
                status=AgentResultStatus.SUCCESS,
                output_text=(
                    output_text
                    if isinstance(output_text, str)
                    else "".join(live.output_chunks)
                ),
                completed_at=fact.observed_at,
                raw=raw_payload,
            )
            live.terminal_event.set()
            return
        if fact.fact_type == "session.cancelled":
            assert live.handle is not None
            live.active_turn = False
            live.waiting_reason = None
            raw_payload = self._payload_dict(fact.payload.get("raw")) or {
                "fact": fact.model_dump(mode="json")
            }
            live.result = AgentResult(
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
            live.terminal_event.set()
            return
        if fact.fact_type == "session.failed":
            assert live.handle is not None
            live.active_turn = False
            live.waiting_reason = None
            message = fact.payload.get("message")
            raw_payload = self._payload_dict(fact.payload.get("raw")) or {
                "fact": fact.model_dump(mode="json")
            }
            live.result = AgentResult(
                session_id=live.handle.session_id,
                status=AgentResultStatus.FAILED,
                completed_at=fact.observed_at,
                error=AgentError(
                    code=self._payload_str(fact.payload.get("error_code"))
                    or "agent_session_failed",
                    message=message if isinstance(message, str) else "Agent session failed.",
                    retryable=False,
                    raw=raw_payload,
                ),
                raw=raw_payload,
            )
            live.terminal_event.set()
            return
        if fact.fact_type == "session.discontinuity_observed":
            assert live.handle is not None
            live.active_turn = False
            live.waiting_reason = None
            message = fact.payload.get("message")
            raw_payload = self._payload_dict(fact.payload.get("raw")) or {
                "fact": fact.model_dump(mode="json")
            }
            live.result = AgentResult(
                session_id=live.handle.session_id,
                status=AgentResultStatus.DISCONNECTED,
                completed_at=fact.observed_at,
                error=AgentError(
                    code=self._payload_str(fact.payload.get("error_code"))
                    or "agent_session_disconnected",
                    message=message if isinstance(message, str) else "Agent session disconnected.",
                    retryable=True,
                    raw=raw_payload,
                ),
                raw=raw_payload,
            )
            live.terminal_event.set()

    @staticmethod
    def _payload_dict(value: object) -> dict[str, object]:
        return dict(value) if isinstance(value, dict) else {}

    @staticmethod
    def _payload_str(value: object) -> str | None:
        return value if isinstance(value, str) else None
