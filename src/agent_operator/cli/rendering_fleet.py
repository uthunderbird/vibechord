from __future__ import annotations

from collections.abc import Callable

from rich.columns import Columns
from rich.console import Group
from rich.panel import Panel
from rich.table import Table

from agent_operator.domain import SchedulerState


def _rows_from_payload(payload: dict[str, object]) -> list[tuple[str, list[dict[str, object]]]]:
    rows = payload.get("rows")
    if isinstance(rows, list):
        buckets: dict[str, list[dict[str, object]]] = {
            "needs_attention": [],
            "active": [],
            "recent": [],
        }
        for raw_item in rows:
            if not isinstance(raw_item, dict):
                continue
            bucket = str(raw_item.get("sort_bucket") or "recent")
            if bucket not in buckets:
                bucket = "recent"
            buckets[bucket].append(raw_item)
        return [
            ("needs_attention", buckets["needs_attention"]),
            ("active", buckets["active"]),
            ("recent", buckets["recent"]),
        ]
    needs_attention = payload.get("needs_attention")
    active = payload.get("active")
    recent = payload.get("recent")
    return [
        ("needs_attention", needs_attention if isinstance(needs_attention, list) else []),
        ("active", active if isinstance(active, list) else []),
        ("recent", recent if isinstance(recent, list) else []),
    ]


def _metric_counts(
    payload: dict[str, object],
    header_key: str,
    mix_key: str | None = None,
) -> dict[str, int]:
    header = payload.get("header")
    if isinstance(header, dict):
        value = header.get(header_key)
        if isinstance(value, dict):
            return {
                str(metric): int(count)
                for metric, count in value.items()
                if isinstance(metric, str) and isinstance(count, int)
            }
    mix = payload.get("mix")
    if isinstance(mix, dict) and mix_key is not None:
        value = mix.get(mix_key)
        if isinstance(value, dict):
            return {
                str(metric): int(count)
                for metric, count in value.items()
                if isinstance(metric, str) and isinstance(count, int)
            }
    return {}


def format_fleet_mix_counts(counts: dict[str, int]) -> str:
    return ", ".join(
        f"{key}={count}"
        for key, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    )


def render_fleet_items_table(
    items: list[dict[str, object]],
    *,
    shorten_live_text: Callable[[str | None], str | None],
) -> Table:
    table = Table(expand=True)
    table.add_column("Operation", no_wrap=True)
    table.add_column("State", no_wrap=True)
    table.add_column("Signal", no_wrap=True)
    table.add_column("Cue")
    table.add_column("Hint")
    table.add_column("Details")
    if not items:
        table.add_row("-", "-", "none", "-", "-", "-")
        return table
    for item in items[:8]:
        state = str(item.get("state_label") or item.get("status") or "-")
        scheduler_state = str(item.get("scheduler_state") or "")
        if (
            scheduler_state
            and scheduler_state != SchedulerState.ACTIVE.value
            and "/" not in state
        ):
            state += f" / {scheduler_state}"
        signal = str(item.get("attention_badge") or "-")
        runtime_alert = shorten_live_text(str(item.get("runtime_alert") or ""))
        if runtime_alert is not None:
            signal = "!!"
        cue = str(item.get("agent_cue") or item.get("project_profile_name") or "-")
        hint = str(item.get("row_hint") or "-")
        recency = shorten_live_text(
            str(item.get("recency_brief") or item.get("focus_brief") or item.get("latest_outcome_brief") or "-")
        )
        details = shorten_live_text(
            str(item.get("display_name") or item.get("objective_brief") or "-"),
            limit=78,
        ) or "-"
        if recency is not None:
            details = f"{details} | {recency}"
        table.add_row(
            str(item.get("operation_id") or "-"),
            state,
            signal,
            cue,
            hint,
            details,
        )
    return table


def render_fleet_dashboard(
    payload: dict[str, object],
    *,
    shorten_live_text: Callable[[str | None], str | None],
) -> Group:
    buckets = _rows_from_payload(payload)
    bucket_map = {name: rows for name, rows in buckets}
    needs_attention = bucket_map["needs_attention"]
    active = bucket_map["active"]
    recent = bucket_map["recent"]
    hints = payload.get("control_hints")
    bucket_counts = _metric_counts(payload, "bucket_counts", "bucket_counts")
    status_counts = _metric_counts(payload, "status_counts", "status_counts")
    scheduler_counts = _metric_counts(payload, "scheduler_counts", "scheduler_counts")
    involvement_counts = _metric_counts(payload, "involvement_counts", "involvement_counts")
    total_operations = payload.get("total_operations", 0)
    header_lines = [
        f"total_operations={total_operations}",
        (
            f"project={payload.get('project')}"
            if isinstance(payload.get("project"), str) and payload.get("project")
            else "project=all"
        ),
        f"needs_attention={len(needs_attention)} active={len(active)} recent={len(recent)}",
    ]
    if bucket_counts:
        header_lines.append("buckets=" + format_fleet_mix_counts(bucket_counts))
    if status_counts:
        header_lines.append("status_mix=" + format_fleet_mix_counts(status_counts))
    if scheduler_counts:
        header_lines.append("scheduler_mix=" + format_fleet_mix_counts(scheduler_counts))
    if involvement_counts:
        header_lines.append("involvement_mix=" + format_fleet_mix_counts(involvement_counts))
    header = payload.get("header")
    if isinstance(header, dict):
        needs_human_count = header.get("needs_human_count")
        running_count = header.get("running_count")
        paused_count = header.get("paused_count")
        if needs_human_count is not None or running_count is not None or paused_count is not None:
            header_lines.append(
                "needs_human="
                + str(needs_human_count if needs_human_count is not None else 0)
                + f" running={running_count if running_count is not None else 0}"
                + f" paused={paused_count if paused_count is not None else 0}"
            )
    hint_renderable = "\n".join(str(item) for item in hints if isinstance(item, str)) or "- none"
    recent_renderable = render_fleet_items_table(recent, shorten_live_text=shorten_live_text) if isinstance(recent, list) else "-"
    return Group(
        Panel("\n".join(header_lines), title="Fleet Dashboard", border_style="cyan"),
        Columns(
            [
                Panel(render_fleet_items_table(needs_attention, shorten_live_text=shorten_live_text) if isinstance(needs_attention, list) else "-", title=f"Needs Attention ({len(needs_attention)})" if isinstance(needs_attention, list) else "Needs Attention", border_style="yellow"),
                Panel(render_fleet_items_table(active, shorten_live_text=shorten_live_text) if isinstance(active, list) else "-", title=f"Active ({len(active)})" if isinstance(active, list) else "Active", border_style="green"),
            ]
        ),
        Columns(
            [
                Panel(recent_renderable, title=f"Recent ({len(recent)})" if isinstance(recent, list) else "Recent", border_style="blue"),
                Panel(hint_renderable, title="Suggested Next Commands", border_style="magenta"),
            ]
        ),
    )
