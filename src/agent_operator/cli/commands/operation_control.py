from __future__ import annotations

import anyio
import typer

from agent_operator.domain import (
    CommandTargetScope,
    InvolvementLevel,
    OperationCommandType,
    RunMode,
)

from ..app import app, debug_app
from ..helpers.resolution import resolve_operation_id
from ..options import (
    COMMAND_ALLOWED_AGENT_OPTION,
    COMMAND_CLEAR_SUCCESS_CRITERIA_OPTION,
    COMMAND_MAX_ITERATIONS_OPTION,
    COMMAND_SUCCESS_CRITERION_OPTION,
    COMMAND_TYPE_OPTION,
    INVOLVEMENT_LEVEL_OPTION,
    PATCH_CLEAR_CRITERIA_OPTION,
    PATCH_CRITERIA_OPTION,
    PROMOTE_POLICY_AGENT_OPTION,
    PROMOTE_POLICY_INVOLVEMENT_OPTION,
    PROMOTE_POLICY_OBJECTIVE_KEYWORD_OPTION,
    PROMOTE_POLICY_RUN_MODE_OPTION,
    PROMOTE_POLICY_TASK_KEYWORD_OPTION,
)
from ..workflows import (
    answer_async,
    ask_async,
    cancel_async,
    enqueue_command_async,
    status_async,
    stop_turn_async,
)


@app.command()
def status(
    operation_ref: str,
    json_mode: bool = typer.Option(False, "--json", help="Emit machine-readable JSON."),
    brief: bool = typer.Option(False, "--brief", help="Emit a single-line summary."),
) -> None:
    anyio.run(status_async, resolve_operation_id(operation_ref), json_mode, brief)


@app.command()
def ask(
    operation_ref: str,
    question: str,
    json_mode: bool = typer.Option(False, "--json", help="Emit machine-readable JSON."),
) -> None:
    anyio.run(ask_async, operation_ref, question, json_mode)


@app.command()
def cancel(
    operation_ref: str,
    yes: bool = typer.Option(False, "--yes", help="Skip confirmation prompt."),
    session_id: str | None = typer.Option(None, "--session", help="Cancel a specific session."),
    run_id: str | None = typer.Option(None, "--run", help="Cancel a specific background run."),
    json_mode: bool = typer.Option(False, "--json", help="Emit machine-readable JSON."),
) -> None:
    resolved_operation_id = resolve_operation_id(operation_ref)
    if session_id is None and run_id is None and not yes:
        confirmed = typer.confirm(f"Cancel operation {resolved_operation_id}?")
        if not confirmed:
            typer.echo("cancelled")
            raise typer.Exit()
    anyio.run(cancel_async, resolved_operation_id, session_id, run_id, json_mode)


@app.command(hidden=True)
def command(
    operation_id: str,
    type: OperationCommandType = COMMAND_TYPE_OPTION,
    text: str | None = typer.Option(None, "--text", help="Command text payload."),
    success_criterion: list[str] | None = COMMAND_SUCCESS_CRITERION_OPTION,
    clear_success_criteria: bool = COMMAND_CLEAR_SUCCESS_CRITERIA_OPTION,
    allowed_agent: list[str] | None = COMMAND_ALLOWED_AGENT_OPTION,
    max_iterations: int | None = COMMAND_MAX_ITERATIONS_OPTION,
) -> None:
    anyio.run(
        enqueue_command_async,
        operation_id,
        type,
        text,
        False,
        CommandTargetScope.OPERATION,
        None,
        None,
        success_criterion,
        clear_success_criteria,
        allowed_agent,
        max_iterations,
    )


@debug_app.command("command")
def debug_command(
    operation_id: str,
    type: OperationCommandType = COMMAND_TYPE_OPTION,
    text: str | None = typer.Option(None, "--text", help="Command text payload."),
    success_criterion: list[str] | None = COMMAND_SUCCESS_CRITERION_OPTION,
    clear_success_criteria: bool = COMMAND_CLEAR_SUCCESS_CRITERIA_OPTION,
    allowed_agent: list[str] | None = COMMAND_ALLOWED_AGENT_OPTION,
    max_iterations: int | None = COMMAND_MAX_ITERATIONS_OPTION,
) -> None:
    command(
        operation_id,
        type,
        text,
        success_criterion,
        clear_success_criteria,
        allowed_agent,
        max_iterations,
    )


