from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from agent_operator.application.operation_agenda_queries import OperationAgendaQueryService
from agent_operator.application.operation_projections import OperationProjectionService
from agent_operator.domain import PolicyStatus, ProjectProfile, ResolvedProjectRunConfig
from agent_operator.protocols import PolicyStore


@dataclass(slots=True)
class OperationProjectDashboardQueryService:
    agenda_queries: OperationAgendaQueryService
    projection_service: OperationProjectionService
    policy_store: PolicyStore

    async def load_payload(
        self,
        *,
        profile: ProjectProfile,
        resolved: ResolvedProjectRunConfig,
        profile_path: Path,
    ) -> dict[str, object]:
        active_policies = await self.policy_store.list(
            project_scope=f"profile:{profile.name}",
            status=PolicyStatus.ACTIVE,
        )
        fleet_snapshot = await self.agenda_queries.load_snapshot(
            project=profile.name,
            include_recent=True,
        )
        fleet_payload = self.projection_service.build_fleet_payload(
            fleet_snapshot,
            project=profile.name,
        )
        return self.projection_service.build_project_dashboard_payload(
            profile=profile,
            resolved=resolved.model_dump(mode="json"),
            profile_path=profile_path,
            fleet=fleet_payload,
            active_policies=active_policies,
        )
