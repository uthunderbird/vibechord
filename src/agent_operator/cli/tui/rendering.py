from __future__ import annotations

from rich.columns import Columns
from rich.console import Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from .models import (
    TASK_LANE_ORDER,
    FleetWorkbenchState,
    event_detail_lines,
    filtered_dashboard_tasks,
    filtered_decisions,
    filtered_memory_entries,
    filtered_raw_transcript_lines,
    filtered_session_timeline_events,
    operation_scope_attentions,
    raw_transcript_lines,
    selected_session,
    session_brief,
    session_event_glyph,
    session_event_label,
    session_identity_text,
    signal_text,
    status_text,
    task_attention_titles,
    task_lane,
    task_scope_attentions,
    task_session_summary,
    task_signal_text,
    task_status_glyph,
)


def render_workbench(state: FleetWorkbenchState) -> Group:
    header = header_lines(state)
    left = Panel(
        render_left_pane(state),
        title=(
            "Event Context"
            if state.view_level == "forensic"
            else "Timeline"
            if state.view_level == "session"
            else "Tasks"
            if state.view_level == "operation"
            else "Operations"
        ),
        border_style="cyan",
    )
    right = Panel(render_right_pane(state), title=right_pane_title(state), border_style="green")
    footer = render_footer_text(state)
    return Group(
        Panel("\n".join(header), border_style="blue"),
        Columns([left, right], equal=True, expand=True),
        Panel(footer, border_style="magenta"),
    )


def header_lines(state: FleetWorkbenchState) -> list[str]:
    breadcrumb = "fleet"
    if state.view_level == "operation" and state.selected_item is not None:
        breadcrumb += f" > {state.selected_item.operation_id}"
    if state.view_level == "session" and state.selected_item is not None:
        breadcrumb += f" > {state.selected_item.operation_id}"
        if state.selected_task is not None:
            breadcrumb += f" > {state.selected_task.task_short_id}"
    if state.view_level == "forensic" and state.selected_item is not None:
        breadcrumb += f" > {state.selected_item.operation_id}"
        if state.selected_task is not None:
            breadcrumb += f" > {state.selected_task.task_short_id}"
        if state.selected_timeline_event is not None:
            breadcrumb += (
                f" > iter-{state.selected_timeline_event.iteration}:"
                f"{state.selected_timeline_event.event_type}"
            )
    lines = [f"breadcrumb={breadcrumb}"]
    if state.view_level == "session":
        identity = session_identity_text(state.selected_operation_payload, state.selected_task)
        if state.session_filter_query:
            identity += f"  session_filter={state.session_filter_query}"
        lines.append(identity)
        return lines
    if state.view_level == "forensic":
        scope = session_identity_text(state.selected_operation_payload, state.selected_task)
        if state.forensic_filter_query:
            scope += f"  forensic_filter={state.forensic_filter_query}"
        lines.append(scope)
        return lines
    scope = (f"project={state.project}" if state.project is not None else "project=all") + (
        f"  operations={state.total_operations}"
    )
    if state.view_level == "operation" and state.task_filter_query:
        scope += f"  task_filter={state.task_filter_query}"
    if state.filter_query:
        scope += f"  filter={state.filter_query}"
    lines.append(scope)
    return lines


def right_pane_title(state: FleetWorkbenchState) -> str:
    if state.attention_picker_active:
        return "Attention Picker"
    if state.help_overlay_active:
        return "Help"
    if state.view_level == "operation":
        mode = state.operation_panel_mode.title()
        if state.selected_task is not None:
            return f"{mode}: {state.selected_task.task_short_id}"
        return mode
    if state.view_level == "session":
        if state.session_panel_mode == "report":
            return "Report"
        if state.session_panel_mode == "raw_transcript":
            return "Raw Transcript"
        return "Session Detail"
    if state.view_level == "forensic":
        event = state.selected_timeline_event
        return (
            f"Forensic Transcript: iter {event.iteration}"
            if event is not None
            else "Forensic Transcript"
        )
    if state.selected_item is not None:
        return f"Detail: {state.selected_item.operation_id}"
    return "Detail"


