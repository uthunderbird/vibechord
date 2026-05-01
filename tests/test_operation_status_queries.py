from __future__ import annotations

import ast
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from agent_operator.application import OperationProjectionService, OperationStatusQueryService
from agent_operator.cli.helpers.rendering import build_runtime_alert
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
    StoredOperationDomainEvent,
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
    def __init__(
        self,
        checkpoint: OperationCheckpoint,
        *,
        last_applied_sequence: int = 1,
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
        last_applied_sequence: int = 1,
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


class _FactStore:
    def __init__(self, last_sequence: int) -> None:
        self._last_sequence = last_sequence

    async def load_last_sequence(self, operation_id: str) -> int:
        return self._last_sequence


def test_build_runtime_alert_ignores_terminal_background_run_when_live_run_exists() -> None:
    """Catches the mutation where resume guidance appears during active progress."""
    alert = build_runtime_alert(
        status=OperationStatus.RUNNING,
        wakeups=[],
        background_runs=[
            {"status": "completed"},
            {"status": "running"},
        ],
    )

    assert alert is None


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


@pytest.mark.anyio
async def test_status_payload_prefers_event_sourced_replay_over_stale_snapshot() -> None:
    """Catches the mutation where status loads a stale snapshot before v2 replay."""
    store = MemoryStore()
    stale_state = OperationState(
        operation_id="op-status-v2-stale",
        goal=OperationGoal(objective="Stale snapshot objective."),
        status=OperationStatus.RUNNING,
        **state_settings(),
    )
    await store.save_operation(stale_state)
    checkpoint = OperationCheckpoint.initial("op-status-v2-stale")
    checkpoint.objective = ObjectiveState(objective="Canonical event objective.")
    checkpoint.status = OperationStatus.COMPLETED
    checkpoint.final_summary = "canonical v2 completed"
    service = OperationStatusQueryService(
        store=store,
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

    operation, outcome, _, _ = await service.build_status_payload("op-status-v2-stale")

    assert outcome is None
    assert operation is not None
    assert operation.goal.objective == "Canonical event objective."
    assert operation.status is OperationStatus.COMPLETED


@pytest.mark.anyio
async def test_status_payload_falls_back_to_canonical_latest_turn_when_trace_brief_is_missing(
) -> None:
    checkpoint = OperationCheckpoint.initial("op-status-v2-turn")
    checkpoint.objective = ObjectiveState(objective="Show latest turn from canonical events.")
    checkpoint.status = OperationStatus.RUNNING

    timestamp = datetime.now(UTC)
    canonical_events = [
        StoredOperationDomainEvent(
            operation_id="op-status-v2-turn",
            sequence=1,
            event_type="session.created",
            payload={
                "handle": {
                    "adapter_key": "codex_acp",
                    "session_id": "sess-1",
                    "session_name": "repo-audit",
                    "display_name": "Codex via ACP",
                    "one_shot": False,
                    "metadata": {},
                },
                "adapter_key": "codex_acp",
            },
            timestamp=timestamp,
        ),
        StoredOperationDomainEvent(
            operation_id="op-status-v2-turn",
            sequence=2,
            event_type="agent.turn.completed",
            payload={
                "session_id": "sess-1",
                "adapter_key": "codex_acp",
                "status": "completed",
                "output_text": "Completed the ADR audit and updated the blocker notes.",
                "completed_at": timestamp.isoformat(),
            },
            timestamp=timestamp,
        ),
    ]
    service = OperationStatusQueryService(
        store=MemoryStore(),
        projection_service=OperationProjectionService(),
        trace_store=MemoryTraceStore(),
        background_inspection_store=_BackgroundInspectionStore(),
        wakeup_inspection_store=None,
        replay_service=_ReplayService(checkpoint),
        event_store=_EventStore(canonical_events),
        build_runtime_alert=lambda **kwargs: None,
        render_status_brief=lambda operation: "",
        render_inspect_summary=lambda operation, brief, runtime_alert=None: "",
        render_status_summary=(
            lambda operation, brief, runtime_alert=None, action_hint=None: ""
        ),
    )

    payload = json.loads(
        await service.render_status_output(
            "op-status-v2-turn",
            json_mode=True,
            brief=False,
        )
    )
    summary = payload["summary"]["summary"]

    assert summary["latest_turn"]["agent_key"] == "codex_acp"
    assert summary["latest_turn"]["session_id"] == "sess-1"
    assert summary["latest_turn"]["status"] == "completed"
    assert summary["work_summary"] == "Completed the ADR audit and updated the blocker notes."
    assert summary["next_step"] is None
    assert summary["blockers_summary"] is None


def test_operation_status_query_service_isolates_snapshot_reads_to_named_fallback() -> None:
    source = Path("src/agent_operator/application/queries/operation_status_queries.py").read_text(
        encoding="utf-8"
    )
    tree = ast.parse(source)

    callers = sorted(
        {
            node.name
            for node in ast.walk(tree)
            if isinstance(node, ast.AsyncFunctionDef)
            and any(
                isinstance(child, ast.Attribute) and child.attr == "load_operation"
                for child in ast.walk(node)
            )
        }
    )

    assert callers == ["_load_snapshot_fallback"]

    helper_calls = sorted(
        {
            node.name
            for node in ast.walk(tree)
            if isinstance(node, ast.AsyncFunctionDef)
            and any(
                isinstance(child, ast.Attribute) and child.attr == "_load_snapshot_fallback"
                for child in ast.walk(node)
            )
        }
    )

    assert helper_calls == ["build_read_payload"]


@pytest.mark.anyio
async def test_status_json_uses_shared_read_payload_overlay_metadata() -> None:
    """Catches JSON status recomputing from a separate non-overlay path."""
    checkpoint = OperationCheckpoint.initial("op-status-v2-overlay")
    checkpoint.objective = ObjectiveState(objective="Report overlay status.")
    service = OperationStatusQueryService(
        store=MemoryStore(),
        projection_service=OperationProjectionService(),
        trace_store=MemoryTraceStore(),
        background_inspection_store=_BackgroundInspectionStore(),
        wakeup_inspection_store=None,
        replay_service=_ReplayService(checkpoint),
        build_runtime_alert=lambda **kwargs: "runtime wakeup pending",
        render_status_brief=lambda operation: "",
        render_inspect_summary=lambda operation, brief, runtime_alert=None: "",
        render_status_summary=(
            lambda operation, brief, runtime_alert=None, action_hint=None: ""
        ),
    )

    read_payload = await service.build_read_payload("op-status-v2-overlay")
    payload = json.loads(
        await service.render_status_output(
            "op-status-v2-overlay",
            json_mode=True,
            brief=False,
        )
    )

    assert read_payload.source == "event_sourced"
    assert payload["source"] == read_payload.source
    assert payload["summary"] == read_payload.live_snapshot
    assert payload["runtime_overlay"]["runtime_alert"] == "runtime wakeup pending"
    assert (
        payload["runtime_overlay"]["authorities"]["wakeup_inspection"]
        == "runtime_overlay"
    )
    assert payload["runtime_overlay"]["sync_health"]["checkpoint_sequence"] == 1


@pytest.mark.anyio
async def test_status_json_reports_sync_health_when_checkpoint_lags_canonical_events(
) -> None:
    checkpoint = OperationCheckpoint.initial("op-status-v2-sync")
    checkpoint.objective = ObjectiveState(objective="Report sync health.")
    timestamp = datetime.now(UTC)
    canonical_events = [
        StoredOperationDomainEvent(
            operation_id="op-status-v2-sync",
            sequence=1,
            event_type="operation.created",
            payload={},
            timestamp=timestamp,
        ),
        StoredOperationDomainEvent(
            operation_id="op-status-v2-sync",
            sequence=2,
            event_type="session.created",
            payload={"adapter_key": "codex_acp"},
            timestamp=timestamp,
        ),
        StoredOperationDomainEvent(
            operation_id="op-status-v2-sync",
            sequence=3,
            event_type="agent.turn.completed",
            payload={
                "session_id": "sess-1",
                "adapter_key": "codex_acp",
                "status": "completed",
                "output_text": "done",
            },
            timestamp=timestamp,
        ),
    ]
    service = OperationStatusQueryService(
        store=MemoryStore(),
        projection_service=OperationProjectionService(),
        trace_store=MemoryTraceStore(),
        background_inspection_store=_BackgroundInspectionStore(),
        wakeup_inspection_store=None,
        replay_service=_ReplayService(checkpoint, last_applied_sequence=1),
        event_store=_EventStore(canonical_events),
        build_runtime_alert=lambda **kwargs: None,
        render_status_brief=lambda operation: "",
        render_inspect_summary=lambda operation, brief, runtime_alert=None: "",
        render_status_summary=(
            lambda operation, brief, runtime_alert=None, action_hint=None: ""
        ),
    )

    payload = json.loads(
        await service.render_status_output(
            "op-status-v2-sync",
            json_mode=True,
            brief=False,
        )
    )

    sync_health = payload["runtime_overlay"]["sync_health"]
    assert sync_health["canonical_sequence"] == 3
    assert sync_health["fact_sequence"] is None
    assert sync_health["translated_fact_sequence"] is None
    assert sync_health["untranslated_fact_count"] is None
    assert sync_health["checkpoint_sequence"] == 1
    assert sync_health["projection_sequence"] == 1
    assert sync_health["canonical_lag"] == 2
    assert sync_health["sync_alert"] == "checkpoint_lagging_canonical_events"


@pytest.mark.anyio
async def test_status_json_reports_persisted_fact_cursor_in_sync_health() -> None:
    checkpoint = OperationCheckpoint.initial("op-status-v2-facts")
    checkpoint.objective = ObjectiveState(objective="Report fact cursor.")
    service = OperationStatusQueryService(
        store=MemoryStore(),
        projection_service=OperationProjectionService(),
        trace_store=MemoryTraceStore(),
        background_inspection_store=_BackgroundInspectionStore(),
        wakeup_inspection_store=None,
        replay_service=_ReplayService(checkpoint, last_applied_sequence=1),
        fact_store=_FactStore(last_sequence=4),
        build_runtime_alert=lambda **kwargs: None,
        render_status_brief=lambda operation: "",
        render_inspect_summary=lambda operation, brief, runtime_alert=None: "",
        render_status_summary=(
            lambda operation, brief, runtime_alert=None, action_hint=None: ""
        ),
    )

    payload = json.loads(
        await service.render_status_output(
            "op-status-v2-facts",
            json_mode=True,
            brief=False,
        )
    )

    sync_health = payload["runtime_overlay"]["sync_health"]
    assert sync_health["fact_sequence"] == 4
    assert sync_health["checkpoint_sequence"] == 1


@pytest.mark.anyio
async def test_status_json_replays_permission_events_into_durable_truth() -> None:
    """Catches omitting replayed permission events from status/inspect query payloads."""
    checkpoint = OperationCheckpoint.initial("op-status-v2-permission")
    checkpoint.objective = ObjectiveState(objective="Report permission replay.")
    checkpoint.permission_events = [
        {
            "event_type": "permission.request.followup_required",
            "sequence": 7,
            "timestamp": "2026-04-23T00:00:00+00:00",
            "payload": {
                "adapter_key": "codex_acp",
                "session_id": "sess-1",
                "required_followup_reason": "Codex needs replacement instructions.",
            },
        }
    ]
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

    payload = json.loads(
        await service.render_status_output(
            "op-status-v2-permission",
            json_mode=True,
            brief=False,
        )
    )

    permission_events = payload["durable_truth"]["permission_events"]
    assert permission_events[0]["event_type"] == "permission.request.followup_required"
    assert permission_events[0]["sequence"] == 7
    assert (
        permission_events[0]["payload"]["required_followup_reason"]
        == "Codex needs replacement instructions."
    )
