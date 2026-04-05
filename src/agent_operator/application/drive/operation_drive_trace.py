from __future__ import annotations

from agent_operator.application.operation_event_relay import OperationEventRelay
from agent_operator.application.operation_traceability import OperationTraceabilityService
from agent_operator.domain import (
    IterationState,
    OperationState,
    RunEventKind,
    TaskState,
)


class OperationDriveTraceService:
    """Own drive-loop event emission and traceability delegation."""

    def __init__(
        self,
        *,
        event_relay: OperationEventRelay,
        traceability_service: OperationTraceabilityService,
    ) -> None:
        self._event_relay = event_relay
        self._traceability_service = traceability_service

    async def _emit(
        self,
        event_type: str,
        state: OperationState,
        iteration: int,
        payload: dict[str, object],
        *,
        task_id: str | None = None,
        session_id: str | None = None,
        kind: RunEventKind = RunEventKind.TRACE,
        category: str | None = "domain",
    ) -> None:
        await self._event_relay.emit(
            event_type,
            state,
            iteration,
            payload,
            task_id=task_id,
            session_id=session_id,
            kind=kind,
            category=category,
        )

    async def _record_decision_memo(
        self,
        state: OperationState,
        iteration: IterationState,
        task: TaskState | None,
    ) -> None:
        await self._traceability_service.record_decision_memo(state, iteration, task)

    async def _record_iteration_brief(
        self,
        state: OperationState,
        iteration: IterationState,
        task: TaskState | None,
    ) -> None:
        await self._traceability_service.record_iteration_brief(state, iteration, task)

    async def _sync_traceability_artifacts(self, state: OperationState) -> None:
        await self._traceability_service.sync_traceability_artifacts(state)

    def _default_outcome_summary(self, state: OperationState) -> str:
        return self._traceability_service.default_outcome_summary(state)
