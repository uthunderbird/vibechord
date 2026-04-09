from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

import anyio
import typer
from rich.console import Console as RichConsole
from rich.live import Live

from agent_operator.bootstrap import build_event_sink, build_wakeup_inbox
from agent_operator.domain import (
    AgentSessionHandle,
    BackgroundRuntimeMode,
    CommandTargetScope,
    ExecutionBudget,
    InvolvementLevel,
    OperationCommandType,
    OperationGoal,
    OperationOutcome,
    OperationPolicy,
    OperationStatus,
    RunEvent,
    RunMode,
    RunOptions,
    RuntimeHints,
)
from agent_operator.runtime import apply_project_profile_settings, resolve_project_run_config

from ..helpers_rendering import (
    cli_projection_payload,
    format_live_event,
    format_live_snapshot,
    render_dashboard,
)
from ..helpers_resolution import resolve_project_profile_selection
from ..helpers_services import (
    build_operation_dashboard_query_service,
    build_projected_service,
    build_projecting_delivery_commands_service,
    build_status_query_service,
    delivery_commands_service,
    emit_free_mode_stub,
    load_settings,
    load_settings_with_data_dir,
)


class CliEventProjector:
    def __init__(self, *, json_mode: bool) -> None:
        self._json_mode = json_mode

    def emit_operation(self, operation_id: str) -> None:
        if self._json_mode:
            typer.echo(
                json.dumps({"type": "operation", "operation_id": operation_id}, ensure_ascii=False)
            )
            return
        typer.echo(f"operation_id={operation_id}", err=True)

    def handle_event(self, event: RunEvent) -> None:
        if self._json_mode:
            typer.echo(
                json.dumps(
                    {"type": "event", "event": event.model_dump(mode="json")}, ensure_ascii=False
                )
            )
            return
        rendered = format_live_event(event)
        if rendered is not None:
            typer.echo(rendered)

    def emit_snapshot(self, snapshot: dict[str, object]) -> None:
        if self._json_mode:
            typer.echo(json.dumps({"type": "snapshot", "snapshot": snapshot}, ensure_ascii=False))
            return
        typer.echo(format_live_snapshot(snapshot))

    def emit_outcome(self, outcome: OperationOutcome) -> None:
        if self._json_mode:
            typer.echo(
                json.dumps(
                    {"type": "outcome", "outcome": outcome.model_dump(mode="json")},
                    ensure_ascii=False,
                )
            )
            return
        typer.echo(f"{outcome.status.value}: {outcome.summary}")


