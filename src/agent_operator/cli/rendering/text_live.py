from __future__ import annotations

from collections.abc import Callable

from agent_operator.domain import RunEvent


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
    """Render a compact one-line operation summary.

    Example:
        render_operation_list_line(
            "op-1",
            "running",
            objective="Ship dashboard",
            focus="Implement live view",
            latest=None,
            blocker=None,
            runtime_alert=None,
        )
    """
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
    """Render the human-first multi-line live snapshot view.

    Example:
        format_live_snapshot(
            {"operation_id": "op-1", "status": "running"},
            base_formatter=lambda payload: str(payload),
            shorten_live_text=lambda text: text,
        )
    """
    _ = base_formatter
    operation_id = snapshot.get("operation_id")
    status = str(snapshot.get("status") or "unknown").upper()
    lines = [
        f"Operation {operation_id} [{status}]"
        if isinstance(operation_id, str) and operation_id
        else f"Operation [{status}]"
    ]

    focus = shorten_live_text(
        str(snapshot.get("focus")) if snapshot.get("focus") is not None else None
    )
    summary_payload = snapshot.get("summary")
    latest: str | None = None
    next_step: str | None = None
    if isinstance(summary_payload, dict):
        latest = shorten_live_text(
            str(summary_payload.get("work_summary"))
            if summary_payload.get("work_summary") is not None
            else None
        )
        next_step = shorten_live_text(
            str(summary_payload.get("next_step"))
            if summary_payload.get("next_step") is not None
            else None
        )
        if focus is None:
            focus = shorten_live_text(
                str(summary_payload.get("objective"))
                if summary_payload.get("objective") is not None
                else None
            )
    elif summary_payload is not None:
        latest = shorten_live_text(str(summary_payload))
    if focus is not None:
        lines.append(f"Now: {focus}")

    session_id = snapshot.get("session_id")
    adapter_key = snapshot.get("adapter_key")
    latest_turn = snapshot.get("latest_turn")
    latest_turn_agent = (
        latest_turn.get("agent_key")
        if isinstance(latest_turn, dict) and isinstance(latest_turn.get("agent_key"), str)
        else None
    )
    latest_turn_session = None
    if isinstance(latest_turn, dict):
        session_display = latest_turn.get("session_display_name")
        if isinstance(session_display, str) and session_display.strip():
            latest_turn_session = session_display.strip()
        else:
            session_value = latest_turn.get("session_id")
            if isinstance(session_value, str) and session_value.strip():
                latest_turn_session = session_value.strip()
    agent_bits: list[str] = []
    if isinstance(latest_turn_agent, str) and latest_turn_agent:
        agent_bits.append(latest_turn_agent)
    elif isinstance(adapter_key, str) and adapter_key:
        agent_bits.append(adapter_key)
    if latest_turn_session:
        agent_bits.append(latest_turn_session)
    elif isinstance(session_id, str) and session_id:
        agent_bits.append(session_id)
    if agent_bits:
        lines.append(f"Agent: {' | '.join(agent_bits)}")
    assignment_brief = shorten_live_text(
        str(latest_turn.get("assignment_brief"))
        if isinstance(latest_turn, dict) and latest_turn.get("assignment_brief") is not None
        else None
    )
    if assignment_brief is not None:
        lines.append(f"Task: {assignment_brief}")

    waiting_reason = shorten_live_text(
        str(snapshot.get("waiting_reason")) if snapshot.get("waiting_reason") is not None else None
    )
    if waiting_reason is not None:
        lines.append(f"Wait: {waiting_reason}")
    blocking_reason = shorten_live_text(
        str(snapshot.get("blocking_reason"))
        if snapshot.get("blocking_reason") is not None
        else None
    )
    if blocking_reason is not None and waiting_reason is None:
        lines.append(f"Wait: {blocking_reason}")
    attention_brief = shorten_live_text(
        str(snapshot.get("attention_brief"))
        if snapshot.get("attention_brief") is not None
        else None
    )
    if attention_brief is None:
        attention_brief = shorten_live_text(
            str(snapshot.get("attention_title"))
            if snapshot.get("attention_title") is not None
            else None
        )
    if attention_brief is not None:
        count = snapshot.get("open_attention_count")
        if isinstance(count, int) and count > 0:
            lines.append(f"Attention: {count} open; {attention_brief}")
    else:
        lines.append("Attention: none")
    action_hint = shorten_live_text(
        str(snapshot.get("action_hint")) if snapshot.get("action_hint") is not None else None
    )
    if action_hint is not None and attention_brief is not None:
        lines.append(f"Action: {action_hint}")
    if latest is not None and latest != focus:
        lines.append(f"Latest: {latest}")
    if next_step is not None:
        lines.append(f"Next: {next_step}")
    runtime_alert = shorten_live_text(
        str(snapshot.get("runtime_alert")) if snapshot.get("runtime_alert") is not None else None
    )
    if runtime_alert is not None:
        lines.append(f"Alert: {runtime_alert}")
    return "\n".join(lines)


