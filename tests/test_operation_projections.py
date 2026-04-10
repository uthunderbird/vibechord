from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from agent_operator.application import OperationProjectionService
from agent_operator.domain import (
    AgentSessionHandle,
    AgentTurnBrief,
    AgentTurnSummary,
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
    OperationSummary,
    ProjectProfile,
    RuntimeHints,
    SchedulerState,
    SessionRecord,
    SessionRecordStatus,
    TaskState,
    TaskStatus,
    TraceBriefBundle,
)
from agent_operator.runtime import AgendaBucket, AgendaItem, AgendaSnapshot, build_agenda_item


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


def _operation_with_mixed_attention() -> tuple[OperationState, OperationSummary]:
    operation = _operation().model_copy(deep=True)
    operation.attention_requests = [
        AttentionRequest(
            attention_id="att-1",
            operation_id="op-1",
            attention_type=AttentionType.NOVEL_STRATEGIC_FORK,
            status=AttentionStatus.OPEN,
            title="Need a policy response",
            question="How to route this task?",
            target_scope=CommandTargetScope.OPERATION,
            target_id="op-1",
            blocking=True,
        ),
        AttentionRequest(
            attention_id="att-2",
            operation_id="op-1",
            attention_type=AttentionType.POLICY_GAP,
            status=AttentionStatus.OPEN,
            title="Additional context needed",
            question="Can you add context?",
            target_scope=CommandTargetScope.OPERATION,
            target_id="op-1",
            blocking=False,
        ),
    ]
    summary = OperationSummary(
        operation_id="op-1",
        status=operation.status,
        objective_prompt="Ship dashboard",
        final_summary=None,
        focus=None,
        runnable_task_count=0,
        reusable_session_count=0,
        updated_at=datetime.now(UTC),
    )
    return operation, summary


def _operation_with_task_session() -> OperationState:
    operation = _operation().model_copy(deep=True)
    operation.tasks = [
        TaskState(
            task_id="task-1",
            title="Implement session view",
            goal="Ship normalized session payload",
            definition_of_done="Session payload is shared",
            status=TaskStatus.RUNNING,
            linked_session_id="session-1",
        )
    ]
    operation.sessions[0].bound_task_ids = ["task-1"]
    return operation


def test_build_agenda_item_splits_open_attention_counts() -> None:
    operation, summary = _operation_with_mixed_attention()
    item = build_agenda_item(operation, summary)

    assert item.open_attention_count == 2
    assert item.open_blocking_attention_count == 1
    assert item.open_nonblocking_attention_count == 1


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


def test_build_operation_context_payload_exposes_invocation_modes_separately() -> None:
    operation = _operation()
    operation.runtime_hints.metadata["continuity_run_mode"] = "attached"
    operation.runtime_hints.metadata["continuity_background_runtime_mode"] = "attached_live"
    operation.runtime_hints.metadata["invocation_run_mode"] = "resumable"
    operation.runtime_hints.metadata["invocation_background_runtime_mode"] = "resumable_wakeup"

    payload = OperationProjectionService().build_operation_context_payload(operation)

    assert payload["run_mode"] == "attached"
    assert payload["invocation_run_mode"] == "resumable"
    assert payload["background_runtime_mode"] == "attached_live"
    assert payload["invocation_background_runtime_mode"] == "resumable_wakeup"


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


