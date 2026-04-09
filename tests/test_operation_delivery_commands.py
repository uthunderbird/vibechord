from __future__ import annotations

import json

import pytest

from agent_operator.application import (
    OperationDeliveryCommandService,
    OperationProjectionService,
)
from agent_operator.domain import (
    AgentSessionHandle,
    AttentionRequest,
    AttentionStatus,
    AttentionType,
    CommandTargetScope,
    InvolvementLevel,
    OperationGoal,
    OperationOutcome,
    OperationPolicy,
    OperationCommandType,
    OperationState,
    OperationStatus,
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
        return OperationOutcome(
            operation_id=operation_id,
            status=OperationStatus.RUNNING,
            summary="resumed",
        )

    async def cancel(self, operation_id: str, *, session_id=None, run_id=None):
        return OperationOutcome(
            operation_id=operation_id,
            status=OperationStatus.CANCELLED,
            summary="cancelled",
        )

    async def tick(self, operation_id: str, *, options=None):
        return OperationOutcome(
            operation_id=operation_id,
            status=OperationStatus.RUNNING,
            summary="ticked",
        )

    async def recover(self, operation_id: str, *, session_id=None, options=None):
        return OperationOutcome(
            operation_id=operation_id,
            status=OperationStatus.RUNNING,
            summary="recovered",
        )


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
        attention_requests=[
            AttentionRequest(
                attention_id="att-1",
                operation_id="op-1",
                attention_type=AttentionType.NOVEL_STRATEGIC_FORK,
                status=AttentionStatus.OPEN,
                blocking=True,
                title="Choose path",
                question="Which path?",
                target_scope=CommandTargetScope.OPERATION,
                target_id="op-1",
            )
        ],
    )


def _service(store: MemoryStore, inbox: MemoryCommandInbox) -> OperationDeliveryCommandService:
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
        render_status_brief=lambda operation: f"brief:{operation.operation_id}",
        render_inspect_summary=lambda operation, brief, runtime_alert=None: f"inspect:{operation.operation_id}",
        find_task_by_display_id=lambda operation, task_id: None,
    )


@pytest.mark.anyio
async def test_render_status_output_json_uses_projection_payload() -> None:
    store = MemoryStore()
    inbox = MemoryCommandInbox()
    operation = _operation()
    await store.save_operation(operation)
    await store.save_outcome(
        OperationOutcome(
            operation_id="op-1",
            status=OperationStatus.RUNNING,
            summary="still running",
        )
    )
    service = _service(store, inbox)

    rendered = await service.render_status_output("op-1", json_mode=True, brief=False)
    payload = json.loads(rendered)

    assert payload["operation_id"] == "op-1"
    assert payload["status"] == "running"
    assert len(payload["durable_truth"]["tasks"]) == 1


def test_build_live_snapshot_uses_shared_delivery_builder() -> None:
    service = _service(MemoryStore(), MemoryCommandInbox())
    operation = _operation()

    payload = service.build_live_snapshot("op-1", operation, None)

    assert payload["operation_id"] == "op-1"
    assert payload["status"] == "running"
    assert payload["session_id"] == "session-1"
    assert payload["open_attention_count"] == 1


@pytest.mark.anyio
async def test_enqueue_command_returns_command_and_stores_it() -> None:
    store = MemoryStore()
    inbox = MemoryCommandInbox()
    await store.save_operation(_operation())
    service = _service(store, inbox)

    command, outcome, note = await service.enqueue_command(
        "op-1",
        command_type=OperationCommandType.PAUSE_OPERATOR,
        payload={},
        target_scope=CommandTargetScope.OPERATION,
        target_id="op-1",
    )

    assert command.operation_id == "op-1"
    assert outcome is None
    assert note is None
    listed = await inbox.list("op-1")
    assert len(listed) == 1


@pytest.mark.anyio
async def test_answer_attention_enqueues_answer() -> None:
    store = MemoryStore()
    inbox = MemoryCommandInbox()
    await store.save_operation(_operation())
    service = _service(store, inbox)

    answer_command, policy_command, outcome = await service.answer_attention(
        "op-1",
        attention_id=None,
        text="Take path A",
        promote=False,
        policy_payload={},
    )

    assert answer_command.command_type.value == "answer_attention_request"
    assert policy_command is None
    assert outcome is None


def test_build_policy_decision_payload_requires_promote() -> None:
    service = _service(MemoryStore(), MemoryCommandInbox())

    with pytest.raises(RuntimeError, match="Policy options require --promote."):
        service.build_policy_decision_payload(
            promote=False,
            category="general",
            title="Keep this",
            text=None,
            objective_keyword=None,
            task_keyword=None,
            agent=None,
            run_mode=None,
            involvement=None,
            rationale=None,
        )


@pytest.mark.anyio
async def test_tick_and_recover_delegate_to_operator_service() -> None:
    store = MemoryStore()
    inbox = MemoryCommandInbox()
    await store.save_operation(_operation())
    service = _service(store, inbox)

    resume_outcome = await service.resume("op-1", max_cycles=5)
    tick_outcome = await service.tick("op-1")
    recover_outcome = await service.recover("op-1", session_id=None, max_cycles=3)

    assert resume_outcome.summary == "resumed"
    assert tick_outcome.summary == "ticked"
    assert recover_outcome.summary == "recovered"


@pytest.mark.anyio
async def test_daemon_sweep_resumes_ready_operations() -> None:
    store = MemoryStore()
    inbox = MemoryCommandInbox()
    await store.save_operation(_operation())
    service = _service(store, inbox)
    seen_operations: list[str] = []
    seen_outcomes: list[str] = []

    resumed = await service.daemon_sweep(
        ready_operation_ids=["op-1"],
        max_cycles_per_operation=2,
        emit_operation=seen_operations.append,
        emit_outcome=lambda outcome: seen_outcomes.append(outcome.operation_id),
    )

    assert resumed == 1
    assert seen_operations == ["op-1"]
    assert seen_outcomes == ["op-1"]
