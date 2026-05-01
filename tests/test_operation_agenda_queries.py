from __future__ import annotations

import pytest

from agent_operator.application import (
    OperationAgendaQueryService,
    OperationFleetWorkbenchQueryService,
    OperationProjectionService,
    OperationStatusQueryService,
)
from agent_operator.domain import (
    AgentSessionHandle,
    InvolvementLevel,
    OperationCheckpoint,
    OperationGoal,
    OperationPolicy,
    OperationStatus,
    OperationSummary,
    RuntimeHints,
    SchedulerState,
    SessionRecord,
    SessionRecordStatus,
    StoredOperationDomainEvent,
)
from agent_operator.domain.operation import ObjectiveState
from agent_operator.testing.operator_service_support import (
    MemoryStore,
    MemoryTraceStore,
)


class _BackgroundInspectionStore:
    async def list_runs(self, operation_id: str) -> list:
        return []


class _Service:
    async def resume(self, operation_id: str, *, options=None, session_id=None):
        raise AssertionError("resume should not be called in agenda query tests")

    async def cancel(self, operation_id: str, *, session_id=None, run_id=None):
        raise AssertionError("cancel should not be called in agenda query tests")

    async def tick(self, operation_id: str, *, options=None):
        raise AssertionError("tick should not be called in agenda query tests")

    async def recover(self, operation_id: str, *, session_id=None, options=None):
        raise AssertionError("recover should not be called in agenda query tests")


class _ReplayState:
    def __init__(
        self,
        checkpoint: OperationCheckpoint,
        *,
        last_applied_sequence: int,
    ) -> None:
        self.checkpoint = checkpoint
        self.last_applied_sequence = last_applied_sequence
        self.suffix_events = []
        self.stored_checkpoint = object()


class _ReplayService:
    def __init__(
        self,
        checkpoint: OperationCheckpoint,
        *,
        last_applied_sequence: int,
    ) -> None:
        self._checkpoint = checkpoint
        self._last_applied_sequence = last_applied_sequence

    async def load(self, operation_id: str) -> _ReplayState:
        assert operation_id == self._checkpoint.operation_id
        return _ReplayState(
            self._checkpoint,
            last_applied_sequence=self._last_applied_sequence,
        )


class _EventStore:
    def __init__(self, events: list[StoredOperationDomainEvent]) -> None:
        self._events = list(events)

    async def load_after(
        self,
        operation_id: str,
        *,
        after_sequence: int = 0,
    ) -> list[StoredOperationDomainEvent]:
        return [
            event
            for event in self._events
            if event.operation_id == operation_id and event.sequence > after_sequence
        ]


class _ReadModelProjectionStore:
    def __init__(self, sequence: int | None) -> None:
        self._sequence = sequence

    async def load_source_event_sequence(
        self,
        operation_id: str,
        projection_type: str,
    ) -> int | None:
        assert operation_id
        assert projection_type == "status"
        return self._sequence

    def projection_lag(
        self,
        *,
        canonical_sequence: int,
        projection_sequence: int | None,
    ) -> int | None:
        if projection_sequence is None:
            return None
        return max(canonical_sequence - projection_sequence, 0)


def _operation():
    from agent_operator.domain import OperationState

    return OperationState(
        operation_id="op-1",
        goal=OperationGoal(
            objective="Ship dashboard",
            metadata={"project_profile_name": "operator", "policy_scope": "profile:operator"},
        ),
        policy=OperationPolicy(
            allowed_agents=["codex_acp"],
            involvement_level=InvolvementLevel.COLLABORATIVE,
        ),
        runtime_hints=RuntimeHints(metadata={"run_mode": "attached"}),
        status=OperationStatus.RUNNING,
        scheduler_state=SchedulerState.ACTIVE,
        involvement_level=InvolvementLevel.COLLABORATIVE,
        sessions=[
            SessionRecord(
                handle=AgentSessionHandle(
                    adapter_key="codex_acp",
                    session_id="session-1",
                    session_name="dash",
                ),
                status=SessionRecordStatus.RUNNING,
                waiting_reason="Working",
            )
        ],
    )


def _operation_with_id(operation_id: str):
    operation = _operation()
    operation.operation_id = operation_id
    return operation


