from __future__ import annotations

from .model_types import FleetItem, OperationTaskItem, optional_int, optional_text

TASK_LANE_ORDER = (
    "RUNNING",
    "READY",
    "BLOCKED",
    "COMPLETED",
    "FAILED",
    "CANCELLED",
)


def payload_items(payload: dict[str, object]) -> list[FleetItem]:
    items: list[FleetItem] = []
    rows = payload.get("rows")
    if isinstance(rows, list):
        for raw_item in rows:
            if isinstance(raw_item, dict):
                items.append(FleetItem.from_payload(raw_item))
        return items
    for bucket in ("needs_attention", "active", "recent"):
        raw_items = payload.get(bucket)
        if not isinstance(raw_items, list):
            continue
        for entry in raw_items:
            if not isinstance(entry, dict):
                continue
            item = FleetItem.from_payload(entry)
            if item.bucket != bucket:
                item = FleetItem(
                    operation_id=item.operation_id,
                    attention_badge=item.attention_badge,
                    display_name=item.display_name,
                    state_label=item.state_label,
                    agent_cue=item.agent_cue,
                    recency_brief=item.recency_brief,
                    row_hint=item.row_hint,
                    status=item.status,
                    scheduler_state=item.scheduler_state,
                    objective_brief=item.objective_brief,
                    focus_brief=item.focus_brief,
                    latest_outcome_brief=item.latest_outcome_brief,
                    blocker_brief=item.blocker_brief,
                    runtime_alert=item.runtime_alert,
                    open_attention_count=item.open_attention_count,
                    open_blocking_attention_count=item.open_blocking_attention_count,
                    open_nonblocking_attention_count=item.open_nonblocking_attention_count,
                    attention_briefs=item.attention_briefs,
                    project_profile_name=item.project_profile_name,
                    brief=item.brief,
                    bucket=bucket,
                )
            items.append(item)
    return items


def filter_fleet_items(items: list[FleetItem], query: str) -> list[FleetItem]:
    normalized = query.strip().lower()
    if not normalized:
        return list(items)
    terms = [term for term in normalized.split() if term]
    if not terms:
        return list(items)
    return [item for item in items if _fleet_item_matches_filter(item, terms)]


def dashboard_tasks(payload: dict[str, object] | None) -> list[OperationTaskItem]:
    if not isinstance(payload, dict):
        return []
    raw_tasks = payload.get("tasks")
    if not isinstance(raw_tasks, list):
        return []
    return [OperationTaskItem.from_payload(item) for item in raw_tasks if isinstance(item, dict)]


def filtered_dashboard_tasks(
    payload: dict[str, object] | None,
    query: str,
) -> list[OperationTaskItem]:
    tasks = dashboard_tasks(payload)
    normalized = query.strip().lower()
    if not normalized:
        return sort_dashboard_tasks(tasks)
    terms = [term for term in normalized.split() if term]
    if not terms:
        return sort_dashboard_tasks(tasks)
    return sort_dashboard_tasks([task for task in tasks if _task_matches_filter(task, terms)])


def status_text(item: FleetItem) -> str:
    return item.state_label


def signal_text(item: FleetItem) -> str:
    if item.attention_badge in {"", "-"}:
        return "-"
    if item.attention_badge.startswith("B"):
        return f"[!!{item.attention_badge.removeprefix('B')}]"
    if item.attention_badge.startswith("Q"):
        return f"[!{item.attention_badge.removeprefix('Q')}]"
    if item.attention_badge.startswith("A"):
        return f"[~{item.attention_badge.removeprefix('A')}]"
    if item.attention_badge == "!!":
        return "[!! alert]"
    return "-"


def task_lane(task: OperationTaskItem) -> str:
    if task.status == "running":
        return "RUNNING"
    if task.status == "completed":
        return "COMPLETED"
    if task.status == "failed":
        return "FAILED"
    if task.status == "cancelled":
        return "CANCELLED"
    if task.dependencies:
        return "BLOCKED"
    return "READY"


def task_status_glyph(task: OperationTaskItem) -> str:
    lane = task_lane(task)
    if lane == "RUNNING":
        return "▶"
    if lane == "READY":
        return "○"
    if lane == "BLOCKED":
        return "◐"
    if lane == "COMPLETED":
        return "✓"
    if lane == "FAILED":
        return "✕"
    if lane == "CANCELLED":
        return "⊘"
    return "·"


def sort_dashboard_tasks(tasks: list[OperationTaskItem]) -> list[OperationTaskItem]:
    lane_rank = {lane: index for index, lane in enumerate(TASK_LANE_ORDER)}
    return sorted(tasks, key=lambda task: lane_rank.get(task_lane(task), len(TASK_LANE_ORDER)))


def filtered_decisions(
    payload: dict[str, object] | None,
    task: OperationTaskItem | None,
) -> list[str]:
    if not isinstance(payload, dict):
        return []
    raw_decisions = payload.get("decision_memos")
    if not isinstance(raw_decisions, list):
        return []
    entries: list[str] = []
    for item in raw_decisions:
        if not isinstance(item, dict):
            continue
        task_id = optional_text(item.get("task_id"))
        if task is not None and task_id not in {None, task.task_id}:
            continue
        iteration = optional_int(item.get("iteration"))
        chosen_action = optional_text(item.get("chosen_action")) or "-"
        rationale = optional_text(item.get("rationale")) or "-"
        context = optional_text(item.get("decision_context_summary"))
        parts = [f"iter {iteration}: {chosen_action}"]
        if context is not None:
            parts.append(f"context: {context}")
        parts.append(f"why: {rationale}")
        entries.append("\n".join(parts))
    return entries


def filtered_memory_entries(
    payload: dict[str, object] | None,
    task: OperationTaskItem | None,
) -> list[str]:
    if not isinstance(payload, dict):
        return []
    raw_entries = payload.get("memory_entries")
    if not isinstance(raw_entries, list):
        return []
    rendered: list[str] = []
    for item in raw_entries:
        if not isinstance(item, dict):
            continue
        scope_id = optional_text(item.get("scope_id"))
        memory_id = optional_text(item.get("memory_id")) or "-"
        freshness = optional_text(item.get("freshness")) or "-"
        scope = optional_text(item.get("scope")) or "-"
        summary = optional_text(item.get("summary")) or "-"
        if (
            task is not None
            and scope_id not in {None, task.task_id}
            and memory_id not in task.memory_refs
        ):
            continue
        rendered.append(f"{memory_id} [{scope}/{freshness}]\n{summary}")
    return rendered


def _fleet_item_matches_filter(item: FleetItem, terms: list[str]) -> bool:
    haystack = " ".join(
        value.lower()
        for value in (
            item.operation_id,
            item.display_name,
            item.state_label,
            item.status,
            item.scheduler_state,
            item.agent_cue,
            item.objective_brief,
            item.focus_brief or "",
            item.latest_outcome_brief or "",
            item.blocker_brief or "",
            item.runtime_alert or "",
            item.project_profile_name or "",
            " ".join(item.attention_briefs),
        )
        if value
    )
    return all(term in haystack for term in terms)


def _task_matches_filter(task: OperationTaskItem, terms: list[str]) -> bool:
    haystack = " ".join(
        value.lower()
        for value in (
            task.task_id,
            task.task_short_id,
            task.title,
            task.goal,
            task.definition_of_done,
            task.status,
            task.assigned_agent or "",
            " ".join(task.notes),
        )
        if value
    )
    return all(term in haystack for term in terms)
