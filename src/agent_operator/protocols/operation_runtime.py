from __future__ import annotations

from typing import Protocol, Self

from agent_operator.domain import (
    AgentResult,
    AgentSessionHandle,
    BackgroundRunStatus,
    ExecutionState,
)
from agent_operator.dtos.requests import AgentRunRequest


class OperationRuntime(Protocol):
    """Operation-scoped coordination boundary for runtime dispatch and supervision."""

    async def __aenter__(self) -> Self: ...

    async def __aexit__(self, exc_type, exc, tb) -> None: ...

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
    ) -> ExecutionState: ...

    async def poll_background_turn(self, run_id: str) -> ExecutionState | None: ...

    async def collect_background_turn(self, run_id: str) -> AgentResult | None: ...

    async def finalize_background_turn(
        self,
        run_id: str,
        status: BackgroundRunStatus,
        *,
        error: str | None = None,
    ) -> None: ...

    async def cancel_operation_runs(self, run_ids: list[str]) -> None: ...
