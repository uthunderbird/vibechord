from __future__ import annotations

from agent_operator.application.attached_session_registry import (
    AttachedRuntimeBinding,
    AttachedSessionRuntimeRegistry,
)
from agent_operator.domain import (
    AgentDescriptor,
    AgentProgress,
    AgentResult,
    AgentSessionHandle,
)
from agent_operator.dtos.requests import AgentRunRequest
from agent_operator.protocols import AgentSessionManager


class RegistryBackedAgentSessionManager(AgentSessionManager):
    """Thin app-facing manager adapter over the current attached-session registry."""

    def __init__(self, registry: AttachedSessionRuntimeRegistry) -> None:
        self._registry = registry

    @classmethod
    def from_bindings(
        cls,
        bindings: dict[str, AttachedRuntimeBinding],
    ) -> RegistryBackedAgentSessionManager:
        return cls(AttachedSessionRuntimeRegistry(bindings))

    def keys(self) -> list[str]:
        return self._registry.keys()

    def has(self, adapter_key: str) -> bool:
        return self._registry.has(adapter_key)

    async def describe(self, adapter_key: str) -> AgentDescriptor:
        return await self._registry.describe(adapter_key)

    async def start(
        self,
        adapter_key: str,
        request: AgentRunRequest,
    ) -> AgentSessionHandle:
        return await self._registry.start(adapter_key, request)

    async def send(self, handle: AgentSessionHandle, message: str) -> None:
        await self._registry.send(handle, message)

    async def poll(self, handle: AgentSessionHandle) -> AgentProgress:
        return await self._registry.poll(handle)

    async def collect(self, handle: AgentSessionHandle) -> AgentResult:
        return await self._registry.collect(handle)

    async def cancel(self, handle: AgentSessionHandle) -> None:
        await self._registry.cancel(handle)

    async def close(self, handle: AgentSessionHandle) -> None:
        await self._registry.close(handle)
