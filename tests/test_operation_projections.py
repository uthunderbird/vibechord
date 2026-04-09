from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from agent_operator.application import OperationProjectionService
from agent_operator.domain import (
    AgentSessionHandle,
    AttentionRequest,
    AttentionStatus,
    AttentionType,
    CommandTargetScope,
    InvolvementLevel,
    MemoryEntry,
    MemoryFreshness,
    MemoryScope,
    OperationGoal,
    OperationPolicy,
    OperationState,
    OperationStatus,
    ProjectProfile,
    RuntimeHints,
    SchedulerState,
    SessionRecord,
    SessionRecordStatus,
)
from agent_operator.runtime import AgendaBucket, AgendaItem, AgendaSnapshot


def _operation() -> OperationState:
    return OperationState(
        operation_id="op-1",
        goal=OperationGoal(
            objective="Ship dashboard",
            harness_instructions="Keep delivery thin.",
            success_criteria=["docs updated"],
            metadata={
                "project_profile_name": "operator",
                "policy_scope": "profile:operator",
                "resolved_project_profile": {"profile_name": "operator"},
            },
        ),
        policy=OperationPolicy(
            allowed_agents=["codex_acp"],
            involvement_level=InvolvementLevel.COLLABORATIVE,
        ),
        runtime_hints=RuntimeHints(
            metadata={
                "run_mode": "attached",
                "available_agent_descriptors": [{"key": "codex_acp"}],
            }
        ),
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
        memory_entries=[
            MemoryEntry(
                memory_id="m1",
                scope=MemoryScope.PROJECT,
                scope_id="op-1",
                summary="Current",
                freshness=MemoryFreshness.CURRENT,
            ),
            MemoryEntry(
                memory_id="m2",
                scope=MemoryScope.PROJECT,
                scope_id="op-1",
                summary="Old",
                freshness=MemoryFreshness.STALE,
            ),
        ],
        attention_requests=[
            AttentionRequest(
                attention_id="att-1",
                operation_id="op-1",
                attention_type=AttentionType.NOVEL_STRATEGIC_FORK,
                status=AttentionStatus.OPEN,
                title="Choose path",
                question="Which path?",
                target_scope=CommandTargetScope.OPERATION,
                target_id="op-1",
            )
        ],
    )


def test_build_durable_truth_payload_splits_memory() -> None:
    payload = OperationProjectionService().build_durable_truth_payload(
        _operation(),
        include_inactive_memory=True,
    )

    assert [item["memory_id"] for item in payload["memory"]["current"]] == ["m1"]
    assert [item["memory_id"] for item in payload["memory"]["inactive"]] == ["m2"]


def test_build_operation_context_payload_preserves_context() -> None:
    payload = OperationProjectionService().build_operation_context_payload(_operation())

    assert payload["operation_id"] == "op-1"
    assert payload["run_mode"] == "attached"
    assert payload["allowed_agents"] == ["codex_acp"]
    assert payload["project_context"]["profile_name"] == "operator"
    assert payload["available_agent_descriptors"] == [{"key": "codex_acp"}]
    assert payload["open_attention"][0]["attention_id"] == "att-1"


def test_build_fleet_payload_returns_actions() -> None:
    item = AgendaItem(
        operation_id="op-1",
        bucket=AgendaBucket.ACTIVE,
        status=OperationStatus.RUNNING,
        scheduler_state=SchedulerState.ACTIVE,
        involvement_level=InvolvementLevel.COLLABORATIVE,
        objective_brief="Ship dashboard",
        updated_at=datetime.now(UTC),
    )
    payload = OperationProjectionService().build_fleet_payload(
        AgendaSnapshot(total_operations=1, needs_attention=[], active=[item], recent=[]),
        project=None,
    )

    assert payload["mix"]["bucket_counts"]["active"] == 1
    assert any(action["cli_command"] == "operator watch op-1" for action in payload["actions"])


def test_build_project_dashboard_payload_merges_fleet_actions() -> None:
    profile = ProjectProfile(name="operator", cwd=Path("/tmp/operator"))
    payload = OperationProjectionService().build_project_dashboard_payload(
        profile=profile,
        resolved={},
        profile_path=Path("/tmp/operator-profile.yaml"),
        fleet={
            "actions": [
                {
                    "key": "dashboard",
                    "label": "Dashboard",
                    "cli_command": "operator dashboard op-1",
                    "scope": "operation",
                    "destructive": False,
                    "enabled": True,
                    "reason": None,
                }
            ]
        },
        active_policies=[],
    )

    commands = [item["cli_command"] for item in payload["actions"]]
    assert "operator project inspect operator" in commands
    assert "operator dashboard op-1" in commands


def test_build_live_snapshot_and_format_live_snapshot() -> None:
    service = OperationProjectionService()
    snapshot = service.build_live_snapshot(_operation(), None, runtime_alert="rate limit soon")

    assert snapshot["operation_id"] == "op-1"
    assert snapshot["summary"]["objective"] == "Ship dashboard"

    rendered = service.format_live_snapshot(snapshot)
    assert "state: running" in rendered
    assert "objective=Ship dashboard" in rendered
    assert "alert=rate limit soon" in rendered
