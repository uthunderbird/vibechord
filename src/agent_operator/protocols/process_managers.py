from __future__ import annotations

from typing import Any, Protocol

from agent_operator.domain import OperationState, PlanningTrigger


class ProcessManagerSignal(Protocol):
    """Signal payload forwarded into bridge process managers."""

    signal_id: str
    operation_id: str
    signal_type: str
    source_command_id: str | None
    task_id: str | None
    session_id: str | None
    execution_id: str | None
    metadata: dict[str, Any]
    observed_at: object


class ProcessManager(Protocol):
    """Control-plane reactor that emits only internal planning triggers."""

    async def react(
        self,
        signal: ProcessManagerSignal,
        state: OperationState,
    ) -> list[PlanningTrigger]: ...


class ProcessManagerPolicy(Protocol):
    """Policy unit evaluated by a process manager."""

    async def evaluate(
        self,
        signal: ProcessManagerSignal,
        state: OperationState,
    ) -> PlanningTrigger | None: ...


class ProcessManagerBuilder(Protocol):
    """Assembly-time builder for process managers from bounded policy sets."""

    def build(self) -> list[ProcessManager]: ...