def render_left_pane(state: FleetWorkbenchState) -> Table:
    if state.view_level == "forensic":
        return render_forensic_context(state)
    if state.view_level == "session":
        return render_session_timeline(state)
    if state.view_level == "operation":
        return render_task_board(state)
    return render_list_table(state)


def render_right_pane(state: FleetWorkbenchState) -> Group | Table | Text:
    if state.attention_picker_active:
        return render_attention_picker(state)
    if state.help_overlay_active:
        return render_help_overlay(state)
    if state.view_level == "forensic":
        return render_forensic_transcript_panel(state)
    if state.view_level == "session":
        return render_session_panel(state)
    if state.view_level == "operation":
        return render_operation_panel(state)
    return render_detail_table(state)


def render_list_table(state: FleetWorkbenchState) -> Table:
    table = Table(expand=True, box=None, show_header=True)
    table.add_column("", no_wrap=True)
    table.add_column("Op", no_wrap=True)
    table.add_column("State", no_wrap=True)
    table.add_column("Signal", no_wrap=True)
    table.add_column("Objective")
    if not state.items:
        table.add_row(
            "",
            "-",
            "-",
            "-",
            Text(
                "No operations match the current filter."
                if state.filter_query
                else "No active operations. Run 'operator run [goal]' to start."
            ),
        )
        return table
    for index, item in enumerate(state.items):
        table.add_row(
            ">" if index == state.selected_index else " ",
            item.operation_id,
            status_text(item),
            signal_text(item),
            item.objective_brief,
        )
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


def render_fleet_detail_table(state: FleetWorkbenchState) -> Table:
    table = Table(expand=True, box=None, show_header=False)
    table.add_column("Field", no_wrap=True, style="bold")
    table.add_column("Value")
    selected = state.selected_item
    if selected is None:
        table.add_row("Status", "No operation selected.")
        return table
    brief = state.selected_fleet_brief
    if not isinstance(brief, dict):
        table.add_row("Operation", selected.operation_id)
        table.add_row("Goal", selected.objective_brief)
        table.add_row("Now", selected.focus_brief or selected.recency_brief)
        table.add_row("Wait", selected.runtime_alert or selected.latest_outcome_brief or "-")
        table.add_row(
            "Progress",
            _fleet_progress_text(
                {
                    "done": selected.blocker_brief
                    if selected.blocker_brief is not None and selected.status == "completed"
                    else None,
                    "doing": selected.latest_outcome_brief,
                    "next": selected.blocker_brief,
                }
            ),
        )
        table.add_row(
            "Attention", "\n".join(selected.attention_briefs) if selected.attention_briefs else "-"
        )
        table.add_row("Recent", selected.latest_outcome_brief or "-")
        return table
    table.add_row("Operation", selected.operation_id)
    table.add_row("Goal", _fleet_optional_text(brief.get("goal")))
    table.add_row("Now", _fleet_optional_text(brief.get("now")))
    table.add_row("Wait", _fleet_optional_text(brief.get("wait")))
    table.add_row("Progress", _fleet_progress_text(brief.get("progress")))
    table.add_row("Attention", _fleet_optional_text(brief.get("attention")))
    table.add_row("Recent", _fleet_optional_text(brief.get("recent")))
    return table


def _fleet_optional_text(value: object) -> str:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return "-"


def _fleet_progress_text(progress: object) -> str:
    if not isinstance(progress, dict):
        return "-"
    done = progress.get("done")
    doing = progress.get("doing")
    next_step = progress.get("next")
    parts: list[str] = []
    if isinstance(done, str) and done.strip():
        parts.append(f"done={done.strip()}")
    if isinstance(doing, str) and doing.strip():
        parts.append(f"doing={doing.strip()}")
    if isinstance(next_step, str) and next_step.strip():
        parts.append(f"next={next_step.strip()}")
    return "\n".join(parts) or "-"


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