def _status_queries(
    store: MemoryStore,
    *,
    replay_service: _ReplayService | None = None,
    event_store: _EventStore | None = None,
    read_model_projection_store: _ReadModelProjectionStore | None = None,
) -> OperationStatusQueryService:
    return OperationStatusQueryService(
        store=store,
        projection_service=OperationProjectionService(),
        trace_store=MemoryTraceStore(),
        background_inspection_store=_BackgroundInspectionStore(),
        wakeup_inspection_store=None,
        replay_service=replay_service,
        event_store=event_store,
        read_model_projection_store=read_model_projection_store,
        build_runtime_alert=lambda **kwargs: None,
        render_status_brief=lambda operation: "",
        render_inspect_summary=lambda operation, brief, runtime_alert=None: "",
        render_status_summary=(
            lambda operation, brief, runtime_alert=None, action_hint=None: ""
        ),
    )


class _StoreWithSummaries(MemoryStore):
    async def list_operations(self) -> list[OperationSummary]:
        operation = self.operations["op-1"]
        return [
            OperationSummary(
                operation_id=operation.operation_id,
                status=operation.status,
                objective_prompt=operation.goal.objective,
                final_summary=None,
                focus=None,
                runnable_task_count=0,
                reusable_session_count=0,
                updated_at=operation.updated_at,
            )
        ]


class _CanonicalLister:
    def __init__(self, operations: list) -> None:
        self._operations = operations

    async def list_canonical_operation_states(self) -> list:
        return self._operations


@pytest.mark.anyio
async def test_load_snapshot_filters_by_project() -> None:
    store = _StoreWithSummaries()
    await store.save_operation(_operation())
    service = OperationAgendaQueryService(store=store, status_service=_status_queries(store))

    snapshot = await service.load_snapshot(project="operator", include_recent=True)

    assert snapshot.total_operations == 1
    assert len(snapshot.active) == 1
    assert snapshot.active[0].operation_id == "op-1"


@pytest.mark.anyio
async def test_load_snapshot_uses_canonical_lister_for_event_sourced_only_operation() -> None:
    """Catches agenda enumeration using only legacy store summaries."""
    store = MemoryStore()
    operation = _operation_with_id("op-event-only-agenda")
    await store.save_operation(operation)
    service = OperationAgendaQueryService(
        store=MemoryStore(),
        status_service=_status_queries(store),
        canonical_lister=_CanonicalLister([operation]),
    )

    snapshot = await service.load_snapshot(project="operator", include_recent=True)

    assert snapshot.total_operations == 1
    assert snapshot.active[0].operation_id == "op-event-only-agenda"


@pytest.mark.anyio
async def test_load_snapshot_carries_sync_health_into_fleet_payloads() -> None:
    """Catches fleet surfaces hiding stale persisted read-model projection labels."""
    store = _StoreWithSummaries()
    await store.save_operation(_operation())
    checkpoint = OperationCheckpoint.initial("op-1")
    checkpoint.objective = ObjectiveState(objective="Ship dashboard")
    canonical_events = [
        StoredOperationDomainEvent(
            operation_id="op-1",
            sequence=1,
            event_type="operation.created",
            payload={},
        ),
        StoredOperationDomainEvent(
            operation_id="op-1",
            sequence=2,
            event_type="agent.turn.completed",
            payload={"status": "completed"},
        ),
    ]
    agenda_queries = OperationAgendaQueryService(
        store=store,
        status_service=_status_queries(
            store,
            replay_service=_ReplayService(checkpoint, last_applied_sequence=2),
            event_store=_EventStore(canonical_events),
            read_model_projection_store=_ReadModelProjectionStore(sequence=1),
        ),
    )

    snapshot = await agenda_queries.load_snapshot(project=None, include_recent=True)
    fleet_payload = OperationProjectionService().build_fleet_payload(
        snapshot,
        project=None,
    )
    workbench_payload = await OperationFleetWorkbenchQueryService(
        agenda_queries=agenda_queries,
        projection_service=OperationProjectionService(),
    ).load_payload(project=None, include_recent=True)

    sync_health = snapshot.active[0].sync_health
    assert sync_health is not None
    assert sync_health["persisted_read_model_projection_sequence"] == 1
    assert sync_health["persisted_read_model_projection_lag"] == 1
    assert fleet_payload["active"][0]["sync_health"] == sync_health
    assert workbench_payload["rows"][0]["sync_health"] == sync_health
