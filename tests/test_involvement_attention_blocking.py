"""State-machine test matrix for attention_should_block across all InvolvementLevel values.

Tests marked with # BUG document behavior that is wrong and should change.
"""

from __future__ import annotations

from agent_operator.application.commands.operation_attention import OperationAttentionCoordinator
from agent_operator.domain import (
    AttentionType,
    InvolvementLevel,
    OperationGoal,
    OperationState,
)


def _state(level: InvolvementLevel) -> OperationState:
    return OperationState(goal=OperationGoal(objective="test"), involvement_level=level)


def _blocks(level: InvolvementLevel, attention_type: AttentionType) -> bool:
    return OperationAttentionCoordinator().attention_should_block(_state(level), attention_type)


# ---------------------------------------------------------------------------
# UNATTENDED — should only block for hard-stop conditions, not routine attention
# ---------------------------------------------------------------------------


def test_attention_blocking_unattended_question_is_not_blocking() -> None:
    assert _blocks(InvolvementLevel.UNATTENDED, AttentionType.QUESTION) is False


def test_attention_blocking_unattended_policy_gap_is_not_blocking() -> None:
    assert _blocks(InvolvementLevel.UNATTENDED, AttentionType.POLICY_GAP) is False


def test_attention_blocking_unattended_novel_fork_is_not_blocking() -> None:
    assert _blocks(InvolvementLevel.UNATTENDED, AttentionType.NOVEL_STRATEGIC_FORK) is False


def test_attention_blocking_unattended_approval_request_is_blocking() -> None:
    # CURRENT BEHAVIOR: APPROVAL_REQUEST blocks even in UNATTENDED mode.
    # This is arguably correct (hard stops should still stop), but it contradicts
    # ADR 0017's "prefer defer-and-continue" rule for unattended.
    # Documenting as current behavior; revisit when fixing permission path.
    assert _blocks(InvolvementLevel.UNATTENDED, AttentionType.APPROVAL_REQUEST) is True


def test_attention_blocking_unattended_blocked_external_dep_is_blocking() -> None:
    # CURRENT BEHAVIOR: same class as APPROVAL_REQUEST — always blocks.
    assert _blocks(InvolvementLevel.UNATTENDED, AttentionType.BLOCKED_EXTERNAL_DEPENDENCY) is True


def test_attention_blocking_unattended_document_update_is_not_blocking() -> None:
    assert _blocks(InvolvementLevel.UNATTENDED, AttentionType.DOCUMENT_UPDATE_PROPOSAL) is False


# ---------------------------------------------------------------------------
# AUTO — should block for novel/policy situations, not for routine questions
# ---------------------------------------------------------------------------


def test_attention_blocking_auto_question_is_blocking() -> None:
    assert _blocks(InvolvementLevel.AUTO, AttentionType.QUESTION) is True


def test_attention_blocking_auto_policy_gap_is_blocking() -> None:
    assert _blocks(InvolvementLevel.AUTO, AttentionType.POLICY_GAP) is True


def test_attention_blocking_auto_novel_fork_is_blocking() -> None:
    assert _blocks(InvolvementLevel.AUTO, AttentionType.NOVEL_STRATEGIC_FORK) is True


def test_attention_blocking_auto_approval_request_is_blocking() -> None:
    assert _blocks(InvolvementLevel.AUTO, AttentionType.APPROVAL_REQUEST) is True


def test_attention_blocking_auto_blocked_external_dep_is_blocking() -> None:
    assert _blocks(InvolvementLevel.AUTO, AttentionType.BLOCKED_EXTERNAL_DEPENDENCY) is True


# ---------------------------------------------------------------------------
# COLLABORATIVE — same blocking behavior as AUTO (more eager, not less)
# ---------------------------------------------------------------------------


def test_attention_blocking_collaborative_question_is_blocking() -> None:
    assert _blocks(InvolvementLevel.COLLABORATIVE, AttentionType.QUESTION) is True


def test_attention_blocking_collaborative_policy_gap_is_blocking() -> None:
    assert _blocks(InvolvementLevel.COLLABORATIVE, AttentionType.POLICY_GAP) is True


def test_attention_blocking_collaborative_novel_fork_is_blocking() -> None:
    assert _blocks(InvolvementLevel.COLLABORATIVE, AttentionType.NOVEL_STRATEGIC_FORK) is True


def test_attention_blocking_collaborative_approval_request_is_blocking() -> None:
    assert _blocks(InvolvementLevel.COLLABORATIVE, AttentionType.APPROVAL_REQUEST) is True


# ---------------------------------------------------------------------------
# APPROVAL_HEAVY — everything blocks
# ---------------------------------------------------------------------------


def test_attention_blocking_approval_heavy_question_is_blocking() -> None:
    assert _blocks(InvolvementLevel.APPROVAL_HEAVY, AttentionType.QUESTION) is True


def test_attention_blocking_approval_heavy_policy_gap_is_blocking() -> None:
    assert _blocks(InvolvementLevel.APPROVAL_HEAVY, AttentionType.POLICY_GAP) is True


def test_attention_blocking_approval_heavy_novel_fork_is_blocking() -> None:
    assert _blocks(InvolvementLevel.APPROVAL_HEAVY, AttentionType.NOVEL_STRATEGIC_FORK) is True


def test_attention_blocking_approval_heavy_approval_request_is_blocking() -> None:
    assert _blocks(InvolvementLevel.APPROVAL_HEAVY, AttentionType.APPROVAL_REQUEST) is True


def test_attention_blocking_approval_heavy_document_update_is_blocking() -> None:
    assert _blocks(InvolvementLevel.APPROVAL_HEAVY, AttentionType.DOCUMENT_UPDATE_PROPOSAL) is True
