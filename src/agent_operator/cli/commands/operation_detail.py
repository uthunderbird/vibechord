from __future__ import annotations

import json
import sys
from dataclasses import asdict
from pathlib import Path

import anyio
import typer
from rich.console import Console as RichConsole
from rich.live import Live

from agent_operator.bootstrap import build_store, build_trace_store
from agent_operator.domain import TaskState
from agent_operator.runtime import (
    find_codex_session_log,
    format_claude_log_event,
    format_codex_log_event,
    iter_claude_log_events,
    iter_codex_log_events,
    load_claude_log_events,
    load_codex_log_events,
)

from ..app import app
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
    artifact_preview,
    format_task_line,
    memory_payload,
    shorten_live_text,
    summarize_task_counts,
)
from ..helpers.resolution import resolve_operation_id, resolve_operation_id_async
from ..helpers.services import (
    build_operation_dashboard_query_service,
    build_status_query_service,
    load_settings,
)
from ..options import CODEX_HOME_OPTION, JSON_OPTION, MEMORY_ALL_OPTION, WATCH_POLL_INTERVAL_OPTION
from ..workflows import dashboard_async, watch_async


def _resolve_task(operation, task_ref: str) -> TaskState:
    key = task_ref.removeprefix("task-")
    direct = [task for task in operation.tasks if task.task_id == task_ref]
    if len(direct) > 1:
        raise typer.BadParameter(f"Task reference {task_ref!r} is ambiguous.")
    if direct:
        return direct[0]
    matches = [task for task in operation.tasks if task.task_short_id == key]
    if not matches:
        raise typer.BadParameter(f"Task {task_ref!r} was not found.")
    if len(matches) > 1:
        raise typer.BadParameter(
            f"Task reference {task_ref!r} is ambiguous: "
            + ", ".join(sorted(task.task_id for task in matches))
        )
    return matches[0]


def _resolve_task_session_view(
    operation_payload: dict[str, object],
    task_id: str,
) -> dict[str, object]:
    session_views = operation_payload.get("session_views")
    if isinstance(session_views, list):
        for session_view in session_views:
            if not isinstance(session_view, dict):
                continue
            if str(session_view.get("task_id") or "") == task_id:
                return session_view
    raise typer.BadParameter(f"Session view for task {task_id!r} was not found.")


def _shorten(value: object) -> str:
    if not isinstance(value, str):
        return "-"
    return shorten_live_text(value, limit=120)


def _selected_event_summary(event: object) -> str | None:
    if not isinstance(event, dict):
        return None
    summary = event.get("summary")
    if not isinstance(summary, str):
        return None
    stripped = summary.strip()
    if not stripped:
        return None
    return shorten_live_text(stripped, limit=160) or stripped


def _selected_event_detail(event: object, key: str) -> str | None:
    if not isinstance(event, dict):
        return None
    detail = event.get("detail")
    if not isinstance(detail, dict):
        return None
    value = detail.get(key)
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    if not stripped:
        return None
    return shorten_live_text(stripped, limit=180) or stripped


async def _load_session_snapshot(
    *,
    queries,
    operation_id: str,
    task_record: TaskState,
) -> dict[str, object]:
    payload = await queries.load_payload(operation_id)
    session_view = _resolve_task_session_view(payload, task_record.task_id)
    session_payload_data = session_view.get("session", {})
    session_brief = session_view.get("session_brief", {})
    session_events = session_view.get("timeline", [])
    latest_event = session_view.get("selected_event")
    transcript_hint = session_view.get("transcript_hint", {})
    session_snapshot = {
        "operation_id": operation_id,
        "task": task_record.model_dump(mode="json"),
        "session_id": session_payload_data.get("session_id") or task_record.linked_session_id,
        "session": session_payload_data,
        "session_brief": session_brief,
        "timeline_events": [event for event in session_events if isinstance(event, dict)],
        "selected_event": latest_event if isinstance(latest_event, dict) else None,
        "transcript_hint": transcript_hint if isinstance(transcript_hint, dict) else {},
    }
    return session_snapshot