def render_help_overlay(state: FleetWorkbenchState) -> Table:
    table = Table(expand=True, box=None, show_header=False)
    table.add_column("Key", no_wrap=True, style="bold")
    table.add_column("Action")
    for key, action in _help_rows_for_view(state.view_level):
        table.add_row(key, action)
    return table


def _help_rows_for_view(view_level: str) -> list[tuple[str, str]]:
    common = [("?", "close help"), ("Esc", "close help or go back"), ("q", "quit")]
    if view_level == "operation":
        return [
            ("j / k", "move task selection"),
            ("Enter", "open selected task session"),
            ("/", "filter tasks"),
            ("Tab", "jump to next blocking task attention"),
            ("a", "answer oldest blocking attention for selected task"),
            ("n", "answer oldest non-blocking attention for selected task"),
            ("A", "open attention picker for selected task"),
            ("i / d / t / m / o", "switch right pane detail mode"),
            ("p / u / s / c / r", "pause, unpause, interrupt, cancel, refresh"),
            *common,
        ]
    if view_level == "session":
        return [
            ("j / k", "move timeline selection"),
            ("Enter", "open selected event in forensic view"),
            ("/", "filter session timeline"),
            ("r", "open forensic raw transcript"),
            ("i / o", "show live session detail or retrospective report"),
            ("a", "answer oldest blocking attention for current task"),
            ("n", "answer oldest non-blocking attention for current task"),
            ("A", "open attention picker for current task"),
            ("p / u / s / c", "pause, unpause, interrupt, cancel"),
            *common,
        ]
    if view_level == "forensic":
        return [
            ("/", "filter forensic transcript/detail"),
            ("a", "answer oldest blocking attention for current task"),
            ("n", "answer oldest non-blocking attention for current task"),
            ("A", "open attention picker for current task"),
            ("?", "close help"),
            ("Esc / q", "return to session timeline"),
            ("ctrl+c", "quit"),
        ]
    return [
        ("j / k", "move operation selection"),
        ("Enter", "open selected operation"),
        ("/", "filter fleet operations"),
        ("Tab", "jump to next blocking attention"),
        ("a", "answer oldest blocking attention in selected operation"),
        ("n", "answer oldest non-blocking attention in selected operation"),
        ("A", "open attention picker in selected operation"),
        ("p / u / s / c / r", "pause, unpause, interrupt, cancel, refresh"),
        *common,
    ]


def render_attention_picker(state: FleetWorkbenchState) -> Table:
    table = Table(expand=True, box=None, show_header=True)
    table.add_column("", no_wrap=True)
    table.add_column("Kind", no_wrap=True)
    table.add_column("Attention", no_wrap=True)
    table.add_column("Title")
    table.add_column("Question")
    items = _attention_picker_items(state)
    if not items:
        table.add_row("", "-", "-", "No attention items in the current scope.", "-")
        return table
    for index, item in enumerate(items):
        table.add_row(
            ">" if index == state.attention_picker_index else " ",
            "blocking" if item.blocking else "non-blocking",
            item.attention_id,
            item.title or "-",
            item.question or "-",
        )
    return table


def _attention_picker_items(state: FleetWorkbenchState):
    payload = state.selected_operation_payload
    operation_id = state.attention_picker_operation_id
    if not isinstance(payload, dict) or operation_id is None:
        return []
    if state.attention_picker_task_id is not None:
        return task_scope_attentions(payload, task_id=state.attention_picker_task_id)
    return operation_scope_attentions(payload, operation_id=operation_id)


