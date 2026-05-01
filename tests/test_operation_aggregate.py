"""Unit tests for OperationAggregate — v2 domain aggregate (ADR 0193)."""
from __future__ import annotations

from datetime import UTC, datetime

from agent_operator.domain.aggregate import OperationAggregate
from agent_operator.domain.enums import OperationStatus, SchedulerState
from agent_operator.domain.event_sourcing import StoredOperationDomainEvent
from agent_operator.domain.operation import OperationGoal, OperationPolicy

# ── Helpers ────────────────────────────────────────────────────────────────────


def _goal(objective: str = "Test the system") -> OperationGoal:
    return OperationGoal(objective=objective)


def _event(event_type: str, payload: dict | None = None) -> StoredOperationDomainEvent:
    return StoredOperationDomainEvent(
        operation_id="op-test",
        sequence=1,
        event_type=event_type,
        payload=payload or {},
        timestamp=datetime.now(UTC),
    )


# ── create() ──────────────────────────────────────────────────────────────────


def test_create_initialises_defaults() -> None:
    agg = OperationAggregate.create(_goal())

    assert agg.status == OperationStatus.RUNNING
    assert agg.scheduler_state == SchedulerState.ACTIVE
    assert agg.tasks == []
    assert agg.sessions == []
    assert agg.operator_messages == []
    assert agg.processed_command_ids == []
    assert agg.pending_replan_command_ids == []
    assert agg.pending_attention_resolution_ids == []
    assert agg.current_focus is None
    assert agg.final_summary is None
    assert not hasattr(agg, "active_policies")
    assert not hasattr(agg, "policy_coverage")
    assert not hasattr(agg, "involvement_level")


def test_create_sets_objective_from_goal() -> None:
    agg = OperationAggregate.create(_goal("Build a rocket"))
    assert agg.objective is not None
    assert agg.objective.objective == "Build a rocket"


def test_create_copies_policy_allowed_agents() -> None:
    policy = OperationPolicy(allowed_agents=["agent-a", "agent-b"])
    agg = OperationAggregate.create(_goal(), policy=policy)
    assert agg.allowed_agents == ["agent-a", "agent-b"]


def test_create_uses_provided_operation_id() -> None:
    agg = OperationAggregate.create(_goal(), operation_id="op-fixed")
    assert agg.operation_id == "op-fixed"


# ── apply_events() immutability ────────────────────────────────────────────────


def test_apply_events_returns_new_instance() -> None:
    agg = OperationAggregate.create(_goal())
    event = _event("operation.status.changed", {"status": "completed", "final_summary": "Done"})

    new_agg = agg.apply_events([event])

    assert new_agg is not agg
    assert agg.status == OperationStatus.RUNNING  # original unchanged
    assert new_agg.status == OperationStatus.COMPLETED


def test_apply_empty_events_returns_same_object() -> None:
    agg = OperationAggregate.create(_goal())
    result = agg.apply_events([])
    assert result is agg


def test_apply_unknown_event_is_noop() -> None:
    agg = OperationAggregate.create(_goal())
    event = _event("totally.unknown.event.type", {"some": "data"})
    result = agg.apply_events([event])
    # Should not raise and should return same logical state
    assert result.status == agg.status
    assert result.scheduler_state == agg.scheduler_state


# ── operation slice ────────────────────────────────────────────────────────────


def test_status_changes_via_event() -> None:
    agg = OperationAggregate.create(_goal())
    event = _event("operation.status.changed", {"status": "failed", "final_summary": "Oops"})

    result = agg.apply_events([event])

    assert result.status == OperationStatus.FAILED
    assert result.final_summary == "Oops"


def test_allowed_agents_updated_via_event() -> None:
    agg = OperationAggregate.create(_goal())
    event = _event("operation.allowed_agents.updated", {"allowed_agents": ["claude", "codex"]})

    result = agg.apply_events([event])

    assert result.allowed_agents == ["claude", "codex"]


