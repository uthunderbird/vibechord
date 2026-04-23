from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from agent_operator.application.event_sourcing.event_sourced_replay import EventSourcedReplayService
from agent_operator.domain import (
    AttentionRequest,
    AttentionType,
    ExecutionProfileOverride,
    ObjectiveState,
    OperationCheckpoint,
    OperationCheckpointRecord,
    OperationDomainEventDraft,
    OperationStatus,
    SchedulerState,
)
from agent_operator.projectors import DefaultOperationProjector
from agent_operator.runtime import FileOperationCheckpointStore, FileOperationEventStore


async def _seed_event_stream(
    event_store: FileOperationEventStore,
    operation_id: str,
) -> None:
    """Seed one simple event stream for replay tests."""
    created = ObjectiveState(
        objective="Initial objective",
        harness_instructions="Initial harness",
        success_criteria=["Done"],
    )
    updated = created.model_copy(update={"objective": "Updated objective"}, deep=True)
    await event_store.append(
        operation_id,
        0,
        [
            OperationDomainEventDraft(
                event_type="operation.created",
                payload={
                    **created.model_dump(mode="json"),
                    "involvement_level": "auto",
                    "created_at": datetime(2026, 4, 3, tzinfo=UTC).isoformat(),
                },
                timestamp=datetime(2026, 4, 3, 12, 0, 0, tzinfo=UTC),
            ),
            OperationDomainEventDraft(
                event_type="objective.updated",
                payload=updated.model_dump(mode="json"),
                timestamp=datetime(2026, 4, 3, 12, 0, 1, tzinfo=UTC),
            ),
        ],
    )


@pytest.mark.anyio
async def test_event_sourced_replay_loads_from_checkpoint_plus_suffix(
    tmp_path: Path,
) -> None:
    event_store = FileOperationEventStore(tmp_path / "events")
    checkpoint_store = FileOperationCheckpointStore(tmp_path / "checkpoints")
    projector = DefaultOperationProjector()
    replay = EventSourcedReplayService(
        event_store=event_store,
        checkpoint_store=checkpoint_store,
        projector=projector,
    )
    operation_id = "op-1"
    await _seed_event_stream(event_store, operation_id)
    await checkpoint_store.save(
        OperationCheckpointRecord(
            operation_id=operation_id,
            checkpoint_payload={
                "operation_id": operation_id,
                "objective": {
                    "objective": "Initial objective",
                    "harness_instructions": "Initial harness",
                    "success_criteria": ["Done"],
                },
            },
            last_applied_sequence=1,
            checkpoint_format_version=1,
        )
    )

    state = await replay.load(operation_id)

    assert state.last_applied_sequence == 2
    assert state.suffix_events
    assert state.checkpoint.objective is not None
    assert state.checkpoint.objective.objective == "Updated objective"


@pytest.mark.anyio
async def test_event_sourced_replay_materialize_refreshes_checkpoint_from_stream(
    tmp_path: Path,
) -> None:
    event_store = FileOperationEventStore(tmp_path / "events")
    checkpoint_store = FileOperationCheckpointStore(tmp_path / "checkpoints")
    projector = DefaultOperationProjector()
    replay = EventSourcedReplayService(
        event_store=event_store,
        checkpoint_store=checkpoint_store,
        projector=projector,
    )
    operation_id = "op-2"
    await _seed_event_stream(event_store, operation_id)

    state = await replay.load(operation_id)
    record = await replay.materialize(state)

    assert record.last_applied_sequence == 2
    persisted = await checkpoint_store.load_latest(operation_id)
    assert persisted is not None
    assert persisted.last_applied_sequence == 2
    assert persisted.checkpoint_payload["objective"]["objective"] == "Updated objective"


@pytest.mark.anyio
async def test_event_sourced_replay_rejects_checkpoint_ahead_of_stream(
    tmp_path: Path,
) -> None:
    event_store = FileOperationEventStore(tmp_path / "events")
    checkpoint_store = FileOperationCheckpointStore(tmp_path / "checkpoints")
    projector = DefaultOperationProjector()
    replay = EventSourcedReplayService(
        event_store=event_store,
        checkpoint_store=checkpoint_store,
        projector=projector,
    )
    operation_id = "op-3"
    await _seed_event_stream(event_store, operation_id)
    await checkpoint_store.save(
        OperationCheckpointRecord(
            operation_id=operation_id,
            checkpoint_payload={"operation_id": operation_id},
            last_applied_sequence=3,
            checkpoint_format_version=1,
        )
    )

    with pytest.raises(ValueError, match="ahead of stream"):
        await replay.load(operation_id)


