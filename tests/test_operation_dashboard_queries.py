from __future__ import annotations

import pytest

from agent_operator.application import (
    OperationDashboardQueryService,
    OperationDeliveryCommandService,
    OperationProjectionService,
)
from agent_operator.domain import (
    AgentSessionHandle,
    InvolvementLevel,
    OperationGoal,
    OperationPolicy,
    OperationState,
    OperationStatus,
    RuntimeHints,
    SchedulerState,
    SessionRecord,
    SessionRecordStatus,
)
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
    )


def _delivery(store: MemoryStore, inbox: MemoryCommandInbox) -> OperationDeliveryCommandService:
    return OperationDeliveryCommandService(
        store=store,
        command_inbox=inbox,
        projection_service=OperationProjectionService(),
        trace_store=MemoryTraceStore(),
        background_inspection_store=_BackgroundInspectionStore(),
        wakeup_inspection_store=None,
        service_factory=lambda: _Service(),
        overlay_live_background_progress=lambda operation, runs: operation,
        build_runtime_alert=lambda **kwargs: None,
        render_status_brief=lambda operation: "",
        render_inspect_summary=lambda operation, brief, runtime_alert=None: "",
        find_task_by_display_id=lambda operation, task_id: None,
    )


@pytest.mark.anyio
async def test_load_payload_builds_dashboard_payload() -> None:
    store = MemoryStore()
    inbox = MemoryCommandInbox()
    await store.save_operation(_operation())
    service = OperationDashboardQueryService(
        status_service=_delivery(store, inbox),
        projection_service=OperationProjectionService(),
        command_inbox=inbox,
        event_reader=_EventReader(),
        build_upstream_transcript=lambda operation: {"title": "Codex Log", "events": ["line"]},
    )

    payload = await service.load_payload("op-1")

    assert payload["operation_id"] == "op-1"
    assert payload["status"] == "running"
    assert payload["upstream_transcript"]["title"] == "Codex Log"
