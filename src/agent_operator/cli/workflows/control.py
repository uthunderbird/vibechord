from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, cast
from uuid import uuid4

import anyio
import typer

from agent_operator.application.ticketing import TicketIntakeService
from agent_operator.bootstrap import (
    build_brain,
    build_event_sink,
    build_store,
    build_v2_service,
)
from agent_operator.bootstrap import (
    build_service as bootstrap_build_service,
)
from agent_operator.config import OperatorSettings, load_global_config
from agent_operator.domain import (
    BackgroundRuntimeMode,
    CommandStatus,
    CommandTargetScope,
    ExecutionBudget,
    InvolvementLevel,
    OperationCommandType,
    OperationGoal,
    OperationPolicy,
    OperationStatus,
    RunMode,
    RunOptions,
    RuntimeHints,
    SchedulerState,
)
from agent_operator.runtime import (
    ProjectingEventSink,
    apply_project_profile_settings,
    resolve_project_run_config,
)

from ..helpers.exit_codes import raise_for_operation_status
from ..helpers.resolution import resolve_project_profile_selection
from ..helpers.services import (
    build_projected_service,
    delivery_commands_service,
    emit_free_mode_stub,
    load_settings,
    load_settings_with_data_dir,
)
from . import control_runtime as _control_runtime
from .converse import (
    ConverseCommand,
)
from .converse import (
    converse_async as converse_loop_async,
)
from .run_output import CliEventProjector, emit_run_outcome
from .run_support import run_with_startup_failure_handling

if TYPE_CHECKING:
    from agent_operator.application import OperatorService


ask_async = _control_runtime.ask_async
cancel_async = _control_runtime.cancel_async
daemon_async = _control_runtime.daemon_async
dashboard_async = _control_runtime.dashboard_async
recover_async = _control_runtime.recover_async
resume_async = _control_runtime.resume_async
status_async = _control_runtime.status_async
tick_async = _control_runtime.tick_async
watch_async = _control_runtime.watch_async
_build_run_goal_metadata = _control_runtime._build_run_goal_metadata
_restore_operation_scoped_runtime_settings = (
    _control_runtime._restore_operation_scoped_runtime_settings
)
_wait_for_operation_outcome = _control_runtime._wait_for_operation_outcome


def _build_cli_service(settings: OperatorSettings) -> OperatorService:
    try:
        import agent_operator.cli.main as cli_main

        factory = getattr(cli_main, "build_service", bootstrap_build_service)
    except Exception:
        factory = bootstrap_build_service
    return cast("OperatorService", factory(settings))


async def _execute_converse_command(command: ConverseCommand) -> None:
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


