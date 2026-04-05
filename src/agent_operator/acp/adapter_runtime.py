from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from agent_operator.acp.client import AcpConnection
from agent_operator.domain import AdapterCommand, AdapterCommandType, AdapterFactDraft


class AcpAdapterRuntime:
    """ACP-backed transport runtime implementing the `AdapterRuntime` contract.

    This runtime owns the ACP connection lifecycle, transport command ingress, and live adapter-fact
    observation of drained ACP notifications.

    Examples:
        >>> runtime = AcpAdapterRuntime(  # doctest: +SKIP
        ...     adapter_key="codex_acp",
        ...     working_directory=Path.cwd(),
        ...     connection=None,
        ... )
    """

    def __init__(
        self,
        *,
        adapter_key: str,
        working_directory: Path,
        connection: AcpConnection,
        poll_interval_seconds: float = 0.05,
    ) -> None:
        self._adapter_key = adapter_key
        self._working_directory = working_directory
        self._connection = connection
        self._poll_interval_seconds = poll_interval_seconds
        self._closed = False
        self._events_claimed = False

    async def __aenter__(self) -> AcpAdapterRuntime:
        await self._connection.start()
        self._closed = False
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.cancel(reason="context_exit")

    async def send(self, command: AdapterCommand) -> None:
        """Send one transport-scoped command through the ACP connection."""
        if command.command_type == AdapterCommandType.REQUEST:
            await self._connection.request(command.method or "", command.params)
            return
        if command.command_type == AdapterCommandType.NOTIFY:
            await self._connection.notify(command.method or "", command.params)
            return
        if command.command_type == AdapterCommandType.RESPOND:
            await self._connection.respond(
                command.request_id or 0,
                result=command.result,
                error=command.error,
            )
            return
        raise ValueError(f"Unsupported adapter command type: {command.command_type}.")

    def events(self) -> AsyncIterator[AdapterFactDraft]:
        """Yield live adapter facts from drained ACP notifications."""
        if self._events_claimed:
            raise RuntimeError("AdapterRuntime.events() is single-consumer.")
        self._events_claimed = True
        return self._event_stream()

    async def cancel(self, reason: str | None = None) -> None:
        """Close transport resources and terminate live event iteration."""
        if self._closed:
            return
        self._closed = True
        await self._connection.close()

    async def _event_stream(self) -> AsyncIterator[AdapterFactDraft]:
        while not self._closed:
            emitted = False
            for payload in self._connection.drain_notifications():
                emitted = True
                yield AdapterFactDraft(
                    fact_type="acp.notification.received",
                    payload=self._normalize_payload(payload),
                    observed_at=datetime.now(UTC),
                    adapter_key=self._adapter_key,
                    session_id=self._extract_session_id(payload),
                )
            if self._closed:
                return
            if not emitted:
                await asyncio.sleep(self._poll_interval_seconds)

    def _normalize_payload(self, payload: dict[str, Any]) -> dict[str, object]:
        return {
            "method": payload.get("method"),
            "params": payload.get("params", {}),
            "cwd": str(self._working_directory),
        }

    def _extract_session_id(self, payload: dict[str, Any]) -> str | None:
        params = payload.get("params")
        if not isinstance(params, dict):
            return None
        raw_session_id = params.get("sessionId")
        if isinstance(raw_session_id, str) and raw_session_id:
            return raw_session_id
        return None
