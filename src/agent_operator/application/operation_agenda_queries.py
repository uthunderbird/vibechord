from __future__ import annotations

from dataclasses import dataclass

from agent_operator.application.operation_delivery_commands import OperationDeliveryCommandService
from agent_operator.protocols import OperationStore
from agent_operator.runtime import (
    AgendaSnapshot,
    agenda_matches_project,
    build_agenda_item,
    build_agenda_snapshot,
)


@dataclass(slots=True)
class OperationAgendaQueryService:
    store: OperationStore
    status_service: OperationDeliveryCommandService

    async def load_snapshot(
        self,
        *,
        project: str | None,
        include_recent: bool,
    ) -> AgendaSnapshot:
        items = []
        for summary in await self.store.list_operations():
            try:
                operation, _, brief_bundle, runtime_alert = await self.status_service.build_status_payload(
                    summary.operation_id
                )
            except RuntimeError:
                continue
            if operation is None:
                continue
            brief = brief_bundle.operation_brief if brief_bundle is not None else None
            item = build_agenda_item(
                operation,
                summary,
                brief=brief,
                runtime_alert=runtime_alert,
            )
            if agenda_matches_project(item, project):
                items.append(item)
        return build_agenda_snapshot(items, include_recent=include_recent)
