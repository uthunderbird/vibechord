from __future__ import annotations

from collections.abc import Awaitable, Callable

from agent_operator.application.process_signals import ProcessManagerSignal
from agent_operator.domain import ControlIntentStatus, OperationState
from agent_operator.protocols import PlanningTriggerBus, ProcessManager


class OperationProcessSignalDispatcher:
    """Own process-manager reaction and planning-trigger fanout."""

    def __init__(
        self,
        *,
        planning_trigger_bus: PlanningTriggerBus | None,
        process_managers: list[ProcessManager],
        emit: Callable[..., Awaitable[None]],
    ) -> None:
        self._planning_trigger_bus = planning_trigger_bus
        self._process_managers = process_managers
        self._emit = emit

    async def dispatch(
        self,
        state: OperationState,
        iteration: int,
        signal: ProcessManagerSignal,
    ) -> None:
        if self._planning_trigger_bus is None or not self._process_managers:
            return
        for manager in self._process_managers:
            for trigger in await manager.react(signal, state):
                stored = await self._planning_trigger_bus.enqueue_planning_trigger(trigger)
                if stored.status is ControlIntentStatus.PENDING:
                    await self._emit(
                        "planning_trigger.enqueued",
                        state,
                        iteration,
                        {
                            "trigger_id": trigger.trigger_id,
                            "reason": trigger.reason,
                            "source_kind": trigger.source_kind,
                            "source_id": trigger.source_id,
                            "dedupe_key": trigger.dedupe_key,
                        },
                    )
                elif stored.planning_trigger is not None:
                    await self._emit(
                        "planning_trigger.coalesced",
                        state,
                        iteration,
                        {
                            "trigger_id": stored.planning_trigger.trigger_id,
                            "reason": stored.planning_trigger.reason,
                            "source_kind": stored.planning_trigger.source_kind,
                            "source_id": stored.planning_trigger.source_id,
                            "dedupe_key": stored.planning_trigger.dedupe_key,
                        },
                    )
