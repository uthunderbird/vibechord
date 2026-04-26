from __future__ import annotations

from rich.console import Group
from rich.table import Table
from rich.text import Text

from . import rendering_chrome as _rendering_chrome
from . import rendering_detail as _rendering_detail
from . import rendering_lists as _rendering_lists
from .models import FleetWorkbenchState

header_lines = _rendering_chrome.header_lines
human_footer_text = _rendering_chrome.human_footer_text
human_header_lines = _rendering_chrome.human_header_lines
render_attention_picker = _rendering_chrome.render_attention_picker
render_converse_panel = _rendering_chrome.render_converse_panel
render_footer_text = _rendering_chrome.render_footer_text
render_help_overlay = _rendering_chrome.render_help_overlay
rendered_header_lines = _rendering_chrome.rendered_header_lines
right_pane_title = _rendering_chrome.right_pane_title

render_detail_table = _rendering_detail.render_detail_table
render_fleet_detail_table = _rendering_detail.render_fleet_detail_table
render_forensic_transcript_panel = _rendering_detail.render_forensic_transcript_panel
render_operation_brief_table = _rendering_detail.render_operation_brief_table
render_operation_detail_panel = _rendering_detail.render_operation_detail_panel
render_operation_panel = _rendering_detail.render_operation_panel
render_raw_transcript_panel = _rendering_detail.render_raw_transcript_panel
render_session_brief_table = _rendering_detail.render_session_brief_table
render_session_panel = _rendering_detail.render_session_panel
render_task_detail_table = _rendering_detail.render_task_detail_table
render_timeline_detail_table = _rendering_detail.render_timeline_detail_table
_session_timeline_summary = _rendering_detail._session_timeline_summary

render_forensic_context = _rendering_lists.render_forensic_context
render_left_pane = _rendering_lists.render_left_pane
render_list_table = _rendering_lists.render_list_table
render_session_timeline = _rendering_lists.render_session_timeline
render_task_board = _rendering_lists.render_task_board


def render_workbench(state: FleetWorkbenchState) -> Group:
    return _rendering_chrome.render_workbench(
        state,
        render_left_pane=render_left_pane,
        render_right_pane=render_right_pane,
    )


def render_right_pane(state: FleetWorkbenchState) -> Group | Table | Text:
    if state.attention_picker_active:
        return render_attention_picker(state)
    if state.converse_panel_active:
        return render_converse_panel(state)
    if state.help_overlay_active:
        return render_help_overlay(state)
    if state.view_level == "forensic":
        return render_forensic_transcript_panel(state)
    if state.view_level == "session":
        return render_session_panel(state)
    if state.view_level == "operation":
        return render_operation_panel(state)
    return render_detail_table(state)
