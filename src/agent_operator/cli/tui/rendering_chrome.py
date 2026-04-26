from __future__ import annotations

from rich.columns import Columns
from rich.console import Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from .models import (
    FleetWorkbenchState,
    filtered_dashboard_tasks,
    operation_scope_attentions,
    session_brief,
    session_event_label,
    session_identity_text,
    task_lane,
    task_scope_attentions,
)


def render_workbench(state: FleetWorkbenchState, *, render_left_pane, render_right_pane) -> Group:
    header = human_header_lines(state)
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
    footer = human_footer_text(state)
    return Group(
        Panel("\n".join(header), border_style="blue"),
        Columns([left, right], equal=True, expand=True),
        Panel(footer, border_style="magenta"),
    )


def header_lines(state: FleetWorkbenchState) -> list[str]:
    return human_header_lines(state)


def human_header_lines(state: FleetWorkbenchState) -> list[str]:
    return rendered_header_lines(state)


def rendered_header_lines(state: FleetWorkbenchState) -> list[str]:
    breadcrumb = "Fleet"
    if state.view_level == "operation" and state.selected_item is not None:
        breadcrumb = f"Fleet / {state.selected_item.operation_id} / operation"
    if state.view_level == "session" and state.selected_item is not None:
        breadcrumb = f"Fleet / {state.selected_item.operation_id} / session"
        if state.selected_task is not None:
            breadcrumb += f" / {state.selected_task.task_short_id}"
    if state.view_level == "forensic" and state.selected_item is not None:
        breadcrumb = f"Fleet / {state.selected_item.operation_id} / forensic"
        if state.selected_task is not None:
            breadcrumb += f" / {state.selected_task.task_short_id}"
        if state.selected_timeline_event is not None:
            breadcrumb += (
                f" / iter {state.selected_timeline_event.iteration} "
                f"{state.selected_timeline_event.event_type}"
            )

    project_label = state.project if state.project is not None else "all projects"
    lines = [breadcrumb, _fleet_scope_line(state, project_label)]
    if state.view_level == "session":
        lines[1] = session_identity_text(state.selected_operation_payload, state.selected_task)
        brief = session_brief(state.selected_operation_payload, state.selected_task)
        summary = (
            f"Now: {brief['now']}  Wait: {brief['wait']}  Attention: {brief['attention']}"
            f"  Latest output: {brief['latest_output']}"
        )
        if state.session_filter_query:
            summary += f"  Filter: {state.session_filter_query}"
        lines.append(summary)
        return lines
    if state.view_level == "forensic":
        lines[1] = session_identity_text(state.selected_operation_payload, state.selected_task)
        event = state.selected_timeline_event
        summary = (
            f"Selected event: iter {event.iteration} {session_event_label(event)}"
            if event is not None
            else "Selected event: -"
        )
        if state.forensic_filter_query:
            summary += f"  Filter: {state.forensic_filter_query}"
        lines.append(summary)
        return lines

    if state.view_level == "operation" and state.task_filter_query:
        lines[1] += f"  Task filter: {state.task_filter_query}"
    if state.filter_query:
        lines[1] += f"  Fleet filter: {state.filter_query}"
    if state.view_level == "fleet" and state.selected_item is not None:
        selected = state.selected_item
        lines.append(
            "Selected: "
            f"{selected.display_name}  Now: "
            f"{selected.focus_brief or selected.recency_brief}  "
            f"Wait: {selected.runtime_alert or selected.latest_outcome_brief or '-'}"
        )
        return lines
    if state.view_level == "operation" and state.selected_item is not None:
        payload = state.selected_operation_payload
        brief = payload.get("operation_brief") if isinstance(payload, dict) else None
        if not isinstance(brief, dict):
            brief = state.selected_item.brief if isinstance(state.selected_item.brief, dict) else {}
        tasks = filtered_dashboard_tasks(state.selected_operation_payload, state.task_filter_query)
        running = sum(1 for task in tasks if task.status == "running")
        blocked = sum(1 for task in tasks if task_lane(task) == "BLOCKED")
        attention = _optional_text(brief.get("attention"))
        if attention == "-" and state.selected_item.attention_briefs:
            attention = "; ".join(state.selected_item.attention_briefs)
        lines.append(
            f"Tasks: {len(tasks)}  Running: {running}  Blocked: {blocked}  "
            f"Now: {_optional_text(brief.get('now'))}  "
            f"Wait: {_optional_text(brief.get('wait'))}  "
            f"Attention: {attention}"
        )
    return lines


