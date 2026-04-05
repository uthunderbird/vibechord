from __future__ import annotations

from agent_operator.domain import (
    InvolvementLevel,
    OperationCommand,
    OperationState,
    PolicyApplicability,
    PolicyStatus,
    RunMode,
    assess_policy_coverage,
    policy_match_reasons,
)
from agent_operator.protocols import PolicyStore


class OperationPolicyContextCoordinator:
    """Own policy-scope resolution and applicability parsing for one operation."""

    def __init__(self, *, policy_store: PolicyStore | None) -> None:
        self._policy_store = policy_store

    @property
    def has_policy_store(self) -> bool:
        return self._policy_store is not None

    async def refresh_policy_context(self, state: OperationState) -> None:
        project_scope = self.resolve_policy_scope(state)
        if self._policy_store is None:
            state.active_policies = []
            state.policy_coverage = assess_policy_coverage(
                project_scope=project_scope,
                scoped_policies=[],
                active_policies=[],
            )
            return
        if project_scope is None:
            state.active_policies = []
            state.policy_coverage = assess_policy_coverage(
                project_scope=None,
                scoped_policies=[],
                active_policies=[],
            )
            return
        entries = await self._policy_store.list(
            project_scope=project_scope,
            status=PolicyStatus.ACTIVE,
        )
        state.active_policies = [entry for entry in entries if policy_match_reasons(entry, state)]
        state.policy_coverage = assess_policy_coverage(
            project_scope=project_scope,
            scoped_policies=entries,
            active_policies=state.active_policies,
        )

    def resolve_policy_scope(self, state: OperationState) -> str | None:
        raw_scope = state.goal.metadata.get("policy_scope")
        if isinstance(raw_scope, str) and raw_scope.strip():
            return raw_scope.strip()
        profile_name = state.goal.metadata.get("project_profile_name")
        if isinstance(profile_name, str) and profile_name.strip():
            return f"profile:{profile_name.strip()}"
        resolved_profile = state.goal.metadata.get("resolved_project_profile")
        if isinstance(resolved_profile, dict):
            cwd = resolved_profile.get("cwd")
            if isinstance(cwd, str) and cwd.strip():
                return f"cwd:{cwd.strip()}"
        return None

    def build_policy_applicability(self, command: OperationCommand) -> PolicyApplicability:
        return PolicyApplicability(
            objective_keywords=self.normalize_policy_strings(command.payload.get("objective_keywords")),
            task_keywords=self.normalize_policy_strings(command.payload.get("task_keywords")),
            agent_keys=self.normalize_policy_strings(command.payload.get("agent_keys")),
            run_modes=self.parse_policy_run_modes(command.payload.get("run_modes")),
            involvement_levels=self.parse_policy_involvement_levels(
                command.payload.get("involvement_levels")
            ),
        )

    def normalize_policy_strings(self, raw_value: object) -> list[str]:
        if not isinstance(raw_value, list):
            return []
        normalized: list[str] = []
        for item in raw_value:
            if not isinstance(item, str):
                continue
            text = item.strip()
            if text and text not in normalized:
                normalized.append(text)
        return normalized

    def parse_policy_run_modes(self, raw_value: object) -> list[RunMode]:
        modes: list[RunMode] = []
        for item in self.normalize_policy_strings(raw_value):
            try:
                mode = RunMode(item)
            except ValueError:
                continue
            if mode not in modes:
                modes.append(mode)
        return modes

    def parse_policy_involvement_levels(self, raw_value: object) -> list[InvolvementLevel]:
        levels: list[InvolvementLevel] = []
        for item in self.normalize_policy_strings(raw_value):
            try:
                level = InvolvementLevel(item)
            except ValueError:
                continue
            if level not in levels:
                levels.append(level)
        return levels
