from __future__ import annotations

from rich.console import Group
from rich.table import Table
from rich.text import Text

from .models import (
    FleetWorkbenchState,
    event_detail_lines,
    filtered_decisions,
    filtered_memory_entries,
    filtered_raw_transcript_lines,
    filtered_session_timeline_events,
    raw_transcript_lines,
    selected_session,
    session_brief,
    session_timeline_events,
    status_text,
    task_attention_titles,
    task_session_summary,
)


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
            _progress_text(
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
        nonblocking = selected.brief.get("review") if isinstance(selected.brief, dict) else None
        if _optional_text(nonblocking) != "-":
            table.add_row("Review", _optional_text(nonblocking))
        table.add_row("Recent", selected.latest_outcome_brief or "-")
        return table
    table.add_row("Operation", selected.operation_id)
    table.add_row("Goal", _optional_text(brief.get("goal")))
    table.add_row("Now", _optional_text(brief.get("now")))
    table.add_row("Wait", _optional_text(brief.get("wait")))
    if _optional_text(brief.get("agent_activity")) != "-":
        table.add_row("Agent", _optional_text(brief.get("agent_activity")))
    if _optional_text(brief.get("operator_state")) != "-":
        table.add_row("Operator", _optional_text(brief.get("operator_state")))
    table.add_row("Progress", _progress_text(brief.get("progress")))
    table.add_row("Attention", _optional_text(brief.get("attention")))
    if _optional_text(brief.get("review")) != "-":
        table.add_row("Review", _optional_text(brief.get("review")))
    table.add_row("Recent", _optional_text(brief.get("recent")))
    return table


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
    table.add_row("Goal", _optional_text(payload_brief.get("goal")))
    table.add_row("Now", _optional_text(payload_brief.get("now")))
    table.add_row("Wait", _optional_text(payload_brief.get("wait")))
    if _optional_text(payload_brief.get("agent_activity")) != "-":
        table.add_row("Agent", _optional_text(payload_brief.get("agent_activity")))
    if _optional_text(payload_brief.get("operator_state")) != "-":
        table.add_row("Operator", _optional_text(payload_brief.get("operator_state")))
    table.add_row("Progress", _progress_text(payload_brief.get("progress")))
    table.add_row("Attention", _optional_text(payload_brief.get("attention")))
    if _optional_text(payload_brief.get("review")) != "-":
        table.add_row("Review", _optional_text(payload_brief.get("review")))
    table.add_row("Recent", _optional_text(payload_brief.get("recent")))
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
        table.add_row(
            "Next step",
            "Open session Enter  ·  Transcript/log l  ·  Report o  ·  Back Esc  ·  Help ?",
        )
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
    if brief["agent_activity"] != "-":
        table.add_row("Agent", brief["agent_activity"])
    if brief["operator_state"] != "-":
        table.add_row("Operator", brief["operator_state"])
    table.add_row("Attention", brief["attention"])
    if brief["review"] != "-":
        table.add_row("Review", brief["review"])
    table.add_row("Latest output", brief["latest_output"])
    table.add_row("Timeline", _session_timeline_summary(state))
    table.add_row(
        "Next step",
        "Open forensic Enter/r  ·  Live detail i  ·  Report o  ·  Back Esc  ·  Help ?",
    )
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


def _session_timeline_summary(state: FleetWorkbenchState) -> str:
    filtered_events = filtered_session_timeline_events(
        state.selected_operation_payload,
        state.selected_task,
        state.session_filter_query,
    )
    total_events = len(
        session_timeline_events(
            state.selected_operation_payload,
            state.selected_task,
        )
    )
    if not filtered_events:
        if state.session_filter_query and total_events:
            return f"No timeline events match filter; {total_events} total before filter"
        return "No timeline events."
    selected_position = min(state.selected_timeline_index, len(filtered_events) - 1) + 1
    summary = f"Selected {selected_position} of {len(filtered_events)} events (newest first)"
    if state.session_filter_query and total_events != len(filtered_events):
        summary += f"; {total_events} total before filter"
    return summary


def _optional_text(value: object) -> str:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return "-"


def _progress_text(progress: object) -> str:
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