def _render_session_snapshot_text(
    *,
    operation,
    task_record: TaskState,
    operation_id: str,
    session_snapshot: dict[str, object],
    follow: bool,
) -> str:
    session_payload_data = session_snapshot.get("session", {})
    session_brief = session_snapshot.get("session_brief", {})
    session_events = session_snapshot.get("timeline_events", [])
    latest_event = session_snapshot.get("selected_event")
    transcript_hint = session_snapshot.get("transcript_hint", {})
    lines: list[str] = []
    task_line = format_task_line(operation, task_record.task_id)
    if task_line is None:
        task_line = task_record.task_id
    adapter_key = str(session_payload_data.get("adapter_key") or "-")
    session_status = str(session_payload_data.get("status") or "-")
    bound_tasks = ", ".join(task_id for task_id in session_payload_data.get("bound_task_ids", []))
    if not bound_tasks:
        bound_tasks = "-"
    session_display_id = session_payload_data.get("session_id") or task_record.linked_session_id
    transcript_command = (
        transcript_hint.get("command") if isinstance(transcript_hint, dict) else None
    )
    if not (isinstance(transcript_command, str) and transcript_command.strip()):
        transcript_command = f"operator log {operation_id}"
    if follow and " --follow" not in transcript_command:
        transcript_command = f"{transcript_command} --follow"
    lines.append(f"Session scope for {task_line}")
    lines.append(f"Operation: {operation_id}")
    lines.append(f"Session: {session_display_id} [{adapter_key}] state={session_status}")
    lines.append(f"Bound tasks: {bound_tasks}")
    lines.append(f"Now: {_shorten(session_brief.get('now'))}")
    lines.append(f"Wait: {_shorten(session_brief.get('wait'))}")
    lines.append(f"Attention: {_shorten(session_brief.get('attention'))}")
    if _shorten(session_brief.get("review")) != "-":
        lines.append(f"Review: {_shorten(session_brief.get('review'))}")
    lines.append(f"Latest output: {_shorten(session_brief.get('latest_output'))}")
    lines.append("Recent events:")
    event_limit = 2 if follow else 4
    if session_events:
        for event in session_events[-event_limit:]:
            event_line = f"  - iter={event.get('iteration', '-')}: {event.get('event_type', '-')}"
            summary = event.get("summary")
            if isinstance(summary, str) and summary:
                event_line += f" {shorten_live_text(summary, limit=120)}"
            lines.append(event_line)
    else:
        lines.append("  - none")
    if not follow and latest_event is not None:
        lines.append(f"Selected event: {latest_event.get('event_type', '-')}")
        if isinstance(latest_event.get("timestamp"), str) and latest_event.get("timestamp"):
            lines.append(f"  time: {latest_event.get('timestamp')}")
        lines.append(f"  iteration: {latest_event.get('iteration', '-')}")
        lines.append(f"  task: {latest_event.get('task_id', '-')}")
        lines.append(f"  session: {latest_event.get('session_id', '-')}")
        event_summary = _selected_event_summary(latest_event)
        if event_summary is not None:
            lines.append(f"  summary: {event_summary}")
        event_status = _selected_event_detail(latest_event, "status")
        if event_status is not None:
            lines.append(f"  status: {event_status}")
        event_output = _selected_event_detail(latest_event, "output_text")
        if event_output is not None:
            lines.append(f"  output: {event_output}")
        detail = latest_event.get("detail") if isinstance(latest_event, dict) else None
        artifacts = detail.get("artifacts") if isinstance(detail, dict) else None
        if isinstance(artifacts, list) and artifacts:
            lines.append("  artifacts:")
            for artifact in artifacts[:3]:
                if not isinstance(artifact, dict):
                    continue
                artifact_name = str(artifact.get("name") or "-")
                artifact_kind = str(artifact.get("kind") or "-")
                artifact_content = _shorten(artifact.get("content"))
                artifact_line = f"    - {artifact_name} [{artifact_kind}]"
                if artifact_content != "-":
                    artifact_line += f": {artifact_content}"
                lines.append(artifact_line)
    elif not follow:
        lines.append("Selected event: none")
    lines.append(f"Transcript: {transcript_command}")
    return "\n".join(lines)


