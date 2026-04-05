from __future__ import annotations

from datetime import datetime
from typing import Protocol, runtime_checkable

from agent_operator.domain import (
    ControlIntentStatus,
    OperationCommand,
    PlanningTrigger,
    StoredControlIntent,
)


@runtime_checkable
class PlanningTriggerBus(Protocol):
    """Durable bus surface for internal planning triggers."""

    async def enqueue_planning_trigger(self, trigger: PlanningTrigger) -> StoredControlIntent: ...

    async def list_planning_triggers(self, operation_id: str) -> list[PlanningTrigger]: ...

    async def list_pending_planning_triggers(self, operation_id: str) -> list[PlanningTrigger]: ...

    async def mark_planning_trigger_applied(
        self,
        trigger_id: str,
        *,
        applied_at: datetime | None = None,
    ) -> PlanningTrigger | None: ...

    async def mark_planning_trigger_superseded(
        self,
        trigger_id: str,
        *,
        superseded_by_trigger_id: str | None = None,
    ) -> PlanningTrigger | None: ...


class ControlIntentBus(PlanningTriggerBus, Protocol):
    """Durable bus for user commands and internal planning triggers."""

    async def enqueue_command(self, command: OperationCommand) -> StoredControlIntent: ...

    async def list_commands(self, operation_id: str) -> list[OperationCommand]: ...

    async def list_pending_commands(self, operation_id: str) -> list[OperationCommand]: ...

    async def update_command_status(
        self,
        command_id: str,
        status: ControlIntentStatus,
        *,
        rejection_reason: str | None = None,
        applied_at: datetime | None = None,
    ) -> OperationCommand | None: ...
