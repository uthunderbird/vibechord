from __future__ import annotations

from agent_operator.application.decision_execution import DecisionExecutionService
from agent_operator.domain import IterationState, OperationState, RunOptions, TaskState


class OperationDriveDecisionExecutorService:
    """Thin drive-facing adapter over decision execution workflow."""

    def __init__(
        self,
        *,
        decision_execution_service: DecisionExecutionService,
        supervisor_available: bool,
    ) -> None:
        self._decision_execution_service = decision_execution_service
        self._supervisor_available = supervisor_available

    async def _execute_decision(
        self,
        state: OperationState,
        iteration: IterationState,
        task: TaskState | None,
        options: RunOptions,
    ) -> bool:
        return await self._decision_execution_service.execute_decision(
            state,
            iteration,
            task,
            options,
            supervisor_available=self._supervisor_available,
        )
