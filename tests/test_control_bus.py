from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from agent_operator.domain import (
    CommandStatus,
    CommandTargetScope,
    ControlIntentStatus,
    OperationCommand,
    OperationCommandType,
    PlanningTrigger,
)
from agent_operator.runtime import FileControlIntentBus, FileOperationCommandInbox


@pytest.mark.anyio
async def test_file_control_intent_bus_round_trips_commands_and_triggers(
    tmp_path: Path,
) -> None:
    """Bus stores user commands and planning triggers in one durable surface.

    Examples:
        >>> from pathlib import Path
        >>> bus = FileControlIntentBus(Path("/tmp/control-intents"))
        >>> bus is not None
        True
    """

    bus = FileControlIntentBus(tmp_path / "control_intents")
    command = OperationCommand(
        operation_id="op-1",
        command_type=OperationCommandType.PATCH_OBJECTIVE,
        target_scope=CommandTargetScope.OPERATION,
        target_id="op-1",
        payload={"text": "Refine the release workflow."},
    )
    trigger = PlanningTrigger(
        operation_id="op-1",
        reason="objective_updated",
        source_kind="command",
        source_id=command.command_id,
        dedupe_key="op-1:planning_context_changed",
    )

    await bus.enqueue_command(command)
    stored_trigger = await bus.enqueue_planning_trigger(trigger)

    commands = await bus.list_commands("op-1")
    pending_commands = await bus.list_pending_commands("op-1")
    pending_triggers = await bus.list_pending_planning_triggers("op-1")

    assert [item.command_id for item in commands] == [command.command_id]
    assert [item.command_id for item in pending_commands] == [command.command_id]
    assert stored_trigger.status is ControlIntentStatus.PENDING
    assert [item.trigger_id for item in pending_triggers] == [trigger.trigger_id]


@pytest.mark.anyio
async def test_file_control_intent_bus_coalesces_duplicate_pending_triggers(
    tmp_path: Path,
) -> None:
    """Equivalent planning triggers are deduped by operation and dedupe key."""

    bus = FileControlIntentBus(tmp_path / "control_intents")
    first = PlanningTrigger(
        trigger_id="trigger-1",
        operation_id="op-1",
        reason="objective_updated",
        source_kind="signal",
        source_id="sig-1",
        dedupe_key="op-1:planning_context_changed",
    )
    second = PlanningTrigger(
        trigger_id="trigger-2",
        operation_id="op-1",
        reason="harness_updated",
        source_kind="signal",
        source_id="sig-2",
        dedupe_key="op-1:planning_context_changed",
    )

    stored_first = await bus.enqueue_planning_trigger(first)
    stored_second = await bus.enqueue_planning_trigger(second)
    pending = await bus.list_pending_planning_triggers("op-1")

    assert stored_first.planning_trigger is not None
    assert stored_second.planning_trigger is not None
    assert stored_first.planning_trigger.trigger_id == "trigger-1"
    assert stored_second.planning_trigger.trigger_id == "trigger-1"
    assert [item.trigger_id for item in pending] == ["trigger-1"]


@pytest.mark.anyio
async def test_file_control_intent_bus_updates_command_and_trigger_statuses(
    tmp_path: Path,
) -> None:
    """Bus persists command application and trigger lifecycle transitions."""

    bus = FileControlIntentBus(tmp_path / "control_intents")
    command = OperationCommand(
        operation_id="op-1",
        command_type=OperationCommandType.PATCH_HARNESS,
        target_scope=CommandTargetScope.OPERATION,
        target_id="op-1",
        payload={"text": "Prefer swarm for strategic forks."},
    )
    trigger = PlanningTrigger(
        trigger_id="trigger-1",
        operation_id="op-1",
        reason="harness_updated",
        source_kind="command",
        source_id=command.command_id,
        dedupe_key="op-1:planning_context_changed",
    )
    applied_at = datetime(2026, 4, 3, 10, 0, tzinfo=UTC)

    await bus.enqueue_command(command)
    await bus.enqueue_planning_trigger(trigger)
    updated_command = await bus.update_command_status(
        command.command_id,
        ControlIntentStatus.APPLIED,
        applied_at=applied_at,
    )
    applied_trigger = await bus.mark_planning_trigger_applied(
        trigger.trigger_id,
        applied_at=applied_at,
    )
    pending_triggers = await bus.list_pending_planning_triggers("op-1")

    assert updated_command is not None
    assert updated_command.status is CommandStatus.APPLIED
    assert updated_command.applied_at == applied_at
    assert applied_trigger is not None
    assert applied_trigger.trigger_id == trigger.trigger_id
    assert pending_triggers == []


@pytest.mark.anyio
async def test_file_operation_command_inbox_delegates_to_shared_control_bus(
    tmp_path: Path,
) -> None:
    """Command inbox remains a user-command facade over the shared bus."""

    bus = FileControlIntentBus(tmp_path / "control_intents")
    inbox = FileOperationCommandInbox(tmp_path / "commands", bus=bus)
    command = OperationCommand(
        operation_id="op-1",
        command_type=OperationCommandType.PATCH_SUCCESS_CRITERIA,
        target_scope=CommandTargetScope.OPERATION,
        target_id="op-1",
        payload={"success_criteria": ["Tests pass."]},
    )

    await inbox.enqueue(command)
    listed = await inbox.list("op-1")
    await inbox.update_status(command.command_id, CommandStatus.APPLIED)
    pending = await bus.list_pending_commands("op-1")

    assert [item.command_id for item in listed] == [command.command_id]
    assert pending == []
