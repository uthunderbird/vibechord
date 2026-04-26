from __future__ import annotations

from collections.abc import Callable

from agent_operator.domain import (
    AgentTurnBrief,
    AttentionRequest,
    InvolvementLevel,
    IterationBrief,
    OperationState,
    SchedulerState,
)


def render_status_brief(
    operation: OperationState,
    *,
    open_attention_count: int,
    summarize_task_counts: Callable[[OperationState], str],
) -> str:
    """Render a compact single-line status summary.

    Example:
        render_status_brief(
            operation,
            open_attention_count=0,
            summarize_task_counts=lambda current: "none",
        )
    """
    rendered = (
        f"{operation.operation_id} {operation.status.value.upper()} "
        f"iter={len(operation.iterations)}/{operation.execution_budget.max_iterations} "
        f"tasks={summarize_task_counts(operation) or 'none'} "
        f"att=[!!{open_attention_count}]"
    )
    active_session = operation.active_session_record
    if active_session is None:
        return rendered
    rendered += f" session={active_session.session_id} agent={active_session.adapter_key}"
    stamp = active_session.execution_profile_stamp
    if stamp is None:
        return rendered + " model=unknown"
    model = stamp.model.strip() if isinstance(stamp.model, str) and stamp.model.strip() else None
    if model is None:
        return rendered + " model=unknown"
    rendered += f" model={model}"
    effort_value = (
        stamp.effort_value.strip()
        if isinstance(stamp.effort_value, str) and stamp.effort_value.strip()
        else None
    )
    if effort_value is not None:
        rendered += f" effort={effort_value}"
    return rendered


def render_status_summary(
    operation: OperationState,
    *,
    summary: dict[str, object],
    open_attention_requests: Callable[[OperationState], list[AttentionRequest]],
    shorten_paragraph_text: Callable[[str | None], str | None],
    action_hint: str | None,
) -> str:
    """Render the multiline status command output.

    Example:
        render_status_summary(
            operation,
            summary={"status": "running"},
            open_attention_requests=lambda current: [],
            shorten_paragraph_text=lambda text: text,
            action_hint=None,
        )
    """
    open_attention = open_attention_requests(operation)
    max_iterations = operation.execution_budget.max_iterations
    lines = [
        f"{operation.status.value.upper()} · " f"iter {len(operation.iterations)}/{max_iterations}",
        "",
    ]
    progress_values: set[str] = set()
    operation_anchor = (
        shorten_paragraph_text(f"{operation.operation_id} · {operation.objective_state.objective}")
        or operation.operation_id
    )

    lines.extend(["Operation", f"- {operation_anchor}"])

    current_label = "Wait" if summary.get("wait") else "Now"
    current_value = summary.get("wait") or summary.get("now") or operation.status.value
    lines.extend(
        [
            "",
            current_label,
            f"- {shorten_paragraph_text(str(current_value) if current_value else None) or '-'}",
        ]
    )

    lines.append("")
    lines.append("Attention")
    if not open_attention:
        lines.append("- none")
    else:
        first = open_attention[0]
        badge = (
            f"[!!{len(open_attention)}] "
            if first.blocking
            else f"[review {len(open_attention)}] "
        )
        lines.append(
            "- "
            + badge
            + (
                shorten_paragraph_text(f"[{first.attention_type.value}] {first.title}")
                or f"[{first.attention_type.value}] {first.title}"
            )
        )

    progress_lines: list[str] = []
    progress = summary.get("progress")
    if isinstance(progress, dict):
        done = shorten_paragraph_text(
            str(progress.get("done")) if progress.get("done") is not None else None
        )
        doing = shorten_paragraph_text(
            str(progress.get("doing")) if progress.get("doing") is not None else None
        )
        next_step = shorten_paragraph_text(
            str(progress.get("next")) if progress.get("next") is not None else None
        )
        if done:
            progress_lines.append(f"- Done: {done}")
            progress_values.add(done)
        if doing and doing != done:
            progress_lines.append(f"- Doing: {doing}")
            progress_values.add(doing)
        if next_step and next_step not in {done, doing}:
            progress_lines.append(f"- Next: {next_step}")
            progress_values.add(next_step)
    if progress_lines:
        lines.extend(["", "Progress", *progress_lines])

    recent = shorten_paragraph_text(str(summary.get("recent")) if summary.get("recent") else None)
    if recent and recent not in progress_values:
        lines.extend(["", "Recent", f"- {recent}"])

    if action_hint is not None:
        lines.extend(["", "Action", f"- {action_hint}"])

    return "\n".join(lines).rstrip() + "\n"


