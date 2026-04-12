from __future__ import annotations

import asyncio
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol
from uuid import uuid4

from acp.contrib import SessionAccumulator, SessionSnapshot
from acp.schema import SessionNotification, Usage, UsageUpdate

from agent_operator.acp.client import AcpConnection, AcpProtocolError
from agent_operator.domain import (
    AgentError,
    AgentProgress,
    AgentProgressState,
    AgentResult,
    AgentResultStatus,
    AgentSessionHandle,
    AgentUsage,
)
from agent_operator.dtos.requests import AgentRunRequest

JsonObject = dict[str, Any]
McpServerPayload = dict[str, object]


@dataclass
class AcpSessionState:
    handle: AgentSessionHandle
    working_directory: Path
    acp_session_id: str
    connection: AcpConnection | None
    active_prompt: asyncio.Task[JsonObject] | None
    # When the operator process restarts mid-turn, we may lose the in-memory prompt task.
    # In that case we conservatively report RUNNING while draining notifications, and rely on
    # attached-turn timeout recovery (or explicit operator actions) to reconcile.
    assume_running: bool = False
    output_chunks: list[str] = field(default_factory=list)
    notifications: list[JsonObject] = field(default_factory=list)
    stop_reason: str | None = None
    last_error: str | None = None
    pending_input_message: str | None = None
    pending_input_raw: JsonObject | None = None
    last_event_at: datetime | None = None
    session_accumulator: SessionAccumulator = field(default_factory=SessionAccumulator)
    session_snapshot: SessionSnapshot | None = None
    usage: AgentUsage | None = None


@dataclass(frozen=True)
class AcpCollectErrorClassification:
    status: AgentResultStatus
    error: AgentError


class AcpSessionRunnerHooks(Protocol):
    adapter_key: str
    running_message: str
    completed_message: str
    follow_up_running_error: str

    async def configure_new_session(self, connection: AcpConnection, session_id: str) -> None: ...

    async def configure_loaded_session(
        self, connection: AcpConnection, session_id: str
    ) -> None: ...

    async def handle_server_request(
        self,
        session: AcpSessionState,
        payload: JsonObject,
    ) -> None: ...

    def classify_collect_exception(
        self,
        exc: Exception,
        stderr: str,
    ) -> AcpCollectErrorClassification: ...

    def should_reuse_live_connection(self, session: AcpSessionState) -> bool: ...

    def should_keep_connection_after_collect(self, handle: AgentSessionHandle) -> bool: ...

    def unknown_session_error(self, session_id: str) -> str: ...


