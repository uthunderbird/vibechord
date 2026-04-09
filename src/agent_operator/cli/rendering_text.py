from __future__ import annotations

from collections.abc import Callable

from agent_operator.domain import AgentTurnBrief, AttentionRequest, InvolvementLevel, OperationState, RunEvent, SchedulerState


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
    parts = [f"{operation_id} [{status}] {objective}"]
    if focus:
        parts.append(f"focus={focus}")
    if latest:
        parts.append(f"latest={latest}")
    if blocker:
        parts.append(f"blocker={blocker}")
    if scheduler:
        parts.append(f"scheduler={scheduler}")
    if involvement:
        parts.append(f"involvement={involvement}")
    if runtime_alert:
        parts.append(f"alert={runtime_alert}")
    return " | ".join(parts)


def format_live_snapshot(
    snapshot: dict[str, object],
    *,
    base_formatter: Callable[[dict[str, object]], str],
    shorten_live_text: Callable[[str | None], str | None],
) -> str:
    parts = [base_formatter(snapshot)]
    session_id = snapshot.get("session_id")
    if isinstance(session_id, str) and session_id:
        parts.append(f"session={session_id}")
    adapter_key = snapshot.get("adapter_key")
    if isinstance(adapter_key, str) and adapter_key:
        parts.append(f"agent={adapter_key}")
    session_status = snapshot.get("session_status")
    if isinstance(session_status, str) and session_status and session_status != "idle":
        parts.append(f"session_status={session_status}")
    waiting_reason_raw = snapshot.get("waiting_reason")
    waiting_reason = shorten_live_text(
        str(waiting_reason_raw) if waiting_reason_raw is not None else None
    )
    if waiting_reason is not None:
        parts.append(f"waiting={waiting_reason}")
    blocking_reason_raw = snapshot.get("blocking_reason")
    blocking_reason = shorten_live_text(
        str(blocking_reason_raw) if blocking_reason_raw is not None else None
    )
    if blocking_reason is not None:
        parts.append(f"blocked_by={blocking_reason}")
    attention_brief_raw = snapshot.get("attention_brief")
    attention_brief = shorten_live_text(
        str(attention_brief_raw) if attention_brief_raw is not None else None
    )
    if attention_brief is None:
        attention_title_raw = snapshot.get("attention_title")
        attention_brief = shorten_live_text(
            str(attention_title_raw) if attention_title_raw is not None else None
        )
    if attention_brief is not None:
        count = snapshot.get("open_attention_count")
        if isinstance(count, int) and count > 0:
            parts.append(f"attention={count}:{attention_brief}")
    summary_raw = snapshot.get("summary")
    summary = shorten_live_text(str(summary_raw) if summary_raw is not None else None)
    if summary is not None:
        parts.append(f"summary={summary}")
    return " | ".join(parts)


def render_status_brief(
    operation: OperationState,
    *,
    open_attention_count: int,
    summarize_task_counts: Callable[[OperationState], str],
) -> str:
    return (
        f"{operation.operation_id} {operation.status.value.upper()} "
        f"iter={len(operation.iterations)}/{operation.execution_budget.max_iterations} "
        f"tasks={summarize_task_counts(operation) or 'none'} "
        f"att=[!!{open_attention_count}]"
    )


