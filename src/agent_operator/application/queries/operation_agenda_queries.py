from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from agent_operator.application.queries.operation_status_queries import OperationStatusQueryService
from agent_operator.domain import OperationState, OperationSummary
from agent_operator.protocols import OperationStore
from agent_operator.runtime import (
    AgendaSnapshot,
    agenda_matches_project,
    build_agenda_item,
    build_agenda_snapshot,
)


class CanonicalOperationLister(Protocol):
    async def list_canonical_operation_states(self) -> list[OperationState]: ...


@dataclass(slots=True)
class OperationAgendaQueryService:
    store: OperationStore
    status_service: OperationStatusQueryService
    canonical_lister: CanonicalOperationLister | None = None

    async def load_snapshot(
        self,
        *,
        project: str | None,
        include_recent: bool,
    ) -> AgendaSnapshot:
        items = []
        for operation, summary in await self._list_operations():
            try:
                payload = await self.status_service.build_read_payload(summary.operation_id)
            except RuntimeError:
                continue
            if payload.operation is None:
                continue
            operation = payload.operation
            trace_brief = payload.overlay.trace_brief
            brief = trace_brief.operation_brief if trace_brief is not None else None
            item = build_agenda_item(
                operation,
                summary,
                brief=brief,
                runtime_alert=payload.overlay.runtime_alert,
                sync_health=payload.overlay.sync_health,
            )
            if agenda_matches_project(item, project):
                items.append(item)
        return build_agenda_snapshot(items, include_recent=include_recent)

    async def _list_operations(self) -> list[tuple[OperationState, OperationSummary]]:
        if self.canonical_lister is not None:
            states = await self.canonical_lister.list_canonical_operation_states()
            return [(state, self._summary_from_state(state)) for state in states]
        pairs: list[tuple[OperationState, OperationSummary]] = []
        for summary in await self.store.list_operations():
            operation = await self.store.load_operation(summary.operation_id)
            if operation is None:
                continue
            pairs.append((operation, summary))
        return pairs

    def _summary_from_state(self, operation: OperationState) -> OperationSummary:
        return OperationSummary(
            operation_id=operation.operation_id,
            status=operation.status,
            objective_prompt=operation.goal.objective_text,
            final_summary=operation.final_summary,
            focus=None,
            runnable_task_count=0,
            reusable_session_count=0,
            updated_at=operation.updated_at,
        )
