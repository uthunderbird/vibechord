"""Tests for OperationReadModelProjector — Layer 3a."""
from __future__ import annotations

from datetime import UTC, datetime

from agent_operator.application.queries.operation_read_model_projector import (
    OperationReadModelProjector,
)
from agent_operator.domain import StoredOperationDomainEvent
from agent_operator.domain.enums import OperationStatus


def _event(
    event_type: str,
    payload: dict | None = None,
    sequence: int = 1,
) -> StoredOperationDomainEvent:
    return StoredOperationDomainEvent(
        operation_id="op-test",
        sequence=sequence,
        event_type=event_type,
        payload=payload or {},
        timestamp=datetime.now(UTC),
    )


def test_project_empty_events_returns_empty_model():
    projector = OperationReadModelProjector()
    model = projector.project("op-test", [])
    assert model.operation_id == "op-test"
    assert model.decision_records == []
    assert model.iteration_briefs == []
    assert model.agent_turn_briefs == []


def test_project_decision_event_appends_decision_record():
    projector = OperationReadModelProjector()
    event = _event(
        "brain.decision.made",
        {
            "action_type": "start_agent",
            "more_actions": False,
            "wake_cycle_id": "wc-1",
            "rationale": "Start the coding agent.",
            "target_agent": "codex_acp",
        },
    )
    model = projector.project("op-test", [event])
    assert len(model.decision_records) == 1
    record = model.decision_records[0]
    assert record.action_type == "start_agent"
    assert record.more_actions is False
    assert record.wake_cycle_id == "wc-1"
    assert len(model.iteration_briefs) == 1
    assert model.iteration_briefs[0].operator_intent_brief == "Start the coding agent."
    assert model.iteration_briefs[0].assignment_brief == "codex_acp"


def test_project_operation_created_builds_operation_brief():
    projector = OperationReadModelProjector()
    model = projector.project(
        "op-test",
        [_event("operation.created", {"objective": "Inspect repository state"})],
    )
    assert model.operation_brief is not None
    assert model.operation_brief.objective_brief == "Inspect repository state"
    assert model.operation_brief.status is OperationStatus.RUNNING


def test_project_status_change_updates_existing_operation_brief():
    projector = OperationReadModelProjector()
    model = projector.project(
        "op-test",
        [
            _event("operation.created", {"objective": "Inspect repository state"}),
            _event(
                "operation.status.changed",
                {"status": "completed", "final_summary": "All work finished."},
                sequence=2,
            ),
        ],
    )
    assert model.operation_brief is not None
    assert model.operation_brief.status is OperationStatus.COMPLETED
    assert model.operation_brief.latest_outcome_brief == "All work finished."


def test_project_agent_turn_completed_appends_agent_turn_brief():
    projector = OperationReadModelProjector()
    model = projector.project(
        "op-test",
        [
            _event(
                "agent.turn.completed",
                {
                    "session_id": "sess-1",
                    "adapter_key": "codex_acp",
                    "status": "completed",
                    "output_text": "Summarized the architecture.",
                },
            )
        ],
    )
    assert len(model.agent_turn_briefs) == 1
    brief = model.agent_turn_briefs[0]
    assert brief.session_id == "sess-1"
    assert brief.agent_key == "codex_acp"
    assert brief.result_brief == "Summarized the architecture."
    assert brief.status == "completed"


def test_project_unknown_event_is_noop():
    projector = OperationReadModelProjector()
    event = _event("operation.status.changed", {"status": "running"})
    model = projector.project("op-test", [event])
    assert model.decision_records == []
    assert model.iteration_briefs == []
