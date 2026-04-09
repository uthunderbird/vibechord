from __future__ import annotations

from agent_operator.domain import (
    AgentResult,
    AgentSessionHandle,
    BackgroundRunStatus,
    ExecutionState,
)
from agent_operator.dtos.requests import AgentRunRequest
from agent_operator.protocols import AgentRunSupervisor


class SupervisorBackedOperationRuntime:
    """Operation-scoped coordination wrapper around the background supervisor.

    This runtime owns background-run dispatch, polling, collection, finalization, and grouped
    cancellation for one operation-scoped coordination boundary.
    """

    def __init__(self, *, supervisor: AgentRunSupervisor) -> None:
        self._supervisor = supervisor

    async def __aenter__(self) -> SupervisorBackedOperationRuntime:
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    async def dispatch_background_turn(
        self,
        *,
        operation_id: str,
        iteration: int,
        adapter_key: str,
        request: AgentRunRequest,
        existing_session: AgentSessionHandle | None = None,
        task_id: str | None = None,
        wakeup_delivery: str = "enqueue",
    ) -> ExecutionState:
        """Dispatch one background turn under operation-scoped ownership."""
        return await self._supervisor.start_background_turn(
            operation_id,
            iteration,
            adapter_key,
            request,
            existing_session=existing_session,
            task_id=task_id,
            wakeup_delivery=wakeup_delivery,
        )

    async def poll_background_turn(self, run_id: str) -> ExecutionState | None:
        """Poll one background turn by run identifier."""
        return await self._supervisor.poll_background_turn(run_id)

    async def collect_background_turn(self, run_id: str) -> AgentResult | None:
        """Collect terminal result for one background turn."""
        return await self._supervisor.collect_background_turn(run_id)

    async def finalize_background_turn(
        self,
        run_id: str,
        status: BackgroundRunStatus,
        *,
        error: str | None = None,
    ) -> None:
        """Finalize one background run under operation-scoped ownership."""
        await self._supervisor.finalize_background_turn(run_id, status, error=error)

    async def cancel_operation_runs(self, run_ids: list[str]) -> None:
        """Cancel multiple background runs that belong to one operation scope."""
        for run_id in run_ids:
            await self._supervisor.cancel_background_turn(run_id)
