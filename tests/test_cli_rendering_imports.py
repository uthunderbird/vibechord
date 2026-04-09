from agent_operator.cli.main import _format_live_snapshot
from agent_operator.cli.rendering import (
    format_fleet_mix_counts,
    render_dashboard,
    render_fleet_dashboard,
    render_fleet_items_table,
    render_project_dashboard,
    render_project_policy_table,
)
from agent_operator.cli.rendering.text import format_live_event


def test_cli_rendering_package_exports_and_main_imports_resolve() -> None:
    assert callable(format_fleet_mix_counts)
    assert callable(render_dashboard)
    assert callable(render_fleet_dashboard)
    assert callable(render_fleet_items_table)
    assert callable(render_project_dashboard)
    assert callable(render_project_policy_table)
    assert callable(format_live_event)
    assert callable(_format_live_snapshot)