def right_pane_title(state: FleetWorkbenchState) -> str:
    if state.attention_picker_active:
        return "Attention Picker"
    if state.converse_panel_active:
        return "Converse"
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


def render_help_overlay(state: FleetWorkbenchState) -> Table:
    table = Table(expand=True, box=None, show_header=False)
    table.add_column("Key", no_wrap=True, style="bold")
    table.add_column("Action")
    for key, action in _help_rows_for_view(state.view_level):
        table.add_row(key, action)
    return table


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


def render_converse_panel(state: FleetWorkbenchState) -> Text:
    lines = [f"Context: {_converse_scope_label(state)}", ""]
    if not state.converse_transcript_lines:
        lines.append("No conversation yet. Type a message and press Enter.")
    else:
        lines.extend(state.converse_transcript_lines)
    if state.converse_pending_command_text is not None:
        lines.extend(["", f"Pending action: {state.converse_pending_command_text}"])
    return Text("\n".join(lines))


def render_footer_text(state: FleetWorkbenchState) -> Text:
    return human_footer_text(state)


def human_footer_text(state: FleetWorkbenchState) -> Text:
    selected = state.selected_item
    if state.attention_picker_active:
        return Text("Move j/k  Pick Enter  Close A/Esc  Quit q")
    if state.pending_palette_text is not None:
        if state.pending_palette_preview is not None:
            return Text(
                "Command preview: :"
                + state.pending_palette_preview
                + "  Confirm y  Cancel N/Esc"
            )
        return Text(
            "Command: :"
            + (state.pending_palette_text or "")
            + "  Complete Tab  Preview Enter  Cancel Esc"
        )
    if state.converse_panel_active:
        if state.converse_editing_command:
            return Text(
                "Edit proposed action: "
                + state.converse_input_text
                + "  Save Enter  Cancel Esc"
            )
        if state.converse_pending_command_text is not None:
            return Text(
                "Converse proposed action: "
                + state.converse_pending_command_text
                + "  Execute y  Decline N/Esc  Edit e"
            )
        return Text("Converse: " + state.converse_input_text + "  Send Enter  Close Esc")
    if state.help_overlay_active:
        return Text("Close help ?/Esc  Quit q")
    if state.pending_filter_text is not None:
        return Text(
            f"Fleet filter: {state.pending_filter_text}  Apply Enter  Cancel Esc  Edit Backspace"
        )
    if state.pending_task_filter_text is not None:
        return Text(
            "Task filter: "
            f"{state.pending_task_filter_text}  Apply Enter  Cancel Esc  Edit Backspace"
        )
    if state.pending_session_filter_text is not None:
        return Text(
            "Session filter: "
            f"{state.pending_session_filter_text}  Apply Enter  Cancel Esc  Edit Backspace"
        )
    if state.pending_forensic_filter_text is not None:
        return Text(
            "Forensic filter: "
            f"{state.pending_forensic_filter_text}  Apply Enter  Cancel Esc  Edit Backspace"
        )
    if state.pending_answer_operation_id is not None:
        instruction = state.pending_answer_prompt
        return Text(
            f"Answer {state.pending_answer_attention_id} in {state.pending_answer_operation_id}: "
            + instruction
            + state.pending_answer_text
            + "  Send Enter  Cancel Esc"
        )
    if state.pending_confirmation is not None and selected is not None:
        return Text(
            "Cancel "
            f"{state.pending_confirmation}?  Confirm y  Keep working with any other key"
        )
    if state.last_message is not None:
        return Text(state.last_message)
    if state.view_level == "forensic":
        return Text(
            "Forensic: Filter /  Answer a/N  Pick A  Command :  Converse n"
            "  Back Esc/q  Help ?  Quit ctrl+c"
        )
    if state.view_level == "session":
        return Text(
            "Move j/k  Filter /  Open forensic Enter/r  Live detail i  Report o"
            "  Back Esc  Answer a/N  Pick A  Command :  Converse n  Interrupt s  Pause p  Resume u"
            "  Cancel c  Help ?  Quit q"
        )
    if state.view_level == "operation":
        return Text(
            "Move j/k  Open session Enter  Filter /  Answer a/N  Pick A  Command :  Converse n"
            "  Detail i  Decisions d  Events t  Memory m  Transcript l  Report o"
            "  Back Esc  Pause p  Resume u  Interrupt s  Cancel c  Refresh r  Help ?  Quit q"
        )
    footer = Text(
        "Move j/k  Open Enter  Answer a/N  Pick A  Next blocker Tab  Command :  Converse n"
        "  Filter /  Pause p  Resume u  Interrupt s  Cancel c  Refresh r  Help ?  Quit q"
    )
    if selected is None:
        return footer
    return Text(f"Selected {selected.operation_id}. ") + footer


