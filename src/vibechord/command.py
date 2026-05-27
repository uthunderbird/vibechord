"""CommandApplication implementation."""

from __future__ import annotations

import uuid

from vibechord.domain import CommandName, CommandResult, OperationCommand
from vibechord.protocols import EventStore


class CommandApplication:
    """Validate commands and append canonical command/domain events."""

    def __init__(self, event_store: EventStore) -> None:
        """Create command application over one event store."""

        self.event_store = event_store

    def apply(self, command: OperationCommand) -> CommandResult:
        """Apply one typed command."""

        if command.name is CommandName.START:
            return self._start(command)
        if command.operation_id is None:
            return _rejected(
                command, "operation_id_required", "operation_id is required"
            )
        if command.name is CommandName.CANCEL:
            return self._simple_event(command, "operation.cancelled", "cancelled")
        if command.name is CommandName.PAUSE:
            return self._simple_event(command, "operation.paused", "paused")
        if command.name is CommandName.RESUME:
            return self._simple_event(command, "operation.resumed", "resumed")
        if command.name is CommandName.INTERRUPT:
            return self._simple_event(command, "operation.interrupted", "interrupted")
        if command.name is CommandName.ANSWER_ATTENTION:
            return self._answer_attention(command)
        if command.name is CommandName.POST_MESSAGE:
            return self._post_message(command)
        return _rejected(command, "unknown_command", f"unknown command: {command.name}")

    def record_audit(self, operation_id: str, command_id: str, action: str) -> None:
        """Append a delivery audit event through application authority."""

        self.event_store.append(
            operation_id,
            "rest.audit",
            {"action": action},
            f"{command_id}:audit",
        )

    def _start(self, command: OperationCommand) -> CommandResult:
        goal = str(command.payload.get("goal", "")).strip()
        if goal == "":
            return _rejected(command, "invalid_goal", "goal must not be empty")
        operation_id = command.operation_id or str(
            uuid.uuid5(uuid.NAMESPACE_URL, f"vibechord:{command.command_id}")
        )
        accepted = self.event_store.append(
            operation_id,
            "command.accepted",
            {"command": command.name.value},
            command.command_id,
        )
        started = self.event_store.append(
            operation_id,
            "operation.started",
            {
                "goal": goal,
                "max_iterations": int(command.payload.get("max_iterations", 10)),
                "max_agent_calls": int(command.payload.get("max_agent_calls", 10)),
            },
            f"{command.command_id}:operation.started",
        )
        return CommandResult(
            command_id=command.command_id,
            accepted=True,
            code="accepted",
            message="operation started",
            operation_id=operation_id,
            resulting_event_ids=(accepted.event_id, started.event_id),
        )

    def _simple_event(
        self, command: OperationCommand, event_kind: str, message: str
    ) -> CommandResult:
        operation_id = _require_operation_id(command)
        accepted = self.event_store.append(
            operation_id,
            "command.accepted",
            {"command": command.name.value},
            command.command_id,
        )
        event = self.event_store.append(
            operation_id,
            event_kind,
            {"reason": message},
            f"{command.command_id}:{event_kind}",
        )
        return CommandResult(
            command_id=command.command_id,
            accepted=True,
            code="accepted",
            message=message,
            operation_id=operation_id,
            resulting_event_ids=(accepted.event_id, event.event_id),
        )

    def _answer_attention(self, command: OperationCommand) -> CommandResult:
        operation_id = _require_operation_id(command)
        attention_id = str(command.payload.get("attention_id", "")).strip()
        text = str(command.payload.get("text", "")).strip()
        if attention_id == "" or text == "":
            return _rejected(
                command, "invalid_attention_answer", "attention_id and text required"
            )
        accepted = self.event_store.append(
            operation_id,
            "command.accepted",
            {"command": command.name.value},
            command.command_id,
        )
        event = self.event_store.append(
            operation_id,
            "attention.answered",
            {"attention_id": attention_id, "text": text},
            f"{command.command_id}:attention.answered",
        )
        return CommandResult(
            command_id=command.command_id,
            accepted=True,
            code="accepted",
            message="attention answered",
            operation_id=operation_id,
            resulting_event_ids=(accepted.event_id, event.event_id),
        )

    def _post_message(self, command: OperationCommand) -> CommandResult:
        operation_id = _require_operation_id(command)
        text = str(command.payload.get("text", "")).strip()
        if text == "":
            return _rejected(command, "invalid_message", "text must not be empty")
        accepted = self.event_store.append(
            operation_id,
            "command.accepted",
            {"command": command.name.value},
            command.command_id,
        )
        event = self.event_store.append(
            operation_id,
            "operator.message.posted",
            {"text": text},
            f"{command.command_id}:operator.message.posted",
        )
        return CommandResult(
            command_id=command.command_id,
            accepted=True,
            code="accepted",
            message="message posted",
            operation_id=operation_id,
            resulting_event_ids=(accepted.event_id, event.event_id),
        )


def _rejected(command: OperationCommand, code: str, message: str) -> CommandResult:
    return CommandResult(
        command_id=command.command_id,
        accepted=False,
        code=code,
        message=message,
        operation_id=command.operation_id,
    )


def _require_operation_id(command: OperationCommand) -> str:
    if command.operation_id is None:
        raise ValueError("operation_id is required")
    return command.operation_id
