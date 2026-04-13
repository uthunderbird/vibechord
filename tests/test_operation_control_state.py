from __future__ import annotations

from pathlib import Path

import pytest

from agent_operator.application import (
    EventSourcedCommandApplicationService,
    LoadedOperation,
    OperationControlStateCoordinator,
    OperationRuntimeContext,
    OperationTraceabilityService,
)
from agent_operator.application.attached_session_registry import AttachedSessionManager
from agent_operator.application.event_sourcing.event_sourced_birth import (
    EventSourcedOperationBirthService,
)
from agent_operator.application.event_sourcing.event_sourced_replay import EventSourcedReplayService
from agent_operator.domain import OperationGoal, OperationState
from agent_operator.projectors import DefaultOperationProjector
from agent_operator.runtime import FileOperationCheckpointStore, FileOperationEventStore
from agent_operator.testing.operator_service_support import (
    MemoryStore,
    MemoryTraceStore,
    state_settings,
)


class _CountingMemoryStore(MemoryStore):
    def __init__(self) -> None:
        super().__init__()
        self.save_calls = 0

    async def save_operation(self, state) -> None:  # type: ignore[no-untyped-def]
        self.save_calls += 1
        await super().save_operation(state)


@pytest.mark.anyio
async def test_legacy_command_effect_persistence_path_uses_canonical_append(
    tmp_path: Path,
) -> None:
    store = _CountingMemoryStore()
    trace_store = MemoryTraceStore()
    event_store = FileOperationEventStore(tmp_path / "events")
    checkpoint_store = FileOperationCheckpointStore(tmp_path / "checkpoints")
    projector = DefaultOperationProjector()
    birth_service = EventSourcedOperationBirthService(
        event_store=event_store,
        checkpoint_store=checkpoint_store,
        projector=projector,
    )
    replay_service = EventSourcedReplayService(
        event_store=event_store,
        checkpoint_store=checkpoint_store,
        projector=projector,
    )
    loaded_operation = LoadedOperation(attached_session_registry=AttachedSessionManager({}))
    runtime_context = OperationRuntimeContext(
        loaded_operation=loaded_operation,
        attached_session_registry=AttachedSessionManager({}),
    )
    traceability_service = OperationTraceabilityService(
        loaded_operation=loaded_operation,
        trace_store=trace_store,
        runtime_context=runtime_context,
    )
    control_state = OperationControlStateCoordinator(
        store=store,
        traceability_service=traceability_service,
        event_sourced_command_service=EventSourcedCommandApplicationService(
            event_store=event_store,
            checkpoint_store=checkpoint_store,
            projector=projector,
        ),
    )
    operation = OperationState(
        operation_id="op-legacy-command-effect-path",
        goal=OperationGoal(objective="persist legacy command-effect state canonically"),
        **state_settings(allowed_agents=["claude_acp"]),
    )
    await store.save_operation(operation)
    await birth_service.birth(operation)
    save_calls_after_birth = store.save_calls
    previous_updated_at = operation.updated_at

    await control_state.persist_legacy_snapshot_command_effect_state(operation)

    assert store.save_calls == save_calls_after_birth
    assert operation.updated_at >= previous_updated_at
    events = await event_store.load_after(operation.operation_id, after_sequence=0)
    assert [event.event_type for event in events] == [
        "operation.created",
        "operation.control_state.synced",
    ]
    replayed = await replay_service.load(operation.operation_id)
    assert replayed.last_applied_sequence == 2
    assert replayed.checkpoint.updated_at == operation.updated_at
