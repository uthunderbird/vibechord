from __future__ import annotations

from rich.table import Table
from rich.text import Text

from .models import (
    TASK_LANE_ORDER,
    FleetWorkbenchState,
    filtered_dashboard_tasks,
    filtered_session_timeline_events,
    selected_session,
    session_event_glyph,
    session_event_label,
    task_lane,
    task_session_summary,
    task_signal_text,
    task_status_glyph,
)


def render_left_pane(state: FleetWorkbenchState) -> Table:
    if state.view_level == "forensic":
        return render_forensic_context(state)
    if state.view_level == "session":
        return render_session_timeline(state)
    if state.view_level == "operation":
        return render_task_board(state)
    return render_list_table(state)


def render_list_table(state: FleetWorkbenchState) -> Table:
    table = Table(expand=True, box=None, show_header=False)
    table.add_column("", width=2, no_wrap=True)
    table.add_column("Operation")
    if not state.items:
        table.add_row(
            "",
            Text(
                "No operations match the current filter."
                if state.filter_query
                else "No active operations. Run 'operator run [goal]' to start."
            ),
        )
        return table
    for index, item in enumerate(state.items):
        badge = item.attention_badge if item.attention_badge.strip() else "[ ]"
        meta_parts = [item.state_label]
        if item.agent_cue.strip() and item.agent_cue != "-":
            meta_parts.append(item.agent_cue)
        if item.recency_brief.strip():
            meta_parts.append(item.recency_brief)
        row_hint = item.row_hint.strip() if item.row_hint.strip() and item.row_hint != "-" else None
        table.add_row(
            ">" if index == state.selected_index else " ",
            Text.assemble((f"{badge} ", "bold"), item.display_name),
        )
        table.add_row("", " · ".join(meta_parts))
        if row_hint is not None:
            table.add_row("", row_hint)
        if index != len(state.items) - 1:
            table.add_row("", "")
    return table


def render_task_board(state: FleetWorkbenchState) -> Table:
    table = Table(expand=True, box=None, show_header=True)
    table.add_column("", no_wrap=True)
    table.add_column("Task", no_wrap=True)
    table.add_column("Signal", no_wrap=True)
    table.add_column("State", no_wrap=True)
    table.add_column("Title")
    tasks = filtered_dashboard_tasks(state.selected_operation_payload, state.task_filter_query)
    if not tasks:
        table.add_row(
            "",
            "-",
            "-",
            "-",
            "No tasks match the current filter." if state.task_filter_query else "No tasks.",
        )
        return table
    tasks_by_lane = {lane: [] for lane in TASK_LANE_ORDER}
    for index, task in enumerate(tasks):
        tasks_by_lane.setdefault(task_lane(task), []).append((index, task))
    for lane in TASK_LANE_ORDER:
        lane_items = tasks_by_lane.get(lane, [])
        if not lane_items:
            continue
        table.add_row("", f"[{lane}]", "", "", "", style="bold")
        for index, task in lane_items:
            table.add_row(
                ">" if index == state.selected_task_index else " ",
                f"{task_status_glyph(task)} {task.task_short_id}",
                task_signal_text(state.selected_operation_payload or {}, task),
                task.status,
                task.title,
            )
            if lane == "BLOCKED" and task.dependencies:
                table.add_row("", "deps", "", "", ", ".join(task.dependencies))
            session_line = task_session_summary(state.selected_operation_payload or {}, task)
            if session_line is not None:
                table.add_row("", "session", "", "", session_line)
    return table


def render_session_timeline(state: FleetWorkbenchState) -> Table:
    table = Table(expand=True, box=None, show_header=True)
    table.add_column("", no_wrap=True)
    table.add_column("Iter", no_wrap=True)
    table.add_column("", no_wrap=True)
    table.add_column("Event", no_wrap=True)
    table.add_column("Summary")
    events = filtered_session_timeline_events(
        state.selected_operation_payload,
        state.selected_task,
        state.session_filter_query,
    )
    if not events:
        table.add_row(
            "",
            "-",
            "-",
            "-",
            (
                "No session timeline events match the current filter."
                if state.session_filter_query
                else "No session timeline events."
            ),
        )
        return table
    for index, event in enumerate(events):
        table.add_row(
            ">" if index == state.selected_timeline_index else " ",
            str(event.iteration),
            session_event_glyph(event),
            session_event_label(event),
            event.summary,
        )
    return table


def render_forensic_context(state: FleetWorkbenchState) -> Table:
    table = Table(expand=True, box=None, show_header=False)
    table.add_column("Field", no_wrap=True, style="bold")
    table.add_column("Value")
    event = state.selected_timeline_event
    task = state.selected_task
    session = selected_session(state.selected_operation_payload, task)
    if event is None:
        table.add_row("Event", "No forensic event selected.")
        return table
    if task is not None:
        table.add_row("Task", f"{task.task_short_id} · {task.title}")
    if session is not None:
        adapter = str(session.get("adapter_key") or "-")
        session_id = str(session.get("session_id") or event.session_id or "-")
        status = str(session.get("status") or "-")
        table.add_row("Session", f"{adapter} · {session_id} [{status}]")
        waiting_reason = session.get("waiting_reason")
        if isinstance(waiting_reason, str) and waiting_reason.strip():
            table.add_row("Waiting", waiting_reason.strip())
        bound_task_ids = session.get("bound_task_ids")
        if isinstance(bound_task_ids, list):
            bound_tasks = ", ".join(
                str(task_id) for task_id in bound_task_ids if isinstance(task_id, str)
            )
            if bound_tasks:
                table.add_row("Bound tasks", bound_tasks)
    table.add_row("Type", event.event_type)
    table.add_row("Iteration", str(event.iteration))
    if event.task_id is not None:
        table.add_row("Task id", event.task_id)
    if event.session_id is not None:
        table.add_row("Session", event.session_id)
    table.add_row("Summary", event.summary)
    return table
