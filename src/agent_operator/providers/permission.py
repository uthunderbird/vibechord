from __future__ import annotations

from pathlib import Path

from agent_operator.acp.permissions import (
    AcpPermissionDecision,
    AcpPermissionRequest,
    PermissionEvaluationResult,
    find_matching_permission_policy,
    serialize_permission_request,
)
from agent_operator.domain import OperationState, PolicyCategory, PolicyEntry
from agent_operator.protocols import (
    OperationStore,
    PolicyStore,
    StructuredOutputProvider,
)


class ProviderBackedPermissionEvaluator:
    def __init__(
        self,
        provider: StructuredOutputProvider,
        *,
        store: OperationStore,
        policy_store: PolicyStore | None = None,
    ) -> None:
        self._provider = provider
        self._store = store
        self._policy_store = policy_store

    async def evaluate(
        self,
        *,
        operation_id: str,
        working_directory: Path,
        request: AcpPermissionRequest,
    ) -> PermissionEvaluationResult:
        state = await self._store.load_operation(operation_id)
        if state is None:
            return PermissionEvaluationResult(
                decision=AcpPermissionDecision.REJECT,
                rationale=(
                    "Operation state was unavailable while evaluating the permission "
                    "request, so the operator rejected it conservatively."
                ),
                suggested_options=("Reject",),
            )
        active_policies = await self._active_policies_for_operation(state)
        matched_policy = find_matching_permission_policy(request, active_policies=active_policies)
        if matched_policy is not None:
            return PermissionEvaluationResult(
                decision=_decision_from_policy(matched_policy),
                rationale=f"Matched stored autonomy policy {matched_policy.policy_id}.",
                policy_title=matched_policy.title,
                policy_rule_text=matched_policy.rule_text,
            )

        payload = await self._provider.evaluate_permission_request(
            state,
            request_payload=serialize_permission_request(request),
            active_policy_payload=[_serialize_policy_entry(item) for item in active_policies],
        )
        decision = _decision_from_dto(
            payload.decision,
            allow_escalation=state.involvement_level.value in {"collaborative", "approval_heavy"},
        )
        return PermissionEvaluationResult(
            decision=decision,
            rationale=payload.rationale,
            suggested_options=tuple(payload.suggested_options),
            policy_title=payload.policy_title,
            policy_rule_text=payload.policy_rule_text,
        )

    async def _active_policies_for_operation(self, state: OperationState) -> list[PolicyEntry]:
        if self._policy_store is None:
            return list(state.active_policies)
        project_scope = state.policy_coverage.project_scope
        if project_scope is None:
            return list(state.active_policies)
        try:
            policies = await self._policy_store.list(
                project_scope=project_scope,
                include_inactive=False,
            )
        except TypeError:
            policies = await self._policy_store.list(project_scope=project_scope, status=None)
        return [item for item in policies if item.category is PolicyCategory.AUTONOMY]


def _decision_from_dto(raw: str, *, allow_escalation: bool) -> AcpPermissionDecision:
    normalized = raw.strip().lower()
    if normalized == "approve":
        return AcpPermissionDecision.APPROVE
    if normalized == "reject":
        return AcpPermissionDecision.REJECT
    if not allow_escalation:
        return AcpPermissionDecision.REJECT
    return AcpPermissionDecision.ESCALATE


def _decision_from_policy(policy: PolicyEntry) -> AcpPermissionDecision:
    lowered = policy.rule_text.strip().lower()
    if lowered.startswith("decision: approve"):
        return AcpPermissionDecision.APPROVE
    if lowered.startswith("decision: reject"):
        return AcpPermissionDecision.REJECT
    return AcpPermissionDecision.ESCALATE


def _serialize_policy_entry(entry: PolicyEntry) -> dict[str, object]:
    return {
        "policy_id": entry.policy_id,
        "title": entry.title,
        "category": entry.category.value,
        "rule_text": entry.rule_text,
        "permission_signatures": [
            signature.model_dump(mode="json")
            for signature in entry.applicability.permission_signatures
        ],
        "rationale": entry.rationale,
    }
