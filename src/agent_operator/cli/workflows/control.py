from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, cast
from uuid import uuid4

import anyio
import typer
from rich.console import Console as RichConsole
from rich.live import Live

from agent_operator.application.ticketing import TicketIntakeService
from agent_operator.bootstrap import (
    build_event_sink,
    build_store,
    build_wakeup_inbox,
)
from agent_operator.bootstrap import (
    build_service as bootstrap_build_service,
)
from agent_operator.config import OperatorSettings, load_global_config
from agent_operator.domain import (
    AgentSessionHandle,
    BackgroundRuntimeMode,
    CommandStatus,
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
    SchedulerState,
    TaskStatus,
)
from agent_operator.runtime import (
    apply_effective_adapter_settings_snapshot,
    apply_project_profile_settings,
    load_project_profile_from_path,
    resolve_project_run_config,
    snapshot_effective_adapter_settings,
)

from ..helpers.exit_codes import EXIT_INTERNAL_ERROR, raise_for_operation_status
from ..helpers.rendering import (
    cli_projection_payload,
    format_live_event,
    format_live_snapshot,
    render_dashboard,
    render_watch_snapshot,
)
from ..helpers.resolution import resolve_project_profile_selection
from ..helpers.services import (
    build_operation_dashboard_query_service,
    build_projected_service,
    build_projecting_delivery_commands_service,
    build_status_query_service,
    delivery_commands_service,
    emit_free_mode_stub,
    load_settings,
    load_settings_with_data_dir,
)

if TYPE_CHECKING:
    from agent_operator.application import OperatorService


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


