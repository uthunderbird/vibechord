from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

from agent_operator.domain import (
    OperationState,
    PlanningTrigger,
)
from agent_operator.protocols import PlanningTriggerBus


class OperationDriveControlService:
    """Own command and planning-trigger control used by the drive loop."""

    def __init__(
        self,
        *,
        drain_commands: Callable[
            [OperationState], Awaitable[None]
        ],
        finalize_pending_attention_resolutions: Callable[[OperationState], Awaitable[None]],
        planning_trigger_bus: PlanningTriggerBus | None,
        emit: Callable[..., Awaitable[None]],
    ) -> None:
        self._drain_commands_impl = drain_commands
        self._finalize_pending_attention_resolutions_impl = (
            finalize_pending_attention_resolutions
        )
        self._planning_trigger_bus = planning_trigger_bus
        self._emit = emit

    async def _drain_commands(self, state: OperationState) -> None:
        await self._drain_commands_impl(state)

    async def _has_pending_planning_triggers(self, state: OperationState) -> bool:
        if self._planning_trigger_bus is None:
            return False
        return bool(
            await self._planning_trigger_bus.list_pending_planning_triggers(
                state.operation_id
            )
        )

    async def _drain_pending_planning_triggers(
        self,
        state: OperationState,
        *,
        iteration: int,
    ) -> list[PlanningTrigger]:
        if self._planning_trigger_bus is None:
            return []
        pending = await self._planning_trigger_bus.list_pending_planning_triggers(
            state.operation_id
        )
        if not pending:
            return []
        applied_at = datetime.now(UTC)
        for trigger in pending:
            await self._planning_trigger_bus.mark_planning_trigger_applied(
                trigger.trigger_id,
                applied_at=applied_at,
            )
            await self._emit(
                "planning_trigger.applied",
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
        return pending

    async def _finalize_pending_attention_resolutions(self, state: OperationState) -> None:
        await self._finalize_pending_attention_resolutions_impl(state)
