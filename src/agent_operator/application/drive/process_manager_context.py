"""ProcessManagerContext — ephemeral per-drive-call state (ADR 0196).

Created once at the start of DriveService.drive() via build_pm_context() and
discarded when drive() returns. Never persisted or serialized.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from agent_operator.domain.agent import AgentDescriptor
from agent_operator.domain.aggregate import OperationAggregate
from agent_operator.domain.enums import PolicyStatus
from agent_operator.domain.operation import OperationState
from agent_operator.domain.policy import PolicyCoverage
from agent_operator.domain.policy_matching import assess_policy_coverage, policy_match_reasons
from agent_operator.domain.read_model import DecisionRecord
from agent_operator.domain.traceability import AgentTurnBrief
from agent_operator.protocols.runtime import PolicyStore


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
    recent_agent_outputs: list[AgentTurnBrief] = field(default_factory=list)
    session_contexts: dict[str, RuntimeSessionContext] = field(default_factory=dict)
    pending_replan_command_ids: list[str] = field(default_factory=list)
    orphan_check_completed: bool = False
    draining: bool = False
    canonical_replay_advanced: bool = False

    def request_drain(self) -> None:
        """Mark this drive-call context as draining.

        The owning operator service calls this during shutdown so the active
        drive loop can exit after finishing its current cycle.
        """
        self.draining = True


async def build_pm_context(
    agg: OperationAggregate,
    *,
    policy_store: PolicyStore | None,
    adapter_registry: object,
) -> ProcessManagerContext:
    """Reconstruct ProcessManagerContext at the start of each drive() call.

    Queries PolicyStore and AgentSessionManager to populate ephemeral fields.
    The aggregate is read-only here — no mutations.
    """
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
        policy_context=await _build_policy_context(agg, policy_store=policy_store),
    )


def _resolve_policy_scope(agg: OperationAggregate) -> str | None:
    """Derive the project policy scope from aggregate goal metadata."""
    metadata_sources: list[dict[str, object]] = []
    if agg.objective is not None:
        metadata_sources.append(agg.objective.metadata)
    metadata_sources.append(agg.goal.metadata)

    raw_scope = None
    for metadata in metadata_sources:
        candidate = metadata.get("policy_scope")
        if isinstance(candidate, str) and candidate.strip():
            raw_scope = candidate.strip()
            break
    if isinstance(raw_scope, str) and raw_scope.strip():
        return raw_scope.strip()
    for metadata in metadata_sources:
        profile_name = metadata.get("project_profile_name")
        if isinstance(profile_name, str) and profile_name.strip():
            return f"profile:{profile_name.strip()}"
        resolved_profile = metadata.get("resolved_project_profile")
        if isinstance(resolved_profile, dict):
            cwd = resolved_profile.get("cwd")
            if isinstance(cwd, str) and cwd.strip():
                return f"cwd:{cwd.strip()}"
    return None


def _policy_match_state(agg: OperationAggregate) -> OperationState:
    """Build a temporary OperationState for policy applicability matching."""
    return OperationState(
        operation_id=agg.operation_id,
        goal=agg.goal,
        policy=agg.policy,
        execution_budget=agg.execution_budget,
        runtime_hints=agg.runtime_hints,
        execution_profile_overrides=dict(agg.execution_profile_overrides),
        status=agg.status,
        objective=agg.objective,
        tasks=list(agg.tasks),
        features=list(agg.features),
        sessions=list(agg.sessions),
        executions=list(agg.executions),
        artifacts=list(agg.artifacts),
        memory_entries=list(agg.memory_entries),
        current_focus=agg.current_focus,
        attention_requests=list(agg.attention_requests),
        active_policies=[],
        policy_coverage=PolicyCoverage(),
        involvement_level=agg.policy.involvement_level,
        scheduler_state=agg.scheduler_state,
        operator_messages=list(agg.operator_messages),
    )


async def _build_policy_context(
    agg: OperationAggregate,
    *,
    policy_store: PolicyStore | None,
) -> PolicyCoverage:
    """Rebuild the per-drive-call policy coverage snapshot for the aggregate."""
    project_scope = _resolve_policy_scope(agg)
    if policy_store is None:
        return assess_policy_coverage(
            project_scope=project_scope,
            scoped_policies=[],
            active_policies=[],
        )
    if project_scope is None:
        return assess_policy_coverage(
            project_scope=None,
            scoped_policies=[],
            active_policies=[],
        )
    scoped_policies = await policy_store.list(
        project_scope=project_scope,
        status=PolicyStatus.ACTIVE,
    )
    match_state = _policy_match_state(agg)
    active_policies = [
        entry for entry in scoped_policies if policy_match_reasons(entry, match_state)
    ]
    return assess_policy_coverage(
        project_scope=project_scope,
        scoped_policies=scoped_policies,
        active_policies=active_policies,
    )