def render_watch_snapshot(
    snapshot: dict[str, object],
    *,
    base_formatter: Callable[[dict[str, object]], str],
    shorten_live_text: Callable[[str | None], str | None],
    latest_update: str | None = None,
) -> str:
    """Render the watch view with a deduplicated recent line.

    Example:
        render_watch_snapshot(
            {"operation_id": "op-1", "status": "running"},
            base_formatter=lambda payload: str(payload),
            shorten_live_text=lambda text: text,
            latest_update="updated",
        )
    """
    lines = format_live_snapshot(
        snapshot,
        base_formatter=base_formatter,
        shorten_live_text=shorten_live_text,
    ).splitlines()
    recent = shorten_live_text(latest_update)
    if recent is not None:
        latest_index = next(
            (idx for idx, line in enumerate(lines) if line.startswith("Latest: ")),
            None,
        )
        if latest_index is not None and lines[latest_index] == f"Latest: {recent}":
            lines.pop(latest_index)
    if recent is not None:
        lines.append(f"Recent: {recent}")
    return "\n".join(lines)


def format_live_event(
    event: RunEvent,
    *,
    shorten_live_text: Callable[[str | None], str | None],
) -> str | None:
    """Render a single live event line for attached and watch surfaces.

    Example:
        format_live_event(
            RunEvent(event_type="operation.started", payload={}, iteration=0),
            shorten_live_text=lambda text: text,
        )
    """
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
    if event.event_type == "attention.request.created":
        attention_id = str(payload.get("attention_id", "")).strip() or None
        operation_id = str(payload.get("operation_id", "")).strip() or event.operation_id or None
        title = shorten_live_text(str(payload.get("title", "")).strip()) or "attention request"
        if bool(payload.get("blocking")) and attention_id is not None and operation_id is not None:
            return (
                f'{prefix}Attention needed: {title}. Run: operator answer '
                f'{operation_id} {attention_id} --text "..."'
            )
        return f"{prefix}attention created: {title}"
    if event.event_type == "command.applied":
        command_type = str(payload.get("command_type", "")).strip() or "unknown"
        if command_type == "answer_attention_request":
            return f"{prefix}Answer received. Resuming..."
        if command_type == "set_execution_profile":
            adapter_key = str(payload.get("adapter_key", "")).strip() or "agent"
            previous_model = str(payload.get("previous_model", "")).strip() or "unknown"
            previous_effort = str(payload.get("previous_effort_value", "")).strip()
            current_model = str(payload.get("current_model", "")).strip() or "unknown"
            current_effort = str(payload.get("current_effort_value", "")).strip()
            previous_display = (
                f"{previous_model} / {previous_effort}" if previous_effort else previous_model
            )
            current_display = (
                f"{current_model} / {current_effort}" if current_effort else current_model
            )
            return (
                f"{prefix}execution profile updated for {adapter_key}: "
                f"{previous_display} -> {current_display}"
            )
        return f"{prefix}command applied: {command_type}"
    if event.event_type == "session.execution_profile.applied":
        adapter_key = str(payload.get("adapter_key", "")).strip() or "agent"
        session_id = str(payload.get("session_id", "")).strip() or event.session_id or "-"
        model = str(payload.get("model", "")).strip() or "unknown"
        effort = str(payload.get("effort_value", "")).strip()
        applied_via = str(payload.get("applied_via", "")).strip() or "start"
        display = f"{model} / {effort}" if effort else model
        verb = "reused with" if applied_via == "reuse" else "started with"
        return f"{prefix}session {session_id} {verb} {adapter_key} {display}"
    if event.event_type == "command.rejected":
        command_type = str(payload.get("command_type", "")).strip() or "unknown"
        reason = shorten_live_text(str(payload.get("rejection_reason", "")).strip())
        rendered = f"{prefix}command rejected: {command_type}"
        if reason is not None:
            rendered += f" | {reason}"
        return rendered
    if event.event_type == "planning_trigger.enqueued":
        reason = str(payload.get("reason", "")).strip() or "unknown"
        return f"{prefix}planning trigger enqueued: {reason}"
    if event.event_type == "planning_trigger.coalesced":
        reason = str(payload.get("reason", "")).strip() or "unknown"
        return f"{prefix}planning trigger coalesced: {reason}"
    if event.event_type == "planning_trigger.applied":
        reason = str(payload.get("reason", "")).strip() or "unknown"
        return f"{prefix}planning trigger applied: {reason}"
    if event.event_type == "background_wakeup.reconciled":
        run_id = str(payload.get("run_id", "")).strip() or "unknown"
        return f"{prefix}background wakeup reconciled: run={run_id}"
    if event.event_type == "background_run.stale_detected":
        run_id = str(payload.get("run_id", "")).strip() or "unknown"
        return f"{prefix}stale background run detected: run={run_id}"
    if event.event_type == "operation.cycle_finished":
        return None
    return f"{prefix}{event.event_type}"
