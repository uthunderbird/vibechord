"""ProcessManagerContext — ephemeral per-drive-call state (ADR 0196).

Created once at the start of DriveService.drive() via build_pm_context() and
discarded when drive() returns. Never persisted or serialized.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from agent_operator.domain.agent import AgentDescriptor
from agent_operator.domain.policy import PolicyCoverage
from agent_operator.domain.read_model import DecisionRecord


@dataclass
class RuntimeSessionContext:
    """Ephemeral runtime state for one session within a drive call."""

    session_id: str
    is_attached: bool = False
    is_background_running: bool = False


@dataclass
class ProcessManagerContext:
    """Ephemeral coordination state for one DriveService.drive() call.

    Fields that were previously duplicated in OperationState (policy caches,
    per-call dedup sets) live here instead of the aggregate (ADR 0196).
    """

    policy_context: PolicyCoverage | None = None
    available_agents: list[AgentDescriptor] = field(default_factory=list)
    recent_decisions: list[DecisionRecord] = field(default_factory=list)
    session_contexts: dict[str, RuntimeSessionContext] = field(default_factory=dict)
    pending_replan_command_ids: list[str] = field(default_factory=list)
    orphan_check_completed: bool = False
    draining: bool = False

    def request_drain(self) -> None:
        """Mark this drive-call context as draining.

        The owning operator service calls this during shutdown so the active
        drive loop can exit after finishing its current cycle.
        """
        self.draining = True


async def build_pm_context(
    agg: object,
    *,
    policy_store: object,
    adapter_registry: object,
) -> ProcessManagerContext:
    """Reconstruct ProcessManagerContext at the start of each drive() call.

    Queries PolicyStore and AgentSessionManager to populate ephemeral fields.
    The aggregate is read-only here — no mutations.
    """
    from agent_operator.domain.aggregate import OperationAggregate

    assert isinstance(agg, OperationAggregate)
    del policy_store
    if not hasattr(adapter_registry, "has") or not hasattr(adapter_registry, "describe"):
        raise TypeError("adapter_registry must provide has() and describe() for v2 context build.")

    allowed = agg.allowed_agents or list(getattr(adapter_registry, "keys", lambda: [])())
    available: list[AgentDescriptor] = []
    for adapter_key in allowed:
        if not adapter_registry.has(adapter_key):
            continue
        descriptor = await adapter_registry.describe(adapter_key)
        available.append(descriptor)

    return ProcessManagerContext(
        available_agents=available,
    )