def _fleet_scope_line(state: FleetWorkbenchState, project_label: str) -> str:
    running_count, needs_human_count, paused_count = _fleet_counts(state)
    return (
        f"Scope: {project_label}  Operations: {state.total_operations}  "
        f"Running: {running_count}  Needs human: {needs_human_count}  Paused: {paused_count}"
    )


def _fleet_counts(state: FleetWorkbenchState) -> tuple[int, int, int]:
    raw_header = getattr(state, "fleet_header", None)
    header = raw_header if isinstance(raw_header, dict) else {}
    items = state.all_items or state.items
    running = header.get("running_count")
    needs_human = header.get("needs_human_count")
    paused = header.get("paused_count")
    if not isinstance(running, int):
        running = sum(1 for item in items if item.status == "running")
    if not isinstance(needs_human, int):
        needs_human = sum(1 for item in items if item.status == "needs_human")
    if not isinstance(paused, int):
        paused = sum(1 for item in items if item.scheduler_state in {"paused", "pause_requested"})
    return running, needs_human, paused


def _attention_picker_items(state: FleetWorkbenchState):
    payload = state.selected_operation_payload
    operation_id = state.attention_picker_operation_id
    if not isinstance(payload, dict) or operation_id is None:
        return []
    if state.attention_picker_task_id is not None:
        return task_scope_attentions(payload, task_id=state.attention_picker_task_id)
    return operation_scope_attentions(payload, operation_id=operation_id)


def _help_rows_for_view(view_level: str) -> list[tuple[str, str]]:
    common = [("?", "close help"), ("Esc", "close help or go back"), ("q", "quit")]
    if view_level == "operation":
        return [
            ("j / k", "move task selection"),
            ("Enter", "open selected task session"),
            ("l", "open selected task transcript/log path"),
            ("/", "filter tasks"),
            ("Tab", "jump to next blocking task attention"),
            ("a", "answer oldest blocking attention for selected task"),
            ("N", "answer oldest non-blocking attention for selected task"),
            ("A", "open attention picker for selected task"),
            (":", "open command palette"),
            ("n", "open converse panel"),
            ("i / d / t / m / o", "switch right pane detail mode"),
            ("p / u / s / c / r", "pause, unpause, interrupt, cancel, refresh"),
            *common,
        ]
    if view_level == "session":
        return [
            ("j / k", "move timeline selection"),
            ("Enter", "open selected event in forensic view"),
            ("/", "filter session timeline"),
            ("r", "open forensic view"),
            ("i / o", "show live session detail or retrospective report"),
            ("a", "answer oldest blocking attention for current task"),
            ("N", "answer oldest non-blocking attention for current task"),
            ("A", "open attention picker for current task"),
            (":", "open command palette"),
            ("n", "open converse panel"),
            ("p / u / s / c", "pause, unpause, interrupt, cancel"),
            *common,
        ]
    if view_level == "forensic":
        return [
            ("/", "filter forensic transcript/detail"),
            ("a", "answer oldest blocking attention for current task"),
            ("N", "answer oldest non-blocking attention for current task"),
            ("A", "open attention picker for current task"),
            (":", "open command palette"),
            ("n", "open converse panel"),
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
        ("N", "answer oldest non-blocking attention in selected operation"),
        ("A", "open attention picker in selected operation"),
        (":", "open command palette"),
        ("n", "open converse panel"),
        ("p / u / s / c / r", "pause, unpause, interrupt, cancel, refresh"),
        *common,
    ]


def _converse_scope_label(state: FleetWorkbenchState) -> str:
    if state.view_level == "fleet":
        return f"fleet ({state.project or 'all projects'})"
    if state.view_level == "operation" and state.selected_item is not None:
        return f"operation {state.selected_item.operation_id}"
    if state.view_level == "session" and state.selected_task is not None:
        return f"session {state.selected_task.task_short_id}"
    if state.view_level == "forensic" and state.selected_timeline_event is not None:
        return (
            "forensic "
            f"iter {state.selected_timeline_event.iteration} "
            f"{state.selected_timeline_event.event_type}"
        )
    if state.selected_item is not None:
        return state.selected_item.operation_id
    return "fleet"


def _optional_text(value: object) -> str:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return "-"