def render_detail_table(state: FleetWorkbenchState) -> Table:
    if state.view_level == "fleet":
        return render_fleet_detail_table(state)
    table = Table(expand=True, box=None, show_header=False)
    table.add_column("Field", no_wrap=True, style="bold")
    table.add_column("Value")
    selected = state.selected_item
    detail = state.selected_operation_payload
    if selected is None:
        table.add_row("Status", "No operation selected.")
        return table
    table.add_row("Operation", selected.operation_id)
    table.add_row("Status", status_text(selected))
    table.add_row("Objective", selected.objective_brief)
    if selected.project_profile_name is not None:
        table.add_row("Project", selected.project_profile_name)
    if selected.focus_brief is not None:
        table.add_row("Focus", selected.focus_brief)
    if selected.latest_outcome_brief is not None:
        table.add_row("Latest", selected.latest_outcome_brief)
    if selected.blocker_brief is not None:
        table.add_row("Blocker", selected.blocker_brief)
    if selected.runtime_alert is not None:
        table.add_row("Alert", selected.runtime_alert)
    if selected.attention_briefs:
        table.add_row("Attention", "\n".join(selected.attention_briefs))
    if not isinstance(detail, dict):
        table.add_row("Detail", "No operation detail available.")
        return table
    summary = detail.get("summary")
    if isinstance(summary, dict):
        for key, label in [
            ("work_summary", "Work"),
            ("next_step", "Next"),
            ("verification_summary", "Verify"),
        ]:
            value = summary.get(key)
            if isinstance(value, str) and value.strip():
                table.add_row(label, value.strip())
    context = detail.get("context")
    if isinstance(context, dict):
        run_mode = context.get("run_mode")
        involvement = context.get("involvement_level")
        if isinstance(run_mode, str) and run_mode.strip():
            table.add_row("Run mode", run_mode.strip())
        if isinstance(involvement, str) and involvement.strip():
            table.add_row("Involvement", involvement.strip())
        active_session = context.get("active_session")
        if isinstance(active_session, dict):
            session_status = str(active_session.get("status") or "-")
            adapter = str(active_session.get("adapter_key") or "-")
            table.add_row("Session", f"{adapter} [{session_status}]")
            waiting_reason = active_session.get("waiting_reason")
            if isinstance(waiting_reason, str) and waiting_reason.strip():
                table.add_row("Waiting", waiting_reason.strip())
        open_attention = context.get("open_attention")
        if isinstance(open_attention, list) and open_attention:
            titles = [
                str(item.get("title"))
                for item in open_attention
                if isinstance(item, dict) and item.get("title")
            ]
            if titles:
                table.add_row("Open attention", "\n".join(titles[:3]))
    return table


def render_operation_panel(state: FleetWorkbenchState) -> Group | Table | Text:
    if state.operation_panel_mode == "detail":
        return render_operation_detail_panel(state)
    if state.operation_panel_mode == "decisions":
        return Text(
            "\n\n".join(filtered_decisions(state.selected_operation_payload, state.selected_task))
            or "No decision memos for the selected scope."
        )
    if state.operation_panel_mode == "events":
        payload = state.selected_operation_payload
        events = payload.get("recent_events") if isinstance(payload, dict) else None
        return Text(
            "\n".join(str(item) for item in events if isinstance(item, str))
            if isinstance(events, list) and events
            else "No recent events."
        )
    if state.operation_panel_mode == "memory":
        return Text(
            "\n\n".join(
                filtered_memory_entries(state.selected_operation_payload, state.selected_task)
            )
            or "No memory entries for the selected scope."
        )
    if state.operation_panel_mode == "report":
        payload = state.selected_operation_payload
        report_text = payload.get("report_text") if isinstance(payload, dict) else None
        if isinstance(report_text, str) and report_text.strip():
            return Text(report_text.strip())
        return Text("No retrospective report has been recorded for this operation.")
    return render_task_detail_table(state)


def render_operation_detail_panel(state: FleetWorkbenchState) -> Group:
    return Group(render_operation_brief_table(state), render_task_detail_table(state))