@app.command()
def involvement(operation_id: str, level: InvolvementLevel = INVOLVEMENT_LEVEL_OPTION) -> None:
    anyio.run(
        enqueue_command_async, operation_id, OperationCommandType.SET_INVOLVEMENT_LEVEL, level.value
    )


@app.command()
def pause(operation_id: str) -> None:
    anyio.run(
        enqueue_command_async,
        resolve_operation_id(operation_id),
        OperationCommandType.PAUSE_OPERATOR,
        None,
    )


@app.command()
def unpause(operation_id: str) -> None:
    anyio.run(
        enqueue_command_async,
        resolve_operation_id(operation_id),
        OperationCommandType.RESUME_OPERATOR,
        None,
        True,
    )


@app.command("interrupt")
def interrupt(
    operation_ref: str,
    task_id: str | None = typer.Option(
        None, "--task", help="Task ID (UUID or task-XXXX short ID) whose session to stop."
    ),
) -> None:
    anyio.run(stop_turn_async, resolve_operation_id(operation_ref), task_id)


@app.command(hidden=True)
def stop_turn(
    operation_ref: str,
    task_id: str | None = typer.Option(
        None, "--task", help="Task ID (UUID or task-XXXX short ID) whose session to stop."
    ),
) -> None:
    interrupt(operation_ref, task_id)


@app.command()
def message(operation_ref: str, text: str) -> None:
    anyio.run(
        enqueue_command_async,
        resolve_operation_id(operation_ref),
        OperationCommandType.INJECT_OPERATOR_MESSAGE,
        text,
    )


@app.command()
def patch_objective(operation_ref: str, text: str) -> None:
    anyio.run(
        enqueue_command_async,
        resolve_operation_id(operation_ref),
        OperationCommandType.PATCH_OBJECTIVE,
        text,
    )


@app.command()
def patch_harness(operation_ref: str, text: str) -> None:
    anyio.run(
        enqueue_command_async,
        resolve_operation_id(operation_ref),
        OperationCommandType.PATCH_HARNESS,
        text,
    )


@app.command("patch-criteria")
def patch_criteria(
    operation_ref: str,
    criteria: list[str] | None = PATCH_CRITERIA_OPTION,
    clear: bool = PATCH_CLEAR_CRITERIA_OPTION,
) -> None:
    anyio.run(
        enqueue_command_async,
        resolve_operation_id(operation_ref),
        OperationCommandType.PATCH_SUCCESS_CRITERIA,
        None,
        False,
        CommandTargetScope.OPERATION,
        None,
        None,
        criteria,
        clear,
    )


@app.command()
def answer(
    operation_ref: str,
    attention_id: str | None = typer.Argument(None, help="Attention request id."),
    text: str = typer.Option(..., "--text", help="Human answer text."),
    promote: bool = typer.Option(
        False, "--promote", help="Also promote this answered attention into durable project policy."
    ),
    policy_title: str | None = typer.Option(
        None, "--policy-title", help="Optional policy title override when --promote is used."
    ),
    policy_text: str | None = typer.Option(
        None, "--policy-text", help="Optional policy text override when --promote is used."
    ),
    policy_category: str = typer.Option(
        "general", "--policy-category", help="Policy category for --promote."
    ),
    policy_objective_keyword: list[str] | None = PROMOTE_POLICY_OBJECTIVE_KEYWORD_OPTION,
    policy_task_keyword: list[str] | None = PROMOTE_POLICY_TASK_KEYWORD_OPTION,
    policy_agent: list[str] | None = PROMOTE_POLICY_AGENT_OPTION,
    policy_run_mode: list[RunMode] | None = PROMOTE_POLICY_RUN_MODE_OPTION,
    policy_involvement: list[InvolvementLevel] | None = PROMOTE_POLICY_INVOLVEMENT_OPTION,
    policy_rationale: str | None = typer.Option(
        None, "--policy-rationale", help="Optional rationale for the promoted policy."
    ),
    json_mode: bool = typer.Option(False, "--json", help="Emit machine-readable JSON."),
) -> None:
    anyio.run(
        answer_async,
        resolve_operation_id(operation_ref),
        attention_id,
        text,
        promote,
        policy_title,
        policy_text,
        policy_category,
        policy_objective_keyword,
        policy_task_keyword,
        policy_agent,
        policy_run_mode,
        policy_involvement,
        policy_rationale,
        json_mode,
    )