def emit_context_lines(payload: dict[str, object], *, operation_id: str) -> list[str]:
    lines = [f"Operation {operation_id}", "Goal:"]
    lines.append(f"- Objective: {payload['objective']}")
    harness = payload.get("harness_instructions")
    lines.append(f"- Harness: {harness or '-'}")
    success_criteria = payload.get("success_criteria")
    if isinstance(success_criteria, list) and success_criteria:
        lines.append("- Success criteria: " + " | ".join(str(item) for item in success_criteria))
    else:
        lines.append("- Success criteria: -")

    lines.append("Runtime:")
    lines.append(f"- Status: {payload['status']}")
    lines.append(f"- Scheduler: {payload['scheduler_state']}")
    lines.append(f"- Run mode: {payload['run_mode']}")
    lines.append(f"- Involvement: {payload['involvement_level']}")
    allowed_agents = payload.get("allowed_agents")
    if isinstance(allowed_agents, list) and allowed_agents:
        lines.append("- Allowed agents: " + ", ".join(str(item) for item in allowed_agents))
    else:
        lines.append("- Allowed agents: -")
    descriptors = payload.get("available_agent_descriptors")
    if isinstance(descriptors, list) and descriptors:
        lines.append("- Agent capabilities:")
        for descriptor in descriptors:
            if not isinstance(descriptor, dict):
                continue
            capabilities = descriptor.get("capabilities")
            capability_names = (
                ", ".join(
                    str(item.get("name"))
                    for item in capabilities
                    if isinstance(item, dict) and item.get("name")
                )
                if isinstance(capabilities, list)
                else "-"
            )
            descriptor_line = (
                f"  {descriptor.get('key') or '-'}"
                f" ({descriptor.get('display_name') or '-'})"
                f": capabilities={capability_names}"
            )
            if descriptor.get("supports_follow_up") is not None:
                descriptor_line += (
                    f" follow_up={'yes' if descriptor.get('supports_follow_up') else 'no'}"
                )
            lines.append(descriptor_line)
    else:
        lines.append("- Agent capabilities: -")
    lines.append(f"- Max iterations: {payload['max_iterations']}")

    current_focus = payload.get("current_focus")
    if isinstance(current_focus, dict):
        focus_line = (
            f"- Current focus: {current_focus.get('kind')}:{current_focus.get('target_id')}"
        )
        if current_focus.get("mode"):
            focus_line += f" mode={current_focus['mode']}"
        lines.append(focus_line)
    active_session = payload.get("active_session")
    if isinstance(active_session, dict):
        session_line = (
            f"- Active session: {active_session.get('session_id')} "
            f"[{active_session.get('adapter_key')}] status={active_session.get('status')}"
        )
        if active_session.get("session_name"):
            session_line += f" name={active_session.get('session_name')}"
        lines.append(session_line)
        if active_session.get("waiting_reason"):
            lines.append(f"  waiting: {active_session['waiting_reason']}")

    open_attention = payload.get("open_attention")
    lines.append("Open attention:")
    if not isinstance(open_attention, list) or not open_attention:
        lines.append("- none")
    else:
        for item in open_attention:
            if not isinstance(item, dict):
                continue
            title = item.get("title") or "-"
            attention_type = item.get("attention_type") or "-"
            blocking = "blocking" if item.get("blocking") else "non-blocking"
            lines.append(f"- [{attention_type}] {title} ({blocking})")

    project_context = payload.get("project_context")
    lines.append("Project context:")
    if isinstance(project_context, dict):
        lines.append(f"- Profile: {project_context.get('profile_name') or '-'}")
        lines.append(f"- Policy scope: {project_context.get('policy_scope') or '-'}")
        resolved_profile = project_context.get("resolved_profile")
        if isinstance(resolved_profile, dict):
            lines.append(f"- Resolved cwd: {resolved_profile.get('cwd') or '-'}")
            overrides = resolved_profile.get("overrides")
            if isinstance(overrides, list) and overrides:
                lines.append("- CLI/profile overrides: " + ", ".join(str(item) for item in overrides))
    else:
        lines.append("- none")

    policy_coverage = payload.get("policy_coverage")
    if isinstance(policy_coverage, dict):
        lines.append(
            "- Policy coverage: "
            f"{policy_coverage.get('status') or '-'} "
            f"(scope_entries={policy_coverage.get('scoped_policy_count') or 0}, "
            f"active_now={policy_coverage.get('active_policy_count') or 0})"
        )
        summary = policy_coverage.get("summary")
        if isinstance(summary, str) and summary:
            lines.append(f"  summary: {summary}")

    active_policies = payload.get("active_policies")
    lines.append("Active policy:")
    if not isinstance(active_policies, list) or not active_policies:
        lines.append("- none")
        return lines
    for policy in active_policies:
        if not isinstance(policy, dict):
            continue
        lines.append(
            f"- {policy.get('policy_id')} [{policy.get('category')}] {policy.get('title')}"
        )
        lines.append(f"  rule: {policy.get('rule_text')}")
        applicability = policy.get("applicability_summary")
        if isinstance(applicability, str) and applicability:
            lines.append(f"  applies: {applicability}")
        match_reasons = policy.get("match_reasons")
        if isinstance(match_reasons, list) and match_reasons:
            lines.append("  matched_by: " + " | ".join(str(item) for item in match_reasons))
        rationale = policy.get("rationale")
        if isinstance(rationale, str) and rationale:
            lines.append(f"  rationale: {rationale}")
    return lines