class AcpSessionRunner:
    def __init__(
        self,
        *,
        adapter_key: str,
        working_directory: Path,
        connection_factory: Callable[[Path, Path], AcpConnection],
        hooks: AcpSessionRunnerHooks,
        mcp_servers: list[McpServerPayload] | None = None,
    ) -> None:
        self._adapter_key = adapter_key
        self._working_directory = working_directory
        self._mcp_servers = list(mcp_servers or [])
        self._connection_factory = connection_factory
        self._hooks = hooks
        self.sessions: dict[str, AcpSessionState] = {}

    async def start(self, request: AgentRunRequest) -> AgentSessionHandle:
        log_path = acp_log_path(
            request.working_directory,
            adapter_key=self._adapter_key,
            session_token=request.session_name,
        )
        connection = self._connection_factory(request.working_directory, log_path)
        await self._initialize_connection(connection)
        session_id = await self._new_session(connection, request.working_directory)
        await self._hooks.configure_new_session(connection, session_id)
        prompt_task = asyncio.create_task(self._prompt(connection, session_id, request.instruction))
        handle = AgentSessionHandle(
            adapter_key=self._adapter_key,
            session_id=session_id,
            session_name=request.session_name,
            one_shot=request.one_shot,
            metadata={
                **request.metadata,
                "working_directory": str(request.working_directory),
                "log_path": str(log_path),
            },
        )
        self.sessions[session_id] = AcpSessionState(
            handle=handle,
            working_directory=request.working_directory,
            acp_session_id=session_id,
            connection=connection,
            active_prompt=prompt_task,
        )
        return handle

    async def send(self, handle: AgentSessionHandle, message: str) -> None:
        session = self.sessions.get(handle.session_id)
        if session is None:
            session = AcpSessionState(
                handle=handle,
                working_directory=Path(
                    str(handle.metadata.get("working_directory", self._working_directory))
                ),
                acp_session_id=handle.session_id,
                connection=None,
                active_prompt=None,
            )
            self.sessions[handle.session_id] = session
        if session.active_prompt is not None and not session.active_prompt.done():
            raise RuntimeError(self._hooks.follow_up_running_error)
        connection = session.connection
        if connection is None or not self._hooks.should_reuse_live_connection(session):
            log_path = acp_log_path(
                session.working_directory,
                adapter_key=self._adapter_key,
                session_token=session.acp_session_id,
            )
            connection = self._connection_factory(session.working_directory, log_path)
            await self._initialize_connection(connection)
            await connection.request(
                "session/load",
                {
                    "sessionId": session.acp_session_id,
                    "cwd": str(session.working_directory.resolve()),
                    "mcpServers": list(self._mcp_servers),
                },
            )
            await self._hooks.configure_loaded_session(connection, session.acp_session_id)
            connection.drain_notifications()
            session.connection = connection
        self._reset_session(session)
        session.active_prompt = asyncio.create_task(
            self._prompt(connection, session.acp_session_id, message)
        )

    async def poll(self, handle: AgentSessionHandle) -> AgentProgress:
        session = self.sessions.get(handle.session_id)
        if session is None:
            session = AcpSessionState(
                handle=handle,
                working_directory=Path(
                    str(handle.metadata.get("working_directory", self._working_directory))
                ),
                acp_session_id=handle.session_id,
                connection=None,
                active_prompt=None,
                assume_running=True,
            )
            self.sessions[handle.session_id] = session
        if session.connection is None:
            await self._reattach_for_poll(session)
        await self._drain_session_notifications(session)
        if session.pending_input_message is not None:
            state = AgentProgressState.WAITING_INPUT
            message = session.pending_input_message
        elif session.active_prompt is not None and not session.active_prompt.done():
            state = AgentProgressState.RUNNING
            message = self._hooks.running_message
        elif session.assume_running and session.last_error is None:
            state = AgentProgressState.RUNNING
            message = f"{self._hooks.running_message} (reattached)"
        elif session.last_error is not None:
            state = AgentProgressState.FAILED
            message = session.last_error
        else:
            state = AgentProgressState.COMPLETED
            message = self._hooks.completed_message
        return AgentProgress(
            session_id=handle.session_id,
            state=state,
            message=message,
            updated_at=datetime.now(UTC),
            partial_output="".join(session.output_chunks)[-2000:],
            usage=session.usage,
            raw=self.progress_raw(session),
        )

    async def collect(self, handle: AgentSessionHandle) -> AgentResult:
        session = self.require_session(handle)
        if session.active_prompt is None:
            raise RuntimeError(f"No active {self._adapter_key} turn to collect.")
        try:
            response = await session.active_prompt
            await self._drain_session_notifications(session)
            stop_reason = response.get("stopReason")
            session.stop_reason = stop_reason if isinstance(stop_reason, str) else None
            session.usage = merge_agent_usage(
                session.usage,
                agent_usage_from_acp(response.get("usage")),
            )
            status = (
                AgentResultStatus.CANCELLED
                if session.stop_reason == "cancelled"
                else AgentResultStatus.SUCCESS
            )
            error = None
        except Exception as exc:
            await self._drain_session_notifications(session)
            session.last_error = str(exc)
            stderr = session.connection.stderr_text() if session.connection is not None else ""
            classification = self._hooks.classify_collect_exception(exc, stderr)
            status = classification.status
            error = classification.error
            response = {}
        transcript = "".join(session.output_chunks)
        raw_notifications = list(session.notifications)
        stderr = session.connection.stderr_text() if session.connection is not None else ""
        session.active_prompt = None
        if not self._hooks.should_keep_connection_after_collect(handle):
            await self.close_session_connection(session)
        return AgentResult(
            session_id=handle.session_id,
            status=status,
            output_text=transcript,
            error=error,
            completed_at=datetime.now(UTC),
            usage=session.usage,
            transcript=transcript,
            raw={
                "acp_session_id": session.acp_session_id,
                "stop_reason": session.stop_reason,
                "response": response,
                "notifications": raw_notifications,
                "stderr": stderr,
                "session_snapshot_available": session.session_snapshot is not None,
            },
        )

    async def cancel(self, handle: AgentSessionHandle) -> None:
        session = self.require_session(handle)
        if session.connection is not None:
            await session.connection.notify(
                "session/cancel",
                {
                    "sessionId": session.acp_session_id,
                },
            )
            await self.close_session_connection(session)
        if session.active_prompt is not None and not session.active_prompt.done():
            session.active_prompt.cancel()

    async def close(self, handle: AgentSessionHandle) -> None:
        session = self.sessions.get(handle.session_id)
        if session is not None:
            await self.close_session_connection(session)

    async def close_session_connection(self, session: AcpSessionState) -> None:
        connection = session.connection
        session.connection = None
        if connection is not None:
            await connection.close()

    def progress_raw(self, session: AcpSessionState) -> JsonObject:
        stderr = session.connection.stderr_text() if session.connection is not None else ""
        return {
            "stop_reason": session.stop_reason,
            "notification_count": len(session.notifications),
            "stderr": stderr,
            "pending_input_message": session.pending_input_message,
            "pending_input_raw": session.pending_input_raw,
            "last_event_at": session.last_event_at.isoformat()
            if session.last_event_at is not None
            else None,
            "session_snapshot_available": session.session_snapshot is not None,
        }

    def require_session(self, handle: AgentSessionHandle) -> AcpSessionState:
        try:
            return self.sessions[handle.session_id]
        except KeyError as exc:
            raise RuntimeError(self._hooks.unknown_session_error(handle.session_id)) from exc

    async def _reattach_for_poll(self, session: AcpSessionState) -> None:
        """
        Best-effort recovery for `poll()` when the runner has no live connection.

        This happens in practice when the operator process restarts while the ACP agent
        continues running. We reload the session and keep draining notifications so
        attached mode can still show progress and timeouts can be detected/recovered.
        """
        log_path = acp_log_path(
            session.working_directory,
            adapter_key=self._adapter_key,
            session_token=session.acp_session_id,
        )
        connection = self._connection_factory(session.working_directory, log_path)
        try:
            await self._initialize_connection(connection)
            await connection.request(
                "session/load",
                {
                    "sessionId": session.acp_session_id,
                    "cwd": str(session.working_directory.resolve()),
                    "mcpServers": list(self._mcp_servers),
                },
            )
            await self._hooks.configure_loaded_session(connection, session.acp_session_id)
            session.connection = connection
        except Exception as exc:
            session.last_error = str(exc)
            await connection.close()

    async def _initialize_connection(self, connection: AcpConnection) -> None:
        await connection.start()
        await connection.request(
            "initialize",
            {
                "protocolVersion": 1,
                "clientCapabilities": {
                    "fs": {
                        "readTextFile": False,
                        "writeTextFile": False,
                    },
                    "terminal": False,
                },
                "clientInfo": {
                    "name": "agent_operator",
                    "title": "agent_operator",
                    "version": "0.1.0",
                },
            },
        )

    async def _new_session(self, connection: AcpConnection, cwd: Path) -> str:
        response = await connection.request(
            "session/new",
            {
                "cwd": str(cwd.resolve()),
                "mcpServers": list(self._mcp_servers),
            },
        )
        session_id = response.get("sessionId")
        if not isinstance(session_id, str) or not session_id:
            raise AcpProtocolError("ACP agent did not return a sessionId.")
        return session_id

    async def _prompt(
        self,
        connection: AcpConnection,
        session_id: str,
        instruction: str,
    ) -> JsonObject:
        return await connection.request(
            "session/prompt",
            {
                "sessionId": session_id,
                "prompt": [
                    {
                        "type": "text",
                        "text": instruction,
                    }
                ],
            },
        )

    async def _drain_session_notifications(self, session: AcpSessionState) -> None:
        if session.connection is None:
            return
        for notification in session.connection.drain_notifications():
            session.notifications.append(notification)
            session.last_event_at = datetime.now(UTC)
            await self._hooks.handle_server_request(session, notification)
            params = notification.get("params")
            if not isinstance(params, dict):
                continue
            if params.get("sessionId") != session.acp_session_id:
                continue
            update = params.get("update")
            if not isinstance(update, dict):
                continue
            self._apply_structured_session_update(session, params)
            if update.get("sessionUpdate") not in {
                "agent_message_chunk",
                "agent_message",
                "user_message_chunk",
            }:
                continue
            text = extract_text(update.get("content"))
            if text:
                session.output_chunks.append(text)

    def _reset_session(self, session: AcpSessionState) -> None:
        session.output_chunks.clear()
        session.notifications.clear()
        session.stop_reason = None
        session.last_error = None
        session.pending_input_message = None
        session.pending_input_raw = None

    def _apply_structured_session_update(
        self,
        session: AcpSessionState,
        params: JsonObject,
    ) -> None:
        try:
            notification = SessionNotification.model_validate(params)
        except Exception:
            update = params.get("update")
            if isinstance(update, dict) and update.get("sessionUpdate") == "usage_update":
                session.usage = merge_agent_usage(session.usage, agent_usage_from_acp(update))
            return
        with suppress(Exception):
            session.session_snapshot = session.session_accumulator.apply(notification)
        session.usage = merge_agent_usage(session.usage, agent_usage_from_acp(notification.update))


