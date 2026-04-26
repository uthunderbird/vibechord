from __future__ import annotations


def emit_context_lines(payload: dict[str, object], *, operation_id: str) -> list[str]:
    """Render verbose inspect context lines for one operation.

    Example:
        emit_context_lines(
            {"objective": "Ship dashboard", "status": "running"},
            operation_id="op-1",
        )
    """
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
            f"- Current focus: {current_focus.get('kind')}:"
            f"{current_focus.get('target_id')}"
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
                lines.append(
                    "- CLI/profile overrides: " + ", ".join(str(item) for item in overrides)
                )
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