@app.command()
def attention(
    operation_ref: str,
    json_mode: bool = typer.Option(False, "--json", help="Emit machine-readable JSON."),
) -> None:
    settings = load_settings()
    store = build_store(settings)

    async def _attention() -> None:
        resolved_operation_id = await resolve_operation_id_async(operation_ref)
        operation = await store.load_operation(resolved_operation_id)
        if operation is None:
            raise typer.BadParameter(f"Operation {resolved_operation_id!r} was not found.")
        payload = [item.model_dump(mode="json") for item in operation.attention_requests]
        if json_mode:
            typer.echo(
                json.dumps(
                    {"operation_id": resolved_operation_id, "attention_requests": payload},
                    indent=2,
                    ensure_ascii=False,
                )
            )
            return
        typer.echo(f"Operation {resolved_operation_id}")
        typer.echo("Attention requests:")
        if not payload:
            typer.echo("- none")
            return
        for item in payload:
            status = item["status"]
            attention_type = item["attention_type"]
            blocking = item["blocking"]
            typer.echo(
                f"- {item['attention_id']} [{status}] type={attention_type} blocking={blocking}"
            )
            typer.echo(f"  title: {item['title']}")
            typer.echo(f"  question: {item['question']}")
            if item.get("context_brief"):
                typer.echo(f"  context: {item['context_brief']}")
            if item.get("suggested_options"):
                typer.echo(
                    "  options: " + ", ".join(str(option) for option in item["suggested_options"])
                )
            if item.get("answer_text"):
                typer.echo(f"  answer: {item['answer_text']}")

    anyio.run(_attention)


@app.command()
def tasks(
    operation_ref: str,
    json_mode: bool = typer.Option(False, "--json", help="Emit machine-readable JSON."),
) -> None:
    settings = load_settings()
    store = build_store(settings)

    async def _tasks() -> None:
        resolved_operation_id = await resolve_operation_id_async(operation_ref)
        operation = await store.load_operation(resolved_operation_id)
        if operation is None:
            raise typer.BadParameter(f"Operation {resolved_operation_id!r} was not found.")
        payload = [task.model_dump(mode="json") for task in operation.tasks]
        if json_mode:
            typer.echo(
                json.dumps(
                    {
                        "operation_id": resolved_operation_id,
                        "task_counts": summarize_task_counts(operation),
                        "tasks": payload,
                    },
                    indent=2,
                    ensure_ascii=False,
                )
            )
            return
        typer.echo(f"Operation {resolved_operation_id}")
        typer.echo(f"Task counts: {summarize_task_counts(operation) or 'none'}")
        typer.echo("Tasks:")
        if not operation.tasks:
            typer.echo("- none")
            return
        for task in sorted(
            operation.tasks,
            key=lambda item: (-item.effective_priority, item.created_at, item.task_id),
        ):
            task_scope = task.linked_session_id or "-"
            agent = task.assigned_agent or "-"
            typer.echo(
                f"- {task.title} [{task.status.value}] task-{task.task_short_id} ({task.task_id})"
            )
            typer.echo(f"  priority={task.effective_priority} agent={agent} session={task_scope}")
            typer.echo(f"  goal: {task.goal}")
            typer.echo(f"  done: {task.definition_of_done}")
            if task.dependencies:
                typer.echo(f"  depends_on: {', '.join(task.dependencies)}")
            if task.notes:
                typer.echo(f"  notes: {' | '.join(task.notes)}")
            if task.memory_refs:
                typer.echo(f"  memory_refs: {', '.join(task.memory_refs)}")
            if task.artifact_refs:
                typer.echo(f"  artifact_refs: {', '.join(task.artifact_refs)}")

    anyio.run(_tasks)


