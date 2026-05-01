from __future__ import annotations

import json
import sys
from pathlib import Path

import anyio
import typer
from rich.console import Console as RichConsole
from rich.live import Live

from agent_operator.domain import TaskState

from ..app import app, show_app
from ..helpers.rendering import PROJECTIONS, format_task_line, shorten_live_text
from ..helpers.resolution import (
    load_required_canonical_operation_state_async,
    resolve_operation_id,
)
from ..helpers.services import build_operation_dashboard_query_service, load_settings
from ..options import CODEX_HOME_OPTION, WATCH_POLL_INTERVAL_OPTION


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
    return {
        "operation_id": operation_id,
        "task": PROJECTIONS.task_payload(task_record),
        "session_id": session_payload_data.get("session_id") or task_record.linked_session_id,
        "session": session_payload_data,
        "session_brief": session_brief,
        "timeline_events": [event for event in session_events if isinstance(event, dict)],
        "selected_event": latest_event if isinstance(latest_event, dict) else None,
        "transcript_hint": transcript_hint if isinstance(transcript_hint, dict) else {},
    }


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
    task_line = format_task_line(operation, task_record.task_id) or task_record.task_id
    adapter_key = str(session_payload_data.get("adapter_key") or "-")
    session_status = str(session_payload_data.get("status") or "-")
    bound_task_ids = session_payload_data.get("bound_task_ids", [])
    session_display_id = session_payload_data.get("session_id") or task_record.linked_session_id
    transcript_command = (
        transcript_hint.get("command") if isinstance(transcript_hint, dict) else None
    )
    if not (isinstance(transcript_command, str) and transcript_command.strip()):
        transcript_command = f"operator log {operation_id}"
    if follow and " --follow" not in transcript_command:
        transcript_command = f"{transcript_command} --follow"
    lines.append(f"Session for {task_line}")
    lines.append(f"Operation: {operation_id}")
    lines.append(f"Task: {task_record.task_id}")
    lines.append(f"Session: {session_display_id} [{adapter_key}] state={session_status}")
    if isinstance(bound_task_ids, list) and len(bound_task_ids) > 1:
        lines.append(f"Bound tasks: {', '.join(str(task_id) for task_id in bound_task_ids)}")
    lines.append(f"Now: {_shorten(session_brief.get('now'))}")
    attention_text = _shorten(session_brief.get("attention"))
    wait_text = _shorten(session_brief.get("wait"))
    lines.append(f"Attention: {attention_text}" if attention_text != "-" else f"Wait: {wait_text}")
    review_text = _shorten(session_brief.get("review"))
    if review_text != "-":
        lines.append(f"Review: {review_text}")
    lines.append(f"Latest: {_shorten(session_brief.get('latest_output'))}")
    lines.append("Recent:")
    event_limit = 2 if follow else 3
    if session_events:
        for event in session_events[-event_limit:][::-1]:
            event_line = f"  - iter={event.get('iteration', '-')}: {event.get('event_type', '-')}"
            summary = event.get("summary")
            if isinstance(summary, str) and summary:
                event_line += f" {shorten_live_text(summary, limit=120)}"
            lines.append(event_line)
    else:
        lines.append("  - none")
    if not follow and latest_event is not None:
        lines.append(f"Event detail: {latest_event.get('event_type', '-')}")
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
    lines.append(f"Transcript: {transcript_command}")
    return "\n".join(lines)


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

    async def _session() -> None:
        operation = await load_required_canonical_operation_state_async(
            settings, resolved_operation_id
        )
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


@show_app.command("session")
def show_session(
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
    session(operation_ref, task, follow, once, json_mode, poll_interval, codex_home)
