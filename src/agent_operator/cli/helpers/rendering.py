from __future__ import annotations

import typer
from rich.console import Group

from agent_operator.application import OperationProjectionService
from agent_operator.cli.rendering import render_dashboard as _render_dashboard_view
from agent_operator.cli.rendering import render_fleet_dashboard as _render_fleet_dashboard_view
from agent_operator.cli.rendering import render_project_dashboard as _render_project_dashboard_view
from agent_operator.cli.rendering.text import emit_context_lines as _emit_context_lines_view
from agent_operator.cli.rendering.text import format_live_event as _format_live_event_view
from agent_operator.cli.rendering.text import format_live_snapshot as _format_live_snapshot_view
from agent_operator.cli.rendering.text import (
    render_inspect_summary as _render_inspect_summary_view,
)
from agent_operator.cli.rendering.text import (
    render_operation_list_line as _render_operation_list_line_view,
)
from agent_operator.cli.rendering.text import render_status_brief as _render_status_brief_view
from agent_operator.cli.rendering.text import (
    render_status_summary as _render_status_summary_view,
)
from agent_operator.cli.rendering.text import render_watch_snapshot as _render_watch_snapshot_view
from agent_operator.domain import (
    AgentTurnBrief,
    ArtifactRecord,
    AttentionRequest,
    AttentionStatus,
    MemoryEntry,
    MemoryFreshness,
    OperationState,
    OperationStatus,
    RunEvent,
    SchedulerState,
    SessionRecord,
    TaskState,
    TaskStatus,
    TraceBriefBundle,
)
from agent_operator.runtime import AgendaItem

PROJECTIONS = OperationProjectionService()


def shorten_live_text(text: str | None, *, limit: int = 100) -> str | None:
    if text is None:
        return None
    normalized = " ".join(text.strip().split())
    if not normalized:
        return None
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 1].rstrip() + "…"


def normalize_block_text(text: str | None) -> str | None:
    if text is None:
        return None
    lines = [" ".join(line.strip().split()) for line in text.splitlines()]
    non_empty = [line for line in lines if line]
    if not non_empty:
        return None
    return "\n".join(non_empty)


def shorten_block_text(text: str | None, *, limit: int = 320) -> str | None:
    normalized = normalize_block_text(text)
    if normalized is None:
        return None
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 1].rstrip() + "…"


def shorten_paragraph_text(text: str | None, *, limit: int = 220) -> str | None:
    normalized = normalize_block_text(text)
    if normalized is None:
        return None
    single_line = " ".join(normalized.splitlines())
    if len(single_line) <= limit:
        return single_line
    return single_line[: limit - 1].rstrip() + "…"


def latest_agent_turn_brief(brief: TraceBriefBundle | None) -> AgentTurnBrief | None:
    if brief is None or not brief.agent_turn_briefs:
        return None
    return max(brief.agent_turn_briefs, key=lambda item: (item.iteration, item.created_at))


def recent_iteration_briefs(brief: TraceBriefBundle | None, *, limit: int = 3) -> list:
    if brief is None:
        return []
    return sorted(brief.iteration_briefs, key=lambda item: item.iteration)[-limit:]


def recent_agent_turn_briefs(brief: TraceBriefBundle | None, *, limit: int = 2) -> list:
    if brief is None:
        return []
    return sorted(brief.agent_turn_briefs, key=lambda item: (item.iteration, item.created_at))[
        -limit:
    ]


def turn_work_summary(turn: AgentTurnBrief | None) -> str | None:
    if turn is None:
        return None
    summary = turn.turn_summary
    if summary is not None:
        primary = shorten_paragraph_text(summary.actual_work_done, limit=220)
        delta = shorten_paragraph_text(summary.state_delta, limit=220)
        if primary and delta:
            return f"{primary} {delta}"
        return primary or delta
    return shorten_paragraph_text(turn.result_brief, limit=220)


def turn_next_step(turn: AgentTurnBrief | None) -> str | None:
    if turn is None or turn.turn_summary is None:
        return None
    return shorten_paragraph_text(turn.turn_summary.recommended_next_step, limit=220)


def turn_verification_summary(turn: AgentTurnBrief | None) -> str | None:
    if turn is None or turn.turn_summary is None:
        return None
    return shorten_paragraph_text(turn.turn_summary.verification_status, limit=180)


def turn_blockers_summary(turn: AgentTurnBrief | None) -> str | None:
    if turn is None or turn.turn_summary is None or not turn.turn_summary.remaining_blockers:
        return None
    return " | ".join(
        shorten_paragraph_text(item, limit=90) or item
        for item in turn.turn_summary.remaining_blockers[:3]
    )


def render_section(title: str, lines: list[str]) -> list[str]:
    content = [line for line in lines if line.strip()]
    if not content:
        return []
    return [title, *content]


