from __future__ import annotations

import pytest

from agent_operator.application import (
    OperationDashboardQueryService,
    OperationProjectionService,
    OperationStatusQueryService,
)
from agent_operator.domain import (
    AgentSessionHandle,
    DecisionMemo,
    InvolvementLevel,
    MemoryEntry,
    MemoryFreshness,
    MemoryScope,
    OperationBrief,
    OperationCheckpoint,
    OperationGoal,
    OperationPolicy,
    OperationState,
    OperationStatus,
    RuntimeHints,
    SchedulerState,
    SessionRecord,
    SessionRecordStatus,
    StoredOperationDomainEvent,
    TaskState,
)
from agent_operator.domain.operation import ObjectiveState
from agent_operator.testing.operator_service_support import (
    MemoryCommandInbox,
    MemoryStore,
    MemoryTraceStore,
)


class _BackgroundInspectionStore:
    async def list_runs(self, operation_id: str) -> list:
        return []


class _EventReader:
    def read_events(self, operation_id: str) -> list:
        return []


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


class _Service:
    async def resume(self, operation_id: str, *, options=None, session_id=None):
        raise AssertionError("resume should not be called in dashboard query tests")

    async def cancel(self, operation_id: str, *, session_id=None, run_id=None):
        raise AssertionError("cancel should not be called in dashboard query tests")

    async def tick(self, operation_id: str, *, options=None):
        raise AssertionError("tick should not be called in dashboard query tests")

    async def recover(self, operation_id: str, *, session_id=None, options=None):
        raise AssertionError("recover should not be called in dashboard query tests")


def _operation() -> OperationState:
    return OperationState(
        operation_id="op-1",
        goal=OperationGoal(objective="Ship dashboard"),
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
        tasks=[
            TaskState(
                task_id="task-1",
                task_short_id="abcd1234",
                title="Build the task board",
                goal="Render the operation task board.",
                definition_of_done="Task board visible in TUI.",
                linked_session_id="session-1",
                assigned_agent="codex_acp",
            )
        ],
        memory_entries=[
            MemoryEntry(
                memory_id="mem-1",
                scope=MemoryScope.TASK,
                scope_id="task-1",
                summary="Remember the task board layout.",
                freshness=MemoryFreshness.CURRENT,
            )
        ],
    )


