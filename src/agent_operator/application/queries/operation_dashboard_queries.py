from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from agent_operator.application.queries.operation_projections import OperationProjectionService
from agent_operator.application.queries.operation_status_queries import OperationStatusQueryService
from agent_operator.domain import DecisionMemo, OperationState, RunEvent
from agent_operator.protocols import OperationCommandInbox


class EventReaderLike(Protocol):
    def read_events(self, operation_id: str) -> list[RunEvent]: ...


class TraceStoreLike(Protocol):
    async def load_decision_memos(self, operation_id: str) -> list[DecisionMemo]: ...
    async def load_report(self, operation_id: str) -> str | None: ...


@dataclass(slots=True)
class OperationDashboardQueryService:
    status_service: OperationStatusQueryService
    projection_service: OperationProjectionService
    command_inbox: OperationCommandInbox
    event_reader: EventReaderLike
    trace_store: TraceStoreLike
    build_upstream_transcript: Callable[[OperationState], dict[str, object] | None]

    async def load_payload(self, operation_id: str) -> dict[str, object]:
        operation, outcome, brief, runtime_alert = await self.status_service.build_status_payload(
            operation_id
        )
        if operation is None:
            raise RuntimeError(f"Operation {operation_id!r} was not found.")
        commands = await self.command_inbox.list(operation_id)
        events = self.event_reader.read_events(operation_id)
        decision_memos = await self.trace_store.load_decision_memos(operation_id)
        report_text = await self.trace_store.load_report(operation_id)
        payload = self.projection_service.build_dashboard_payload(
            operation,
            brief=brief,
            outcome=outcome,
            runtime_alert=runtime_alert,
            commands=commands,
            events=events,
            decision_memos=decision_memos,
            upstream_transcript=self.build_upstream_transcript(operation),
            report_text=report_text,
        )
        if brief is not None and brief.operation_brief is not None:
            payload["brief"] = brief.operation_brief.model_dump(mode="json")
        return payload