def format_live_event(event: RunEvent) -> str | None:
    return _format_live_event_view(
        event, shorten_live_text=lambda text: shorten_live_text(text, limit=100)
    )


def open_attention_requests(operation: OperationState) -> list[AttentionRequest]:
    return [item for item in operation.attention_requests if item.status is AttentionStatus.OPEN]


def format_live_snapshot(snapshot: dict[str, object]) -> str:
    return _format_live_snapshot_view(
        snapshot,
        base_formatter=PROJECTIONS.format_live_snapshot,
        shorten_live_text=lambda text: shorten_live_text(text, limit=100),
    )


def render_watch_snapshot(snapshot: dict[str, object], *, latest_update: str | None) -> str:
    return _render_watch_snapshot_view(
        snapshot,
        base_formatter=PROJECTIONS.format_live_snapshot,
        shorten_live_text=lambda text: shorten_live_text(text, limit=100),
        latest_update=latest_update,
    )


def build_runtime_alert(
    *,
    status: OperationStatus,
    wakeups: list[dict[str, object]],
    background_runs: list[dict[str, object]],
) -> str | None:
    if status is not OperationStatus.RUNNING:
        return None
    if wakeups:
        return (
            f"{len(wakeups)} wakeup(s) are pending reconciliation. "
            "Run `operator resume <operation-id>`."
        )
    has_terminal_run = any(
        run.get("status") in {"completed", "failed", "cancelled", "disconnected"}
        for run in background_runs
    )
    has_live_run = any(run.get("status") in {"pending", "running"} for run in background_runs)
    if has_terminal_run and not has_live_run:
        return (
            "A background run is already terminal, but this operation still appears "
            "running. Run `operator resume <operation-id>`."
        )
    return None


def render_inspect_summary(
    operation: OperationState,
    brief: TraceBriefBundle | None,
    *,
    runtime_alert: str | None,
) -> str:
    return _render_inspect_summary_view(
        operation,
        summary=PROJECTIONS.build_inspect_summary_payload(
            operation, brief, runtime_alert=runtime_alert
        ),
        brief=brief,
        recent_iteration_briefs=recent_iteration_briefs,
        recent_agent_turn_briefs=recent_agent_turn_briefs,
        shorten_paragraph_text=lambda text: shorten_paragraph_text(text, limit=180),
        turn_work_summary=turn_work_summary,
        turn_verification_summary=turn_verification_summary,
        turn_blockers_summary=turn_blockers_summary,
        turn_next_step=turn_next_step,
        open_attention_requests=open_attention_requests,
        render_section=render_section,
    )


def render_status_summary(
    operation: OperationState,
    brief: TraceBriefBundle | None,
    *,
    runtime_alert: str | None,
    action_hint: str | None,
) -> str:
    return _render_status_summary_view(
        operation,
        summary=PROJECTIONS.build_operation_brief_payload(
            operation,
            brief,
            runtime_alert=runtime_alert,
        ),
        open_attention_requests=open_attention_requests,
        shorten_paragraph_text=lambda text: shorten_paragraph_text(text, limit=180),
        action_hint=action_hint,
    )


def render_operation_list_line(
    operation_id: str,
    status: str,
    *,
    objective: str,
    focus: str | None,
    latest: str | None,
    blocker: str | None,
    runtime_alert: str | None,
    scheduler: str | None = None,
    involvement: str | None = None,
) -> str:
    return _render_operation_list_line_view(
        operation_id,
        status,
        objective=objective,
        focus=focus,
        latest=latest,
        blocker=blocker,
        runtime_alert=runtime_alert,
        scheduler=scheduler,
        involvement=involvement,
    )


def format_agenda_item(item: AgendaItem) -> list[str]:
    header = (
        f"- {item.operation_id} [{item.status.value}] "
        f"{shorten_live_text(item.objective_brief, limit=96) or item.objective_brief}"
    )
    details: list[str] = []
    if item.project_profile_name is not None:
        details.append(f"project={item.project_profile_name}")
    if item.scheduler_state is not SchedulerState.ACTIVE:
        details.append(f"scheduler={item.scheduler_state.value}")
    if item.focus_brief is not None:
        details.append(f"focus={item.focus_brief}")
    if item.open_attention_count > 0:
        details.append(f"attention={item.open_attention_count}")
    if item.runnable_task_count > 0:
        details.append(f"tasks={item.runnable_task_count}")
    if item.reusable_session_count > 0:
        details.append(f"sessions={item.reusable_session_count}")
    lines = [header]
    if details:
        lines.append("  " + " ".join(details))
    if item.runtime_alert is not None:
        lines.append(
            "  alert: "
            + (shorten_paragraph_text(item.runtime_alert, limit=180) or item.runtime_alert)
        )
    elif item.blocker_brief is not None:
        lines.append(
            "  blocker: "
            + (shorten_paragraph_text(item.blocker_brief, limit=180) or item.blocker_brief)
        )
    if item.attention_briefs:
        lines.append(f"  attention: {' | '.join(item.attention_briefs)}")
    elif item.attention_titles:
        lines.append(f"  attention_titles: {' | '.join(item.attention_titles)}")
    if item.latest_outcome_brief is not None:
        latest_brief = (
            shorten_paragraph_text(item.latest_outcome_brief, limit=220)
            or item.latest_outcome_brief
        )
        lines.append("  latest: " + latest_brief)
    return lines