@pytest.mark.anyio
async def test_event_sourced_replay_ignores_incompatible_checkpoint_format(
    tmp_path: Path,
) -> None:
    event_store = FileOperationEventStore(tmp_path / "events")
    checkpoint_store = FileOperationCheckpointStore(tmp_path / "checkpoints")
    replay = EventSourcedReplayService(
        event_store=event_store,
        checkpoint_store=checkpoint_store,
        projector=DefaultOperationProjector(),
    )
    operation_id = "op-incompatible-checkpoint"
    await _seed_event_stream(event_store, operation_id)
    await checkpoint_store.save(
        OperationCheckpointRecord(
            operation_id=operation_id,
            checkpoint_payload={"operation_id": operation_id, "status": "failed"},
            last_applied_sequence=2,
            checkpoint_format_version=2,
        )
    )

    state = await replay.load(operation_id)

    assert state.stored_checkpoint is not None
    assert state.stored_checkpoint.checkpoint_format_version == 2
    assert state.last_applied_sequence == 2
    assert len(state.suffix_events) == 2
    assert state.checkpoint.objective is not None
    assert state.checkpoint.objective.objective == "Updated objective"


@pytest.mark.anyio
async def test_event_sourced_replay_load_aggregate_starts_from_checkpoint_truth(
    tmp_path: Path,
) -> None:
    """Catches rebuilding v2 drive aggregates from a blank operation instead of checkpoint truth."""
    event_store = FileOperationEventStore(tmp_path / "events")
    checkpoint_store = FileOperationCheckpointStore(tmp_path / "checkpoints")
    replay = EventSourcedReplayService(
        event_store=event_store,
        checkpoint_store=checkpoint_store,
        projector=DefaultOperationProjector(),
    )
    operation_id = "op-aggregate-checkpoint"
    checkpoint = OperationCheckpoint.initial(operation_id)
    checkpoint.objective = ObjectiveState(
        objective="Checkpoint objective",
        harness_instructions="Checkpoint harness",
        metadata={"policy_scope": "profile:repo"},
    )
    checkpoint.status = OperationStatus.NEEDS_HUMAN
    checkpoint.scheduler_state = SchedulerState.PAUSED
    checkpoint.allowed_agents = ["codex_acp"]
    checkpoint.execution_profile_overrides = {
        "codex_acp": ExecutionProfileOverride(
            adapter_key="codex_acp",
            model="gpt-5.4-mini",
            reasoning_effort="medium",
        )
    }
    checkpoint.attention_requests = [
        AttentionRequest(
            operation_id=operation_id,
            attention_type=AttentionType.APPROVAL_REQUEST,
            title="Permission required",
            question="Approve?",
            blocking=True,
        )
    ]
    await checkpoint_store.save(
        OperationCheckpointRecord(
            operation_id=operation_id,
            checkpoint_payload=checkpoint.model_dump(mode="json"),
            last_applied_sequence=0,
            checkpoint_format_version=1,
        )
    )

    agg, last_sequence, epoch_id = await replay.load_aggregate(operation_id)

    assert last_sequence == 0
    assert epoch_id == 0
    assert agg.operation_id == operation_id
    assert agg.goal.objective == "Checkpoint objective"
    assert agg.goal.harness_instructions == "Checkpoint harness"
    assert agg.goal.metadata["policy_scope"] == "profile:repo"
    assert agg.status is OperationStatus.NEEDS_HUMAN
    assert agg.scheduler_state is SchedulerState.PAUSED
    assert agg.allowed_agents == ["codex_acp"]
    assert agg.policy.allowed_agents == ["codex_acp"]
    assert agg.execution_profile_overrides["codex_acp"].model == "gpt-5.4-mini"
    assert len(agg.attention_requests) == 1
    assert agg.attention_requests[0].title == "Permission required"
