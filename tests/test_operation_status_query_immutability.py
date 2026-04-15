from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from agent_operator.application.queries.operation_status_queries import (
    OperationStatusQueryService,
)
from agent_operator.domain import (
    AgentSessionHandle,
    BackgroundProgressSnapshot,
    ExecutionState,
    InvolvementLevel,
    OperationGoal,
    OperationOutcome,
    OperationPolicy,
    OperationState,
    OperationStatus,
    RuntimeHints,
    SchedulerState,
    SessionRecord,
    SessionRecordStatus,
)


class _Store:
    def __init__(self, operation: OperationState, outcome: OperationOutcome | None = None) -> None:
        self._operation = operation
        self._outcome = outcome

    async def load_operation(self, operation_id: str) -> OperationState | None:
        return self._operation if operation_id == self._operation.operation_id else None

    async def load_outcome(self, operation_id: str) -> OperationOutcome | None:
        if self._outcome is None or operation_id != self._operation.operation_id:
            return None
        return self._outcome


class _TraceStore:
    async def load_brief_bundle(self, operation_id: str):
        return None


class _BackgroundInspectionStore:
    def __init__(self, runs: list[object]) -> None:
        self._runs = runs

    async def list_runs(self, operation_id: str) -> list[object]:
        return list(self._runs)


class _WakeupInspectionStore:
    def read_all(self, operation_id: str | None = None) -> list[dict[str, object]]:
        return []


def _operation() -> OperationState:
    return OperationState(
        operation_id="op-immutable-status",
        goal=OperationGoal(objective="Inspect status immutability."),
        policy=OperationPolicy(involvement_level=InvolvementLevel.AUTO),
        runtime_hints=RuntimeHints(),
        status=OperationStatus.RUNNING,
        scheduler_state=SchedulerState.ACTIVE,
        sessions=[
            SessionRecord(
                handle=AgentSessionHandle(
                    adapter_key="codex_acp",
                    session_id="session-1",
                ),
                status=SessionRecordStatus.RUNNING,
                waiting_reason="Waiting for the current agent turn to finish.",
                current_execution_id="run-1",
                updated_at=datetime(2026, 4, 14, 12, 0, tzinfo=UTC),
            )
        ],
    )


@pytest.mark.anyio
async def test_build_status_payload_keeps_stored_session_truth_unmodified() -> None:
    operation = _operation()
    original_session_updated_at = operation.sessions[0].updated_at
    original_waiting_reason = operation.sessions[0].waiting_reason
    runtime_progress = BackgroundProgressSnapshot(
        state=operation.sessions[0].status,
        updated_at=datetime(2026, 4, 14, 12, 5, tzinfo=UTC),
        last_event_at=datetime(2026, 4, 14, 12, 6, tzinfo=UTC),
        message="Agent session completed.",
    )
    background_run = ExecutionState(
        execution_id="run-1",
        operation_id=operation.operation_id,
        adapter_key="codex_acp",
        session_id="session-1",
        task_id="task-1",
        progress=runtime_progress,
    )
    service = OperationStatusQueryService(
        store=_Store(operation),
        projection_service=SimpleNamespace(
            build_durable_truth_payload=lambda operation, include_inactive_memory=True: {},
            build_live_snapshot=lambda operation, brief, runtime_alert=None: {
                "status": operation.status.value,
                "runtime_alert": runtime_alert,
            },
        ),
        trace_store=_TraceStore(),
        background_inspection_store=_BackgroundInspectionStore([background_run]),
        wakeup_inspection_store=_WakeupInspectionStore(),
        build_runtime_alert=lambda **kwargs: None,
        render_status_brief=lambda operation: "",
        render_inspect_summary=lambda operation, brief, runtime_alert=None: "",
        render_status_summary=lambda operation, brief, runtime_alert=None, action_hint=None: "",
    )

    loaded_operation, outcome, brief_bundle, runtime_alert = await service.build_status_payload(
        operation.operation_id
    )

    assert loaded_operation is operation
    assert outcome is None
    assert brief_bundle is None
    assert runtime_alert is None
    assert operation.sessions[0].updated_at == original_session_updated_at
    assert operation.sessions[0].waiting_reason == original_waiting_reason


@pytest.mark.anyio
async def test_build_status_payload_uses_derived_background_run_payloads_without_model_dump(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    operation = _operation()
    captured_background_runs: list[dict[str, object]] = []
    background_run = ExecutionState(
        execution_id="run-1",
        operation_id=operation.operation_id,
        adapter_key="codex_acp",
        session_id="session-1",
        task_id="task-1",
        waiting_reason="Waiting for status update.",
    )

    def _fail_execution_model_dump(self, *args, **kwargs):
        raise AssertionError(
            "build_status_payload should not serialize ExecutionState directly"
        )

    monkeypatch.setattr(ExecutionState, "model_dump", _fail_execution_model_dump)

    service = OperationStatusQueryService(
        store=_Store(operation),
        projection_service=SimpleNamespace(
            build_durable_truth_payload=lambda operation, include_inactive_memory=True: {},
            build_live_snapshot=lambda operation, brief, runtime_alert=None: {
                "status": operation.status.value,
                "runtime_alert": runtime_alert,
            },
        ),
        trace_store=_TraceStore(),
        background_inspection_store=_BackgroundInspectionStore([background_run]),
        wakeup_inspection_store=_WakeupInspectionStore(),
        build_runtime_alert=lambda **kwargs: captured_background_runs.extend(
            kwargs["background_runs"]
        )
        or "runtime-alert",
        render_status_brief=lambda operation: "",
        render_inspect_summary=lambda operation, brief, runtime_alert=None: "",
        render_status_summary=lambda operation, brief, runtime_alert=None, action_hint=None: "",
    )

    loaded_operation, outcome, brief_bundle, runtime_alert = await service.build_status_payload(
        operation.operation_id
    )

    assert loaded_operation is operation
    assert outcome is None
    assert brief_bundle is None
    assert runtime_alert == "runtime-alert"
    assert captured_background_runs == [
        {
            "execution_id": "run-1",
            "run_id": "run-1",
            "operation_id": operation.operation_id,
            "adapter_key": "codex_acp",
            "session_id": "session-1",
            "task_id": "task-1",
            "iteration": None,
            "mode": "background",
            "launch_kind": "new",
            "observed_state": "starting",
            "status": "pending",
            "waiting_reason": "Waiting for status update.",
            "handle_ref": None,
            "progress": None,
            "result_ref": None,
            "error_ref": None,
            "pid": None,
            "started_at": background_run.started_at.isoformat(),
            "last_heartbeat_at": None,
            "completed_at": None,
            "raw_ref": None,
        }
    ]
