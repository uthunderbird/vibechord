from __future__ import annotations

from dataclasses import dataclass

from agent_operator.application.operation_agenda_queries import OperationAgendaQueryService
from agent_operator.application.operation_projections import OperationProjectionService
from agent_operator.runtime import AgendaSnapshot


@dataclass(slots=True)
class OperationFleetWorkbenchQueryService:
    agenda_queries: OperationAgendaQueryService
    projection_service: OperationProjectionService

    async def load_payload(self, *, project: str | None, include_recent: bool) -> dict[str, object]:
        snapshot: AgendaSnapshot = await self.agenda_queries.load_snapshot(
            project=project,
            include_recent=include_recent,
        )
        return self.projection_service.build_fleet_workbench_payload(
            snapshot,
            project=project,
        )
