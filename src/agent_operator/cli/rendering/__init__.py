"""CLI rendering family facade."""

from . import text
from .fleet import format_fleet_mix_counts, render_fleet_dashboard, render_fleet_items_table
from .operation import render_dashboard
from .project import render_project_dashboard, render_project_policy_table
from .text import (
    emit_context_lines,
    format_live_event,
    format_live_snapshot,
    render_inspect_summary,
    render_operation_list_line,
    render_status_brief,
)

__all__ = [
    "emit_context_lines",
    "format_fleet_mix_counts",
    "format_live_event",
    "format_live_snapshot",
    "render_dashboard",
    "render_fleet_dashboard",
    "render_fleet_items_table",
    "render_inspect_summary",
    "render_operation_list_line",
    "render_project_dashboard",
    "render_project_policy_table",
    "render_status_brief",
    "text",
]
