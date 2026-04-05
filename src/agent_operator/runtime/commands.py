from __future__ import annotations

import builtins
from datetime import datetime
from pathlib import Path

from agent_operator.domain import (
    CommandStatus,
    ControlIntentStatus,
    OperationCommand,
    PlanningTrigger,
    StoredControlIntent,
)
from agent_operator.runtime.control_bus import FileControlIntentBus


class FileOperationCommandInbox:
    """User-command facade over the shared durable control-intent bus."""

    def __init__(
        self,
        root: Path,
        *,
        bus: FileControlIntentBus | None = None,
    ) -> None:
        self._bus = bus or FileControlIntentBus(root)
        self._root = root
        self._root.mkdir(parents=True, exist_ok=True)

    async def enqueue(self, command: OperationCommand) -> None:
        await self._bus.enqueue_command(command)

    async def list(self, operation_id: str) -> builtins.list[OperationCommand]:
        return await self._bus.list_commands(operation_id)

    async def list_pending(self, operation_id: str) -> builtins.list[OperationCommand]:
        return await self._bus.list_pending_commands(operation_id)

    async def update_status(
        self,
        command_id: str,
        status: CommandStatus,
        *,
        rejection_reason: str | None = None,
        applied_at: datetime | None = None,
    ) -> OperationCommand | None:
        mapped_status = {
            CommandStatus.PENDING: ControlIntentStatus.PENDING,
            CommandStatus.APPLIED: ControlIntentStatus.APPLIED,
            CommandStatus.REJECTED: ControlIntentStatus.REJECTED,
        }[status]
        return await self._bus.update_command_status(
            command_id,
            mapped_status,
            rejection_reason=rejection_reason,
            applied_at=applied_at,
        )

    async def enqueue_planning_trigger(
        self,
        trigger: PlanningTrigger,
    ) -> StoredControlIntent:
        return await self._bus.enqueue_planning_trigger(trigger)

    async def list_planning_triggers(
        self,
        operation_id: str,
    ) -> builtins.list[PlanningTrigger]:
        return await self._bus.list_planning_triggers(operation_id)

    async def list_pending_planning_triggers(
        self,
        operation_id: str,
    ) -> builtins.list[PlanningTrigger]:
        return await self._bus.list_pending_planning_triggers(operation_id)

    async def mark_planning_trigger_applied(
        self,
        trigger_id: str,
        *,
        applied_at: datetime | None = None,
    ) -> PlanningTrigger | None:
        return await self._bus.mark_planning_trigger_applied(trigger_id, applied_at=applied_at)

    async def mark_planning_trigger_superseded(
        self,
        trigger_id: str,
        *,
        superseded_by_trigger_id: str | None = None,
    ) -> PlanningTrigger | None:
        return await self._bus.mark_planning_trigger_superseded(
            trigger_id,
            superseded_by_trigger_id=superseded_by_trigger_id,
        )