@app.command()
def memory(
    operation_ref: str,
    include_all: bool = MEMORY_ALL_OPTION,
    json_mode: bool = typer.Option(False, "--json", help="Emit machine-readable JSON."),
) -> None:
    settings = load_settings()
    store = build_store(settings)

    async def _memory() -> None:
        resolved_operation_id = await resolve_operation_id_async(operation_ref)
        operation = await store.load_operation(resolved_operation_id)
        if operation is None:
            raise typer.BadParameter(f"Operation {resolved_operation_id!r} was not found.")
        entries = memory_payload(operation, include_inactive=include_all)
        payload = [entry.model_dump(mode="json") for entry in entries]
        if json_mode:
            typer.echo(
                json.dumps(
                    {"operation_id": resolved_operation_id, "memory_entries": payload},
                    indent=2,
                    ensure_ascii=False,
                )
            )
            return
        typer.echo(f"Operation {resolved_operation_id}")
        typer.echo("Memory:")
        if not entries:
            typer.echo("- none")
            return
        for entry in entries:
            scope_id = entry.scope_id
            scope_value = entry.scope.value
            freshness = entry.freshness.value
            typer.echo(f"- {entry.memory_id} [{scope_value}:{scope_id}] {freshness}")
            typer.echo(f"  summary: {entry.summary}")
            if entry.scope.value == "task":
                typer.echo(f"  target: {format_task_line(operation, entry.scope_id)}")
            if entry.source_refs:
                typer.echo(
                    "  sources: "
                    + ", ".join(f"{ref.kind}:{ref.ref_id}" for ref in entry.source_refs)
                )

    anyio.run(_memory)


@app.command()
def artifacts(
    operation_ref: str,
    json_mode: bool = typer.Option(False, "--json", help="Emit machine-readable JSON."),
) -> None:
    settings = load_settings()
    store = build_store(settings)

    async def _artifacts() -> None:
        resolved_operation_id = await resolve_operation_id_async(operation_ref)
        operation = await store.load_operation(resolved_operation_id)
        if operation is None:
            raise typer.BadParameter(f"Operation {resolved_operation_id!r} was not found.")
        payload = [artifact.model_dump(mode="json") for artifact in operation.artifacts]
        if json_mode:
            typer.echo(
                json.dumps(
                    {"operation_id": resolved_operation_id, "artifacts": payload},
                    indent=2,
                    ensure_ascii=False,
                )
            )
            return
        typer.echo(f"Operation {resolved_operation_id}")
        typer.echo("Artifacts:")
        if not operation.artifacts:
            typer.echo("- none")
            return
        for artifact in operation.artifacts:
            task_ref = format_task_line(operation, artifact.task_id)
            artifact_session = artifact.session_id or "-"
            typer.echo(
                f"- {artifact.artifact_id} [{artifact.kind}] producer={artifact.producer} "
                f"task={task_ref} session={artifact_session}"
            )
            typer.echo(f"  content: {artifact_preview(artifact)}")
            if artifact.raw_ref:
                typer.echo(f"  raw_ref: {artifact.raw_ref}")

    anyio.run(_artifacts)


@app.command()
def report(
    operation_ref: str,
    json_mode: bool = typer.Option(False, "--json", help="Emit a machine-readable report payload."),
) -> None:
    resolved_operation_id = resolve_operation_id(operation_ref)
    settings = load_settings()
    trace_store = build_trace_store(settings)
    status_queries = build_status_query_service(settings)

    async def _report() -> None:
        try:
            operation, outcome, brief, _ = await status_queries.build_status_payload(
                resolved_operation_id
            )
        except RuntimeError as exc:
            raise typer.BadParameter(
                f"Report for {resolved_operation_id!r} was not found."
            ) from exc
        report_text = await trace_store.load_report(resolved_operation_id)
        if operation is None or report_text is None:
            raise typer.BadParameter(f"Report for {resolved_operation_id!r} was not found.")
        if json_mode:
            payload = {
                "operation_id": resolved_operation_id,
                "brief": brief.model_dump(mode="json") if brief is not None else None,
                "outcome": outcome.model_dump(mode="json") if outcome is not None else None,
                "report": report_text,
                "durable_truth": PROJECTIONS.build_durable_truth_payload(
                    operation, include_inactive_memory=True
                ),
            }
            typer.echo(json.dumps(payload, indent=2, ensure_ascii=False))
            return
        typer.echo(report_text)

    anyio.run(_report)