def test_involvement_level_update_rewrites_policy_not_aggregate_shadow() -> None:
    agg = OperationAggregate.create(_goal(), policy=OperationPolicy(involvement_level="auto"))
    event = _event("operation.involvement_level.updated", {"involvement_level": "unattended"})

    result = agg.apply_events([event])

    assert result.policy.involvement_level.value == "unattended"
    assert not hasattr(result, "involvement_level")


def test_operation_created_updates_policy_budget_and_runtime_hints() -> None:
    agg = OperationAggregate.create(_goal())
    event = _event(
        "operation.created",
        {
            "objective": "Focused objective",
            "allowed_agents": ["codex_acp"],
            "involvement_level": "auto",
            "policy": {
                "allowed_agents": ["codex_acp"],
                "involvement_level": "auto",
            },
            "execution_budget": {"max_iterations": 3},
            "runtime_hints": {"operator_message_window": 7},
        },
    )

    result = agg.apply_events([event])

    assert result.policy.allowed_agents == ["codex_acp"]
    assert result.execution_budget.max_iterations == 3
    assert result.runtime_hints.operator_message_window == 7

# ── session slice ──────────────────────────────────────────────────────────────


def test_session_registered_via_event() -> None:
    from agent_operator.domain.agent import AgentSessionHandle
    from agent_operator.domain.enums import SessionObservedState, SessionStatus

    agg = OperationAggregate.create(_goal())
    handle = AgentSessionHandle(adapter_key="claude", session_id="sess-1")
    event = _event(
        "session.created",
        {
            "handle": handle.model_dump(),
            "observed_state": SessionObservedState.IDLE.value,
            "status": SessionStatus.IDLE.value,
        },
    )

    result = agg.apply_events([event])

    assert len(result.sessions) == 1
    assert result.sessions[0].handle.session_id == "sess-1"
    assert result.sessions[0].status is SessionStatus.IDLE
    assert "observed_state" not in result.sessions[0].model_dump()
    assert "terminal_state" not in result.sessions[0].model_dump()


# ── coordination state ────────────────────────────────────────────────────────


def test_processed_command_ids_accumulates() -> None:
    agg = OperationAggregate.create(_goal())
    e1 = _event("command.processed", {"command_id": "cmd-1"})
    e2 = _event("command.processed", {"command_id": "cmd-2"})

    result = agg.apply_events([e1, e2])

    assert "cmd-1" in result.processed_command_ids
    assert "cmd-2" in result.processed_command_ids


def test_processed_command_ids_deduplicates() -> None:
    agg = OperationAggregate.create(_goal())
    e1 = _event("command.processed", {"command_id": "cmd-1"})
    e2 = _event("command.processed", {"command_id": "cmd-1"})

    result = agg.apply_events([e1, e2])

    assert result.processed_command_ids.count("cmd-1") == 1


def test_pending_replan_scheduled_and_consumed() -> None:
    agg = OperationAggregate.create(_goal())
    scheduled = _event("replan.scheduled", {"command_id": "cmd-r"})
    consumed = _event("replan.consumed", {"command_id": "cmd-r"})

    after_schedule = agg.apply_events([scheduled])
    assert "cmd-r" in after_schedule.pending_replan_command_ids

    after_consume = after_schedule.apply_events([consumed])
    assert "cmd-r" not in after_consume.pending_replan_command_ids


def test_attention_answer_queued_and_consumed() -> None:
    agg = OperationAggregate.create(_goal())
    queued = _event("attention.answer.queued", {"request_id": "req-1"})
    consumed = _event("attention.answer.consumed", {"request_id": "req-1"})

    after_queue = agg.apply_events([queued])
    assert "req-1" in after_queue.pending_attention_resolution_ids

    after_consume = after_queue.apply_events([consumed])
    assert "req-1" not in after_consume.pending_attention_resolution_ids


# ── scheduler slice ───────────────────────────────────────────────────────────


def test_scheduler_state_changes_via_event() -> None:
    agg = OperationAggregate.create(_goal())
    event = _event("scheduler.state.changed", {"scheduler_state": "paused"})

    result = agg.apply_events([event])

    assert result.scheduler_state == SchedulerState.PAUSED