def print_agenda_section(title: str, items: list[AgendaItem]) -> None:
    typer.echo(title)
    if not items:
        typer.echo("- none")
        return
    for item in items:
        for line in format_agenda_item(item):
            typer.echo(line)


def projection_control_hints(payload: dict[str, object]) -> list[str]:
    actions = payload.get("actions")
    if not isinstance(actions, list):
        return []
    hints: list[str] = []
    for item in actions:
        if not isinstance(item, dict):
            continue
        cli_command = item.get("cli_command")
        enabled = item.get("enabled", True)
        if isinstance(cli_command, str) and cli_command and enabled and cli_command not in hints:
            hints.append(cli_command)
    return hints


def cli_projection_payload(payload: dict[str, object]) -> dict[str, object]:
    payload["control_hints"] = projection_control_hints(payload)
    return payload


def render_fleet_dashboard(payload: dict[str, object]) -> Group:
    return _render_fleet_dashboard_view(
        payload, shorten_live_text=lambda text, *, limit=48: shorten_live_text(text, limit=limit)
    )


def render_project_dashboard(payload: dict[str, object]) -> Group:
    return _render_project_dashboard_view(
        payload, shorten_live_text=lambda text: shorten_live_text(text, limit=88)
    )


def render_dashboard(payload: dict[str, object]) -> Group:
    return _render_dashboard_view(
        payload, shorten_live_text=lambda text: shorten_live_text(text, limit=60)
    )


def resolve_task_title(operation: OperationState, task_id: str | None) -> str | None:
    if task_id is None:
        return None
    for task in operation.tasks:
        if task.task_id == task_id:
            return task.title
    return None


def resolve_task_short_id(operation: OperationState, task_id: str | None) -> str | None:
    if task_id is None:
        return None
    for task in operation.tasks:
        if task.task_id == task_id:
            return task.task_short_id
    return None


def find_task_by_display_id(operation: OperationState, display_id: str) -> TaskState | None:
    key = display_id.removeprefix("task-")
    for task in operation.tasks:
        if task.task_id == display_id or task.task_short_id == key:
            return task
    return None


def format_task_line(operation: OperationState, task_id: str | None) -> str:
    title = resolve_task_title(operation, task_id)
    if title is None:
        return task_id or "-"
    short_id = resolve_task_short_id(operation, task_id)
    display_id = f"task-{short_id}" if short_id else task_id
    return f"{title} ({display_id})"


def summarize_task_counts(operation: OperationState) -> str:
    counts = {status: 0 for status in TaskStatus}
    for task in operation.tasks:
        counts[task.status] += 1
    return ", ".join(
        f"{status.value}={counts[status]}"
        for status in (
            TaskStatus.READY,
            TaskStatus.RUNNING,
            TaskStatus.BLOCKED,
            TaskStatus.COMPLETED,
            TaskStatus.FAILED,
            TaskStatus.CANCELLED,
            TaskStatus.PENDING,
        )
        if counts[status] > 0
    )


def artifact_preview(artifact: ArtifactRecord, *, limit: int = 100) -> str:
    return shorten_live_text(artifact.content, limit=limit) or artifact.kind


def memory_payload(operation: OperationState, *, include_inactive: bool) -> list[MemoryEntry]:
    entries = sorted(operation.memory_entries, key=lambda item: item.created_at)
    if include_inactive:
        return entries
    return [entry for entry in entries if entry.freshness is MemoryFreshness.CURRENT]


def operation_payload(operation: OperationState) -> dict[str, object]:
    return PROJECTIONS.operation_payload(operation)


def session_payload(session: SessionRecord) -> dict[str, object]:
    return PROJECTIONS.session_payload(session)


def emit_context_lines(payload: dict[str, object], *, operation_id: str) -> list[str]:
    return _emit_context_lines_view(payload, operation_id=operation_id)


def render_status_brief(operation: OperationState) -> str:
    return _render_status_brief_view(
        operation,
        open_attention_count=len(open_attention_requests(operation)),
        summarize_task_counts=summarize_task_counts,
    )
