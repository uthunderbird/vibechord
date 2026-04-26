from __future__ import annotations

from collections.abc import Awaitable, Callable

from agent_operator.domain import CommandTargetScope, OperationCommandType

from .converse import ConverseCommand


async def execute_converse_command(
    command: ConverseCommand,
    *,
    answer_async: Callable[..., Awaitable[None]],
    enqueue_command_async: Callable[..., Awaitable[None]],
    stop_turn_async: Callable[..., Awaitable[None]],
    cancel_async: Callable[..., Awaitable[None]],
) -> None:
    """Execute a parsed converse command through caller-owned workflow seams."""
    if command.command_name == "answer":
        assert command.attention_id is not None
        assert command.text is not None
        await answer_async(
            command.operation_id,
            command.attention_id,
            command.text,
            False,
            None,
            None,
            "general",
            None,
            None,
            None,
            None,
            None,
            None,
            False,
        )
        return
    if command.command_name == "message":
        assert command.text is not None
        await enqueue_command_async(
            command.operation_id,
            OperationCommandType.INJECT_OPERATOR_MESSAGE,
            command.text,
        )
        return
    if command.command_name == "pause":
        await enqueue_command_async(
            command.operation_id,
            OperationCommandType.PAUSE_OPERATOR,
            None,
        )
        return
    if command.command_name == "unpause":
        await enqueue_command_async(
            command.operation_id,
            OperationCommandType.RESUME_OPERATOR,
            None,
            True,
        )
        return
    if command.command_name == "interrupt":
        await stop_turn_async(command.operation_id, command.task_id)
        return
    if command.command_name == "patch-objective":
        assert command.text is not None
        await enqueue_command_async(
            command.operation_id,
            OperationCommandType.PATCH_OBJECTIVE,
            command.text,
            False,
            CommandTargetScope.OPERATION,
            None,
            None,
            None,
            False,
            None,
            None,
            True,
        )
        return
    if command.command_name == "cancel":
        await cancel_async(command.operation_id, None, None, False)
        return
    raise RuntimeError(f"Unsupported converse command: {command.command_name}")
