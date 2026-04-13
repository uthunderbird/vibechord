from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Protocol, Self

from agent_operator.domain import AgentSessionCommand, TechnicalFactDraft


class AgentSessionRuntime(Protocol):
    """Session-focused async runtime contract with one-live-session ownership."""

    async def __aenter__(self) -> Self: ...

    async def __aexit__(self, exc_type, exc, tb) -> None: ...

    async def send(self, command: AgentSessionCommand) -> None: ...

    def events(self) -> AsyncIterator[TechnicalFactDraft]: ...

    async def close(self) -> None: ...

    async def cancel(self, reason: str | None = None) -> None: ...