async def run_async(
    objective: str | None,
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
    json_mode: bool,
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
    resolved = resolve_project_run_config(
        settings,
        profile=profile,
        objective=objective,
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
    operation_id = str(uuid4())
    projector = CliEventProjector(json_mode=json_mode)
    service = build_projected_service(settings, operation_id=operation_id, projector=projector)
    attached_sessions = []
    goal_metadata: dict[str, object] = {}
    if attach_session is not None:
        if attach_agent is None:
            raise typer.BadParameter("--attach-agent is required when --attach-session is used.")
        session_metadata: dict[str, str] = {}
        effective_attach_working_dir = attach_working_dir or resolved.cwd
        if effective_attach_working_dir is not None:
            session_metadata["working_directory"] = str(effective_attach_working_dir)
        attached_sessions.append(
            AgentSessionHandle(
                adapter_key=attach_agent,
                session_id=attach_session,
                session_name=attach_name,
                metadata=session_metadata,
            )
        )
        goal_metadata["requires_same_agent_session"] = True
        goal_metadata["attached_session_ids"] = [attach_session]
    effective_working_dir = attach_working_dir or resolved.cwd
    if effective_working_dir is not None:
        goal_metadata["working_directory"] = str(effective_working_dir)
    goal_metadata["resolved_operator_launch"] = {
        "data_dir": str(settings.data_dir),
        "data_dir_source": data_dir_source,
        "profile_source": profile_source,
        "profile_path": str(selected_profile_path) if selected_profile_path is not None else None,
    }
    if profile is not None:
        goal_metadata["project_profile_name"] = profile.name
        goal_metadata["policy_scope"] = f"profile:{profile.name}"
        goal_metadata["resolved_project_profile"] = resolved.model_dump(mode="json")
        if selected_profile_path is not None:
            goal_metadata["project_profile_path"] = str(selected_profile_path)
        if profile_source is not None:
            goal_metadata["project_profile_source"] = profile_source
        goal_metadata["data_dir_source"] = data_dir_source
    elif resolved.cwd is not None:
        goal_metadata["policy_scope"] = f"cwd:{resolved.cwd}"
    if not json_mode:
        typer.echo(f"# data_dir={settings.data_dir} source={data_dir_source}", err=True)
        if profile is not None:
            typer.echo(
                "# project_profile="
                f"{profile.name} source={profile_source or 'unknown'}"
                + (f" path={selected_profile_path}" if selected_profile_path is not None else ""),
                err=True,
            )
    projector.emit_operation(operation_id)
    outcome = await service.run(
        OperationGoal(
            objective=resolved.objective_text,
            harness_instructions=resolved.harness_instructions,
            success_criteria=resolved.success_criteria,
            metadata=goal_metadata,
        ),
        policy=OperationPolicy(
            allowed_agents=resolved.default_agents,
            involvement_level=resolved.involvement_level,
        ),
        budget=ExecutionBudget(max_iterations=resolved.max_iterations),
        runtime_hints=RuntimeHints(operator_message_window=resolved.message_window),
        options=RunOptions(
            run_mode=effective_mode,
            background_runtime_mode=(
                BackgroundRuntimeMode.ATTACHED_LIVE
                if effective_mode is RunMode.ATTACHED
                else BackgroundRuntimeMode.RESUMABLE_WAKEUP
            ),
        ),
        operation_id=operation_id,
        attached_sessions=attached_sessions or None,
    )
    projector.emit_outcome(outcome)


async def watch_async(operation_id: str, json_mode: bool, poll_interval: float) -> None:
    settings = load_settings()
    event_sink = build_event_sink(settings, operation_id)
    projector = CliEventProjector(json_mode=json_mode)
    status_queries = build_status_query_service(settings)
    try:
        _, outcome, _, _ = await status_queries.build_status_payload(operation_id)
    except RuntimeError as exc:
        raise typer.BadParameter(str(exc)) from exc
    projector.emit_operation(operation_id)
    seen_event_ids: set[str] = set()
    for event in event_sink.iter_events(operation_id):
        seen_event_ids.add(event.event_id)
        projector.handle_event(event)
    last_snapshot: dict[str, object] | None = None
    while True:
        for event in event_sink.iter_events(operation_id):
            if event.event_id in seen_event_ids:
                continue
            seen_event_ids.add(event.event_id)
            projector.handle_event(event)
        operation, outcome, _, _ = await status_queries.build_status_payload(operation_id)
        snapshot = status_queries.build_live_snapshot(operation_id, operation, outcome)
        if snapshot != last_snapshot:
            projector.emit_snapshot(snapshot)
            last_snapshot = snapshot
        if outcome is not None and outcome.status is not OperationStatus.RUNNING:
            projector.emit_outcome(outcome)
            return
        await anyio.sleep(poll_interval)


async def dashboard_async(
    operation_id: str,
    once: bool,
    json_mode: bool,
    poll_interval: float,
    codex_home: Path,
) -> None:
    settings = load_settings()
    queries = build_operation_dashboard_query_service(
        settings,
        operation_id=operation_id,
        codex_home=codex_home,
    )

    async def load_payload() -> dict[str, object]:
        try:
            payload = await queries.load_payload(operation_id)
        except RuntimeError as exc:
            raise typer.BadParameter(str(exc)) from exc
        return cli_projection_payload(payload)

    payload = await load_payload()
    if json_mode:
        typer.echo(json.dumps(payload, indent=2, ensure_ascii=False))
        return
    console = RichConsole()
    if once:
        console.print(render_dashboard(payload))
        return
    with Live(render_dashboard(payload), console=console, refresh_per_second=4) as live:
        while True:
            payload = await load_payload()
            live.update(render_dashboard(payload), refresh=True)
            if payload.get("status") != OperationStatus.RUNNING.value:
                return
            await anyio.sleep(poll_interval)


async def resume_async(operation_id: str, max_cycles: int, json_mode: bool) -> None:
    settings = load_settings()
    projector = CliEventProjector(json_mode=json_mode)
    if json_mode:
        projector.emit_operation(operation_id)
    delivery = build_projecting_delivery_commands_service(
        settings,
        operation_id=operation_id,
        projector=projector,
    )
    outcome = await delivery.resume(operation_id, max_cycles=max_cycles)
    projector.emit_outcome(outcome)


async def status_async(operation_id: str, json_mode: bool, brief: bool) -> None:
    service = build_status_query_service(load_settings())
    try:
        typer.echo(
            await service.render_status_output(operation_id, json_mode=json_mode, brief=brief)
        )
    except RuntimeError as exc:
        raise typer.BadParameter(str(exc)) from exc


async def tick_async(operation_id: str) -> None:
    service = delivery_commands_service()
    outcome = await service.tick(operation_id)
    typer.echo(f"{outcome.status.value}: {outcome.summary}")
    typer.echo(f"operation_id={outcome.operation_id}", err=True)


async def daemon_async(
    once: bool,
    poll_interval: float,
    max_cycles_per_operation: int,
    json_mode: bool,
) -> None:
    settings = load_settings()
    inbox = build_wakeup_inbox(settings)
    projector = CliEventProjector(json_mode=json_mode)
    delivery = build_projecting_delivery_commands_service(
        settings, operation_id="sweep", projector=projector
    )

    async def sweep() -> int:
        resumed = await delivery.daemon_sweep(
            ready_operation_ids=list(inbox.ready_operation_ids()),
            max_cycles_per_operation=max_cycles_per_operation,
            emit_operation=projector.emit_operation if json_mode else None,
            emit_outcome=projector.emit_outcome,
        )
        if json_mode:
            typer.echo(
                json.dumps({"daemon_once": True, "resumed_operations": resumed}, ensure_ascii=False)
            )
        elif resumed > 0:
            typer.echo(f"resumed_operations={resumed}")
        return resumed

    if once:
        await sweep()
        return
    while True:
        await sweep()
        await anyio.sleep(poll_interval)


async def recover_async(
    operation_id: str, session_id: str | None, max_cycles: int, json_mode: bool
) -> None:
    settings = load_settings()
    projector = CliEventProjector(json_mode=json_mode)
    if json_mode:
        projector.emit_operation(operation_id)
    delivery = build_projecting_delivery_commands_service(
        settings, operation_id=operation_id, projector=projector
    )
    outcome = await delivery.recover(operation_id, session_id=session_id, max_cycles=max_cycles)
    projector.emit_outcome(outcome)


async def cancel_async(operation_id: str, session_id: str | None, run_id: str | None) -> None:
    service = delivery_commands_service()
    outcome = await service.cancel(operation_id, session_id=session_id, run_id=run_id)
    typer.echo(f"{outcome.status.value}: {outcome.summary}")
    typer.echo(f"operation_id={outcome.operation_id}", err=True)


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
    typer.echo(f"enqueued: {answer_command.command_type.value} [{answer_command.command_id}]")
    if policy_command is not None:
        typer.echo(f"enqueued: {policy_command.command_type.value} [{policy_command.command_id}]")
    if outcome is not None:
        typer.echo(f"{outcome.status.value}: {outcome.summary}")


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
) -> None:
    service = delivery_commands_service()
    try:
        payload = service.build_command_payload(
            command_type,
            text,
            success_criteria,
            clear_success_criteria,
            allowed_agents,
            max_iterations,
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