def _status_queries(
    store: MemoryStore,
    trace_store: MemoryTraceStore | None = None,
    replay_service: _ReplayService | None = None,
    event_store: _EventStore | None = None,
    read_model_projection_store: _ReadModelProjectionStore | None = None,
) -> OperationStatusQueryService:
    trace_store = trace_store or MemoryTraceStore()
    return OperationStatusQueryService(
        store=store,
        projection_service=OperationProjectionService(),
        trace_store=trace_store,
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


@pytest.mark.anyio
async def test_load_payload_builds_dashboard_payload() -> None:
    store = MemoryStore()
    inbox = MemoryCommandInbox()
    trace_store = MemoryTraceStore()
    await store.save_operation(_operation())
    await trace_store.save_decision_memo(
        "op-1",
        DecisionMemo(
            operation_id="op-1",
            iteration=2,
            task_id="task-1",
            decision_context_summary="Task selected for execution.",
            chosen_action="start_agent",
            rationale="Need implementation progress.",
        ),
    )
    await trace_store.save_operation_brief(
        OperationBrief(
            operation_id="op-1",
            status=OperationStatus.RUNNING,
            objective_brief="Ship dashboard",
            focus_brief="Build the task board",
            latest_outcome_brief="Running task-board migration",
            blocker_brief="awaiting policy review",
            runtime_alert_brief="needs policy confirmation",
        ),
    )
    service = OperationDashboardQueryService(
        status_service=_status_queries(store, trace_store),
        projection_service=OperationProjectionService(),
        command_inbox=inbox,
        event_reader=_EventReader(),
        trace_store=trace_store,
        build_upstream_transcript=lambda operation: {"title": "Codex Log", "events": ["line"]},
    )

    payload = await service.load_payload("op-1")

    assert payload["operation_id"] == "op-1"
    assert payload["status"] == "running"
    assert payload["upstream_transcript"]["title"] == "Codex Log"
    assert payload["tasks"][0]["goal"] == "Render the operation task board."
    assert payload["memory_entries"][0]["memory_id"] == "mem-1"
    assert payload["decision_memos"][0]["chosen_action"] == "start_agent"
    operation_brief = payload["operation_brief"]
    assert isinstance(operation_brief, dict)
    assert operation_brief["goal"] == "Ship dashboard"
    assert operation_brief["now"] == "Build the task board"
    assert operation_brief["wait"] == "needs policy confirmation"
    assert operation_brief["agent_activity"] == "codex_acp active session"
    assert operation_brief["operator_state"] is None
    progress = operation_brief["progress"]
    assert isinstance(progress, dict)
    assert progress["doing"] == "Running task-board migration"
    assert operation_brief["attention"] == ""


@pytest.mark.anyio
async def test_load_payload_uses_derived_brief_payload_without_operation_brief_model_dump(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = MemoryStore()
    inbox = MemoryCommandInbox()
    trace_store = MemoryTraceStore()
    await store.save_operation(_operation())
    await trace_store.save_operation_brief(
        OperationBrief(
            operation_id="op-1",
            status=OperationStatus.RUNNING,
            objective_brief="Ship dashboard",
            focus_brief="Build the task board",
        )
    )
    service = OperationDashboardQueryService(
        status_service=_status_queries(store, trace_store),
        projection_service=OperationProjectionService(),
        command_inbox=inbox,
        event_reader=_EventReader(),
        trace_store=trace_store,
        build_upstream_transcript=lambda operation: None,
    )

    def _fail_operation_brief_model_dump(self, *args, **kwargs):
        raise AssertionError(
            "dashboard query should not serialize OperationBrief directly"
        )

    monkeypatch.setattr(OperationBrief, "model_dump", _fail_operation_brief_model_dump)

    payload = await service.load_payload("op-1")

    assert payload["brief"]["objective_brief"] == "Ship dashboard"
    assert payload["brief"]["focus_brief"] == "Build the task board"


@pytest.mark.anyio
async def test_load_payload_exposes_sync_health_for_cached_projection_freshness() -> None:
    """Catches dashboard hiding stale persisted read-model projection labels."""
    store = MemoryStore()
    inbox = MemoryCommandInbox()
    trace_store = MemoryTraceStore()
    operation = _operation()
    operation.operation_id = "op-dashboard-sync"
    await store.save_operation(operation)
    checkpoint = OperationCheckpoint.initial("op-dashboard-sync")
    checkpoint.objective = ObjectiveState(objective="Ship dashboard")
    canonical_events = [
        StoredOperationDomainEvent(
            operation_id="op-dashboard-sync",
            sequence=1,
            event_type="operation.created",
            payload={},
        ),
        StoredOperationDomainEvent(
            operation_id="op-dashboard-sync",
            sequence=2,
            event_type="agent.turn.completed",
            payload={"status": "completed"},
        ),
    ]
    service = OperationDashboardQueryService(
        status_service=_status_queries(
            store,
            trace_store,
            replay_service=_ReplayService(checkpoint, last_applied_sequence=2),
            event_store=_EventStore(canonical_events),
            read_model_projection_store=_ReadModelProjectionStore(sequence=1),
        ),
        projection_service=OperationProjectionService(),
        command_inbox=inbox,
        event_reader=_EventReader(),
        trace_store=trace_store,
        build_upstream_transcript=lambda operation: None,
    )

    payload = await service.load_payload("op-dashboard-sync")

    sync_health = payload["runtime_overlay"]["sync_health"]
    assert sync_health["checkpoint_lag"] == 0
    assert sync_health["persisted_read_model_projection_sequence"] == 1
    assert sync_health["persisted_read_model_projection_lag"] == 1
    assert (
        sync_health["sync_alert"]
        == "persisted_read_model_projection_lagging_canonical_events"
    )
