"""State-machine test matrix for ProviderBackedPermissionEvaluator and _decision_from_dto.

Covers: InvolvementLevel × LLM-decision-output × evaluator behavior.

Tests marked with # CURRENT BEHAVIOR document what the code does today.
Tests marked with # BUG document behavior that is wrong and should change.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from agent_operator.acp.permissions import (
    AcpPermissionDecision,
    AcpPermissionInteraction,
    AcpPermissionRequest,
)
from agent_operator.domain import InvolvementLevel, OperationGoal, OperationState
from agent_operator.dtos.brain import PermissionDecisionDTO
from agent_operator.providers.permission import (
    ProviderBackedPermissionEvaluator,
    _decision_from_dto,
)

# ---------------------------------------------------------------------------
# Layer 1 — _decision_from_dto unit tests
# ---------------------------------------------------------------------------


def test_decision_from_dto_approve_with_escalation_allowed() -> None:
    assert _decision_from_dto("approve", allow_escalation=True) is AcpPermissionDecision.APPROVE


def test_decision_from_dto_approve_with_escalation_forbidden() -> None:
    assert _decision_from_dto("approve", allow_escalation=False) is AcpPermissionDecision.APPROVE


def test_decision_from_dto_approve_case_insensitive() -> None:
    assert _decision_from_dto("APPROVE", allow_escalation=False) is AcpPermissionDecision.APPROVE


def test_decision_from_dto_reject_with_escalation_allowed() -> None:
    assert _decision_from_dto("reject", allow_escalation=True) is AcpPermissionDecision.REJECT


def test_decision_from_dto_reject_with_escalation_forbidden() -> None:
    assert _decision_from_dto("reject", allow_escalation=False) is AcpPermissionDecision.REJECT


def test_decision_from_dto_escalate_allowed_when_escalation_permitted() -> None:
    assert _decision_from_dto("escalate", allow_escalation=True) is AcpPermissionDecision.ESCALATE


def test_decision_from_dto_escalate_silently_rejects_when_escalation_forbidden() -> None:
    # CURRENT BEHAVIOR: ESCALATE → REJECT when allow_escalation=False
    # This is the core of the bug: the LLM's escalation intent is silently discarded.
    assert _decision_from_dto("escalate", allow_escalation=False) is AcpPermissionDecision.REJECT


def test_decision_from_dto_unknown_value_with_escalation_allowed() -> None:
    # Garbage LLM output falls through to ESCALATE when escalation is permitted.
    assert _decision_from_dto("maybe", allow_escalation=True) is AcpPermissionDecision.ESCALATE


def test_decision_from_dto_unknown_value_silently_rejects_when_escalation_forbidden() -> None:
    # CURRENT BEHAVIOR: unknown LLM output → REJECT when allow_escalation=False
    assert _decision_from_dto("maybe", allow_escalation=False) is AcpPermissionDecision.REJECT


# ---------------------------------------------------------------------------
# Layer 2 — ProviderBackedPermissionEvaluator.evaluate (InvolvementLevel matrix)
# ---------------------------------------------------------------------------


class _FakePermissionDecisionProvider:
    """Returns a fixed PermissionDecisionDTO from evaluate_permission_request."""

    def __init__(self, decision: str, rationale: str = "test") -> None:
        self.decision = decision
        self.rationale = rationale
        self.call_count = 0

    async def evaluate_permission_request(
        self,
        state: OperationState,
        *,
        request_payload: dict[str, object],
        active_policy_payload: list[dict[str, object]],
    ) -> PermissionDecisionDTO:
        self.call_count += 1
        return PermissionDecisionDTO(
            decision=self.decision,
            rationale=self.rationale,
        )


class _FakeOperationStore:
    def __init__(self, state: OperationState | None) -> None:
        self._state = state

    async def load_operation(self, operation_id: str) -> OperationState | None:
        return self._state


def _make_request() -> AcpPermissionRequest:
    return AcpPermissionRequest(
        request_id=1,
        adapter_key="codex_acp",
        method="session/request_permission",
        interaction=AcpPermissionInteraction.APPROVAL,
        working_directory=Path("/tmp/repo"),
    )


def _make_evaluator(
    *,
    llm_decision: str,
    involvement_level: InvolvementLevel,
) -> ProviderBackedPermissionEvaluator:
    state = OperationState(
        goal=OperationGoal(objective="test"),
        involvement_level=involvement_level,
    )
    provider = _FakePermissionDecisionProvider(decision=llm_decision)
    store = _FakeOperationStore(state)
    return ProviderBackedPermissionEvaluator(provider, store=store)


@pytest.mark.anyio
async def test_evaluator_llm_approve_approval_heavy_returns_approve() -> None:
    evaluator = _make_evaluator(
        llm_decision="approve", involvement_level=InvolvementLevel.APPROVAL_HEAVY
    )
    result = await evaluator.evaluate(
        operation_id="op-1",
        working_directory=Path("/tmp"),
        request=_make_request(),
    )
    assert result.decision is AcpPermissionDecision.APPROVE


@pytest.mark.anyio
async def test_evaluator_llm_approve_auto_returns_approve() -> None:
    evaluator = _make_evaluator(llm_decision="approve", involvement_level=InvolvementLevel.AUTO)
    result = await evaluator.evaluate(
        operation_id="op-1",
        working_directory=Path("/tmp"),
        request=_make_request(),
    )
    assert result.decision is AcpPermissionDecision.APPROVE


@pytest.mark.anyio
async def test_evaluator_llm_reject_any_level_returns_reject() -> None:
    for level in InvolvementLevel:
        evaluator = _make_evaluator(llm_decision="reject", involvement_level=level)
        result = await evaluator.evaluate(
            operation_id="op-1",
            working_directory=Path("/tmp"),
            request=_make_request(),
        )
        assert result.decision is AcpPermissionDecision.REJECT, f"failed for {level}"


@pytest.mark.anyio
async def test_evaluator_llm_escalate_approval_heavy_returns_escalate() -> None:
    evaluator = _make_evaluator(
        llm_decision="escalate", involvement_level=InvolvementLevel.APPROVAL_HEAVY
    )
    result = await evaluator.evaluate(
        operation_id="op-1",
        working_directory=Path("/tmp"),
        request=_make_request(),
    )
    assert result.decision is AcpPermissionDecision.ESCALATE


@pytest.mark.anyio
async def test_evaluator_llm_escalate_auto_returns_reject() -> None:
    # AUTO decides autonomously — LLM escalation intent is correctly rejected.
    evaluator = _make_evaluator(llm_decision="escalate", involvement_level=InvolvementLevel.AUTO)
    result = await evaluator.evaluate(
        operation_id="op-1",
        working_directory=Path("/tmp"),
        request=_make_request(),
    )
    assert result.decision is AcpPermissionDecision.REJECT


@pytest.mark.anyio
async def test_evaluator_llm_escalate_collaborative_returns_escalate() -> None:
    # COLLABORATIVE allows escalation — LLM's escalation intent is respected.
    evaluator = _make_evaluator(
        llm_decision="escalate", involvement_level=InvolvementLevel.COLLABORATIVE
    )
    result = await evaluator.evaluate(
        operation_id="op-1",
        working_directory=Path("/tmp"),
        request=_make_request(),
    )
    assert result.decision is AcpPermissionDecision.ESCALATE


@pytest.mark.anyio
async def test_evaluator_llm_escalate_unattended_returns_reject() -> None:
    # CURRENT BEHAVIOR: UNATTENDED → REJECT for escalate. This is correct behavior —
    # unattended mode should not block for human escalation.
    evaluator = _make_evaluator(
        llm_decision="escalate", involvement_level=InvolvementLevel.UNATTENDED
    )
    result = await evaluator.evaluate(
        operation_id="op-1",
        working_directory=Path("/tmp"),
        request=_make_request(),
    )
    assert result.decision is AcpPermissionDecision.REJECT  # Correct for UNATTENDED


@pytest.mark.anyio
async def test_evaluator_missing_operation_state_returns_reject() -> None:
    provider = _FakePermissionDecisionProvider(decision="approve")
    store = _FakeOperationStore(state=None)
    evaluator = ProviderBackedPermissionEvaluator(provider, store=store)
    result = await evaluator.evaluate(
        operation_id="op-missing",
        working_directory=Path("/tmp"),
        request=_make_request(),
    )
    assert result.decision is AcpPermissionDecision.REJECT
    assert provider.call_count == 0  # provider not called when state missing
