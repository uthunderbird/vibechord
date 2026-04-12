from __future__ import annotations

import json
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Protocol

import anyio
import typer
from rich.console import Console as RichConsole
from rich.live import Live

from agent_operator.bootstrap import (
    build_background_run_inspection_store,
    build_brain,
    build_history_ledger,
    build_store,
    build_trace_store,
    build_wakeup_inbox,
)
from agent_operator.cli.tui import build_fleet_workbench_controller, run_fleet_workbench
from agent_operator.domain import CommandTargetScope, OperationCommandType, OperationStatus
from agent_operator.runtime import (
    AgendaSnapshot,
    discover_local_project_profile,
    find_codex_session_log,
    format_claude_log_event,
    format_codex_log_event,
    iter_claude_log_events,
    iter_codex_log_events,
    load_claude_log_events,
    load_codex_log_events,
    resolve_project_run_config,
)

from ..helpers.logs import (
    format_opencode_log_event,
    iter_opencode_log_events,
    load_opencode_log_events,
    resolve_claude_log_path_for_session,
    resolve_jsonl_log_path_for_session,
    resolve_log_target,
)
from ..helpers.rendering import (
    build_runtime_alert,
    cli_projection_payload,
    latest_agent_turn_brief,
    render_fleet_dashboard,
    render_operation_list_line,
    render_project_dashboard,
    shorten_live_text,
    turn_work_summary,
)
from ..helpers.resolution import (
    resolve_history_entry,
    resolve_operation_id,
    resolve_project_profile_selection,
)
from ..helpers.services import (
    build_agenda_query_service,
    build_delivery_commands_service,
    build_fleet_workbench_query_service,
    build_operation_dashboard_query_service,
    build_project_dashboard_query_service,
    delivery_commands_service,
    load_settings,
)


class _EnqueuedCommandLike(Protocol):
    command_type: OperationCommandType
    command_id: str


class _OutcomeLike(Protocol):
    status: OperationStatus
    summary: str


def _build_enqueued_command_message(
    command: _EnqueuedCommandLike,
    outcome: _OutcomeLike | None,
    note: str | None,
) -> str:
    """Format a command-dispatch confirmation in the same style as CLI control commands."""
    message = f"enqueued: {command.command_type.value} [{command.command_id}]"
    if note is not None:
        message += f" | {note}"
    if outcome is not None:
        message += f" | {outcome.status.value}: {outcome.summary}"
    return message


async def _load_agenda_snapshot(
    *, project: str | None, include_all: bool
) -> AgendaSnapshot:
    settings = load_settings()
    service = build_agenda_query_service(settings)
    return await service.load_snapshot(project=project, include_recent=include_all)


async def _load_fleet_workbench_payload(
    *, project: str | None, include_all: bool
) -> dict[str, object]:
    settings = load_settings()
    service = build_fleet_workbench_query_service(settings)
    return await service.load_payload(project=project, include_recent=include_all)


async def has_any_operations_async() -> bool:
    snapshot = await _load_agenda_snapshot(project=None, include_all=False)
    return snapshot.total_operations > 0