async def run_async(
    objective: str | None,
    from_ticket: str | None,
    project: str | None,
    harness: str | None,
    success_criteria: list[str] | None,
    max_iterations: int | None,
    allowed_agent: list[str] | None,
    mode: RunMode | None,
    involvement: InvolvementLevel | None,
    attach_session: str | None,
    attach_agent: str | None,
    attach_name: str | None,
    attach_working_dir: Path | None,
    wait: bool,
    timeout: float | None,
    brief: bool,
    json_mode: bool,
    use_v2: bool = False,
) -> None:
    settings, data_dir_source = load_settings_with_data_dir()
    settings.data_dir = Path(settings.data_dir)
    launch_dir = Path.cwd().resolve()
    try:
        profile, selected_profile_path, profile_source = resolve_project_profile_selection(
            settings, name=project
        )
    except RuntimeError as exc:
        raise typer.BadParameter(str(exc)) from exc
    if profile is None and project is None:
        emit_free_mode_stub(cwd=launch_dir, json_mode=json_mode)
        return
    apply_project_profile_settings(settings, profile)
    intake_result = None
    if from_ticket is not None:
        intake_service = TicketIntakeService(global_config=load_global_config())
        intake_result = await intake_service.resolve(from_ticket, profile=profile)
    resolved = resolve_project_run_config(
        settings,
        profile=profile,
        objective=objective
        if objective is not None
        else (intake_result.goal_text if intake_result is not None else None),
        harness=harness,
        success_criteria=success_criteria,
        allowed_agents=allowed_agent,
        max_iterations=max_iterations,
        run_mode=mode,
        involvement_level=involvement,
    )
    if resolved.objective_text is None:
        prompted_objective = typer.prompt("Goal")
        resolved = resolve_project_run_config(
            settings,
            profile=profile,
            objective=prompted_objective,
            harness=harness,
            success_criteria=success_criteria,
            allowed_agents=allowed_agent,
            max_iterations=max_iterations,
            run_mode=mode,
            involvement_level=involvement,
        )
    effective_mode = resolved.run_mode
    if timeout is not None and effective_mode is not RunMode.RESUMABLE:
        raise typer.BadParameter("--timeout is currently supported only with --mode resumable.")
    operation_id = str(uuid4())
    projector = CliEventProjector(json_mode=json_mode)
    service = build_projected_service(settings, operation_id=operation_id, projector=projector)
    attached_sessions, goal_metadata = _build_run_goal_metadata(
        settings=settings,
        resolved=resolved,
        data_dir_source=data_dir_source,
        profile=profile,
        selected_profile_path=selected_profile_path,
        profile_source=profile_source,
        from_ticket=from_ticket,
        intake_result=intake_result,
        objective=objective,
        attach_session=attach_session,
        attach_agent=attach_agent,
        attach_name=attach_name,
        attach_working_dir=attach_working_dir,
    )
    if not json_mode:
        typer.echo(f"# data_dir={settings.data_dir} source={data_dir_source}", err=True)
        if profile is not None:
            typer.echo(
                "# project_profile="
                f"{profile.name} source={profile_source or 'unknown'}"
                + (f" path={selected_profile_path}" if selected_profile_path is not None else ""),
                err=True,
            )
    if not (wait and json_mode):
        projector.emit_operation(operation_id)
    assert resolved.objective_text is not None
    goal = OperationGoal(
        objective=resolved.objective_text,
        harness_instructions=resolved.harness_instructions,
        success_criteria=resolved.success_criteria,
        metadata=goal_metadata,
        external_ticket=intake_result.ticket if intake_result is not None else None,
    )
    policy = OperationPolicy(
        allowed_agents=resolved.default_agents,
        involvement_level=resolved.involvement_level,
    )
    budget = ExecutionBudget(max_iterations=resolved.max_iterations)
    runtime_hints = RuntimeHints(operator_message_window=resolved.message_window)
    options = RunOptions(
        run_mode=effective_mode,
        background_runtime_mode=(
            BackgroundRuntimeMode.ATTACHED_LIVE
            if effective_mode is RunMode.ATTACHED
            else BackgroundRuntimeMode.RESUMABLE_WAKEUP
        ),
    )
    if use_v2:
        v2_service = build_v2_service(
            settings,
            event_sink=ProjectingEventSink(
                build_event_sink(settings, operation_id),
                projector.handle_event,
            ),
        )
        outcome = await v2_service.run(
            goal,
            options,
            operation_id=operation_id,
            policy=policy,
            budget=budget,
            runtime_hints=runtime_hints,
        )
    else:
        outcome = await run_with_startup_failure_handling(
            service=service,
            goal=goal,
            policy=policy,
            budget=budget,
            runtime_hints=runtime_hints,
            options=options,
            operation_id=operation_id,
            attached_sessions=attached_sessions or None,
        )
    if wait and effective_mode is RunMode.RESUMABLE:
        outcome = await _wait_for_operation_outcome(
            operation_id=operation_id,
            poll_interval=0.5,
            timeout=timeout,
            json_mode=json_mode,
        )
    await emit_run_outcome(
        outcome=outcome,
        operation_id=operation_id,
        effective_mode=effective_mode,
        wait=wait,
        brief=brief,
        json_mode=json_mode,
        projector=projector,
    )


async def converse_async(
    operation_ref: str | None,
    project: str | None,
    context_level: str,
) -> None:
    await converse_loop_async(
        operation_ref=operation_ref,
        project=project,
        context_level=context_level,
        build_brain=build_brain,
        load_settings=load_settings,
        build_store=build_store,
        build_event_sink=build_event_sink,
        execute_command=_execute_converse_command,
    )


async def stop_turn_async(operation_id: str, task_id: str | None = None) -> None:
    service = delivery_commands_service()
    try:
        command = await service.enqueue_stop_turn(operation_id, task_id=task_id)
    except RuntimeError as exc:
        raise typer.BadParameter(str(exc)) from exc
    typer.echo(f"enqueued: {command.command_type.value} [{command.command_id}]")


