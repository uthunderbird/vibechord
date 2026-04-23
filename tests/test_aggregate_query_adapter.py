"""Tests for aggregate_query_adapter — Layer 3a bridge."""
from __future__ import annotations

import dataclasses

from agent_operator.application.queries.aggregate_query_adapter import (
    AggregateQueryAdapter,
    aggregate_to_state,
)
from agent_operator.domain.aggregate import OperationAggregate
from agent_operator.domain.enums import (
    AttentionStatus,
    AttentionType,
    OperationStatus,
    SchedulerState,
)
from agent_operator.domain.operation import AttentionRequest, OperationGoal
from agent_operator.domain.policy import PolicyCoverageStatus


def _make_agg(**kwargs) -> OperationAggregate:
    base = OperationAggregate.create(
        goal=OperationGoal(objective="test"),
        operation_id="op-test",
    )
    if kwargs:
        base = dataclasses.replace(base, **kwargs)
    return base


def _make_attn(**kwargs) -> AttentionRequest:
    defaults = dict(
        operation_id="op-test",
        attention_type=AttentionType.QUESTION,
        title="Q?",
        question="What?",
        blocking=True,
        status=AttentionStatus.OPEN,
    )
    defaults.update(kwargs)
    return AttentionRequest(**defaults)


def test_aggregate_to_state_preserves_status():
    agg = _make_agg(status=OperationStatus.RUNNING)
    state = aggregate_to_state(agg)
    assert state.status is OperationStatus.RUNNING


def test_aggregate_to_state_preserves_sessions():
    agg = _make_agg()
    state = aggregate_to_state(agg)
    assert isinstance(state.sessions, list)


def test_aggregate_to_state_preserves_attention_requests():
    attn = _make_attn()
    agg = _make_agg(attention_requests=[attn])
    state = aggregate_to_state(agg)
    assert len(state.attention_requests) == 1
    assert state.attention_requests[0].attention_id == attn.attention_id


def test_aggregate_to_state_preserves_operation_id():
    agg = _make_agg()
    state = aggregate_to_state(agg)
    assert state.operation_id == "op-test"


def test_aggregate_to_state_derives_policy_context_from_policy_and_goal_metadata() -> None:
    agg = OperationAggregate.create(
        goal=OperationGoal(objective="test", metadata={"policy_scope": "profile:test"}),
        operation_id="op-test",
    )

    state = aggregate_to_state(agg)

    assert state.involvement_level is agg.policy.involvement_level
    assert state.policy_coverage.project_scope == "profile:test"
    assert state.policy_coverage.status is PolicyCoverageStatus.NO_SCOPE
    assert state.active_policies == []


def test_adapter_build_status_action_hint_open_attention():
    attn = _make_attn(status=AttentionStatus.OPEN)
    agg = _make_agg(attention_requests=[attn])

    class _FakeProjection:
        pass

    adapter = AggregateQueryAdapter(_FakeProjection())
    hint = adapter.build_status_action_hint(agg)
    assert hint is not None
    assert f"operator answer op-test {attn.attention_id}" in hint


def test_adapter_build_status_action_hint_paused():
    agg = _make_agg(scheduler_state=SchedulerState.PAUSED)

    class _FakeProjection:
        pass

    adapter = AggregateQueryAdapter(_FakeProjection())
    hint = adapter.build_status_action_hint(agg)
    assert hint == "operator unpause op-test"


def test_adapter_build_status_action_hint_none_when_running():
    agg = _make_agg(status=OperationStatus.RUNNING)

    class _FakeProjection:
        pass

    adapter = AggregateQueryAdapter(_FakeProjection())
    hint = adapter.build_status_action_hint(agg)
    assert hint is None
