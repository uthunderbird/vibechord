from __future__ import annotations

import json

import pytest

from agent_operator.application import OperationProjectionService, OperationStatusQueryService
from agent_operator.domain import (
    AgentSessionHandle,
    ExecutionProfileStamp,
    OperationCheckpoint,
    OperationGoal,
    OperationState,
    OperationStatus,
    SchedulerState,
    SessionRecord,
    SessionRecordStatus,
)
from agent_operator.domain.operation import ObjectiveState
from agent_operator.testing.operator_service_support import (
    MemoryStore,
    MemoryTraceStore,
    state_settings,
)


class _BackgroundInspectionStore:
    async def list_runs(self, operation_id: str) -> list:
        return []


class _ReplayState:
    def __init__(self, checkpoint: OperationCheckpoint) -> None:
        self.checkpoint = checkpoint
        self.last_applied_sequence = 1
        self.suffix_events = []
        self.stored_checkpoint = object()


class _ReplayService:
    def __init__(self, checkpoint: OperationCheckpoint) -> None:
        self._checkpoint = checkpoint

    async def load(self, operation_id: str) -> _ReplayState:
        assert operation_id == self._checkpoint.operation_id
        return _ReplayState(self._checkpoint)


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


@pytest.mark.anyio
async def test_build_live_snapshot_omits_active_session_execution_profile_without_active_session(
) -> None:
    store = MemoryStore()
    state = OperationState(
        operation_id="op-status-no-active-profile",
        goal=OperationGoal(objective="Do not invent an active session model."),
        status=OperationStatus.RUNNING,
        scheduler_state=SchedulerState.ACTIVE,
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
            "op-status-no-active-profile",
            json_mode=True,
            brief=False,
        )
    )
    snapshot = payload["summary"]

    assert "active_session_execution_profile" not in snapshot
    assert "session_execution_profile_known" not in snapshot


@pytest.mark.anyio
async def test_status_payload_falls_back_to_event_sourced_replay() -> None:
    checkpoint = OperationCheckpoint.initial("op-status-v2")
    checkpoint.objective = ObjectiveState(objective="Report v2 status.")
    checkpoint.status = OperationStatus.COMPLETED
    checkpoint.final_summary = "v2 completed"
    service = OperationStatusQueryService(
        store=MemoryStore(),
        projection_service=OperationProjectionService(),
        trace_store=MemoryTraceStore(),
        background_inspection_store=_BackgroundInspectionStore(),
        wakeup_inspection_store=None,
        replay_service=_ReplayService(checkpoint),
        build_runtime_alert=lambda **kwargs: None,
        render_status_brief=lambda operation: "",
        render_inspect_summary=lambda operation, brief, runtime_alert=None: "",
        render_status_summary=(
            lambda operation, brief, runtime_alert=None, action_hint=None: ""
        ),
    )

    operation, outcome, _, _ = await service.build_status_payload("op-status-v2")

    assert outcome is None
    assert operation is not None
    assert operation.canonical_persistence_mode.value == "event_sourced"
    assert operation.goal.objective == "Report v2 status."
    assert operation.status is OperationStatus.COMPLETED