def acp_log_path(
    working_directory: Path,
    *,
    adapter_key: str,
    session_token: str | None = None,
) -> Path:
    token = session_token or uuid4().hex
    safe_token = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in token)
    return working_directory / ".operator" / "acp" / adapter_key / f"{safe_token}.jsonl"


def extract_text(content: object) -> str:
    if isinstance(content, dict):
        content_type = content.get("type")
        if content_type == "text":
            text = content.get("text")
            return text if isinstance(text, str) else ""
        if "content" in content:
            return extract_text(content["content"])
        return ""
    if isinstance(content, list):
        parts = [extract_text(item) for item in content]
        return "".join(part for part in parts if part)
    return ""


def agent_usage_from_acp(payload: object) -> AgentUsage | None:
    if isinstance(payload, Usage):
        metadata = {
            "cached_read_tokens": payload.cached_read_tokens,
            "cached_write_tokens": payload.cached_write_tokens,
        }
        if payload.thought_tokens is not None:
            metadata["thought_tokens"] = payload.thought_tokens
        return AgentUsage(
            input_tokens=payload.input_tokens,
            output_tokens=payload.output_tokens,
            total_tokens=payload.total_tokens,
            metadata={k: v for k, v in metadata.items() if v is not None},
        )
    if isinstance(payload, UsageUpdate):
        metadata: dict[str, Any] = {}
        if payload.field_meta is not None:
            metadata["acp_meta"] = payload.field_meta
        return AgentUsage(
            context_window_size=payload.size,
            context_tokens_used=payload.used,
            cost_amount=payload.cost.amount if payload.cost is not None else None,
            cost_currency=payload.cost.currency if payload.cost is not None else None,
            metadata=metadata,
        )
    if isinstance(payload, dict):
        if payload.get("sessionUpdate") == "usage_update":
            try:
                return agent_usage_from_acp(UsageUpdate.model_validate(payload))
            except Exception:
                return None
        if any(
            key in payload
            for key in (
                "inputTokens",
                "outputTokens",
                "totalTokens",
                "input_tokens",
                "output_tokens",
                "total_tokens",
            )
        ):
            metadata: dict[str, Any] = {}
            thought = payload.get("thoughtTokens", payload.get("thought_tokens"))
            cached_read = payload.get("cachedReadTokens", payload.get("cached_read_tokens"))
            cached_write = payload.get("cachedWriteTokens", payload.get("cached_write_tokens"))
            if thought is not None:
                metadata["thought_tokens"] = thought
            if cached_read is not None:
                metadata["cached_read_tokens"] = cached_read
            if cached_write is not None:
                metadata["cached_write_tokens"] = cached_write
            return AgentUsage(
                input_tokens=_coerce_int(payload.get("inputTokens", payload.get("input_tokens"))),
                output_tokens=_coerce_int(
                    payload.get("outputTokens", payload.get("output_tokens"))
                ),
                total_tokens=_coerce_int(payload.get("totalTokens", payload.get("total_tokens"))),
                metadata=metadata,
            )
    return None


