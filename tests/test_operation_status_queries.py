from __future__ import annotations

import json

import pytest

from agent_operator.application import OperationProjectionService, OperationStatusQueryService
from agent_operator.domain import (
    AgentSessionHandle,
    ExecutionProfileStamp,
    OperationGoal,
    OperationState,
    OperationStatus,
    SchedulerState,
    SessionRecord,
    SessionRecordStatus,
)
from agent_operator.testing.operator_service_support import (
    MemoryStore,
    MemoryTraceStore,
    state_settings,
)


class _BackgroundInspectionStore:
    async def list_runs(self, operation_id: str) -> list:
        return []


@pytest.mark.anyio
async def test_build_live_snapshot_omits_stale_waiting_reason_when_runtime_alert_present() -> None:
    store = MemoryStore()
    state = OperationState(
        operation_id="op-status-derived",
        goal=OperationGoal(objective="Check live status."),
        status=OperationStatus.RUNNING,
        scheduler_state=SchedulerState.ACTIVE,
        sessions=[
            SessionRecord(
                handle=AgentSessionHandle(
                    adapter_key="codex_acp",
                    session_id="session-1",
                    session_name="repo-audit",
                ),
                status=SessionRecordStatus.RUNNING,
                waiting_reason="Agent session completed.",
            )
        ],
        **state_settings(),
    )
    await store.save_operation(state)

    service = OperationStatusQueryService(
        store=store,
        projection_service=OperationProjectionService(),
        trace_store=MemoryTraceStore(),
        background_inspection_store=_BackgroundInspectionStore(),
        wakeup_inspection_store=None,
        build_runtime_alert=lambda **kwargs: "2 wakeup(s) are pending reconciliation.",
        render_status_brief=lambda operation: "",
        render_inspect_summary=lambda operation, brief, runtime_alert=None: "",
        render_status_summary=(
            lambda operation, brief, runtime_alert=None, action_hint=None: ""
        ),
    )

    payload = json.loads(
        await service.render_status_output(
            "op-status-derived",
            json_mode=True,
            brief=False,
        )
    )
    snapshot = payload["summary"]

    assert snapshot["status"] == "running"
    assert snapshot["runtime_alert"] == "2 wakeup(s) are pending reconciliation."
    assert "waiting_reason" not in snapshot


@pytest.mark.anyio
async def test_build_live_snapshot_exposes_active_session_execution_profile() -> None:
    store = MemoryStore()
    state = OperationState(
        operation_id="op-status-profile",
        goal=OperationGoal(objective="Check active session model."),
        status=OperationStatus.RUNNING,
        scheduler_state=SchedulerState.ACTIVE,
        sessions=[
            SessionRecord(
                handle=AgentSessionHandle(
                    adapter_key="codex_acp",
                    session_id="session-1",
                    session_name="repo-audit",
                ),
                status=SessionRecordStatus.RUNNING,
                execution_profile_stamp=ExecutionProfileStamp(
                    adapter_key="codex_acp",
                    model="gpt-5.4-mini",
                    effort_field_name="reasoning_effort",
                    effort_value="medium",
                ),
            )
        ],
        **state_settings(),
    )
    await store.save_operation(state)

    service = OperationStatusQueryService(
        store=store,
        projection_service=OperationProjectionService(),
        trace_store=MemoryTraceStore(),
        background_inspection_store=_BackgroundInspectionStore(),
        wakeup_inspection_store=None,
        build_runtime_alert=lambda **kwargs: None,
        render_status_brief=lambda operation: "",
        render_inspect_summary=lambda operation, brief, runtime_alert=None: "",
        render_status_summary=(
            lambda operation, brief, runtime_alert=None, action_hint=None: ""
        ),
    )

    payload = json.loads(
        await service.render_status_output(
            "op-status-profile",
            json_mode=True,
            brief=False,
        )
    )
    snapshot = payload["summary"]

    assert snapshot["active_session_execution_profile"]["model"] == "gpt-5.4-mini"
    assert snapshot["active_session_execution_profile"]["effort_value"] == "medium"
    assert snapshot["session_execution_profile_known"] is True
