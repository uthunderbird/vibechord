from __future__ import annotations

import pytest

from agent_operator.application import (
    OperationDashboardQueryService,
    OperationDeliveryCommandService,
    OperationProjectionService,
)
from agent_operator.domain import (
    AgentSessionHandle,
    DecisionMemo,
    OperationBrief,
    InvolvementLevel,
    MemoryEntry,
    MemoryFreshness,
    MemoryScope,
    OperationGoal,
    OperationPolicy,
    OperationState,
    OperationStatus,
    RuntimeHints,
    SchedulerState,
    SessionRecord,
    SessionRecordStatus,
    TaskState,
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


def _delivery(
    store: MemoryStore,
    inbox: MemoryCommandInbox,
    trace_store: MemoryTraceStore | None = None,
) -> OperationDeliveryCommandService:
    trace_store = trace_store or MemoryTraceStore()
    return OperationDeliveryCommandService(
        store=store,
        command_inbox=inbox,
        projection_service=OperationProjectionService(),
        trace_store=trace_store,
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
        status_service=_delivery(store, inbox, trace_store),
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
    progress = operation_brief["progress"]
    assert isinstance(progress, dict)
    assert progress["doing"] == "Running task-board migration"
    assert operation_brief["attention"] == ""