def render_operation_brief_table(state: FleetWorkbenchState) -> Table:
    table = Table(expand=True, box=None, show_header=False)
    table.add_column("Field", no_wrap=True, style="bold")
    table.add_column("Value")
    selected = state.selected_item
    if selected is None:
        table.add_row("Status", "No operation selected.")
        return table
    payload = (
        state.selected_operation_payload
        if isinstance(state.selected_operation_payload, dict)
        else {}
    )
    payload_brief = payload.get("operation_brief")
    if not isinstance(payload_brief, dict):
        payload_brief = {
            "goal": selected.objective_brief,
            "now": selected.focus_brief or selected.recency_brief,
            "wait": selected.runtime_alert or selected.latest_outcome_brief,
            "progress": {
                "done": selected.blocker_brief if selected.status == "completed" else None,
                "doing": selected.latest_outcome_brief,
                "next": selected.blocker_brief,
            },
            "attention": "\n".join(selected.attention_briefs),
            "recent": selected.latest_outcome_brief,
        }

    table.add_row("Operation", selected.operation_id)
    table.add_row("Goal", _fleet_optional_text(payload_brief.get("goal")))
    table.add_row("Now", _fleet_optional_text(payload_brief.get("now")))
    table.add_row("Wait", _fleet_optional_text(payload_brief.get("wait")))
    table.add_row("Progress", _fleet_progress_text(payload_brief.get("progress")))
    table.add_row("Attention", _fleet_optional_text(payload_brief.get("attention")))
    table.add_row("Recent", _fleet_optional_text(payload_brief.get("recent")))
    return table


def render_session_panel(state: FleetWorkbenchState) -> Group | Table | Text:
    if state.session_panel_mode == "report":
        payload = state.selected_operation_payload
        report_text = payload.get("report_text") if isinstance(payload, dict) else None
        if isinstance(report_text, str) and report_text.strip():
            return Text(report_text.strip())
        return Text("No retrospective report has been recorded for this operation.")
    if state.session_panel_mode == "raw_transcript":
        return render_raw_transcript_panel(state)
    return Group(
        render_session_brief_table(state),
        Text("-" * 40),
        render_timeline_detail_table(state),
    )


def render_task_detail_table(state: FleetWorkbenchState) -> Table:
    table = Table(expand=True, box=None, show_header=False)
    table.add_column("Field", no_wrap=True, style="bold")
    table.add_column("Value")
    task = state.selected_task
    payload = (
        state.selected_operation_payload
        if isinstance(state.selected_operation_payload, dict)
        else {}
    )
    if task is None:
        table.add_row("Task", "No task selected.")
        return table
    table.add_row("Task", f"{task.task_short_id} · {task.title}")
    table.add_row("Status", task.status)
    table.add_row("Priority", str(task.priority))
    table.add_row("Goal", task.goal)
    table.add_row("Done", task.definition_of_done)
    if task.assigned_agent is not None:
        table.add_row("Agent", task.assigned_agent)
    if task.linked_session_id is not None:
        table.add_row("Session", task.linked_session_id)
    if task.dependencies:
        table.add_row("Dependencies", ", ".join(task.dependencies))
    if task.memory_refs:
        table.add_row("Memory refs", ", ".join(task.memory_refs))
    if task.artifact_refs:
        table.add_row("Artifact refs", ", ".join(task.artifact_refs))
    if task.notes:
        table.add_row("Notes", "\n".join(task.notes))
    session_line = task_session_summary(payload, task)
    if session_line is not None:
        table.add_row("Session detail", session_line)
        table.add_row("Escalate", "Enter session for live context; o opens retrospective report")
    attentions = task_attention_titles(payload, task)
    if attentions:
        table.add_row("Attention", "\n".join(attentions))
    return table


def render_timeline_detail_table(state: FleetWorkbenchState) -> Table:
    table = Table(expand=True, box=None, show_header=False)
    table.add_column("Field", no_wrap=True, style="bold")
    table.add_column("Value")
    event = state.selected_timeline_event
    for label, value in event_detail_lines(event):
        table.add_row(label, value)
    return table