async def list_async(json_mode: bool) -> None:
    settings = load_settings()
    store = build_store(settings)
    trace_store = build_trace_store(settings)
    inbox = build_wakeup_inbox(settings)
    supervisor = build_background_run_inspection_store(settings)
    for summary in await store.list_operations():
        wakeups = inbox.read_all(summary.operation_id)
        background_runs = [
            item.model_dump(mode="json")
            for item in await supervisor.list_runs(summary.operation_id)
        ]
        runtime_alert = build_runtime_alert(
            status=summary.status, wakeups=wakeups, background_runs=background_runs
        )
        brief = await trace_store.load_brief_bundle(summary.operation_id)
        if brief is not None and brief.operation_brief is not None:
            if json_mode:
                payload = brief.operation_brief.model_dump(mode="json")
                if runtime_alert is not None:
                    payload["runtime_alert"] = runtime_alert
                typer.echo(json.dumps(payload, ensure_ascii=False))
            else:
                operation_brief = brief.operation_brief
                latest_turn = latest_agent_turn_brief(brief)
                focus = (
                    shorten_live_text(operation_brief.focus_brief, limit=28)
                    if operation_brief.focus_brief
                    else None
                )
                latest = shorten_live_text(
                    turn_work_summary(latest_turn) or operation_brief.latest_outcome_brief, limit=56
                )
                blocker = shorten_live_text(operation_brief.blocker_brief, limit=48)
                scheduler = (
                    operation_brief.scheduler_state.value
                    if operation_brief.scheduler_state.value != "active"
                    else None
                )
                involvement = (
                    operation_brief.involvement_level.value
                    if operation_brief.involvement_level.value != "auto"
                    else None
                )
                typer.echo(
                    render_operation_list_line(
                        operation_brief.operation_id,
                        operation_brief.status.value,
                        objective=operation_brief.objective_brief,
                        focus=focus,
                        latest=latest,
                        blocker=blocker,
                        runtime_alert=shorten_live_text(runtime_alert, limit=48),
                        scheduler=scheduler,
                        involvement=involvement,
                    )
                )
            continue
        payload = summary.model_dump(mode="json")
        if runtime_alert is not None:
            payload["runtime_alert"] = runtime_alert
        if json_mode:
            typer.echo(json.dumps(payload, ensure_ascii=False))
        else:
            typer.echo(
                render_operation_list_line(
                    summary.operation_id,
                    summary.status.value,
                    objective=shorten_live_text(summary.objective_prompt, limit=96)
                    or summary.objective_prompt,
                    focus=shorten_live_text(summary.focus, limit=28),
                    latest=shorten_live_text(summary.final_summary, limit=56),
                    blocker=None,
                    runtime_alert=shorten_live_text(runtime_alert, limit=48),
                )
            )


async def history_async(operation_ref: str | None, json_mode: bool) -> None:
    settings = load_settings()
    ledger = build_history_ledger(settings)
    profile_selection = discover_local_project_profile(settings)
    if profile_selection.profile is not None and not profile_selection.profile.history_ledger:
        typer.echo("Committed history ledger is disabled for this project.")
        return
    entries = [entry.model_dump(mode="json") for entry in ledger.list_entries()]
    if operation_ref is not None:
        entries = [resolve_history_entry(operation_ref, entries)]
    if json_mode:
        typer.echo(json.dumps(entries, indent=2, ensure_ascii=False))
        return
    if not entries:
        typer.echo("No committed history entries yet.")
        return
    for entry in entries:
        line = (
            f"{entry['op_id']} {str(entry['status']).upper()} "
            f"{entry['goal']} [reason={entry['stop_reason']}]"
        )
        profile = entry.get("profile")
        if isinstance(profile, str) and profile.strip():
            line += f" [profile={profile}]"
        typer.echo(line)