def _build_cli_service(settings: OperatorSettings) -> OperatorService:
    try:
        import agent_operator.cli.main as cli_main

        factory = getattr(cli_main, "build_service", bootstrap_build_service)
    except Exception:
        factory = bootstrap_build_service
    return cast("OperatorService", factory(settings))


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
    if intake_result is not None:
        goal_metadata["external_ticket_ref"] = from_ticket
        if objective is not None:
            goal_metadata["external_ticket_context"] = intake_result.goal_text
    goal_metadata["resolved_operator_launch"] = {
        "data_dir": str(settings.data_dir),
        "data_dir_source": data_dir_source,
        "profile_source": profile_source,
        "profile_path": str(selected_profile_path) if selected_profile_path is not None else None,
    }
    if profile is not None:
        goal_metadata["project_profile_name"] = profile.name
        goal_metadata["policy_scope"] = f"profile:{profile.name}"
        goal_metadata["effective_adapter_settings"] = snapshot_effective_adapter_settings(
            settings,
            adapter_keys=resolved.default_agents,
        )
        goal_metadata["resolved_project_profile"] = resolved.model_dump(mode="json")
        ticket_reporting = getattr(profile, "ticket_reporting", None)
        if ticket_reporting is not None and hasattr(ticket_reporting, "model_dump"):
            goal_metadata["ticket_reporting"] = ticket_reporting.model_dump(mode="json")
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
    if not (wait and json_mode):
        projector.emit_operation(operation_id)
    assert resolved.objective_text is not None
    try:
        outcome = await service.run(
            OperationGoal(
                objective=resolved.objective_text,
                harness_instructions=resolved.harness_instructions,
                success_criteria=resolved.success_criteria,
                metadata=goal_metadata,
                external_ticket=intake_result.ticket if intake_result is not None else None,
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
    except Exception:
        store = build_store(settings)
        state = await store.load_operation(operation_id)
        if state is not None:
            summary = "Operation failed during startup."
            exc_type, exc, _tb = sys.exc_info()
            if exc is not None:
                summary = str(exc) or summary
            operation_terminal = state.status in {
                OperationStatus.COMPLETED,
                OperationStatus.FAILED,
                OperationStatus.CANCELLED,
            }
            root_task_terminal = bool(state.tasks) and state.tasks[0].status in {
                TaskStatus.COMPLETED,
                TaskStatus.FAILED,
                TaskStatus.CANCELLED,
            }
            if not operation_terminal and not root_task_terminal:
                state.status = OperationStatus.FAILED
                state.final_summary = summary
                state.objective_state.summary = summary
                state.updated_at = datetime.now(UTC)
                if state.tasks:
                    root_task = state.tasks[0]
                    if root_task.status not in {
                        TaskStatus.COMPLETED,
                        TaskStatus.FAILED,
                        TaskStatus.CANCELLED,
                    }:
                        root_task.status = TaskStatus.FAILED
                        root_task.updated_at = state.updated_at
                await store.save_operation(state)
                await store.save_outcome(
                    OperationOutcome(
                        operation_id=operation_id,
                        status=OperationStatus.FAILED,
                        summary=summary,
                        ended_at=state.updated_at,
                    )
                )
        raise
    if wait and effective_mode is RunMode.RESUMABLE:
        outcome = await _wait_for_operation_outcome(
            operation_id=operation_id,
            poll_interval=0.5,
            timeout=timeout,
            json_mode=json_mode,
        )
    if wait:
        if json_mode:
            typer.echo(
                json.dumps(
                    {
                        "operation_id": outcome.operation_id,
                        "status": outcome.status.value,
                        "summary": outcome.summary,
                        "metadata": outcome.metadata,
                    },
                    indent=2,
                    ensure_ascii=False,
                )
            )
        elif brief:
            status_service = build_status_query_service(load_settings())
            operation, _, _, _ = await status_service.build_status_payload(operation_id)
            iteration_count = len(operation.iterations) if operation is not None else 0
            typer.echo(
                "STATUS="
                f"{outcome.status.value} OPERATION={outcome.operation_id} "
                f"ITERATIONS={iteration_count}"
            )
        else:
            projector.emit_outcome(outcome)
        raise_for_operation_status(outcome.status)
    projector.emit_outcome(outcome)


async def watch_async(operation_id: str, once: bool, json_mode: bool, poll_interval: float) -> None:
    settings = load_settings()
    event_sink = build_event_sink(settings, operation_id)
    projector = CliEventProjector(json_mode=json_mode)
    status_queries = build_status_query_service(settings)
    try:
        _, outcome, _, _ = await status_queries.build_status_payload(operation_id)
    except RuntimeError as exc:
        raise typer.BadParameter(str(exc)) from exc
    use_live_tty = not json_mode and sys.stdout.isatty() and sys.stdin.isatty()
    if not use_live_tty and not (once and json_mode):
        projector.emit_operation(operation_id)
    seen_event_ids: set[str] = set()
    latest_update: str | None = None
    for event in event_sink.iter_events(operation_id):
        seen_event_ids.add(event.event_id)
        rendered = format_live_event(event)
        if rendered is not None:
            latest_update = rendered
            if not use_live_tty:
                typer.echo(rendered)
    last_snapshot: dict[str, object] | None = None
    if once:
        operation, outcome, _, _ = await status_queries.build_status_payload(operation_id)
        snapshot = status_queries.build_live_snapshot(operation_id, operation, outcome)
        if json_mode:
            typer.echo(json.dumps(snapshot, indent=2, ensure_ascii=False))
        else:
            projector.emit_snapshot(snapshot)
        if outcome is not None and outcome.status is not OperationStatus.RUNNING:
            projector.emit_outcome(outcome)
        return
    if use_live_tty:
        console = RichConsole()
        initial_operation, initial_outcome, _, _ = await status_queries.build_status_payload(
            operation_id
        )
        initial_snapshot = status_queries.build_live_snapshot(
            operation_id, initial_operation, initial_outcome
        )
        last_snapshot = initial_snapshot
        with Live(
            render_watch_snapshot(initial_snapshot, latest_update=latest_update),
            console=console,
            refresh_per_second=4,
        ) as live:
            while True:
                for event in event_sink.iter_events(operation_id):
                    if event.event_id in seen_event_ids:
                        continue
                    seen_event_ids.add(event.event_id)
                    rendered = format_live_event(event)
                    if rendered is not None:
                        latest_update = rendered
                operation, outcome, _, _ = await status_queries.build_status_payload(operation_id)
                snapshot = status_queries.build_live_snapshot(operation_id, operation, outcome)
                if snapshot != last_snapshot:
                    last_snapshot = snapshot
                live.update(
                    render_watch_snapshot(last_snapshot, latest_update=latest_update),
                    refresh=True,
                )
                if outcome is not None and outcome.status is not OperationStatus.RUNNING:
                    console.print(f"{outcome.status.value}: {outcome.summary}")
                    return
                await anyio.sleep(poll_interval)
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


async def _wait_for_operation_outcome(
    *,
    operation_id: str,
    poll_interval: float,
    timeout: float | None,
    json_mode: bool,
) -> OperationOutcome:
    """Poll operation state until it reaches a terminal or needs-human status."""
    service = build_status_query_service(load_settings())
    deadline = anyio.current_time() + timeout if timeout is not None else None
    while True:
        _, outcome, _, _ = await service.build_status_payload(operation_id)
        if outcome is not None and outcome.status is not OperationStatus.RUNNING:
            return outcome
        if deadline is not None and anyio.current_time() >= deadline:
            if json_mode:
                typer.echo(
                    json.dumps(
                        {
                            "operation_id": operation_id,
                            "status": "timeout",
                            "summary": "Timed out while waiting for operation state.",
                        },
                        indent=2,
                        ensure_ascii=False,
                    )
                )
            else:
                typer.echo("Timed out while waiting for operation state.")
            raise typer.Exit(code=EXIT_INTERNAL_ERROR)
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
    await _restore_operation_scoped_runtime_settings(settings, operation_id)
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


async def _resolve_ask_operation_id(operation_ref: str) -> str:
    settings = load_settings()
    store = build_store(settings)
    summaries = await store.list_operations()
    if operation_ref == "last":
        if not summaries:
            raise RuntimeError("No persisted operations were found.")
        states = [
            operation
            for summary in summaries
            if (operation := await store.load_operation(summary.operation_id)) is not None
        ]
        if not states:
            raise RuntimeError("No persisted operations were found.")
        return max(states, key=lambda item: item.created_at).operation_id
    exact = next(
        (item.operation_id for item in summaries if item.operation_id == operation_ref),
        None,
    )
    if exact is not None:
        return exact
    prefix_matches = [
        item.operation_id for item in summaries if item.operation_id.startswith(operation_ref)
    ]
    if len(prefix_matches) == 1:
        return prefix_matches[0]
    if len(prefix_matches) > 1:
        raise RuntimeError(
            f"Operation reference {operation_ref!r} is ambiguous. Matches: "
            + ", ".join(sorted(prefix_matches))
        )
    profile_matches = []
    for summary in summaries:
        operation = await store.load_operation(summary.operation_id)
        if operation is None:
            continue
        profile_name = operation.goal.metadata.get("project_profile_name")
        if isinstance(profile_name, str) and profile_name == operation_ref:
            profile_matches.append(operation)
    if profile_matches:
        return max(profile_matches, key=lambda item: item.created_at).operation_id
    raise RuntimeError(f"Operation {operation_ref!r} was not found.")


async def ask_async(operation_ref: str, question: str, json_mode: bool) -> None:
    settings = load_settings()
    try:
        operation_id = await _resolve_ask_operation_id(operation_ref)
        service = _build_cli_service(settings)
        answer = (await service.answer_question(operation_id, question)).strip()
    except RuntimeError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=EXIT_INTERNAL_ERROR) from exc
    if json_mode:
        typer.echo(
            json.dumps(
                {
                    "question": question,
                    "answer": answer,
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        return
    typer.echo(f"Question: {question}\n")
    typer.echo(answer)


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
    await _restore_operation_scoped_runtime_settings(settings, operation_id)
    projector = CliEventProjector(json_mode=json_mode)
    if json_mode:
        projector.emit_operation(operation_id)
    delivery = build_projecting_delivery_commands_service(
        settings, operation_id=operation_id, projector=projector
    )
    outcome = await delivery.recover(operation_id, session_id=session_id, max_cycles=max_cycles)
    projector.emit_outcome(outcome)


async def cancel_async(
    operation_id: str,
    session_id: str | None,
    run_id: str | None,
    json_mode: bool,
) -> None:
    service = delivery_commands_service()
    outcome = await service.cancel(operation_id, session_id=session_id, run_id=run_id)
    if json_mode:
        typer.echo(
            json.dumps(
                {
                    "operation_id": outcome.operation_id,
                    "status": outcome.status.value,
                    "summary": outcome.summary,
                    "metadata": outcome.metadata,
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        raise_for_operation_status(outcome.status)
    typer.echo(f"{outcome.status.value}: {outcome.summary}")
    typer.echo(f"operation_id={outcome.operation_id}", err=True)
    raise_for_operation_status(outcome.status)


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
    wait_for_ack: bool = False,
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


async def _restore_operation_scoped_runtime_settings(
    settings: OperatorSettings, operation_id: str
) -> None:
    operation = await build_store(settings).load_operation(operation_id)
    if operation is None:
        return
    metadata = operation.goal.metadata if operation.goal is not None else {}
    snapshot = metadata.get("effective_adapter_settings")
    if isinstance(snapshot, dict):
        apply_effective_adapter_settings_snapshot(settings, snapshot)
        return
    profile_path = metadata.get("project_profile_path")
    if not isinstance(profile_path, str):
        return
    candidate = Path(profile_path)
    if not candidate.is_file():
        return
    try:
        profile = load_project_profile_from_path(candidate)
    except Exception:
        return
    apply_project_profile_settings(settings, profile)
