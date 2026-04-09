from __future__ import annotations

from collections.abc import Callable

from rich.columns import Columns
from rich.console import Group
from rich.panel import Panel
from rich.table import Table

from agent_operator.domain import SchedulerState


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
    table.add_column("Objective")
    table.add_column("Focus")
    table.add_column("Attention / Alert")
    table.add_column("Latest")
    if not items:
        table.add_row("-", "-", "none", "-", "-", "-")
        return table
    for item in items[:8]:
        state = str(item.get("status") or "-")
        scheduler_state = str(item.get("scheduler_state") or "")
        if scheduler_state and scheduler_state != SchedulerState.ACTIVE.value:
            state += f" / {scheduler_state}"
        attention_bits: list[str] = []
        runtime_alert = shorten_live_text(str(item.get("runtime_alert") or ""))
        if runtime_alert is not None:
            attention_bits.append(runtime_alert)
        else:
            attention_briefs = item.get("attention_briefs")
            if isinstance(attention_briefs, list) and attention_briefs:
                attention_bits.append(
                    shorten_live_text(str(attention_briefs[0])) or str(attention_briefs[0])
                )
            blocker_brief = shorten_live_text(str(item.get("blocker_brief") or ""))
            if blocker_brief is not None:
                attention_bits.append(blocker_brief)
        latest = shorten_live_text(str(item.get("latest_outcome_brief") or "-")) or "-"
        focus = shorten_live_text(str(item.get("focus_brief") or "-")) or "-"
        objective = shorten_live_text(str(item.get("objective_brief") or "-")) or "-"
        table.add_row(
            str(item.get("operation_id") or "-"),
            state,
            objective,
            focus,
            " | ".join(attention_bits) if attention_bits else "-",
            latest,
        )
    return table


