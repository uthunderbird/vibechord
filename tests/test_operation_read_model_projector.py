"""Tests for OperationReadModelProjector — Layer 3a."""
from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from agent_operator.application.queries.operation_read_model_projector import (
    OperationReadModelProjectionWriter,
    OperationReadModelProjector,
)
from agent_operator.domain import OperationDomainEventDraft, StoredOperationDomainEvent
from agent_operator.domain.enums import OperationStatus
from agent_operator.runtime import FileOperationEventStore, FileReadModelProjectionStore


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


def test_project_operation_created_accepts_nested_objective_payload():
    """Catches only accepting string objective payloads in operation.created."""
    projector = OperationReadModelProjector()
    model = projector.project(
        "op-test",
        [
            _event(
                "operation.created",
                {
                    "objective": {"objective": "Inspect nested repository state"},
                    "allowed_agents": ["codex_acp"],
                    "created_at": "2026-04-03T12:34:00+00:00",
                },
            )
        ],
    )

    assert model.operation_brief is not None
    assert model.operation_brief.objective_brief == "Inspect nested repository state"


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


@pytest.mark.anyio
async def test_read_model_projection_writer_persists_event_cursor_and_payload(
    tmp_path: Path,
) -> None:
    """Catches refreshing cached projections without advancing the event cursor."""
    operation_id = "op-projection-writer"
    event_store = FileOperationEventStore(tmp_path / "events")
    projection_store = FileReadModelProjectionStore(tmp_path / "read_models")
    await event_store.append(
        operation_id,
        0,
        [
            OperationDomainEventDraft(
                event_type="operation.created",
                payload={"objective": "Persist projection cursor"},
            ),
            OperationDomainEventDraft(
                event_type="agent.turn.completed",
                payload={
                    "session_id": "sess-1",
                    "adapter_key": "codex_acp",
                    "status": "completed",
                    "output_text": "Projection refreshed.",
                },
            ),
        ],
    )
    writer = OperationReadModelProjectionWriter(
        event_store=event_store,
        projection_store=projection_store,
        projector=OperationReadModelProjector(),
    )

    projection = await writer.refresh(operation_id)
    loaded = await projection_store.load(operation_id, "status")

    assert projection.source_event_sequence == 2
    assert loaded is not None
    assert loaded.source_event_sequence == 2
    assert loaded.projection_payload["operation_brief"]["objective_brief"] == (
        "Persist projection cursor"
    )
    assert loaded.projection_payload["agent_turn_briefs"][0]["result_brief"] == (
        "Projection refreshed."
    )
