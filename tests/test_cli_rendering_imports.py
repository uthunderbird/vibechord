import agent_operator.cli.commands as cli_commands
import agent_operator.cli.helpers as cli_helpers
import agent_operator.cli.rendering as cli_rendering
import agent_operator.cli.tui as cli_tui
from agent_operator.cli.main import _format_live_snapshot
from agent_operator.cli.rendering import (
    emit_context_lines,
    format_fleet_mix_counts,
    format_live_event,
    format_live_snapshot,
    render_dashboard,
    render_fleet_dashboard,
    render_fleet_items_table,
    render_inspect_summary,
    render_operation_list_line,
    render_project_dashboard,
    render_project_policy_table,
    render_status_brief,
)


def test_cli_rendering_package_exports_and_main_imports_resolve() -> None:
    assert cli_commands.__doc__ == "CLI command family package."
    assert cli_helpers.__doc__ == "CLI helper family package."
    assert cli_rendering.__doc__ == "CLI rendering family facade."
    assert cli_tui.__doc__ == "CLI TUI family facade."
    assert callable(format_fleet_mix_counts)
    assert callable(emit_context_lines)
    assert callable(format_live_event)
    assert callable(format_live_snapshot)
    assert callable(render_dashboard)
    assert callable(render_fleet_dashboard)
    assert callable(render_fleet_items_table)
    assert callable(render_inspect_summary)
    assert callable(render_operation_list_line)
    assert callable(render_project_dashboard)
    assert callable(render_project_policy_table)
    assert callable(render_status_brief)
    assert callable(_format_live_snapshot)
    assert cli_rendering.text is not None
    assert cli_tui.models is not None
    assert cli_tui.rendering is not None