@app.command()
def dashboard(
    operation_ref: str,
    once: bool = typer.Option(False, "--once", help="Render a single dashboard snapshot and exit."),
    json_mode: bool = typer.Option(
        False, "--json", help="Emit a machine-readable dashboard snapshot."
    ),
    poll_interval: float = WATCH_POLL_INTERVAL_OPTION,
    codex_home: Path = CODEX_HOME_OPTION,
) -> None:
    anyio.run(
        dashboard_async,
        resolve_operation_id(operation_ref),
        once,
        json_mode,
        poll_interval,
        codex_home,
    )


@app.command()
def watch(
    operation_ref: str,
    json_mode: bool = JSON_OPTION,
    poll_interval: float = WATCH_POLL_INTERVAL_OPTION,
) -> None:
    anyio.run(watch_async, resolve_operation_id(operation_ref), json_mode, poll_interval)


@app.command()
def log(
    operation_ref: str,
    limit: int = typer.Option(40, "--limit", min=1, help="Maximum events to print."),
    follow: bool = typer.Option(False, "--follow", help="Follow the agent transcript."),
    agent: str = typer.Option("auto", "--agent", help="auto, codex, claude, or opencode."),
    json_mode: bool = typer.Option(False, "--json", help="Emit machine-readable JSON."),
    codex_home: Path = CODEX_HOME_OPTION,
) -> None:
    resolved_operation_id = resolve_operation_id(operation_ref)
    settings = load_settings()
    store = build_store(settings)

    async def _log() -> None:
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
                for event in iter_codex_log_events(path, follow=True):
                    typer.echo(
                        json.dumps(asdict(event), ensure_ascii=False)
                        if json_mode
                        else format_codex_log_event(event)
                    )
                return
            events = load_codex_log_events(path)[-limit:]
            if json_mode:
                typer.echo(
                    json.dumps(
                        {
                            "operation_id": resolved_operation_id,
                            "session_id": session.session_id,
                            "path": str(path),
                            "agent": "codex",
                            "events": [asdict(event) for event in events],
                        },
                        indent=2,
                        ensure_ascii=False,
                    )
                )
                return
            typer.echo(f"# Codex log for operation {resolved_operation_id}")
            typer.echo(f"# session={session.session_id}")
            typer.echo(f"# file={path}")
            for event in events:
                typer.echo(format_codex_log_event(event))
            return
        if log_kind == "claude":
            path = resolve_claude_log_path_for_session(session)
            if follow:
                typer.echo(f"# Claude log for operation {resolved_operation_id}")
                typer.echo(f"# session={session.session_id}")
                typer.echo(f"# file={path}")
                for event in iter_claude_log_events(path, follow=True):
                    typer.echo(
                        json.dumps(asdict(event), ensure_ascii=False)
                        if json_mode
                        else format_claude_log_event(event)
                    )
                return
            events = load_claude_log_events(path)[-limit:]
            if json_mode:
                typer.echo(
                    json.dumps(
                        {
                            "operation_id": resolved_operation_id,
                            "session_id": session.session_id,
                            "path": str(path),
                            "agent": "claude",
                            "events": [asdict(event) for event in events],
                        },
                        indent=2,
                        ensure_ascii=False,
                    )
                )
                return
            typer.echo(f"# Claude log for operation {resolved_operation_id}")
            typer.echo(f"# session={session.session_id}")
            typer.echo(f"# file={path}")
            for event in events:
                typer.echo(format_claude_log_event(event))
            return
        path = resolve_jsonl_log_path_for_session(session, provider="OpenCode")
        if follow:
            typer.echo(f"# OpenCode log for operation {resolved_operation_id}")
            typer.echo(f"# session={session.session_id}")
            typer.echo(f"# file={path}")
            for event in iter_opencode_log_events(path, follow=True):
                typer.echo(
                    json.dumps(asdict(event), ensure_ascii=False)
                    if json_mode
                    else format_opencode_log_event(event)
                )
            return
        events = load_opencode_log_events(path)[-limit:]
        if json_mode:
            typer.echo(
                json.dumps(
                    {
                        "operation_id": resolved_operation_id,
                        "session_id": session.session_id,
                        "path": str(path),
                        "agent": "opencode",
                        "events": [asdict(event) for event in events],
                    },
                    indent=2,
                    ensure_ascii=False,
                )
            )
            return
        typer.echo(f"# OpenCode log for operation {resolved_operation_id}")
        typer.echo(f"# session={session.session_id}")
        typer.echo(f"# file={path}")
        for event in events:
            typer.echo(format_opencode_log_event(event))

    anyio.run(_log)


