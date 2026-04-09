from __future__ import annotations

from collections.abc import Callable

from rich.columns import Columns
from rich.console import Group
from rich.panel import Panel
from rich.table import Table


def render_dashboard(
    payload: dict[str, object],
    *,
    shorten_live_text: Callable[[str | None], str | None],
) -> Group:
    active_session = payload.get("active_session")
    brief_summary = payload.get("brief_summary")
    project_context = payload.get("project_context")
    policy_coverage = payload.get("policy_coverage")
    active_policies = payload.get("active_policies")
    header_lines = [
        f"status={payload.get('status')} scheduler={payload.get('scheduler_state')} run_mode={payload.get('run_mode')} involvement={payload.get('involvement_level')}",
        f"objective: {brief_summary.get('objective')}" if isinstance(brief_summary, dict) and brief_summary.get("objective") else f"objective: {payload.get('objective')}",
        f"harness: {brief_summary.get('harness')}" if isinstance(brief_summary, dict) and brief_summary.get("harness") else f"harness: {payload.get('harness_instructions') or '-'}",
        f"focus: {brief_summary.get('focus') or '-'}" if isinstance(brief_summary, dict) else f"focus: {payload.get('focus') or '-'}",
        f"task_counts: {payload.get('task_counts') or 'none'}",
    ]
    if isinstance(active_session, dict):
        session_line = f"active session: {active_session.get('session_id')} [{active_session.get('adapter_key')}] status={active_session.get('status')}"
        if active_session.get("session_name"):
            session_line += f" name={active_session.get('session_name')}"
        header_lines.append(session_line)
        waiting_reason = active_session.get("waiting_reason")
        if isinstance(waiting_reason, str) and waiting_reason.strip():
            header_lines.append(f"waiting: {waiting_reason.strip()}")
    runtime_alert = None
    if isinstance(brief_summary, dict):
        for key, label in [("latest", "latest"), ("verification", "verification"), ("blockers", "blockers"), ("next_step", "next"), ("blocker", "blocker")]:
            value = brief_summary.get(key)
            if isinstance(value, str) and value.strip():
                header_lines.append(f"{label}: {value.strip()}")
        runtime_alert = brief_summary.get("runtime_alert")
    else:
        summary = payload.get("summary")
        if isinstance(summary, str) and summary.strip():
            header_lines.append(f"summary: {summary.strip()}")
        runtime_alert = payload.get("runtime_alert")
    if isinstance(runtime_alert, str) and runtime_alert.strip():
        header_lines.append(f"alert: {runtime_alert.strip()}")
    context_lines = []
    if isinstance(project_context, dict):
        context_lines.append(f"profile: {project_context.get('profile_name') or '-'}")
        context_lines.append(f"policy_scope: {project_context.get('policy_scope') or '-'}")
        resolved_profile = project_context.get("resolved_profile")
        if isinstance(resolved_profile, dict):
            context_lines.append(f"cwd: {resolved_profile.get('cwd') or '-'}")
            agents = resolved_profile.get("default_agents") or []
            context_lines.append("default_agents: " + (", ".join(str(item) for item in agents) if agents else "-"))
    available_agent_descriptors = payload.get("available_agent_descriptors")
    if isinstance(available_agent_descriptors, list) and available_agent_descriptors:
        for descriptor in available_agent_descriptors:
            if not isinstance(descriptor, dict):
                continue
            capabilities = descriptor.get("capabilities")
            capability_names = ", ".join(str(item.get("name")) for item in capabilities if isinstance(item, dict) and item.get("name")) if isinstance(capabilities, list) else "-"
            context_lines.append(f"agent: {descriptor.get('key') or '-'} | follow_up={'yes' if descriptor.get('supports_follow_up') else 'no'} | capabilities: {capability_names}")
    if isinstance(policy_coverage, dict):
        context_lines.append(f"policy_coverage: {policy_coverage.get('status') or '-'} (scope_entries={policy_coverage.get('scoped_policy_count') or 0}, active_now={policy_coverage.get('active_policy_count') or 0})")
        summary = policy_coverage.get("summary")
        if isinstance(summary, str) and summary:
            context_lines.append(f"coverage_summary: {summary}")
    if isinstance(active_policies, list) and active_policies:
        for policy in active_policies[:3]:
            if isinstance(policy, dict):
                policy_line = f"policy: {policy.get('policy_id')} [{policy.get('category')}] {policy.get('title')}"
                applicability = policy.get("applicability_summary")
                if isinstance(applicability, str) and applicability:
                    policy_line += f" | applies: {applicability}"
                match_reasons = policy.get("match_reasons")
                if isinstance(match_reasons, list) and match_reasons:
                    policy_line += " | matched_by: " + ", ".join(str(item) for item in match_reasons)
                context_lines.append(policy_line)
    if not context_lines:
        context_lines.append("- none")
    attention_table = Table(expand=True)
    attention_table.add_column("Type"); attention_table.add_column("Title"); attention_table.add_column("Blocking", justify="center")
    attention_items = payload.get("attention")
    if isinstance(attention_items, list) and attention_items:
        for item in attention_items[:5]:
            if not isinstance(item, dict):
                continue
            attention_table.add_row(str(item.get("attention_type") or "-"), shorten_live_text(str(item.get("title") or "-")) or "-", "yes" if item.get("blocking") else "no")
    else:
        attention_table.add_row("-", "none", "-")
    tasks_table = Table(expand=True)
    tasks_table.add_column("Task"); tasks_table.add_column("Status"); tasks_table.add_column("Priority", justify="right"); tasks_table.add_column("Agent")
    task_items = payload.get("tasks")
    if isinstance(task_items, list) and task_items:
        for item in task_items:
            if not isinstance(item, dict):
                continue
            tasks_table.add_row(shorten_live_text(str(item.get("title") or "-")) or "-", str(item.get("status") or "-"), str(item.get("priority") or "-"), str(item.get("assigned_agent") or "-"))
    else:
        tasks_table.add_row("none", "-", "-", "-")
    sessions_table = Table(expand=True)
    sessions_table.add_column("Session"); sessions_table.add_column("Agent"); sessions_table.add_column("Status"); sessions_table.add_column("Waiting")
    session_items = payload.get("sessions")
    if isinstance(session_items, list) and session_items:
        for item in session_items[:6]:
            if not isinstance(item, dict):
                continue
            sessions_table.add_row(str(item.get("session_id") or "-"), str(item.get("adapter_key") or "-"), str(item.get("status") or "-"), shorten_live_text(str(item.get("waiting_reason") or "-")) or "-")
    else:
        sessions_table.add_row("none", "-", "-", "-")
    recent_event_lines = payload.get("recent_events")
    event_renderable = "\n".join(str(item) for item in recent_event_lines if isinstance(item, str)) or "- none"
    recent_command_lines = payload.get("recent_commands")
    command_renderable = "\n".join(str(item.get("summary")) for item in recent_command_lines if isinstance(item, dict) and isinstance(item.get("summary"), str)) or "- none"
    transcript_title = "Upstream Transcript"
    transcript_renderable = "- none"
    transcript_payload = payload.get("upstream_transcript")
    if isinstance(transcript_payload, dict):
        transcript_title = str(transcript_payload.get("title") or transcript_title)
        transcript_lines = []
        session_id = transcript_payload.get("session_id")
        if isinstance(session_id, str) and session_id:
            transcript_lines.append(f"session: {session_id}")
        events = transcript_payload.get("events")
        if isinstance(events, list) and events:
            transcript_lines.extend(str(item) for item in events if isinstance(item, str))
        command_hint = transcript_payload.get("command_hint")
        if isinstance(command_hint, str) and command_hint:
            transcript_lines.append(f"drill-down: {command_hint}")
        transcript_renderable = "\n".join(transcript_lines) or "- none"
    control_hints = payload.get("control_hints")
    hint_renderable = "\n".join(str(item) for item in control_hints if isinstance(item, str)) or "- none"
    return Group(
        Panel("\n".join(header_lines), title=f"Operation Dashboard: {payload.get('operation_id')}", border_style="cyan"),
        Columns([Panel("\n".join(context_lines), title="Control Context", border_style="blue"), Panel(attention_table, title="Attention", border_style="yellow")]),
        Columns([Panel(tasks_table, title="Tasks", border_style="green"), Panel(sessions_table, title="Sessions", border_style="magenta")]),
        Columns([Panel(event_renderable, title="Recent Events", border_style="blue"), Panel(command_renderable, title="Recent Commands", border_style="red")]),
        Columns([Panel(transcript_renderable, title=transcript_title, border_style="magenta"), Panel(hint_renderable, title="Control Hints", border_style="cyan")]),
    )
