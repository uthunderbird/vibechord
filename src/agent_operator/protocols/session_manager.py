from __future__ import annotations

from typing import Protocol

from agent_operator.domain import (
    AgentDescriptor,
    AgentProgress,
    AgentResult,
    AgentSessionHandle,
)
from agent_operator.dtos.requests import AgentRunRequest


class AgentSessionManager(Protocol):
    """Application-facing owner of live agent-session orchestration."""

    def keys(self) -> list[str]: ...

    def has(self, adapter_key: str) -> bool: ...

    async def describe(self, adapter_key: str) -> AgentDescriptor: ...

    async def start(
        self,
        adapter_key: str,
        request: AgentRunRequest,
    ) -> AgentSessionHandle: ...

    async def send(self, handle: AgentSessionHandle, message: str) -> None: ...

    async def poll(self, handle: AgentSessionHandle) -> AgentProgress: ...

    async def collect(self, handle: AgentSessionHandle) -> AgentResult: ...

    async def cancel(self, handle: AgentSessionHandle) -> None: ...

    async def close(self, handle: AgentSessionHandle) -> None: ...