@app.command()
def session(
    operation_ref: str,
    task: str = typer.Option(
        ..., "--task", help="Task ID (UUID or task-XXXX short ID) that owns the session to view."
    ),
    follow: bool = typer.Option(
        False, "--follow", help="Follow the selected session snapshot in-place."
    ),
    once: bool = typer.Option(False, "--once", help="Render a single snapshot and exit."),
    json_mode: bool = typer.Option(False, "--json", help="Emit machine-readable session payload."),
    poll_interval: float = WATCH_POLL_INTERVAL_OPTION,
    codex_home: Path = CODEX_HOME_OPTION,
) -> None:
    resolved_operation_id = resolve_operation_id(operation_ref)
    settings = load_settings()
    store = build_store(settings)

    async def _session() -> None:
        operation = await store.load_operation(resolved_operation_id)
        if operation is None:
            raise typer.BadParameter(f"Operation {resolved_operation_id!r} was not found.")
        task_record = _resolve_task(operation, task)
        if task_record.linked_session_id is None:
            raise typer.BadParameter(
                f"Task {task!r} is not linked to a session. Use a task that has a linked session."
            )
        queries = build_operation_dashboard_query_service(
            settings,
            operation_id=resolved_operation_id,
            codex_home=codex_home,
        )

        async def _render_once(*, live_follow: bool) -> tuple[dict[str, object], str]:
            session_snapshot = await _load_session_snapshot(
                queries=queries,
                operation_id=resolved_operation_id,
                task_record=task_record,
            )
            if json_mode:
                return session_snapshot, json.dumps(session_snapshot, indent=2, ensure_ascii=False)
            return session_snapshot, _render_session_snapshot_text(
                operation=operation,
                task_record=task_record,
                operation_id=resolved_operation_id,
                session_snapshot=session_snapshot,
                follow=live_follow,
            )

        if follow:
            use_live_tty = not json_mode and sys.stdout.isatty() and sys.stdin.isatty()
            if use_live_tty:
                _, initial_render = await _render_once(live_follow=True)
                console = RichConsole()
                with Live(initial_render, console=console, refresh_per_second=4) as live:
                    if once:
                        return
                    last_render = initial_render
                    while True:
                        _, rendered = await _render_once(live_follow=True)
                        if rendered != last_render:
                            live.update(rendered, refresh=True)
                            last_render = rendered
                        await anyio.sleep(poll_interval)
            last_render: str | None = None
            while True:
                _, rendered = await _render_once(live_follow=True)
                if rendered != last_render:
                    typer.echo(rendered)
                    last_render = rendered
                if once:
                    break
                await anyio.sleep(poll_interval)
            return
        _, rendered = await _render_once(live_follow=False)
        typer.echo(rendered)

    anyio.run(_session)
