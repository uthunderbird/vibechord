from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from agent_operator.acp.client import AcpConnection
from agent_operator.domain import (
    AdapterCommand,
    AdapterCommandType,
    AdapterFactDraft,
    AgentSessionCommand,
    AgentSessionCommandType,
    TechnicalFactDraft,
)
from agent_operator.protocols import AdapterRuntime

McpServerPayload = dict[str, object]
SessionConfigurator = callable


class AcpAgentSessionRuntime:
    """ACP-backed session runtime with one-live-session ownership.

    This runtime owns one logical live ACP session at a time and converts adapter facts into
    session-scoped technical facts.
    """

    def __init__(
        self,
        *,
        adapter_runtime: AdapterRuntime,
        working_directory: Path,
        mcp_servers: list[McpServerPayload] | None = None,
        configure_new_session: Any | None = None,
        configure_loaded_session: Any | None = None,
    ) -> None:
        self._adapter_runtime = adapter_runtime
        self._working_directory = working_directory
        self._mcp_servers = list(mcp_servers or [])
        self._configure_new_session = configure_new_session
        self._configure_loaded_session = configure_loaded_session
        self._live_session_id: str | None = None
        self._events_claimed = False
        self._event_queue: asyncio.Queue[TechnicalFactDraft | None] = asyncio.Queue()
        self._adapter_events_task: asyncio.Task[None] | None = None
        self._active_prompt_task: asyncio.Task[None] | None = None
        self._closed = False

    async def __aenter__(self) -> AcpAgentSessionRuntime:
        await self._adapter_runtime.__aenter__()
        self._closed = False
        self._adapter_events_task = asyncio.create_task(self._forward_adapter_events())
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.cancel(reason="context_exit")
        await self._adapter_runtime.__aexit__(exc_type, exc, tb)

    async def send(self, command: AgentSessionCommand) -> None:
        """Apply one session-scoped command with one-live-session enforcement."""
        if command.command_type == AgentSessionCommandType.START_SESSION:
            if self._live_session_id is not None:
                raise RuntimeError("AgentSessionRuntime already has a live session.")
            self._live_session_id = await self._start_new_session(command.instruction or "")
            await self._emit_fact(
                TechnicalFactDraft(
                    fact_type="session.started",
                    payload={
                        "session_id": self._live_session_id,
                        "working_directory": str(self._working_directory),
                    },
                    observed_at=datetime.now(UTC),
                    session_id=self._live_session_id,
                )
            )
            self._start_prompt_task(self._live_session_id, command.instruction or "")
            return
        if command.command_type == AgentSessionCommandType.SEND_MESSAGE:
            if self._live_session_id is None:
                if not isinstance(command.session_id, str) or not command.session_id:
                    raise RuntimeError("No live session is available for follow-up message.")
                await self._request(
                    "session/load",
                    {
                        "sessionId": command.session_id,
                        "cwd": str(self._working_directory.resolve()),
                        "mcpServers": list(self._mcp_servers),
                    },
                )
                await self._configure_loaded(command.session_id)
                self._live_session_id = command.session_id
            if self._active_prompt_task is not None and not self._active_prompt_task.done():
                raise RuntimeError("No live session is available for follow-up message.")
            self._start_prompt_task(self._live_session_id, command.instruction or "")
            return
        if command.command_type == AgentSessionCommandType.REPLACE_SESSION:
            previous_session_id = self._live_session_id
            self._live_session_id = await self._start_new_session(command.instruction or "")
            await self._emit_fact(
                TechnicalFactDraft(
                    fact_type="session.started",
                    payload={
                        "session_id": self._live_session_id,
                        "working_directory": str(self._working_directory),
                    },
                    observed_at=datetime.now(UTC),
                    session_id=self._live_session_id,
                )
            )
            if previous_session_id is not None:
                await self._emit_fact(
                    TechnicalFactDraft(
                    fact_type="session.discontinuity_observed",
                    payload={
                        "previous_session_id": previous_session_id,
                        "new_session_id": self._live_session_id,
                        "reason": "intentional_replacement",
                    },
                    observed_at=datetime.now(UTC),
                    session_id=self._live_session_id,
                )
                )
            self._start_prompt_task(self._live_session_id, command.instruction or "")
            return
        raise ValueError(f"Unsupported agent session command type: {command.command_type}.")

    def events(self) -> AsyncIterator[TechnicalFactDraft]:
        """Yield session-scoped technical facts."""
        if self._events_claimed:
            raise RuntimeError("AgentSessionRuntime.events() is single-consumer.")
        self._events_claimed = True
        return self._event_stream()

    async def cancel(self, reason: str | None = None) -> None:
        """Cancel the current live session, if any."""
        if self._closed:
            return
        self._closed = True
        if self._live_session_id is not None:
            with suppress(Exception):
                await self._adapter_runtime.send(
                    AdapterCommand(
                        command_type=AdapterCommandType.NOTIFY,
                        method="session/cancel",
                        params={"sessionId": self._live_session_id, "reason": reason},
                    )
                )
            if self._active_prompt_task is not None and not self._active_prompt_task.done():
                self._active_prompt_task.cancel()
            await self._emit_fact(
                TechnicalFactDraft(
                    fact_type="session.cancelled",
                    payload={"reason": reason or "cancelled"},
                    observed_at=datetime.now(UTC),
                    session_id=self._live_session_id,
                )
            )
        self._live_session_id = None
        await self._adapter_runtime.cancel(reason=reason)
        task = self._adapter_events_task
        if task is not None:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
        await self._event_queue.put(None)

    async def _start_new_session(self, instruction: str) -> str:
        response = await self._request(
            "session/new",
            {
                "cwd": str(self._working_directory.resolve()),
                "mcpServers": list(self._mcp_servers),
            },
        )
        session_id = response.get("sessionId")
        if not isinstance(session_id, str) or not session_id:
            session_id = self._extract_latest_session_id()
        if session_id is None:
            raise RuntimeError("Adapter runtime did not expose a new session identifier.")
        await self._configure_new(session_id)
        return session_id

    async def _configure_new(self, session_id: str) -> None:
        if self._configure_new_session is None:
            return
        await self._configure_new_session(self._connection(), session_id)

    async def _configure_loaded(self, session_id: str) -> None:
        if self._configure_loaded_session is None:
            return
        await self._configure_loaded_session(self._connection(), session_id)

    def _connection(self) -> AcpConnection:
        connection = getattr(self._adapter_runtime, "_connection", None)
        if connection is None:
            return connection
        return connection

    def _start_prompt_task(self, session_id: str, instruction: str) -> None:
        self._active_prompt_task = asyncio.create_task(self._run_prompt(session_id, instruction))

    async def _run_prompt(self, session_id: str, instruction: str) -> None:
        try:
            response = await self._request(
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
            stop_reason = response.get("stopReason")
            fact_type = "session.cancelled" if stop_reason == "cancelled" else "session.completed"
            await self._emit_fact(
                TechnicalFactDraft(
                    fact_type=fact_type,
                    payload={"stop_reason": stop_reason} if isinstance(stop_reason, str) else {},
                    observed_at=datetime.now(UTC),
                    session_id=session_id,
                )
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            await self._emit_fact(
                TechnicalFactDraft(
                    fact_type="session.failed",
                    payload={"message": str(exc)},
                    observed_at=datetime.now(UTC),
                    session_id=session_id,
                )
            )
        finally:
            self._active_prompt_task = None

    def _extract_latest_session_id(self) -> str | None:
        requests = getattr(self._adapter_runtime, "_connection", None)
        if requests is None:
            return None
        history = getattr(requests, "requests", [])
        for method, _payload in reversed(history):
            if method == "session/new":
                next_session_id = getattr(requests, "next_session_id", None)
                if isinstance(next_session_id, str) and next_session_id:
                    return next_session_id
        return getattr(requests, "next_session_id", None)

    async def _event_stream(self) -> AsyncIterator[TechnicalFactDraft]:
        while True:
            fact = await self._event_queue.get()
            if fact is None:
                return
            yield fact

    async def _forward_adapter_events(self) -> None:
        try:
            async for fact in self._adapter_runtime.events():
                translated = self._translate_adapter_fact(fact)
                if translated is not None:
                    await self._emit_fact(translated)
        except asyncio.CancelledError:
            raise
        finally:
            if not self._closed:
                await self._event_queue.put(None)

    def _translate_adapter_fact(
        self,
        fact: AdapterFactDraft,
    ) -> TechnicalFactDraft | None:
        if fact.fact_type != "acp.notification.received":
            return None
        method = fact.payload.get("method")
        params = fact.payload.get("params")
        if not isinstance(method, str) or not isinstance(params, dict):
            return None
        if method != "session/update":
            return None
        update = params.get("update")
        if not isinstance(update, dict):
            return None
        if update.get("sessionUpdate") == "agent_message_chunk":
            content = update.get("content")
            text = self._extract_text(content)
            return TechnicalFactDraft(
                fact_type="session.output_chunk_observed",
                payload={"text": text},
                observed_at=datetime.now(UTC),
                source_fact_ids=[],
                session_id=fact.session_id,
            )
        if update.get("sessionUpdate") in {"waiting_input", "waiting_for_input", "input_required"}:
            message = update.get("message")
            return TechnicalFactDraft(
                fact_type="session.waiting_input_observed",
                payload={
                    "message": (
                        message
                        if isinstance(message, str)
                        else "Agent is waiting for input."
                    ),
                    "update": update,
                },
                observed_at=datetime.now(UTC),
                source_fact_ids=[],
                session_id=fact.session_id,
            )
        return TechnicalFactDraft(
            fact_type="session.notification_observed",
            payload={"method": method, "update": update},
            observed_at=datetime.now(UTC),
            source_fact_ids=[],
            session_id=fact.session_id,
        )

    def _extract_text(self, content: object) -> str:
        if isinstance(content, dict):
            if content.get("type") == "text":
                text = content.get("text")
                return text if isinstance(text, str) else ""
            if "content" in content:
                return self._extract_text(content["content"])
            return ""
        if isinstance(content, list):
            return "".join(self._extract_text(item) for item in content)
        return ""

    async def _emit_fact(self, fact: TechnicalFactDraft) -> None:
        await self._event_queue.put(fact)

    async def _request(self, method: str, params: dict[str, object]) -> dict[str, Any]:
        connection = getattr(self._adapter_runtime, "_connection", None)
        if connection is None:
            raise RuntimeError("ACP session runtime requires a concrete adapter connection.")
        response = await connection.request(method, params)
        if not isinstance(response, dict):
            raise RuntimeError(f"ACP request {method!r} did not return a JSON object response.")
        return response
