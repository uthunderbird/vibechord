from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Protocol, Self

from agent_operator.domain import AdapterCommand, AdapterFactDraft


class AdapterRuntime(Protocol):
    """Transport-focused async runtime contract for adapter-owned resources.

    Examples:
        Implementations expose explicit async lifecycle, command ingress, live adapter-fact event
        egress, and explicit cancellation.
    """

    async def __aenter__(self) -> Self: ...

    async def __aexit__(self, exc_type, exc, tb) -> None: ...

    async def send(self, command: AdapterCommand) -> None: ...

    def events(self) -> AsyncIterator[AdapterFactDraft]: ...

    async def cancel(self, reason: str | None = None) -> None: ...
