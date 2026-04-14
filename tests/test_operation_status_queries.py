from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest

from agent_operator.application import OperationProjectionService, OperationStatusQueryService
from agent_operator.cli.helpers.rendering import overlay_live_background_progress
from agent_operator.domain import (
    AgentSessionHandle,
    BackgroundProgressSnapshot,
    BackgroundRunHandle,
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


def test_overlay_live_background_progress_keeps_waiting_reason_as_durable_truth() -> None:
    updated_at = datetime(2026, 4, 14, 12, 0, tzinfo=UTC)
    last_event_at = datetime(2026, 4, 14, 12, 1, tzinfo=UTC)
    operation = OperationState(
        operation_id="op-status-overlay",
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
                current_execution_id="run-1",
                waiting_reason="Waiting for the current agent turn to finish.",
            )
        ],
        **state_settings(),
    )

    overlaid = overlay_live_background_progress(
        operation,
        [
            BackgroundRunHandle(
                run_id="run-1",
                operation_id="op-status-overlay",
                adapter_key="codex_acp",
                session_id="session-1",
                progress=BackgroundProgressSnapshot(
                    state=SessionRecordStatus.RUNNING,
                    message="Agent session completed.",
                    updated_at=updated_at,
                    last_event_at=last_event_at,
                ),
            )
        ],
    )

    assert overlaid.sessions[0].updated_at == updated_at
    assert overlaid.sessions[0].last_event_at == last_event_at
    assert overlaid.sessions[0].waiting_reason == (
        "Waiting for the current agent turn to finish."
    )
    assert operation.sessions[0].waiting_reason == (
        "Waiting for the current agent turn to finish."
    )


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
        overlay_live_background_progress=lambda operation, runs: operation,
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
