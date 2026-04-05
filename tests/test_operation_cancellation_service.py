from __future__ import annotations

import pytest

from agent_operator.domain import OperationGoal, OperationState, OperationStatus
from agent_operator.testing.operator_service_support import (
    MemoryEventSink,
    MemoryHistoryLedger,
    MemoryStore,
    MemoryTraceStore,
    make_service,
    state_settings,
)


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
