from __future__ import annotations

import json
import shlex
import sys
from collections.abc import Iterable
from dataclasses import asdict
from datetime import datetime
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
from agent_operator.config import OperatorSettings, load_global_config
from agent_operator.domain import CommandTargetScope, OperationCommandType, OperationStatus
from agent_operator.runtime import (
    AgendaSnapshot,
    add_project_root_parents,
    build_agenda_item,
    build_agenda_snapshot,
    discover_local_project_profile,
    discover_projects,
    discover_workspace_root,
    find_codex_session_log,
    format_claude_log_event,
    format_codex_log_event,
    iter_claude_log_events,
    iter_codex_log_events,
    load_claude_log_events,
    load_codex_log_events,
    project_name_for_root,
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
    PROJECTIONS,
    build_runtime_alert,
    cli_projection_payload,
    render_fleet_dashboard,
    render_operation_list_line,
    render_project_dashboard,
    shorten_live_text,
)
from ..helpers.resolution import (
    resolve_history_entry,
    resolve_operation_id,
    resolve_project_profile_selection,
)
from ..helpers.services import (
    build_delivery_commands_service,
    build_fleet_workbench_query_service,
    build_operation_dashboard_query_service,
    build_project_dashboard_query_service,
    delivery_commands_service,
    load_settings,
)
from .control import _execute_converse_command
from .converse import (
    _load_converse_fleet_operations,
    build_converse_fleet_prompt,
    build_converse_operation_prompt,
    parse_converse_command,
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


def _settings_for_data_dir(settings: OperatorSettings, data_dir: Path) -> OperatorSettings:
    scoped = settings.model_copy(deep=True)
    scoped.data_dir = data_dir
    return scoped


def _iter_fleet_project_scopes(
    *, settings: OperatorSettings
) -> list[tuple[Path | None, Path, str | None]]:
    configured_roots = load_global_config().project_roots
    if configured_roots:
        return [
            (project_root, project_root / ".operator", project_name_for_root(project_root))
            for project_root in discover_projects(list(configured_roots))
        ]
    return [(None, Path(settings.data_dir), None)]


def _matches_fleet_project_name(
    *,
    requested: str | None,
    discovered_name: str,
    operation_project_name: str | None,
) -> bool:
    if requested is None:
        return True
    if discovered_name == requested:
        return True
    return operation_project_name == requested


async def _load_multi_project_agenda_snapshot(
    *, project: str | None, include_all: bool
) -> AgendaSnapshot:
    settings = load_settings()
    items = []
    for _project_root, data_dir, discovered_project_name in _iter_fleet_project_scopes(
        settings=settings
    ):
        project_settings = _settings_for_data_dir(settings, data_dir)
        store = build_store(project_settings)
        trace_store = build_trace_store(project_settings)
        inbox = build_wakeup_inbox(project_settings)
        supervisor = build_background_run_inspection_store(project_settings)
        for summary in await store.list_operations():
            wakeups = inbox.read_all(summary.operation_id)
            background_runs = [
                item.model_dump(mode="json")
                for item in await supervisor.list_runs(summary.operation_id)
            ]
            runtime_alert = build_runtime_alert(
                status=summary.status,
                wakeups=wakeups,
                background_runs=background_runs,
            )
            operation = await store.load_operation(summary.operation_id)
            if operation is None:
                continue
            brief_bundle = await trace_store.load_brief_bundle(summary.operation_id)
            brief = brief_bundle.operation_brief if brief_bundle is not None else None
            item = build_agenda_item(
                operation,
                summary,
                brief=brief,
                runtime_alert=runtime_alert,
            )
            if discovered_project_name is not None:
                item.project_profile_name = item.project_profile_name or discovered_project_name
            if _matches_fleet_project_name(
                requested=project,
                discovered_name=discovered_project_name or "",
                operation_project_name=item.project_profile_name,
            ):
                items.append(item)
    return build_agenda_snapshot(items, include_recent=include_all)


async def _iter_list_payloads() -> list[tuple[dict[str, object], str]]:
    settings = load_settings()
    rows: list[tuple[dict[str, object], str, datetime]] = []
    for _, data_dir, discovered_project_name in _iter_fleet_project_scopes(settings=settings):
        project_settings = _settings_for_data_dir(settings, data_dir)
        store = build_store(project_settings)
        trace_store = build_trace_store(project_settings)
        inbox = build_wakeup_inbox(project_settings)
        supervisor = build_background_run_inspection_store(project_settings)
        for summary in await store.list_operations():
            wakeups = inbox.read_all(summary.operation_id)
            background_runs = [
                item.model_dump(mode="json")
                for item in await supervisor.list_runs(summary.operation_id)
            ]
            runtime_alert = build_runtime_alert(
                status=summary.status,
                wakeups=wakeups,
                background_runs=background_runs,
            )
            brief_bundle = await trace_store.load_brief_bundle(summary.operation_id)
            if brief_bundle is not None and brief_bundle.operation_brief is not None:
                payload = PROJECTIONS.operation_brief_payload(brief_bundle.operation_brief)
                payload["project"] = (
                    payload.get("project_profile_name") or discovered_project_name
                )
                if runtime_alert is not None:
                    payload["runtime_alert"] = runtime_alert
                rows.append((payload, str(payload["project"] or ""), summary.updated_at))
                continue
            payload = summary.model_dump(mode="json")
            payload["project"] = discovered_project_name
            if runtime_alert is not None:
                payload["runtime_alert"] = runtime_alert
            rows.append((payload, str(discovered_project_name or ""), summary.updated_at))
    rows.sort(key=lambda item: (-item[2].timestamp(), str(item[0].get("operation_id") or "")))
    return [(payload, project_name) for payload, project_name, _ in rows]


async def _load_agenda_snapshot(
    *, project: str | None, include_all: bool
) -> AgendaSnapshot:
    return await _load_multi_project_agenda_snapshot(project=project, include_all=include_all)


async def _load_fleet_workbench_payload(
    *, project: str | None, include_all: bool
) -> dict[str, object]:
    settings = load_settings()
    if load_global_config().project_roots:
        service = build_fleet_workbench_query_service(settings)
        return service.projection_service.build_fleet_workbench_payload(
            await _load_multi_project_agenda_snapshot(project=project, include_all=include_all),
            project=project,
        )
    service = build_fleet_workbench_query_service(settings)
    return await service.load_payload(project=project, include_recent=include_all)


def _local_workspace_has_operator_data() -> bool:
    return (discover_workspace_root() / ".operator").is_dir()


def _default_discovery_roots() -> list[Path]:
    configured_roots = load_global_config().project_roots
    if configured_roots:
        return list(configured_roots)
    return [Path.home()]


def _default_discovery_depth() -> int:
    if load_global_config().project_roots:
        return 4
    return 3


def _render_discovered_projects(projects: Iterable[Path]) -> list[str]:
    return [str(path.expanduser()) for path in projects]


def _maybe_run_first_time_fleet_discovery(*, json_mode: bool) -> list[Path]:
    global_config = load_global_config()
    if global_config.project_roots or _local_workspace_has_operator_data() or json_mode:
        return []
    discovered = discover_projects([Path.home()], max_depth=3)
    if not discovered:
        return []
    typer.echo(f"Found {len(discovered)} projects with operator data:")
    for project_path in _render_discovered_projects(discovered):
        typer.echo(f"  {project_path}")
    if typer.confirm("Add them to your fleet view?", default=True):
        add_project_root_parents(discovered)
    return discovered


async def fleet_discover_async(*, json_mode: bool, depth: int, add: bool) -> None:
    discovered = discover_projects(_default_discovery_roots(), max_depth=depth)
    if add:
        config, changed = add_project_root_parents(discovered)
    else:
        config = load_global_config()
        changed = False
    payload = {
        "discovered_projects": [str(path) for path in discovered],
        "project_roots": [str(path) for path in config.project_roots],
        "added": changed,
    }
    if json_mode:
        typer.echo(json.dumps(payload, indent=2, ensure_ascii=False))
        return
    if not discovered:
        typer.echo("No projects discovered.")
        return
    typer.echo("Discovered projects:")
    for project_path in discovered:
        typer.echo(f"- {project_path}")
    if add:
        typer.echo(f"Updated project roots: {len(config.project_roots)}")


async def has_any_operations_async() -> bool:
    snapshot = await _load_agenda_snapshot(project=None, include_all=False)
    return snapshot.total_operations > 0


async def list_async(json_mode: bool) -> None:
    for payload, project_name in await _iter_list_payloads():
        if json_mode:
            typer.echo(json.dumps(payload, ensure_ascii=False))
            continue
        if "objective_brief" in payload:
            focus_raw = payload.get("focus_brief")
            latest_raw = payload.get("latest_outcome_brief")
            blocker_raw = payload.get("blocker_brief")
            scheduler_raw = payload.get("scheduler_state")
            involvement_raw = payload.get("involvement_level")
            runtime_alert = payload.get("runtime_alert")
            objective_brief = str(payload.get("objective_brief") or "")
            objective = objective_brief
            if project_name:
                objective = f"[{project_name}] {objective_brief}"
            typer.echo(
                render_operation_list_line(
                    str(payload.get("operation_id") or ""),
                    str(payload.get("status") or "unknown"),
                    objective=objective,
                    focus=shorten_live_text(str(focus_raw), limit=28) if focus_raw else None,
                    latest=shorten_live_text(
                        str(latest_raw),
                        limit=56,
                    )
                    if latest_raw
                    else None,
                    blocker=shorten_live_text(str(blocker_raw), limit=48) if blocker_raw else None,
                    runtime_alert=shorten_live_text(str(runtime_alert), limit=48)
                    if runtime_alert
                    else None,
                    scheduler=(
                        str(scheduler_raw)
                        if scheduler_raw and scheduler_raw != "active"
                        else None
                    ),
                    involvement=(
                        str(involvement_raw)
                        if involvement_raw and involvement_raw != "auto"
                        else None
                    ),
                )
            )
            continue
        runtime_alert = payload.get("runtime_alert")
        objective_prompt = str(payload.get("objective_prompt") or "")
        objective = objective_prompt
        if project_name:
            objective = f"[{project_name}] {objective_prompt}"
        typer.echo(
            render_operation_list_line(
                str(payload.get("operation_id") or ""),
                str(payload.get("status") or "unknown"),
                objective=shorten_live_text(objective, limit=96) or objective,
                focus=shorten_live_text(str(payload.get("focus")), limit=28)
                if payload.get("focus")
                else None,
                latest=shorten_live_text(str(payload.get("final_summary")), limit=56)
                if payload.get("final_summary")
                else None,
                blocker=None,
                runtime_alert=shorten_live_text(str(runtime_alert), limit=48)
                if runtime_alert
                else None,
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
    project: str | None,
    include_all: bool,
    once: bool,
    json_mode: bool,
    poll_interval: float,
    discover: bool = False,
    depth: int | None = None,
    add: bool = False,
) -> None:
    if discover:
        await fleet_discover_async(
            json_mode=json_mode,
            depth=depth if depth is not None else _default_discovery_depth(),
            add=add,
        )
        return
    _maybe_run_first_time_fleet_discovery(json_mode=json_mode)
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
    brain = build_brain(settings)
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

    def _normalize_tui_command(
        command_text: str,
        *,
        default_operation_id: str | None,
        default_task_id: str | None,
    ) -> str:
        tokens = shlex.split(command_text)
        if not tokens:
            raise RuntimeError("Empty command.")
        command_name = tokens[0]
        if command_name in {"message", "patch-objective"}:
            if default_operation_id is None:
                raise RuntimeError(f"`{command_name}` requires a selected operation.")
            if len(tokens) == 1:
                raise RuntimeError(f"`{command_name}` requires text.")
            return shlex.join([command_name, default_operation_id, " ".join(tokens[1:])])
        if command_name == "answer":
            if default_operation_id is None:
                raise RuntimeError("`answer` requires a selected operation.")
            if len(tokens) < 3:
                raise RuntimeError("`answer` requires an attention id and text.")
            return shlex.join([command_name, tokens[1], "--text", " ".join(tokens[2:])])
        if command_name == "interrupt" and "--task" not in tokens:
            if default_task_id is None:
                raise RuntimeError("`interrupt` requires a selected task with a live session.")
            return shlex.join([command_name, "--task", default_task_id])
        return command_text

    async def execute_tui_command(
        command_text: str,
        default_operation_id: str | None,
        default_task_id: str | None,
    ) -> str:
        normalized_command = _normalize_tui_command(
            command_text,
            default_operation_id=default_operation_id,
            default_task_id=default_task_id,
        )
        command = parse_converse_command(
            normalized_command,
            default_operation_id=default_operation_id,
        )
        await _execute_converse_command(command)
        return f"Executed: {normalized_command}"

    async def converse_turn(
        view_level: str,
        user_message: str,
        operation_id: str | None,
        task_id: str | None,
        event_summary: str | None,
        active_project: str | None,
        history: list[dict[str, str]],
    ) -> tuple[str, str | None]:
        scoped_message = user_message
        if view_level == "session" and task_id is not None:
            scoped_message = f"[Session task {task_id}] {user_message}"
        if view_level == "forensic" and event_summary is not None:
            scoped_message = f"[Forensic focus: {event_summary}] {user_message}"
        if operation_id is not None:
            state = await build_store(settings).load_operation(operation_id)
            if state is None:
                raise RuntimeError(f"Operation {operation_id!r} was not found.")
            prompt = build_converse_operation_prompt(
                state,
                user_message=scoped_message,
                conversation_history=history,
                context_level="brief",
                recent_events=None,
            )
        else:
            operations = await _load_converse_fleet_operations(active_project)
            prompt = build_converse_fleet_prompt(
                operations,
                user_message=scoped_message,
                conversation_history=history,
                context_level="brief",
            )
        turn = await brain.converse(prompt)
        answer = turn.answer.strip()
        proposed = turn.proposed_command.strip() if turn.proposed_command is not None else None
        return answer, proposed

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
        execute_tui_command=execute_tui_command,
        converse_turn=converse_turn,
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