def test_parked_execution_clears_when_matching_wake_predicate_fires() -> None:
    """Catches the mutation where wake predicates are recorded but never evaluated."""
    agg = OperationAggregate.create(_goal()).apply_events(
        [
            _event(
                "operation.parked.updated",
                {
                    "parked_execution": {
                        "kind": "dependency_barrier",
                        "fingerprint": "dependency_barrier:task-1:codex_acp:runtime",
                        "reason": "Runtime health must change.",
                        "wake_predicates": ["runtime_health_changed"],
                    }
                },
            )
        ]
    )

    result = agg.apply_events(
        [
            _event(
                "execution.observed_state.changed",
                {"execution_id": "run-1", "observed_state": "completed"},
            )
        ]
    )

    assert result.parked_execution is None


def test_parked_execution_ignores_unrelated_events() -> None:
    """Catches the mutation where any event wakes a parked operation."""
    agg = OperationAggregate.create(_goal()).apply_events(
        [
            _event(
                "operation.parked.updated",
                {
                    "parked_execution": {
                        "kind": "dependency_barrier",
                        "fingerprint": "dependency_barrier:task-1:codex_acp:human",
                        "reason": "A human answer is required.",
                        "wake_predicates": ["human_answered"],
                    }
                },
            )
        ]
    )

    result = agg.apply_events(
        [_event("operator_message.received", {"message_id": "msg-1", "text": "FYI"})]
    )

    assert result.parked_execution is not None


def test_parked_execution_update_is_not_self_cleared() -> None:
    """Catches the mutation where recording parked state clears itself immediately."""
    agg = OperationAggregate.create(_goal())

    result = agg.apply_events(
        [
            _event(
                "operation.parked.updated",
                {
                    "parked_execution": {
                        "kind": "runtime_drained",
                        "fingerprint": "runtime_drained:op-test",
                        "reason": "Runtime drained.",
                        "wake_predicates": ["operator_resumed"],
                    }
                },
            )
        ]
    )

    assert result.parked_execution is not None
    assert result.parked_execution.kind == "runtime_drained"


def test_parked_execution_clears_when_operator_resumes() -> None:
    """Catches the mutation where operator_resumed ignores scheduler state changes."""
    agg = OperationAggregate.create(_goal()).apply_events(
        [
            _event(
                "operation.parked.updated",
                {
                    "parked_execution": {
                        "kind": "runtime_drained",
                        "fingerprint": "runtime_drained:op-test",
                        "reason": "Runtime drained.",
                        "wake_predicates": ["operator_resumed"],
                    }
                },
            ),
            _event("scheduler.state.changed", {"scheduler_state": "paused"}),
        ]
    )

    assert agg.parked_execution is not None

    result = agg.apply_events(
        [_event("scheduler.state.changed", {"scheduler_state": "active"})]
    )

    assert result.parked_execution is None


# ── operator message slice ────────────────────────────────────────────────────


def test_operator_message_appended_via_event() -> None:
    agg = OperationAggregate.create(_goal())
    event = _event(
        "operator_message.received",
        {"message_id": "msg-1", "text": "Hello", "submitted_at": datetime.now(UTC).isoformat()},
    )

    result = agg.apply_events([event])

    assert len(result.operator_messages) == 1
    assert result.operator_messages[0].message_id == "msg-1"


def test_operator_messages_capped_at_50() -> None:
    agg = OperationAggregate.create(_goal())
    events = [
        _event(
            "operator_message.received",
            {
                "message_id": f"msg-{i}",
                "text": f"Message {i}",
                "submitted_at": datetime.now(UTC).isoformat(),
            },
        )
        for i in range(55)
    ]

    result = agg.apply_events(events)

    assert len(result.operator_messages) == 50
    # Should keep the most recent 50
    assert result.operator_messages[-1].message_id == "msg-54"


def test_policy_cache_events_are_ignored_by_aggregate() -> None:
    agg = OperationAggregate.create(_goal())

    result = agg.apply_events(
        [
            _event("policy.coverage.updated", {"status": "covered"}),
            _event("policy.active_set.updated", {"policies": [{"policy_id": "p-1"}]}),
        ]
    )

    assert result == agg
    assert not hasattr(result, "policy_coverage")
    assert not hasattr(result, "active_policies")
