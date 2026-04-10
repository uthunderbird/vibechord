from __future__ import annotations

from collections.abc import Callable

from rich.columns import Columns
from rich.console import Group
from rich.panel import Panel
from rich.table import Table

from .fleet import format_fleet_mix_counts, render_fleet_items_table


def render_project_policy_table(
    items: list[dict[str, object]],
    *,
    shorten_live_text: Callable[[str | None], str | None],
) -> Table:
    table = Table(expand=True)
    table.add_column("Policy", no_wrap=True)
    table.add_column("Category", no_wrap=True)
    table.add_column("Applicability")
    table.add_column("Rule")
    if not items:
        table.add_row("-", "-", "none", "-")
        return table
    for item in items[:8]:
        table.add_row(
            str(item.get("policy_id") or "-"),
            str(item.get("category") or "-"),
            shorten_live_text(str(item.get("applicability_summary") or "-")) or "-",
            shorten_live_text(str(item.get("rule_text") or "-")) or "-",
        )
    return table


def render_project_dashboard(
    payload: dict[str, object],
    *,
    shorten_live_text: Callable[[str | None], str | None],
) -> Group:
    resolved = payload.get("resolved")
    fleet = payload.get("fleet")
    policy_summary = payload.get("policy_summary")
    active_policies = payload.get("active_policies")
    hints = payload.get("control_hints")
    header_lines = [
        f"project={payload.get('project')}",
        f"profile_path={payload.get('profile_path')}",
    ]
    if isinstance(resolved, dict):
        cwd = resolved.get("cwd")
        if cwd:
            header_lines.append(f"cwd={cwd}")
        agents = resolved.get("default_agents")
        if isinstance(agents, list) and agents:
            header_lines.append("default_agents=" + ", ".join(str(item) for item in agents))
        header_lines.append(
            "max_iterations="
            + str(resolved.get("max_iterations", "-"))
            + " involvement="
            + str(resolved.get("involvement_level", "-"))
        )
    if isinstance(policy_summary, dict):
        header_lines.append(f"active_policies={policy_summary.get('active_count', 0)}")
        category_counts = policy_summary.get("category_counts")
        if isinstance(category_counts, dict) and category_counts:
            header_lines.append("policy_mix=" + format_fleet_mix_counts(category_counts))
    resolved_lines = ["- none"]
    if isinstance(resolved, dict):
        resolved_lines = []
        if resolved.get("cwd"):
            resolved_lines.append(f"cwd={resolved['cwd']}")
        agents = resolved.get("default_agents")
        if isinstance(agents, list) and agents:
            resolved_lines.append("default_agents=" + ", ".join(str(item) for item in agents))
        harness = shorten_live_text(str(resolved.get("harness_instructions") or "-")) or "-"
        resolved_lines.append(f"harness={harness}")
        success_criteria = resolved.get("success_criteria")
        if isinstance(success_criteria, list) and success_criteria:
            resolved_lines.append(
                "success_criteria=" + " | ".join(str(item) for item in success_criteria[:3])
            )
        resolved_lines.append(f"max_iterations={resolved.get('max_iterations', '-')}")
        resolved_lines.append(f"involvement={resolved.get('involvement_level', '-')}")
        overrides = resolved.get("overrides")
        if isinstance(overrides, list) and overrides:
            resolved_lines.append("overrides=" + ", ".join(str(item) for item in overrides))
    fleet_payload = fleet if isinstance(fleet, dict) else {}
    needs_attention = fleet_payload.get("needs_attention")
    active = fleet_payload.get("active")
    recent = fleet_payload.get("recent")
    mix = fleet_payload.get("mix")
    fleet_lines = [f"total_operations={fleet_payload.get('total_operations', 0)}"]
    if isinstance(mix, dict):
        bucket_counts = mix.get("bucket_counts")
        if isinstance(bucket_counts, dict) and bucket_counts:
            fleet_lines.append("buckets=" + format_fleet_mix_counts(bucket_counts))
    hint_renderable = "\n".join(str(item) for item in hints if isinstance(item, str)) or "- none"
    return Group(
        Panel(
            "\n".join(header_lines),
            title=f"Project Dashboard: {payload.get('project')}",
            border_style="cyan",
        ),
        Columns(
            [
                Panel("\n".join(resolved_lines), title="Resolved Defaults", border_style="green"),
                Panel(
                    render_project_policy_table(
                        active_policies, shorten_live_text=shorten_live_text
                    )
                    if isinstance(active_policies, list)
                    else "-",
                    title=f"Active Policies ({len(active_policies)})"
                    if isinstance(active_policies, list)
                    else "Active Policies",
                    border_style="yellow",
                ),
            ]
        ),
        Panel("\n".join(fleet_lines), title="Fleet Summary", border_style="blue"),
        Columns(
            [
                Panel(
                    render_fleet_items_table(needs_attention, shorten_live_text=shorten_live_text)
                    if isinstance(needs_attention, list)
                    else "-",
                    title=f"Needs Attention ({len(needs_attention)})"
                    if isinstance(needs_attention, list)
                    else "Needs Attention",
                    border_style="yellow",
                ),
                Panel(
                    render_fleet_items_table(active, shorten_live_text=shorten_live_text)
                    if isinstance(active, list)
                    else "-",
                    title=f"Active ({len(active)})" if isinstance(active, list) else "Active",
                    border_style="green",
                ),
            ]
        ),
        Columns(
            [
                Panel(
                    render_fleet_items_table(recent, shorten_live_text=shorten_live_text)
                    if isinstance(recent, list)
                    else "-",
                    title=f"Recent ({len(recent)})" if isinstance(recent, list) else "Recent",
                    border_style="blue",
                ),
                Panel(hint_renderable, title="Suggested Next Commands", border_style="magenta"),
            ]
        ),
    )