async def answer_async(
    operation_id: str,
    attention_id: str | None,
    text: str,
    promote: bool,
    policy_title: str | None,
    policy_text: str | None,
    policy_category: str,
    policy_objective_keyword: list[str] | None,
    policy_task_keyword: list[str] | None,
    policy_agent: list[str] | None,
    policy_run_mode: list[RunMode] | None,
    policy_involvement: list[InvolvementLevel] | None,
    policy_rationale: str | None,
    json_mode: bool,
) -> None:
    service = delivery_commands_service()
    try:
        policy_payload = service.build_policy_decision_payload(
            promote=promote,
            category=policy_category,
            title=policy_title,
            text=policy_text,
            objective_keyword=policy_objective_keyword,
            task_keyword=policy_task_keyword,
            agent=policy_agent,
            run_mode=policy_run_mode,
            involvement=policy_involvement,
            rationale=policy_rationale,
        )
        answer_command, policy_command, outcome = await service.answer_attention(
            operation_id,
            attention_id=attention_id,
            text=text,
            promote=promote,
            policy_payload=policy_payload,
        )
    except RuntimeError as exc:
        raise typer.BadParameter(str(exc)) from exc
    if json_mode:
        typer.echo(
            json.dumps(
                {
                    "operation_id": operation_id,
                    "answer_command": answer_command.model_dump(mode="json"),
                    "policy_command": (
                        policy_command.model_dump(mode="json")
                        if policy_command is not None
                        else None
                    ),
                    "outcome": outcome.model_dump(mode="json") if outcome is not None else None,
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        if outcome is not None and outcome.status is not OperationStatus.RUNNING:
            raise_for_operation_status(outcome.status)
        return
    typer.echo(f"enqueued: {answer_command.command_type.value} [{answer_command.command_id}]")
    if policy_command is not None:
        typer.echo(f"enqueued: {policy_command.command_type.value} [{policy_command.command_id}]")
    if outcome is not None:
        typer.echo(f"{outcome.status.value}: {outcome.summary}")
        if outcome.status is not OperationStatus.RUNNING:
            raise_for_operation_status(outcome.status)


async def enqueue_command_async(
    operation_id: str,
    command_type: OperationCommandType,
    text: str | None,
    auto_resume_when_paused: bool = False,
    target_scope: CommandTargetScope = CommandTargetScope.OPERATION,
    target_id: str | None = None,
    auto_resume_blocked_attention_id: str | None = None,
    success_criteria: list[str] | None = None,
    clear_success_criteria: bool = False,
    allowed_agents: list[str] | None = None,
    max_iterations: int | None = None,
    model: str | None = None,
    effort: str | None = None,
    wait_for_ack: bool = False,
) -> None:
    service = delivery_commands_service()
    try:
        if model is None and effort is None:
            payload = service.build_command_payload(
                command_type,
                text,
                success_criteria,
                clear_success_criteria,
                allowed_agents,
                max_iterations,
            )
        else:
            payload = service.build_command_payload(
                command_type=command_type,
                text=text,
                success_criteria=success_criteria,
                clear_success_criteria=clear_success_criteria,
                allowed_agents=allowed_agents,
                max_iterations=max_iterations,
                model=model,
                effort=effort,
            )
    except RuntimeError as exc:
        raise typer.BadParameter(str(exc)) from exc
    command, outcome, note = await service.enqueue_command(
        operation_id,
        command_type,
        payload,
        target_scope=target_scope,
        target_id=target_id or operation_id,
        auto_resume_when_paused=auto_resume_when_paused,
        auto_resume_blocked_attention_id=auto_resume_blocked_attention_id,
    )
    if wait_for_ack:
        operation = await service.store.load_operation(operation_id)
        if operation is not None and (
            operation.status
            in {
                OperationStatus.COMPLETED,
                OperationStatus.FAILED,
                OperationStatus.CANCELLED,
            }
            or operation.scheduler_state is SchedulerState.PAUSED
        ):
            await service.tick(operation_id)
        for _ in range(20):
            commands = await service.command_inbox.list(operation_id)
            updated = next(
                (item for item in commands if item.command_id == command.command_id),
                None,
            )
            if updated is None or updated.status is CommandStatus.PENDING:
                await anyio.sleep(0.05)
                continue
            if updated.status is CommandStatus.REJECTED:
                typer.echo(
                    f"Error: patch rejected - {updated.rejection_reason or 'unknown_rejection'}"
                )
                raise typer.Exit(1)
            typer.echo(f"accepted: {updated.command_type.value} [{updated.command_id}]")
            return
    typer.echo(f"enqueued: {command.command_type.value} [{command.command_id}]")
    if note is not None:
        typer.echo(note)
    if outcome is not None:
        typer.echo(f"{outcome.status.value}: {outcome.summary}")


async def enqueue_custom_command_async(
    operation_id: str,
    command_type: OperationCommandType,
    payload: dict[str, object],
    target_scope: CommandTargetScope,
    target_id: str,
) -> None:
    service = delivery_commands_service()
    command, _, _ = await service.enqueue_command(
        operation_id,
        command_type,
        payload,
        target_scope=target_scope,
        target_id=target_id,
    )
    typer.echo(f"enqueued: {command.command_type.value} [{command.command_id}]")
