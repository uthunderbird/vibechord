from __future__ import annotations

import pytest

from agent_operator.application import (
    OperationAgendaQueryService,
    OperationDeliveryCommandService,
    OperationProjectionService,
)
from agent_operator.domain import (
    AgentSessionHandle,
    InvolvementLevel,
    OperationGoal,
    OperationPolicy,
    OperationStatus,
    OperationSummary,
    RuntimeHints,
    SchedulerState,
    SessionRecord,
    SessionRecordStatus,
)
from agent_operator.testing.operator_service_support import MemoryCommandInbox, MemoryStore, MemoryTraceStore


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


def _delivery(store: MemoryStore) -> OperationDeliveryCommandService:
    return OperationDeliveryCommandService(
        store=store,
        command_inbox=MemoryCommandInbox(),
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


@pytest.mark.anyio
async def test_load_snapshot_filters_by_project() -> None:
    store = _StoreWithSummaries()
    await store.save_operation(_operation())
    service = OperationAgendaQueryService(store=store, status_service=_delivery(store))

    snapshot = await service.load_snapshot(project="operator", include_recent=True)

    assert snapshot.total_operations == 1
    assert len(snapshot.active) == 1
    assert snapshot.active[0].operation_id == "op-1"