def test_build_fleet_workbench_payload_normalizes_rows_and_header() -> None:
    items = [
        AgendaItem(
            operation_id="op-alert",
            bucket=AgendaBucket.NEEDS_ATTENTION,
            status=OperationStatus.NEEDS_HUMAN,
            scheduler_state=SchedulerState.ACTIVE,
            involvement_level=InvolvementLevel.AUTO,
            objective_brief="Answer a policy question",
            project_profile_name="operator",
            updated_at=datetime(2026, 1, 3, 12, 0, 0, tzinfo=UTC),
            runtime_alert="Operator needs manual intervention",
            open_attention_count=2,
            open_blocking_attention_count=1,
            open_nonblocking_attention_count=1,
            attention_titles=["policy gap", "timeout check"],
            blocking_attention_titles=["policy gap"],
            nonblocking_attention_titles=["timeout check"],
            focus_brief="waiting on input",
            latest_outcome_brief="paused at checkpoint",
            blocker_brief="blocked by human policy",
        ),
        AgendaItem(
            operation_id="op-running",
            bucket=AgendaBucket.ACTIVE,
            status=OperationStatus.RUNNING,
            scheduler_state=SchedulerState.ACTIVE,
            involvement_level=InvolvementLevel.COLLABORATIVE,
            objective_brief="Ship the dashboard",
            updated_at=datetime(2026, 1, 3, 12, 0, 5, tzinfo=UTC),
            focus_brief="agent started",
            latest_outcome_brief="running task board migration",
            blocker_brief=None,
            attention_titles=[],
        ),
    ]
    payload = OperationProjectionService().build_fleet_workbench_payload(
        AgendaSnapshot(
            total_operations=2,
            needs_attention=[items[0]],
            active=[items[1]],
            recent=[],
        ),
        project="operator",
    )

    assert payload["project"] == "operator"
    assert payload["total_operations"] == 2
    rows = payload["rows"]
    assert isinstance(rows, list)
    assert rows[0]["operation_id"] == "op-alert"
    assert rows[1]["operation_id"] == "op-running"
    assert rows[0]["sort_bucket"] == "needs_attention"
    assert rows[1]["sort_bucket"] == "active"
    assert rows[0]["attention_badge"] == "!!"
    assert rows[0]["state_label"] == "needs_human"
    assert rows[0]["agent_cue"] == "profile:operator"
    assert rows[0]["row_hint"] == "now: runtime alert"
    brief = rows[0]["brief"]
    assert brief["goal"] == "Answer a policy question"
    assert isinstance(brief["progress"], dict)
    assert brief["progress"]["done"] is None
    assert brief["attention"] == "policy gap"
    assert brief["review"] == "timeout check"
    assert brief["operator_state"] is None
    assert "status_counts" in payload["mix"]
    assert payload["mix"]["bucket_counts"]["needs_attention"] == 1
    assert payload["mix"]["bucket_counts"]["active"] == 1


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


def test_build_dashboard_payload_emits_normalized_session_views() -> None:
    operation = _operation_with_task_session()
    payload = OperationProjectionService().build_dashboard_payload(
        operation,
        brief=None,
        outcome=None,
        runtime_alert=None,
        commands=[],
        events=[],
        decision_memos=[],
        upstream_transcript=None,
        report_text="# Report\n\nRetrospective summary.",
    )

    session_views = payload["session_views"]
    assert isinstance(session_views, list)
    assert len(session_views) == 1
    session_view = session_views[0]
    assert session_view["task_id"] == "task-1"
    assert session_view["session"]["session_id"] == "session-1"
    assert session_view["session_brief"]["wait"] == "Working"
    assert session_view["session_brief"]["agent_activity"] == "codex_acp session"
    assert session_view["session_brief"]["operator_state"] == "observing"
    assert session_view["session_brief"]["attention"] == "-"
    assert session_view["session_brief"]["review"] is None
    assert session_view["transcript_hint"]["command"] == "operator log op-1 --agent codex"
    assert payload["report_text"] == "# Report\n\nRetrospective summary."


def test_build_operation_brief_payload_splits_blocking_and_nonblocking_attention() -> None:
    operation, _ = _operation_with_mixed_attention()

    payload = OperationProjectionService().build_operation_brief_payload(
        operation,
        brief=None,
        runtime_alert=None,
    )

    assert payload["attention"] == "Need a policy response"
    assert payload["review"] == "Additional context needed"


def test_build_live_snapshot_and_format_live_snapshot() -> None:
    service = OperationProjectionService()
    snapshot = service.build_live_snapshot(_operation(), None, runtime_alert="rate limit soon")

    assert snapshot["operation_id"] == "op-1"
    assert snapshot["summary"]["objective"] == "Ship dashboard"

    rendered = service.format_live_snapshot(snapshot)
    assert "state: running" in rendered
    assert "objective=Ship dashboard" in rendered
    assert "alert=rate limit soon" in rendered


def test_build_inspect_summary_payload_uses_recommended_next_step() -> None:
    service = OperationProjectionService()
    brief = TraceBriefBundle(
        agent_turn_briefs=[
            AgentTurnBrief(
                operation_id="op-1",
                iteration=4,
                agent_key="codex_acp",
                session_id="session-1",
                assignment_brief="Implement the next TUI slice.",
                result_brief="Completed the slice.",
                status="success",
                turn_summary=AgentTurnSummary(
                    declared_goal="Improve the TUI.",
                    actual_work_done="Implemented the next operation-view slice.",
                    state_delta="Repository now includes the new drill-down.",
                    verification_status="Focused tests passed.",
                    recommended_next_step="Implement the watch redesign next.",
                ),
            )
        ]
    )

    payload = service.build_inspect_summary_payload(
        _operation(),
        brief,
        runtime_alert=None,
    )

    assert payload["next_step"] == "Implement the watch redesign next."