def render_inspect_summary(
    operation: OperationState,
    *,
    summary: dict[str, object],
    brief: object,
    recent_iteration_briefs: Callable[[object], list],
    recent_agent_turn_briefs: Callable[[object], list],
    shorten_paragraph_text: Callable[[str | None], str | None],
    turn_work_summary: Callable[[AgentTurnBrief | None], str | None],
    turn_verification_summary: Callable[[AgentTurnBrief | None], str | None],
    turn_blockers_summary: Callable[[AgentTurnBrief | None], str | None],
    turn_next_step: Callable[[AgentTurnBrief | None], str | None],
    open_attention_requests: Callable[[OperationState], list[AttentionRequest]],
    render_section: Callable[[str, list[str]], list[str]],
) -> str:
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
        turn_lines.append(
            f"  assignment: {shorten_paragraph_text(turn.assignment_brief) or '-'}"
        )
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
    for attention in open_attention_requests(operation):
        blocking_label = "blocking" if attention.blocking else "non-blocking"
        attention_lines.append(
            f"- [{attention.attention_type.value}] {attention.title} ({blocking_label})"
        )
        if attention.question:
            attention_lines.append(f"  {shorten_paragraph_text(attention.question) or ''}".rstrip())
        attention_lines.append(
            f"  → operator answer {operation.operation_id} "
            f"--attention {attention.attention_id} --text '...'"
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


def format_live_event(
    event: RunEvent,
    *,
    shorten_live_text: Callable[[str | None], str | None],
) -> str | None:
    payload = event.payload if isinstance(event.payload, dict) else {}
    prefix = f"[iter {event.iteration}] " if event.iteration > 0 else ""
    if event.event_type == "operation.started":
        objective = shorten_live_text(str(payload.get("objective", "")).strip())
        return f"starting: {objective}" if objective is not None else "starting operation"
    if event.event_type == "brain.decision.made":
        action = str(payload.get("action_type", "")).strip() or "unknown"
        target_agent = str(payload.get("target_agent", "")).strip() or None
        rationale = shorten_live_text(str(payload.get("rationale", "")).strip())
        rendered = f"{prefix}decision: {action}"
        if target_agent is not None:
            rendered += f" -> {target_agent}"
        if rationale is not None:
            rendered += f" | {rationale}"
        return rendered
    if event.event_type == "agent.invocation.started":
        adapter_key = str(payload.get("adapter_key", "")).strip() or "agent"
        rendered = f"{prefix}agent started: {adapter_key}"
        if event.session_id is not None:
            rendered += f" session={event.session_id}"
        session_name = str(payload.get("session_name", "")).strip() or None
        if session_name is not None:
            rendered += f" name={session_name}"
        return rendered
    if event.event_type == "agent.invocation.background_started":
        adapter_key = str(payload.get("adapter_key", "")).strip() or "agent"
        rendered = f"{prefix}background agent started: {adapter_key}"
        run_id = str(payload.get("run_id", "")).strip() or None
        if run_id is not None:
            rendered += f" run={run_id}"
        return rendered
    if event.event_type == "agent.invocation.completed":
        status = str(payload.get("status", "")).strip() or "unknown"
        output_text = shorten_live_text(str(payload.get("output_text", "")).strip())
        rendered = f"{prefix}agent completed: {status}"
        if output_text is not None:
            rendered += f" | {output_text}"
        return rendered
    if event.event_type == "evaluation.completed":
        should_continue = bool(payload.get("should_continue"))
        goal_satisfied = bool(payload.get("goal_satisfied"))
        summary = shorten_live_text(str(payload.get("summary", "")).strip())
        rendered = (
            f"{prefix}evaluation: continue"
            if should_continue
            else f"{prefix}evaluation: goal satisfied"
            if goal_satisfied
            else f"{prefix}evaluation: stop"
        )
        if summary is not None:
            rendered += f" | {summary}"
        return rendered
    if event.event_type == "command.applied":
        return f"{prefix}command applied: {str(payload.get('command_type', '')).strip() or 'unknown'}"
    if event.event_type == "command.rejected":
        command_type = str(payload.get("command_type", "")).strip() or "unknown"
        reason = shorten_live_text(str(payload.get("rejection_reason", "")).strip())
        rendered = f"{prefix}command rejected: {command_type}"
        if reason is not None:
            rendered += f" | {reason}"
        return rendered
    if event.event_type == "planning_trigger.enqueued":
        return f"{prefix}planning trigger enqueued: {str(payload.get('reason', '')).strip() or 'unknown'}"
    if event.event_type == "planning_trigger.coalesced":
        return f"{prefix}planning trigger coalesced: {str(payload.get('reason', '')).strip() or 'unknown'}"
    if event.event_type == "planning_trigger.applied":
        return f"{prefix}planning trigger applied: {str(payload.get('reason', '')).strip() or 'unknown'}"
    if event.event_type == "background_wakeup.reconciled":
        return f"{prefix}background wakeup reconciled: run={str(payload.get('run_id', '')).strip() or 'unknown'}"
    if event.event_type == "background_run.stale_detected":
        return f"{prefix}stale background run detected: run={str(payload.get('run_id', '')).strip() or 'unknown'}"
    if event.event_type == "operation.cycle_finished":
        return None
    return f"{prefix}{event.event_type}"
