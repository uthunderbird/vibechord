from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from agent_operator.domain import (
    CommandStatus,
    ControlIntentKind,
    ControlIntentStatus,
    OperationCommand,
    PlanningTrigger,
    StoredControlIntent,
)
from agent_operator.runtime.files import atomic_write_text, read_text_with_retry


class FileControlIntentBus:
    """File-backed durable bus for user commands and planning triggers.

    Examples:
        >>> from pathlib import Path
        >>> bus = FileControlIntentBus(Path("/tmp/control_bus"))
        >>> bus._path("id-1").name
        'id-1.json'
    """

    def __init__(self, root: Path) -> None:
        self._root = root
        self._root.mkdir(parents=True, exist_ok=True)

    async def enqueue_command(self, command: OperationCommand) -> StoredControlIntent:
        record = StoredControlIntent.for_command(command)
        atomic_write_text(self._path(record.intent_id), record.model_dump_json(indent=2))
        return record

    async def list_commands(self, operation_id: str) -> list[OperationCommand]:
        return [
            record.command.model_copy(deep=True)
            for record in self._load_all()
            if record.operation_id == operation_id
            and record.intent_kind is ControlIntentKind.USER_COMMAND
            and record.command is not None
        ]

    async def list_pending_commands(self, operation_id: str) -> list[OperationCommand]:
        return [
            command
            for command in await self.list_commands(operation_id)
            if command.status is CommandStatus.PENDING
        ]

    async def update_command_status(
        self,
        command_id: str,
        status: ControlIntentStatus,
        *,
        rejection_reason: str | None = None,
        applied_at: datetime | None = None,
    ) -> OperationCommand | None:
        record = self._load_by_id(command_id)
        if record is None or record.command is None:
            return None
        updated = record.model_copy(deep=True)
        command = updated.command
        assert command is not None
        updated.status = status
        updated.rejection_reason = (
            rejection_reason if status is ControlIntentStatus.REJECTED else None
        )
        updated.applied_at = (
            applied_at or datetime.now(UTC) if status is ControlIntentStatus.APPLIED else None
        )
        command.status = self._map_control_status_to_command_status(status)
        command.rejection_reason = updated.rejection_reason
        command.applied_at = updated.applied_at
        atomic_write_text(self._path(command_id), updated.model_dump_json(indent=2))
        return command.model_copy(deep=True)

    async def enqueue_planning_trigger(self, trigger: PlanningTrigger) -> StoredControlIntent:
        existing = self._find_pending_trigger_by_dedupe_key(
            trigger.operation_id,
            trigger.dedupe_key,
        )
        if existing is not None:
            return existing
        record = StoredControlIntent.for_planning_trigger(trigger)
        atomic_write_text(self._path(record.intent_id), record.model_dump_json(indent=2))
        return record

    async def list_planning_triggers(self, operation_id: str) -> list[PlanningTrigger]:
        return [
            record.planning_trigger.model_copy(deep=True)
            for record in self._load_all()
            if record.operation_id == operation_id
            and record.intent_kind is ControlIntentKind.PLANNING_TRIGGER
            and record.planning_trigger is not None
        ]

    async def list_pending_planning_triggers(self, operation_id: str) -> list[PlanningTrigger]:
        pending: list[PlanningTrigger] = []
        for record in self._load_all():
            if (
                record.operation_id == operation_id
                and record.intent_kind is ControlIntentKind.PLANNING_TRIGGER
                and record.status is ControlIntentStatus.PENDING
                and record.planning_trigger is not None
            ):
                pending.append(record.planning_trigger.model_copy(deep=True))
        return pending

    async def mark_planning_trigger_applied(
        self,
        trigger_id: str,
        *,
        applied_at: datetime | None = None,
    ) -> PlanningTrigger | None:
        record = self._load_by_id(trigger_id)
        if record is None or record.planning_trigger is None:
            return None
        updated = record.model_copy(deep=True)
        planning_trigger = updated.planning_trigger
        assert planning_trigger is not None
        updated.status = ControlIntentStatus.APPLIED
        updated.applied_at = applied_at or datetime.now(UTC)
        atomic_write_text(self._path(trigger_id), updated.model_dump_json(indent=2))
        return planning_trigger.model_copy(deep=True)

    async def mark_planning_trigger_superseded(
        self,
        trigger_id: str,
        *,
        superseded_by_trigger_id: str | None = None,
    ) -> PlanningTrigger | None:
        record = self._load_by_id(trigger_id)
        if record is None or record.planning_trigger is None:
            return None
        updated = record.model_copy(deep=True)
        planning_trigger = updated.planning_trigger
        assert planning_trigger is not None
        updated.status = ControlIntentStatus.SUPERSEDED
        updated.superseded_at = datetime.now(UTC)
        updated.superseded_by_intent_id = superseded_by_trigger_id
        atomic_write_text(self._path(trigger_id), updated.model_dump_json(indent=2))
        return planning_trigger.model_copy(deep=True)

    def _find_pending_trigger_by_dedupe_key(
        self,
        operation_id: str,
        dedupe_key: str | None,
    ) -> StoredControlIntent | None:
        if dedupe_key is None:
            return None
        for record in self._load_all():
            if (
                record.operation_id == operation_id
                and record.intent_kind is ControlIntentKind.PLANNING_TRIGGER
                and record.status is ControlIntentStatus.PENDING
                and record.planning_trigger is not None
                and record.planning_trigger.dedupe_key == dedupe_key
            ):
                return record.model_copy(deep=True)
        return None

    def _load_by_id(self, intent_id: str) -> StoredControlIntent | None:
        path = self._path(intent_id)
        if not path.exists():
            return None
        return self._load_record(path)

    def _load_all(self) -> list[StoredControlIntent]:
        records = [self._load_record(path) for path in sorted(self._root.glob("*.json"))]
        records.sort(key=lambda item: (item.submitted_at, item.intent_id))
        return records

    def _load_record(self, path: Path) -> StoredControlIntent:
        payload = read_text_with_retry(path)
        try:
            return StoredControlIntent.model_validate_json(payload)
        except Exception:
            command = OperationCommand.model_validate_json(payload)
            return StoredControlIntent.for_command(command)

    def _path(self, intent_id: str) -> Path:
        return self._root / f"{intent_id}.json"

    def _map_control_status_to_command_status(
        self,
        status: ControlIntentStatus,
    ) -> CommandStatus:
        mapping = {
            ControlIntentStatus.PENDING: CommandStatus.PENDING,
            ControlIntentStatus.APPLIED: CommandStatus.APPLIED,
            ControlIntentStatus.REJECTED: CommandStatus.REJECTED,
            ControlIntentStatus.SUPERSEDED: CommandStatus.APPLIED,
        }
        return mapping[status]