def render_fleet_dashboard(
    payload: dict[str, object],
    *,
    shorten_live_text: Callable[[str | None], str | None],
) -> Group:
    needs_attention = payload.get("needs_attention")
    active = payload.get("active")
    recent = payload.get("recent")
    hints = payload.get("control_hints")
    mix = payload.get("mix")
    header_lines = [
        f"total_operations={payload.get('total_operations', 0)}",
        (
            f"project={payload.get('project')}"
            if isinstance(payload.get("project"), str) and payload.get("project")
            else "project=all"
        ),
        (
            f"needs_attention={len(needs_attention)} active={len(active)} recent={len(recent)}"
            if isinstance(needs_attention, list)
            and isinstance(active, list)
            and isinstance(recent, list)
            else "needs_attention=0 active=0 recent=0"
        ),
    ]
    if isinstance(mix, dict):
        status_counts = mix.get("status_counts")
        scheduler_counts = mix.get("scheduler_counts")
        involvement_counts = mix.get("involvement_counts")
        if isinstance(status_counts, dict) and status_counts:
            header_lines.append("status_mix=" + format_fleet_mix_counts(status_counts))
        if isinstance(scheduler_counts, dict) and scheduler_counts:
            header_lines.append("scheduler_mix=" + format_fleet_mix_counts(scheduler_counts))
        if isinstance(involvement_counts, dict) and involvement_counts:
            header_lines.append("involvement_mix=" + format_fleet_mix_counts(involvement_counts))
    hint_renderable = "\n".join(str(item) for item in hints if isinstance(item, str)) or "- none"
    recent_renderable = (
        render_fleet_items_table(recent, shorten_live_text=shorten_live_text)
        if isinstance(recent, list)
        else "-"
    )
    return Group(
        Panel("\n".join(header_lines), title="Fleet Dashboard", border_style="cyan"),
        Columns(
            [
                Panel(
                    (
                        render_fleet_items_table(
                            needs_attention,
                            shorten_live_text=shorten_live_text,
                        )
                        if isinstance(needs_attention, list)
                        else "-"
                    ),
                    title=(
                        f"Needs Attention ({len(needs_attention)})"
                        if isinstance(needs_attention, list)
                        else "Needs Attention"
                    ),
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
                    recent_renderable,
                    title=f"Recent ({len(recent)})" if isinstance(recent, list) else "Recent",
                    border_style="blue",
                ),
                Panel(hint_renderable, title="Suggested Next Commands", border_style="magenta"),
            ]
        ),
    )


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
                        active_policies,
                        shorten_live_text=shorten_live_text,
                    )
                    if isinstance(active_policies, list)
                    else "-",
                    title=(
                        f"Active Policies ({len(active_policies)})"
                        if isinstance(active_policies, list)
                        else "Active Policies"
                    ),
                    border_style="yellow",
                ),
            ]
        ),
        Panel("\n".join(fleet_lines), title="Fleet Summary", border_style="blue"),
        Columns(
            [
                Panel(
                    render_fleet_items_table(
                        needs_attention,
                        shorten_live_text=shorten_live_text,
                    )
                    if isinstance(needs_attention, list)
                    else "-",
                    title=(
                        f"Needs Attention ({len(needs_attention)})"
                        if isinstance(needs_attention, list)
                        else "Needs Attention"
                    ),
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
        f"status={payload.get('status')} scheduler={payload.get('scheduler_state')} "
        f"run_mode={payload.get('run_mode')} involvement={payload.get('involvement_level')}",
        (
            f"objective: {brief_summary.get('objective')}"
            if isinstance(brief_summary, dict) and brief_summary.get("objective")
            else f"objective: {payload.get('objective')}"
        ),
        (
            f"harness: {brief_summary.get('harness')}"
            if isinstance(brief_summary, dict) and brief_summary.get("harness")
            else f"harness: {payload.get('harness_instructions') or '-'}"
        ),
        (
            f"focus: {brief_summary.get('focus') or '-'}"
            if isinstance(brief_summary, dict)
            else f"focus: {payload.get('focus') or '-'}"
        ),
        f"task_counts: {payload.get('task_counts') or 'none'}",
    ]
    if isinstance(active_session, dict):
        session_line = (
            "active session: "
            f"{active_session.get('session_id')} [{active_session.get('adapter_key')}] "
            f"status={active_session.get('status')}"
        )
        if active_session.get("session_name"):
            session_line += f" name={active_session.get('session_name')}"
        header_lines.append(session_line)
        waiting_reason = active_session.get("waiting_reason")
        if isinstance(waiting_reason, str) and waiting_reason.strip():
            header_lines.append(f"waiting: {waiting_reason.strip()}")
    if isinstance(brief_summary, dict):
        latest = brief_summary.get("latest")
        if isinstance(latest, str) and latest.strip():
            header_lines.append(f"latest: {latest.strip()}")
        verification = brief_summary.get("verification")
        if isinstance(verification, str) and verification.strip():
            header_lines.append(f"verification: {verification.strip()}")
        blockers = brief_summary.get("blockers")
        if isinstance(blockers, str) and blockers.strip():
            header_lines.append(f"blockers: {blockers.strip()}")
        next_step = brief_summary.get("next_step")
        if isinstance(next_step, str) and next_step.strip():
            header_lines.append(f"next: {next_step.strip()}")
        blocker = brief_summary.get("blocker")
        if isinstance(blocker, str) and blocker.strip():
            header_lines.append(f"blocker: {blocker.strip()}")
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
            context_lines.append(
                "default_agents: " + (", ".join(str(item) for item in agents) if agents else "-")
            )
    available_agent_descriptors = payload.get("available_agent_descriptors")
    if isinstance(available_agent_descriptors, list) and available_agent_descriptors:
        for descriptor in available_agent_descriptors:
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
            context_lines.append(
                f"agent: {descriptor.get('key') or '-'}"
                f" | follow_up={'yes' if descriptor.get('supports_follow_up') else 'no'}"
                f" | capabilities: {capability_names}"
            )
    if isinstance(policy_coverage, dict):
        context_lines.append(
            "policy_coverage: "
            f"{policy_coverage.get('status') or '-'} "
            f"(scope_entries={policy_coverage.get('scoped_policy_count') or 0}, "
            f"active_now={policy_coverage.get('active_policy_count') or 0})"
        )
        summary = policy_coverage.get("summary")
        if isinstance(summary, str) and summary:
            context_lines.append(f"coverage_summary: {summary}")
    if isinstance(active_policies, list) and active_policies:
        for policy in active_policies[:3]:
            if isinstance(policy, dict):
                policy_line = (
                    f"policy: {policy.get('policy_id')} [{policy.get('category')}] "
                    f"{policy.get('title')}"
                )
                applicability = policy.get("applicability_summary")
                if isinstance(applicability, str) and applicability:
                    policy_line += f" | applies: {applicability}"
                match_reasons = policy.get("match_reasons")
                if isinstance(match_reasons, list) and match_reasons:
                    policy_line += " | matched_by: " + ", ".join(
                        str(item) for item in match_reasons
                    )
                context_lines.append(policy_line)
    if not context_lines:
        context_lines.append("- none")

    attention_table = Table(expand=True)
    attention_table.add_column("Type")
    attention_table.add_column("Title")
    attention_table.add_column("Blocking", justify="center")
    attention_items = payload.get("attention")
    if isinstance(attention_items, list) and attention_items:
        for item in attention_items[:5]:
            if not isinstance(item, dict):
                continue
            attention_table.add_row(
                str(item.get("attention_type") or "-"),
                shorten_live_text(str(item.get("title") or "-")) or "-",
                "yes" if item.get("blocking") else "no",
            )
    else:
        attention_table.add_row("-", "none", "-")

    tasks_table = Table(expand=True)
    tasks_table.add_column("Task")
    tasks_table.add_column("Status")
    tasks_table.add_column("Priority", justify="right")
    tasks_table.add_column("Agent")
    task_items = payload.get("tasks")
    if isinstance(task_items, list) and task_items:
        for item in task_items:
            if not isinstance(item, dict):
                continue
            tasks_table.add_row(
                shorten_live_text(str(item.get("title") or "-")) or "-",
                str(item.get("status") or "-"),
                str(item.get("priority") or "-"),
                str(item.get("assigned_agent") or "-"),
            )
    else:
        tasks_table.add_row("none", "-", "-", "-")

    sessions_table = Table(expand=True)
    sessions_table.add_column("Session")
    sessions_table.add_column("Agent")
    sessions_table.add_column("Status")
    sessions_table.add_column("Waiting")
    session_items = payload.get("sessions")
    if isinstance(session_items, list) and session_items:
        for item in session_items[:6]:
            if not isinstance(item, dict):
                continue
            sessions_table.add_row(
                str(item.get("session_id") or "-"),
                str(item.get("adapter_key") or "-"),
                str(item.get("status") or "-"),
                shorten_live_text(str(item.get("waiting_reason") or "-")) or "-",
            )
    else:
        sessions_table.add_row("none", "-", "-", "-")

    recent_event_lines = payload.get("recent_events")
    event_renderable = (
        "\n".join(str(item) for item in recent_event_lines if isinstance(item, str)) or "- none"
    )
    recent_command_lines = payload.get("recent_commands")
    command_renderable = (
        "\n".join(
            str(item.get("summary"))
            for item in recent_command_lines
            if isinstance(item, dict) and isinstance(item.get("summary"), str)
        )
        or "- none"
    )
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
    hint_renderable = (
        "\n".join(str(item) for item in control_hints if isinstance(item, str)) or "- none"
    )

    return Group(
        Panel(
            "\n".join(header_lines),
            title=f"Operation Dashboard: {payload.get('operation_id')}",
            border_style="cyan",
        ),
        Columns(
            [
                Panel("\n".join(context_lines), title="Control Context", border_style="blue"),
                Panel(attention_table, title="Attention", border_style="yellow"),
            ]
        ),
        Columns(
            [
                Panel(tasks_table, title="Tasks", border_style="green"),
                Panel(sessions_table, title="Sessions", border_style="magenta"),
            ]
        ),
        Columns(
            [
                Panel(event_renderable, title="Recent Events", border_style="blue"),
                Panel(command_renderable, title="Recent Commands", border_style="red"),
            ]
        ),
        Columns(
            [
                Panel(transcript_renderable, title=transcript_title, border_style="magenta"),
                Panel(hint_renderable, title="Control Hints", border_style="cyan"),
            ]
        ),
    )