def merge_agent_usage(
    existing: AgentUsage | None,
    incoming: AgentUsage | None,
) -> AgentUsage | None:
    if existing is None:
        return incoming
    if incoming is None:
        return existing
    metadata = dict(existing.metadata)
    metadata.update(incoming.metadata)
    return existing.model_copy(
        update={
            "input_tokens": (
                incoming.input_tokens
                if incoming.input_tokens is not None
                else existing.input_tokens
            ),
            "output_tokens": (
                incoming.output_tokens
                if incoming.output_tokens is not None
                else existing.output_tokens
            ),
            "total_tokens": (
                incoming.total_tokens
                if incoming.total_tokens is not None
                else existing.total_tokens
            ),
            "context_window_size": (
                incoming.context_window_size
                if incoming.context_window_size is not None
                else existing.context_window_size
            ),
            "context_tokens_used": (
                incoming.context_tokens_used
                if incoming.context_tokens_used is not None
                else existing.context_tokens_used
            ),
            "cost_amount": (
                incoming.cost_amount
                if incoming.cost_amount is not None
                else existing.cost_amount
            ),
            "cost_currency": (
                incoming.cost_currency
                if incoming.cost_currency is not None
                else existing.cost_currency
            ),
            "metadata": metadata,
        }
    )


def _coerce_int(value: object) -> int | None:
    return value if isinstance(value, int) else None