async def ask_async(operation_id: str, question: str, json_mode: bool) -> None:
    settings = load_settings()
    store = build_store(settings)
    operation = await store.load_operation(operation_id)
    if operation is None:
        raise typer.Exit(code=4)
    brain = build_brain(settings)
    answer = (await brain.answer_question(operation, question)).strip()
    if json_mode:
        typer.echo(
            json.dumps(
                {
                    "operation_id": operation_id,
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


async def agenda_async(project: str | None, include_all: bool, json_mode: bool) -> None:
    from ..helpers.rendering import print_agenda_section

    snapshot = await _load_agenda_snapshot(project=project, include_all=include_all)
    if json_mode:
        typer.echo(json.dumps(snapshot.model_dump(mode="json"), indent=2, ensure_ascii=False))
        return
    typer.echo("Agenda")
    if project is not None:
        typer.echo(f"Project: {project}")
    typer.echo(f"Operations: {snapshot.total_operations}")
    print_agenda_section("Needs attention:", snapshot.needs_attention)
    print_agenda_section("Active:", snapshot.active)
    if snapshot.recent:
        print_agenda_section("Recent:", snapshot.recent)


async def _compat_fleet_tui_async(
    project: str | None, include_all: bool, poll_interval: float
) -> None:
    import agent_operator.cli.main as cli_main

    callback = getattr(cli_main, "_fleet_tui_async", fleet_tui_async)
    await callback(project, include_all, poll_interval)


async def fleet_async(
    project: str | None, include_all: bool, once: bool, json_mode: bool, poll_interval: float
) -> None:
    if sys.stdout.isatty() and sys.stdin.isatty() and not once and not json_mode:
        await _compat_fleet_tui_async(project, include_all, poll_interval)
        return

    async def load_payload() -> dict[str, object]:
        payload = await _load_fleet_workbench_payload(project=project, include_all=include_all)
        return cli_projection_payload(payload)

    payload = await load_payload()
    if json_mode:
        typer.echo(json.dumps(payload, indent=2, ensure_ascii=False))
        return
    console = RichConsole()
    if once:
        console.print(render_fleet_dashboard(payload))
        return
    with Live(render_fleet_dashboard(payload), console=console, refresh_per_second=4) as live:
        while True:
            payload = await load_payload()
            live.update(render_fleet_dashboard(payload), refresh=True)
            await anyio.sleep(poll_interval)


async def fleet_tui_async(project: str | None, include_all: bool, poll_interval: float) -> None:
    settings = load_settings()
    codex_home = Path.home() / ".codex"

    async def load_payload() -> dict[str, object]:
        return await _load_fleet_workbench_payload(project=project, include_all=include_all)

    async def load_operation_payload(operation_id: str) -> dict[str, object] | None:
        queries = build_operation_dashboard_query_service(
            settings, operation_id=operation_id, codex_home=codex_home
        )
        return await queries.load_payload(operation_id)

    async def enqueue_simple_command(
        operation_id: str,
        command_type: OperationCommandType,
        *,
        auto_resume_when_paused: bool = False,
    ) -> str:
        """CLI-equivalent control action used by TUI state transitions."""
        delivery = build_delivery_commands_service(settings)
        command, outcome, note = await delivery.enqueue_command(
            operation_id,
            command_type,
            {},
            target_scope=CommandTargetScope.OPERATION,
            target_id=operation_id,
            auto_resume_when_paused=auto_resume_when_paused,
        )
        return _build_enqueued_command_message(command, outcome, note)

    async def interrupt_operation(operation_id: str, task_id: str | None) -> str:
        """CLI-equivalent of `operator interrupt <operation_id> [--task ...]`."""
        delivery = build_delivery_commands_service(settings)
        command = await delivery.enqueue_stop_turn(operation_id, task_id=task_id)
        return _build_enqueued_command_message(command, None, None)

    async def answer_attention(operation_id: str, attention_id: str, text: str) -> str:
        """CLI-equivalent of `operator answer <operation_id> <attention_id> --text ...`."""
        delivery = build_delivery_commands_service(settings)
        answer_command, _, outcome = await delivery.answer_attention(
            operation_id,
            attention_id=attention_id,
            text=text,
            promote=False,
            policy_payload={},
        )
        return _build_enqueued_command_message(answer_command, outcome, None)

    async def cancel_operation(operation_id: str) -> str:
        """CLI-equivalent of `operator cancel <operation_id>`."""
        outcome = await delivery_commands_service().cancel(
            operation_id, session_id=None, run_id=None
        )
        return f"{outcome.status.value}: {outcome.summary}"

    controller = build_fleet_workbench_controller(
        load_payload=load_payload,
        load_operation_payload=load_operation_payload,
        pause_operation=lambda operation_id: enqueue_simple_command(
            operation_id, OperationCommandType.PAUSE_OPERATOR
        ),
        unpause_operation=lambda operation_id: enqueue_simple_command(
            operation_id,
            OperationCommandType.RESUME_OPERATOR,
            auto_resume_when_paused=True,
        ),
        interrupt_operation=interrupt_operation,
        answer_attention=answer_attention,
        cancel_operation=cancel_operation,
    )
    await run_fleet_workbench(controller=controller, poll_interval=poll_interval)


async def project_dashboard_async(
    name: str | None, once: bool, json_mode: bool, poll_interval: float
) -> None:
    async def load_payload() -> dict[str, object]:
        settings = load_settings()
        try:
            profile, selected_path, _ = resolve_project_profile_selection(settings, name=name)
        except RuntimeError as exc:
            raise typer.BadParameter(str(exc)) from exc
        if profile is None:
            raise typer.BadParameter("No local operator-profile.yaml was found.")
        resolved = resolve_project_run_config(
            settings,
            profile=profile,
            objective=None,
            harness=None,
            success_criteria=None,
            allowed_agents=None,
            max_iterations=None,
            run_mode=None,
            involvement_level=None,
        )
        payload = await build_project_dashboard_query_service(settings).load_payload(
            profile=profile,
            resolved=resolved,
            profile_path=selected_path if selected_path is not None else Path("."),
        )
        return cli_projection_payload(payload)

    payload = await load_payload()
    if json_mode:
        typer.echo(json.dumps(payload, indent=2, ensure_ascii=False))
        return
    console = RichConsole()
    if once:
        console.print(render_project_dashboard(payload))
        return
    with Live(render_project_dashboard(payload), console=console, refresh_per_second=4) as live:
        while True:
            payload = await load_payload()
            live.update(render_project_dashboard(payload), refresh=True)
            await anyio.sleep(poll_interval)


async def log_async(
    operation_ref: str,
    *,
    limit: int,
    follow: bool,
    agent: str,
    json_mode: bool,
    codex_home: Path,
) -> None:
    resolved_operation_id = resolve_operation_id(operation_ref)
    settings = load_settings()
    store = build_store(settings)
    operation = await store.load_operation(resolved_operation_id)
    if operation is None:
        raise typer.BadParameter(f"Operation {resolved_operation_id!r} was not found.")
    log_kind, session = resolve_log_target(operation, agent=agent)
    if log_kind == "codex":
        path = find_codex_session_log(codex_home, session.session_id)
        if path is None:
            raise typer.BadParameter(
                "Codex transcript for session "
                f"{session.session_id!r} was not found under {str(codex_home)!r}."
            )
        if follow:
            typer.echo(f"# Codex log for operation {resolved_operation_id}")
            typer.echo(f"# session={session.session_id}")
            typer.echo(f"# file={path}")
            for codex_event in iter_codex_log_events(path, follow=True):
                typer.echo(
                    json.dumps(asdict(codex_event), ensure_ascii=False)
                    if json_mode
                    else format_codex_log_event(codex_event)
                )
            return
        codex_events = load_codex_log_events(path)[-limit:]
        if json_mode:
            typer.echo(
                json.dumps(
                    {
                        "operation_id": resolved_operation_id,
                        "session_id": session.session_id,
                        "path": str(path),
                        "agent": "codex",
                        "events": [asdict(codex_event) for codex_event in codex_events],
                    },
                    indent=2,
                    ensure_ascii=False,
                )
            )
            return
        typer.echo(f"# Codex log for operation {resolved_operation_id}")
        typer.echo(f"# session={session.session_id}")
        typer.echo(f"# file={path}")
        for codex_event in codex_events:
            typer.echo(format_codex_log_event(codex_event))
        return
    if log_kind == "claude":
        path = resolve_claude_log_path_for_session(session)
        if follow:
            typer.echo(f"# Claude log for operation {resolved_operation_id}")
            typer.echo(f"# session={session.session_id}")
            typer.echo(f"# file={path}")
            for claude_event in iter_claude_log_events(path, follow=True):
                typer.echo(
                    json.dumps(asdict(claude_event), ensure_ascii=False)
                    if json_mode
                    else format_claude_log_event(claude_event)
                )
            return
        claude_events = load_claude_log_events(path)[-limit:]
        if json_mode:
            typer.echo(
                json.dumps(
                    {
                        "operation_id": resolved_operation_id,
                        "session_id": session.session_id,
                        "path": str(path),
                        "agent": "claude",
                        "events": [asdict(claude_event) for claude_event in claude_events],
                    },
                    indent=2,
                    ensure_ascii=False,
                )
            )
            return
        typer.echo(f"# Claude log for operation {resolved_operation_id}")
        typer.echo(f"# session={session.session_id}")
        typer.echo(f"# file={path}")
        for claude_event in claude_events:
            typer.echo(format_claude_log_event(claude_event))
        return
    path = resolve_jsonl_log_path_for_session(session, provider="OpenCode")
    if follow:
        typer.echo(f"# OpenCode log for operation {resolved_operation_id}")
        typer.echo(f"# session={session.session_id}")
        typer.echo(f"# file={path}")
        for opencode_event in iter_opencode_log_events(path, follow=True):
            typer.echo(
                json.dumps(asdict(opencode_event), ensure_ascii=False)
                if json_mode
                else format_opencode_log_event(opencode_event)
            )
        return
    opencode_events = load_opencode_log_events(path)[-limit:]
    if json_mode:
        typer.echo(
            json.dumps(
                {
                    "operation_id": resolved_operation_id,
                    "session_id": session.session_id,
                    "path": str(path),
                    "agent": "opencode",
                    "events": [asdict(opencode_event) for opencode_event in opencode_events],
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        return
    typer.echo(f"# OpenCode log for operation {resolved_operation_id}")
    typer.echo(f"# session={session.session_id}")
    typer.echo(f"# file={path}")
    for opencode_event in opencode_events:
        typer.echo(format_opencode_log_event(opencode_event))
