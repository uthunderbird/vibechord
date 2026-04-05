from __future__ import annotations

from agent_operator.domain.enums import PolicyCoverageStatus, RunMode
from agent_operator.domain.operation import OperationState
from agent_operator.domain.policy import PolicyCoverage, PolicyEntry


def policy_match_reasons(policy: PolicyEntry, operation: OperationState) -> list[str]:
    applicability = policy.applicability
    reasons: list[str] = []
    if applicability.is_global:
        return ["global policy"]
    context = _build_policy_match_context(operation)

    if applicability.objective_keywords:
        matched = [
            keyword
            for keyword in applicability.objective_keywords
            if keyword.casefold() in context["objective_text"]
        ]
        if not matched:
            return []
        reasons.append("objective keyword=" + ", ".join(matched))
    if applicability.task_keywords:
        matched = [
            keyword
            for keyword in applicability.task_keywords
            if keyword.casefold() in context["task_text"]
        ]
        if not matched:
            return []
        reasons.append("task keyword=" + ", ".join(matched))
    if applicability.agent_keys:
        matched = [
            agent
            for agent in applicability.agent_keys
            if agent in context["allowed_agents"]
        ]
        if not matched:
            return []
        reasons.append("agent=" + ", ".join(matched))
    if applicability.run_modes:
        matched = [
            mode.value
            for mode in applicability.run_modes
            if mode.value == context["run_mode"]
        ]
        if not matched:
            return []
        reasons.append("run_mode=" + ", ".join(matched))
    if applicability.involvement_levels:
        matched = [
            level.value
            for level in applicability.involvement_levels
            if level is context["involvement_level"]
        ]
        if not matched:
            return []
        reasons.append("involvement=" + ", ".join(matched))
    if applicability.permission_signatures:
        matched = [
            signature.adapter_key
            for signature in applicability.permission_signatures
            if signature.adapter_key in context["allowed_agents"]
        ]
        if not matched:
            return []
        reasons.append("permission_signature=" + ", ".join(matched))
    return reasons


def policy_mismatch_reasons(policy: PolicyEntry, operation: OperationState) -> list[str]:
    applicability = policy.applicability
    if applicability.is_global:
        return []
    context = _build_policy_match_context(operation)
    reasons: list[str] = []

    if applicability.objective_keywords and not any(
        keyword.casefold() in context["objective_text"]
        for keyword in applicability.objective_keywords
    ):
        reasons.append("objective missing " + ", ".join(applicability.objective_keywords))
    if applicability.task_keywords and not any(
        keyword.casefold() in context["task_text"] for keyword in applicability.task_keywords
    ):
        reasons.append("task missing " + ", ".join(applicability.task_keywords))
    if applicability.agent_keys and not any(
        agent in context["allowed_agents"] for agent in applicability.agent_keys
    ):
        reasons.append("agent mismatch " + ", ".join(applicability.agent_keys))
    if applicability.run_modes and not any(
        mode.value == context["run_mode"] for mode in applicability.run_modes
    ):
        reasons.append(
            "run mode mismatch expected "
            + ", ".join(mode.value for mode in applicability.run_modes)
            + f" but was {context['run_mode']}"
        )
    if applicability.involvement_levels and not any(
        level is context["involvement_level"] for level in applicability.involvement_levels
    ):
        reasons.append(
            "involvement mismatch expected "
            + ", ".join(level.value for level in applicability.involvement_levels)
            + f" but was {context['involvement_level'].value}"
        )
    if applicability.permission_signatures and not any(
        signature.adapter_key in context["allowed_agents"]
        for signature in applicability.permission_signatures
    ):
        reasons.append("permission signature agent mismatch")
    return reasons


def policy_applies_to_operation(policy: PolicyEntry, operation: OperationState) -> bool:
    return bool(policy_match_reasons(policy, operation))


def assess_policy_coverage(
    *,
    project_scope: str | None,
    scoped_policies: list[PolicyEntry],
    active_policies: list[PolicyEntry],
) -> PolicyCoverage:
    if project_scope is None:
        return PolicyCoverage()
    if not scoped_policies:
        return PolicyCoverage(
            status=PolicyCoverageStatus.NO_POLICY,
            project_scope=project_scope,
            summary="No project policy exists yet for this scope.",
        )
    if active_policies:
        return PolicyCoverage(
            status=PolicyCoverageStatus.COVERED,
            project_scope=project_scope,
            scoped_policy_count=len(scoped_policies),
            active_policy_count=len(active_policies),
            summary=(
                f"{len(active_policies)} active policy "
                f"{'entry applies' if len(active_policies) == 1 else 'entries apply'} now."
            ),
        )
    return PolicyCoverage(
        status=PolicyCoverageStatus.UNCOVERED,
        project_scope=project_scope,
        scoped_policy_count=len(scoped_policies),
        summary="This scope has project policy, but none of it currently applies.",
    )


def describe_policy_applicability(policy: PolicyEntry) -> str:
    applicability = policy.applicability
    if applicability.is_global:
        return "all operations in this project scope"
    parts: list[str] = []
    if applicability.objective_keywords:
        parts.append("objective contains " + ", ".join(applicability.objective_keywords))
    if applicability.task_keywords:
        parts.append("task contains " + ", ".join(applicability.task_keywords))
    if applicability.agent_keys:
        parts.append("agent in " + ", ".join(applicability.agent_keys))
    if applicability.run_modes:
        parts.append("run mode in " + ", ".join(mode.value for mode in applicability.run_modes))
    if applicability.involvement_levels:
        parts.append(
            "involvement in " + ", ".join(level.value for level in applicability.involvement_levels)
        )
    if applicability.permission_signatures:
        parts.append(
            "permission signatures="
            + ", ".join(signature.adapter_key for signature in applicability.permission_signatures)
        )
    return "; ".join(parts)


def _build_policy_match_context(operation: OperationState) -> dict[str, object]:
    objective_text = " ".join(
        filter(
            None,
            [
                operation.objective_state.objective,
                operation.objective_state.harness_instructions,
                *operation.objective_state.success_criteria,
            ],
        )
    ).casefold()
    task_text = " ".join(
        filter(
            None,
            [task.title for task in operation.tasks]
            + [task.goal for task in operation.tasks]
            + [note for task in operation.tasks for note in task.notes],
        )
    ).casefold()
    allowed_agents = set(operation.policy.allowed_agents)
    allowed_agents.update(session.adapter_key for session in operation.sessions)
    raw_mode = operation.runtime_hints.metadata.get("run_mode")
    run_mode = RunMode.ATTACHED.value
    if isinstance(raw_mode, str) and raw_mode.strip():
        run_mode = raw_mode.strip()
    return {
        "objective_text": objective_text,
        "task_text": task_text,
        "allowed_agents": allowed_agents,
        "run_mode": run_mode,
        "involvement_level": operation.involvement_level,
    }
