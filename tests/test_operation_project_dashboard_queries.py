from __future__ import annotations

from pathlib import Path

import pytest

from agent_operator.application import (
    OperationAgendaQueryService,
    OperationDeliveryCommandService,
    OperationProjectDashboardQueryService,
    OperationProjectionService,
)
from agent_operator.domain import (
    AgentSessionHandle,
    InvolvementLevel,
    OperationGoal,
    OperationPolicy,
    OperationState,
    OperationStatus,
    OperationSummary,
    PolicyCategory,
    PolicyEntry,
    PolicyStatus,
    ProjectProfile,
    ResolvedProjectRunConfig,
    RunMode,
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


class _Service:
    async def resume(self, operation_id: str, *, options=None, session_id=None):
        raise AssertionError("resume should not be called in project dashboard query tests")

    async def cancel(self, operation_id: str, *, session_id=None, run_id=None):
        raise AssertionError("cancel should not be called in project dashboard query tests")

    async def tick(self, operation_id: str, *, options=None):
        raise AssertionError("tick should not be called in project dashboard query tests")

    async def recover(self, operation_id: str, *, session_id=None, options=None):
        raise AssertionError("recover should not be called in project dashboard query tests")


class _PolicyStore:
    async def list(self, *, project_scope=None, status=None) -> list[PolicyEntry]:
        return [
            PolicyEntry(
                policy_id="p-1",
                title="Use codex",
                category=PolicyCategory.GENERAL,
                rule_text="Prefer codex_acp.",
                project_scope=project_scope,
                status=status or PolicyStatus.ACTIVE,
            )
        ]


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


def _operation() -> OperationState:
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


@pytest.mark.anyio
async def test_load_payload_builds_project_dashboard() -> None:
    store = _StoreWithSummaries()
    await store.save_operation(_operation())
    agenda_queries = OperationAgendaQueryService(store=store, status_service=_delivery(store))
    service = OperationProjectDashboardQueryService(
        agenda_queries=agenda_queries,
        projection_service=OperationProjectionService(),
        policy_store=_PolicyStore(),
    )

    payload = await service.load_payload(
        profile=ProjectProfile(name="operator"),
        resolved=ResolvedProjectRunConfig(
            profile_name="operator",
            cwd=Path("."),
            objective_text="Ship dashboard",
            default_agents=["codex_acp"],
            harness_instructions="Keep delivery thin.",
            success_criteria=[],
            max_iterations=8,
            run_mode=RunMode.ATTACHED,
            involvement_level=InvolvementLevel.COLLABORATIVE,
        ),
        profile_path=Path("/tmp/operator-profile.yaml"),
    )

    assert payload["project"] == "operator"
    assert payload["policy_summary"]["active_count"] == 1
    assert payload["fleet"]["total_operations"] == 1