def render_session_brief_table(state: FleetWorkbenchState) -> Table:
    table = Table(expand=True, box=None, show_header=False)
    table.add_column("Field", no_wrap=True, style="bold")
    table.add_column("Value")
    brief = session_brief(state.selected_operation_payload, state.selected_task)
    task = state.selected_task
    session = selected_session(state.selected_operation_payload, task)
    if task is not None:
        table.add_row("Task", f"{task.task_short_id} · {task.title}")
    if session is not None:
        adapter = str(session.get("adapter_key") or "-")
        session_id = str(session.get("session_id") or "-")
        table.add_row("Session", f"{adapter} · {session_id}")
    table.add_row("Now", brief["now"])
    table.add_row("Wait", brief["wait"])
    table.add_row("Attention", brief["attention"])
    table.add_row("Latest output", brief["latest_output"])
    table.add_row("Escalate", "Enter/r transcript-log path; o retrospective report")
    return table


def render_raw_transcript_panel(state: FleetWorkbenchState) -> Text:
    lines = (
        filtered_raw_transcript_lines(
            state.selected_operation_payload,
            state.forensic_filter_query,
        )
        if state.view_level == "forensic"
        else raw_transcript_lines(state.selected_operation_payload)
    )
    event = state.selected_timeline_event
    prefix: list[str] = []
    if event is not None:
        prefix = [
            f"Focused event: {event.summary}",
            f"event_type={event.event_type} iteration={event.iteration}",
            "",
        ]
    if not lines:
        message = (
            "No raw transcript lines match the current filter."
            if state.view_level == "forensic" and state.forensic_filter_query
            else "No raw transcript available for the selected session."
        )
        return Text("\n".join(prefix + [message]))
    return Text("\n".join(prefix + lines))


def render_forensic_transcript_panel(state: FleetWorkbenchState) -> Text:
    return render_raw_transcript_panel(state)


def render_footer_text(state: FleetWorkbenchState) -> Text:
    selected = state.selected_item
    if state.attention_picker_active:
        return Text("j/k move  Enter select attention  A or Esc close  q quit")
    if state.help_overlay_active:
        return Text("? or Esc close help  q quit")
    if state.pending_filter_text is not None:
        return Text(
            f"fleet filter: {state.pending_filter_text}  Enter apply  Esc cancel  Backspace edit"
        )
    if state.pending_task_filter_text is not None:
        return Text(
            "task filter: "
            f"{state.pending_task_filter_text}  Enter apply  Esc cancel  Backspace edit"
        )
    if state.pending_session_filter_text is not None:
        return Text(
            "session filter: "
            f"{state.pending_session_filter_text}  Enter apply  Esc cancel  Backspace edit"
        )
    if state.pending_forensic_filter_text is not None:
        return Text(
            "forensic filter: "
            f"{state.pending_forensic_filter_text}  Enter apply  Esc cancel  Backspace edit"
        )
    if state.pending_answer_operation_id is not None:
        instruction = state.pending_answer_prompt
        return Text(
            f"answer[{state.pending_answer_attention_id}] for {state.pending_answer_operation_id}: "
            + instruction
            + state.pending_answer_text
            + "  Enter send  Esc cancel"
        )
    if state.pending_confirmation is not None and selected is not None:
        return Text(f"Cancel {state.pending_confirmation}? [y/N]  Any non-affirmative key aborts.")
    if state.last_message is not None:
        return Text(state.last_message)
    if state.view_level == "forensic":
        return Text("a/n answer  A picker  / filter  Esc/q back to session timeline  ctrl+c quit")
    if state.view_level == "session":
        return Text(
            "j/k move  / filter  Enter forensic  r forensic/raw transcript  i live detail  o report"
            "  Esc back  a/n answer"
            "  A picker"
            "  s interrupt task/session  p pause  u unpause  c cancel  q quit"
        )
    if state.view_level == "operation":
        return Text(
            "j/k move  Enter session  / filter  a/n answer"
            "  A picker"
            "  i detail  d decisions  t events  m memory  o report"
            "  Esc back  p pause  u unpause  s interrupt task/session  c cancel  r refresh  q quit"
        )
    help_line = Text(
        "j/k or arrows move  Enter open  a/n answer  A picker  tab next-attention"
        "  / filter  p pause  u unpause  s interrupt  c cancel  r refresh  q quit"
    )
    if selected is None:
        return help_line
    return Text(f"{selected.operation_id} selected. ") + help_line
