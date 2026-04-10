from __future__ import annotations

from agent_operator.domain import (
    InvolvementLevel,
    OperationState,
    PolicyEntry,
    RunMode,
    describe_policy_applicability,
    policy_match_reasons,
    policy_mismatch_reasons,
)


def policy_applicability_payload(
    objective_keyword: list[str] | None,
    task_keyword: list[str] | None,
    agent: list[str] | None,
    run_mode: list[RunMode] | None,
    involvement: list[InvolvementLevel] | None,
) -> dict[str, object]:
    payload: dict[str, object] = {}
    if objective_keyword:
        payload["objective_keywords"] = [item.strip() for item in objective_keyword if item.strip()]
    if task_keyword:
        payload["task_keywords"] = [item.strip() for item in task_keyword if item.strip()]
    if agent:
        payload["agent_keys"] = [item.strip() for item in agent if item.strip()]
    if run_mode:
        payload["run_modes"] = [item.value for item in run_mode]
    if involvement:
        payload["involvement_levels"] = [item.value for item in involvement]
    return payload


def policy_payload(
    policy: PolicyEntry, operation: OperationState | None = None
) -> dict[str, object]:
    payload = policy.model_dump(mode="json")
    payload["applicability_summary"] = describe_policy_applicability(policy)
    if operation is not None:
        payload["match_reasons"] = policy_match_reasons(policy, operation)
    return payload


def resolve_operation_policy_scope(operation: OperationState) -> str | None:
    policy_scope = operation.policy_coverage.project_scope
    if isinstance(policy_scope, str) and policy_scope.strip():
        return policy_scope.strip()
    raw_scope = operation.goal.metadata.get("policy_scope")
    if isinstance(raw_scope, str) and raw_scope.strip():
        return raw_scope.strip()
    return None


def policy_evaluation_payload(policy: PolicyEntry, operation: OperationState) -> dict[str, object]:
    payload = policy_payload(policy, operation)
    match_reasons = payload.get("match_reasons")
    matched = isinstance(match_reasons, list) and len(match_reasons) > 0
    payload["applies_now"] = matched
    payload["skip_reasons"] = [] if matched else policy_mismatch_reasons(policy, operation)
    return payload
