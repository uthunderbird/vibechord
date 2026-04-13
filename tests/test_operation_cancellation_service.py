from __future__ import annotations

import pytest

from agent_operator.application import OperationProjectionService, OperationStatusQueryService
from agent_operator.domain import (
    AgentSessionHandle,
    OperationGoal,
    OperationState,
    OperationStatus,
    SchedulerState,
    SessionRecord,
    SessionRecordStatus,
)
from agent_operator.testing.operator_service_support import (
    MemoryEventSink,
    MemoryHistoryLedger,
    MemoryStore,
    MemoryTraceStore,
    make_service,
    state_settings,
)


class _BackgroundInspectionStore:
    async def list_runs(self, operation_id: str) -> list:
        return []


@pytest.mark.anyio
async def test_cancel_appends_history_ledger_for_whole_operation_cancel() -> None:
    store = MemoryStore()
    history = MemoryHistoryLedger()
    state = OperationState(
        operation_id="op-cancel-ledger",
        goal=OperationGoal(objective="Cancel me."),
        **state_settings(),
    )
    await store.save_operation(state)
    service = make_service(
        brain=object(),
        store=store,
        trace_store=MemoryTraceStore(),
        event_sink=MemoryEventSink(),
        history_ledger=history,
        agent_runtime_bindings={},
    )

    outcome = await service.cancel("op-cancel-ledger")

    assert outcome.status is OperationStatus.CANCELLED
    assert len(history.entries) == 1
    recorded_state, recorded_outcome = history.entries[0]
    assert recorded_state.operation_id == "op-cancel-ledger"
    assert recorded_outcome.summary == "Operation cancelled."


@pytest.mark.anyio
async def test_whole_operation_cancel_clears_active_session_from_status_snapshot() -> None:
    store = MemoryStore()
    session = AgentSessionHandle(
        adapter_key="codex_acp",
        session_id="session-1",
        session_name="adr-slice",
    )
    state = OperationState(
        operation_id="op-cancel-status",
        goal=OperationGoal(objective="Cancel me."),
        status=OperationStatus.RUNNING,
        scheduler_state=SchedulerState.ACTIVE,
        sessions=[
            SessionRecord(
                handle=session,
                status=SessionRecordStatus.RUNNING,
                waiting_reason="Working through the next slice.",
            )
        ],
        active_session=session,
        **state_settings(),
    )
    await store.save_operation(state)
    service = make_service(
        brain=object(),
        store=store,
        trace_store=MemoryTraceStore(),
        event_sink=MemoryEventSink(),
        history_ledger=MemoryHistoryLedger(),
        agent_runtime_bindings={},
    )

    outcome = await service.cancel("op-cancel-status")
    updated = await store.load_operation("op-cancel-status")

    assert outcome.status is OperationStatus.CANCELLED
    assert updated is not None
    assert updated.status is OperationStatus.CANCELLED
    assert updated.active_session is None
    assert updated.active_session_record is None

    status_queries = OperationStatusQueryService(
        store=store,
        projection_service=OperationProjectionService(),
        trace_store=MemoryTraceStore(),
        background_inspection_store=_BackgroundInspectionStore(),
        wakeup_inspection_store=None,
        overlay_live_background_progress=lambda operation, runs: operation,
        build_runtime_alert=lambda **kwargs: None,
        render_status_brief=lambda operation: "",
        render_inspect_summary=lambda operation, brief, runtime_alert=None: "",
        render_status_summary=(
            lambda operation, brief, runtime_alert=None, action_hint=None: ""
        ),
    )
    operation, stored_outcome, _brief, runtime_alert = await status_queries.build_status_payload(
        "op-cancel-status"
    )

    assert operation is not None
    assert runtime_alert is None
    snapshot = status_queries.build_live_snapshot("op-cancel-status", operation, stored_outcome)
    assert snapshot["status"] == "cancelled"
    assert "session_id" not in snapshot
    assert "session_status" not in snapshot
    assert status_queries.build_status_action_hint(operation) is None