def render_inspect_summary(
    operation: OperationState,
    *,
    summary: dict[str, object],
    brief: object,
    recent_iteration_briefs: Callable[[object], list[IterationBrief]],
    recent_agent_turn_briefs: Callable[[object], list[AgentTurnBrief]],
    shorten_paragraph_text: Callable[[str | None], str | None],
    turn_work_summary: Callable[[AgentTurnBrief | None], str | None],
    turn_verification_summary: Callable[[AgentTurnBrief | None], str | None],
    turn_blockers_summary: Callable[[AgentTurnBrief | None], str | None],
    turn_next_step: Callable[[AgentTurnBrief | None], str | None],
    open_attention_requests: Callable[[OperationState], list[AttentionRequest]],
    render_section: Callable[[str, list[str]], list[str]],
) -> str:
    """Render the human-readable inspect output.

    Example:
        render_inspect_summary(
            operation,
            summary={"status": "running", "objective": "Ship dashboard"},
            brief=None,
            recent_iteration_briefs=lambda current: [],
            recent_agent_turn_briefs=lambda current: [],
            shorten_paragraph_text=lambda text: text,
            turn_work_summary=lambda turn: None,
            turn_verification_summary=lambda turn: None,
            turn_blockers_summary=lambda turn: None,
            turn_next_step=lambda turn: None,
            open_attention_requests=lambda current: [],
            render_section=lambda title, lines: [title, *lines] if lines else [],
        )
    """
    now_lines: list[str] = []
    if summary.get("runtime_alert"):
        now_lines.append(f"alert: {summary['runtime_alert']}")
    if summary.get("work_summary"):
        now_lines.append(f"latest: {summary['work_summary']}")
    if summary.get("verification_summary"):
        now_lines.append(f"verification: {summary['verification_summary']}")
    if summary.get("blockers_summary"):
        now_lines.append(f"remaining blockers: {summary['blockers_summary']}")
    if summary.get("next_step"):
        now_lines.append(f"recommended next step: {summary['next_step']}")

    operation_lines = [
        f"status: {summary.get('status')}",
        (
            f"scheduler: {summary.get('scheduler_state')}"
            if summary.get("scheduler_state") != SchedulerState.ACTIVE.value
            else ""
        ),
        (
            f"involvement: {operation.involvement_level.value}"
            if operation.involvement_level is not InvolvementLevel.AUTO
            else ""
        ),
    ]
    objective_lines = [f"objective: {summary.get('objective')}"]
    iteration_lines: list[str] = []
    for item in recent_iteration_briefs(brief):
        iteration_lines.append(f"- Iteration {item.iteration}")
        iteration_lines.append(
            f"  intent: {shorten_paragraph_text(item.operator_intent_brief) or '-'}"
        )
        if item.assignment_brief:
            iteration_lines.append(
                f"  assignment: {shorten_paragraph_text(item.assignment_brief) or '-'}"
            )
        if item.result_brief:
            iteration_lines.append(f"  result: {shorten_paragraph_text(item.result_brief) or '-'}")
        iteration_lines.append(f"  status: {shorten_paragraph_text(item.status_brief) or '-'}")
    turn_lines: list[str] = []
    for turn in recent_agent_turn_briefs(brief):
        session_label = turn.session_display_name or turn.session_id
        turn_lines.append(f"- {turn.agent_key} ({session_label}) [{turn.status}]")
        turn_lines.append(f"  assignment: {shorten_paragraph_text(turn.assignment_brief) or '-'}")
        work = turn_work_summary(turn)
        if work:
            turn_lines.append(f"  work: {work}")
        verification = turn_verification_summary(turn)
        if verification:
            turn_lines.append(f"  verification: {verification}")
        blockers = turn_blockers_summary(turn)
        if blockers:
            turn_lines.append(f"  blockers: {blockers}")
        next_step = turn_next_step(turn)
        if next_step:
            turn_lines.append(f"  next: {next_step}")
        if turn.raw_log_refs:
            turn_lines.append(
                "  refs: raw_logs="
                + ", ".join(turn.raw_log_refs[:2])
                + ("…" if len(turn.raw_log_refs) > 2 else "")
            )
    attention_lines: list[str] = []
    open_attention = open_attention_requests(operation)
    if not open_attention:
        attention_lines.append("- none")
    for attention in open_attention:
        blocking_label = "blocking" if attention.blocking else "non-blocking"
        attention_lines.append(
            f"- [{attention.attention_type.value}] {attention.title} ({blocking_label})"
        )
        if attention.question:
            attention_lines.append(f"  {shorten_paragraph_text(attention.question) or ''}".rstrip())
        attention_lines.append(
            f"  → operator answer {operation.operation_id} "
            f"{attention.attention_id} --text '...'"
        )

    lines = [f"Operation {operation.operation_id}", ""]
    for section in (
        render_section("Operation", operation_lines),
        render_section("Objective", objective_lines),
        render_section("Now", now_lines),
        render_section("Open Attention", attention_lines),
        render_section("Recent Iterations", iteration_lines),
        render_section("Recent Agent Turns", turn_lines),
    ):
        if section:
            if lines and lines[-1] != "":
                lines.append("")
            lines.extend(section)
    return "\n".join(lines).rstrip() + "\n"
