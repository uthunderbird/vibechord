from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from rich.console import Console

from agent_operator.application import OperationProjectionService
from agent_operator.cli.rendering.operation import render_dashboard
from agent_operator.domain import (
    AgentArtifact,
    AgentError,
    AgentResult,
    AgentResultStatus,
    AgentSessionHandle,
    AgentTurnBrief,
    AgentTurnSummary,
    AgentUsage,
    ArtifactRecord,
    AttentionRequest,
    AttentionStatus,
    AttentionType,
    BackgroundProgressSnapshot,
    BlockingFocus,
    BrainActionType,
    BrainDecision,
    CommandTargetScope,
    ExecutionHandleRef,
    ExecutionProfileOverride,
    ExecutionProfileStamp,
    ExecutionState,
    ExternalTicketLink,
    FeatureDraft,
    FeaturePatch,
    FeatureState,
    FocusKind,
    FocusMode,
    FocusState,
    InvolvementLevel,
    IterationBrief,
    IterationState,
    MemoryEntry,
    MemoryFreshness,
    MemoryScope,
    MemorySourceRef,
    OperationBrief,
    OperationGoal,
    OperationPolicy,
    OperationState,
    OperationStatus,
    OperationSummary,
    OperatorMessage,
    PolicyCategory,
    PolicyCoverage,
    PolicyCoverageStatus,
    PolicyEntry,
    PolicyStatus,
    ProjectProfile,
    RunEvent,
    RunEventKind,
    RuntimeHints,
    SchedulerState,
    SessionRecord,
    SessionRecordStatus,
    SessionStatus,
    TaskDraft,
    TaskPatch,
    TaskState,
    TaskStatus,
    TraceBriefBundle,
    TypedRefs,
    WakeupRef,
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
                "effective_adapter_settings": {
                    "codex_acp": {"model": "gpt-5.4", "reasoning_effort": "low"}
                },
                "allowed_execution_profiles": {
                    "codex_acp": [
                        {"model": "gpt-5.4", "reasoning_effort": "low"},
                        {"model": "gpt-5.4-mini", "reasoning_effort": "medium"},
                    ]
                },
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
                execution_profile_stamp=ExecutionProfileStamp(
                    adapter_key="codex_acp",
                    model="gpt-5.4",
                    effort_field_name="reasoning_effort",
                    effort_value="low",
                ),
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
    assert payload["execution_profiles"]["codex_acp"]["default"]["model"] == "gpt-5.4"
    assert payload["execution_profiles"]["codex_acp"]["effective"]["effort_value"] == "low"
    assert payload["project_context"]["profile_name"] == "operator"
    assert payload["available_agent_descriptors"] == [{"key": "codex_acp"}]
    assert payload["open_attention"][0]["attention_id"] == "att-1"


def test_build_operation_context_payload_includes_execution_profile_overlay() -> None:
    operation = _operation()
    operation.execution_profile_overrides["codex_acp"] = ExecutionProfileOverride(
        adapter_key="codex_acp",
        model="gpt-5.4-mini",
        reasoning_effort="medium",
    )

    payload = OperationProjectionService().build_operation_context_payload(operation)

    codex = payload["execution_profiles"]["codex_acp"]
    assert codex["default"]["model"] == "gpt-5.4"
    assert codex["overlay"]["model"] == "gpt-5.4-mini"
    assert codex["effective"]["reasoning_effort"] == "medium"
    assert codex["allowed_models"][1]["model"] == "gpt-5.4-mini"


def test_session_payload_includes_execution_profile_stamp() -> None:
    payload = OperationProjectionService().session_payload(_operation().sessions[0])

    assert payload["execution_profile_stamp"] == {
        "adapter_key": "codex_acp",
        "model": "gpt-5.4",
        "effort_field_name": "reasoning_effort",
        "effort_value": "low",
    }


def test_build_operation_context_payload_includes_unknown_active_session_execution_profile(
) -> None:
    operation = _operation()
    operation.sessions[0].execution_profile_stamp = None

    payload = OperationProjectionService().build_operation_context_payload(operation)

    assert payload["active_session_execution_profile"] == {
        "session_id": "session-1",
        "adapter_key": "codex_acp",
        "known": False,
        "model": None,
        "effort_field_name": None,
        "effort_value": None,
        "display": "unknown",
    }


def test_build_operation_context_payload_is_derived_without_truth_model_dump_patchup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    operation = _operation()
    operation.current_focus = FocusState(
        kind=FocusKind.SESSION,
        target_id="session-1",
        mode=FocusMode.ADVISORY,
    )
    operation.policy_coverage = PolicyCoverage(
        status=PolicyCoverageStatus.COVERED,
        project_scope="profile:operator",
        scoped_policy_count=1,
        active_policy_count=1,
        summary="1 active policy entry applies now.",
    )
    operation.active_policies = [
        PolicyEntry(
            project_scope="profile:operator",
            title="Use codex",
            category=PolicyCategory.GENERAL,
            rule_text="Prefer codex_acp.",
            status=PolicyStatus.ACTIVE,
        )
    ]

    def _fail_focus_model_dump(self, *args, **kwargs):
        raise AssertionError("context payload should not serialize FocusState directly")

    def _fail_attention_model_dump(self, *args, **kwargs):
        raise AssertionError("context payload should not serialize AttentionRequest directly")

    def _fail_policy_coverage_model_dump(self, *args, **kwargs):
        raise AssertionError("context payload should not serialize PolicyCoverage directly")

    def _fail_policy_entry_model_dump(self, *args, **kwargs):
        raise AssertionError("context payload should not serialize PolicyEntry directly")

    monkeypatch.setattr(type(operation.current_focus), "model_dump", _fail_focus_model_dump)
    monkeypatch.setattr(AttentionRequest, "model_dump", _fail_attention_model_dump)
    monkeypatch.setattr(PolicyCoverage, "model_dump", _fail_policy_coverage_model_dump)
    monkeypatch.setattr(PolicyEntry, "model_dump", _fail_policy_entry_model_dump)

    payload = OperationProjectionService().build_operation_context_payload(operation)

    assert payload["current_focus"]["target_id"] == "session-1"
    assert payload["open_attention"][0]["attention_id"] == "att-1"
    assert payload["policy_coverage"]["status"] == "covered"
    assert payload["active_policies"][0]["title"] == "Use codex"


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


def test_build_fleet_payload_uses_explicit_agenda_item_serializer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    item = AgendaItem(
        operation_id="op-1",
        bucket=AgendaBucket.ACTIVE,
        status=OperationStatus.RUNNING,
        scheduler_state=SchedulerState.ACTIVE,
        involvement_level=InvolvementLevel.COLLABORATIVE,
        objective_brief="Ship dashboard",
        runtime_alert="wakeup pending",
        updated_at=datetime.now(UTC),
    )

    def _fail_agenda_item_model_dump(self, *args, **kwargs):
        raise AssertionError("build_fleet_payload should not serialize AgendaItem directly")

    monkeypatch.setattr(AgendaItem, "model_dump", _fail_agenda_item_model_dump)

    payload = OperationProjectionService().build_fleet_payload(
        AgendaSnapshot(total_operations=1, needs_attention=[], active=[item], recent=[]),
        project=None,
    )

    assert payload["active"][0]["operation_id"] == "op-1"
    assert payload["active"][0]["runtime_alert"] == "wakeup pending"
    assert payload["active"][0]["bucket"] == "active"


def test_build_session_view_payload_includes_selected_event_details() -> None:
    operation = _operation_with_task_session()
    service = OperationProjectionService()
    event = RunEvent(
        event_type="agent.invocation.completed",
        kind=RunEventKind.TRACE,
        category="domain",
        operation_id="op-1",
        iteration=3,
        task_id="task-1",
        session_id="session-1",
        timestamp=datetime(2026, 4, 12, 9, 30, 0, tzinfo=UTC),
        payload={
            "status": AgentResultStatus.SUCCESS.value,
            "output_text": "Implemented the session detail projection and verified the output.",
            "artifacts": [
                AgentArtifact(
                    name="session-note.md",
                    kind="note",
                    content="Captured the session rendering decision and next steps.",
                ).model_dump(mode="json")
            ],
        },
    )

    payload = service.build_session_view_payload(
        operation_id="op-1",
        task=operation.tasks[0],
        session=operation.sessions[0],
        events=[event],
        open_attention=[],
    )

    selected_event = payload["selected_event"]
    assert selected_event["timestamp"] == "2026-04-12T09:30:00+00:00"
    assert selected_event["detail"]["status"] == "success"
    assert (
        selected_event["detail"]["output_text"]
        == "Implemented the session detail projection and verified the output."
    )
    assert selected_event["detail"]["artifacts"] == [
        {
            "name": "session-note.md",
            "kind": "note",
            "uri": None,
            "content": "Captured the session rendering decision and next steps.",
        }
    ]


def test_build_dashboard_payload_uses_derived_event_fallback_without_run_event_model_dump(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    operation = _operation_with_task_session()
    event = RunEvent(
        event_type="custom.event",
        kind=RunEventKind.TRACE,
        category="domain",
        operation_id="op-1",
        iteration=2,
        task_id="task-1",
        session_id="session-1",
        payload={"summary": "Custom dashboard event."},
        raw={"source": "test"},
    )

    def _fail_run_event_model_dump(self, *args, **kwargs):
        raise AssertionError("dashboard payload should not serialize RunEvent directly")

    monkeypatch.setattr(RunEvent, "model_dump", _fail_run_event_model_dump)

    payload = OperationProjectionService().build_dashboard_payload(
        operation,
        brief=None,
        outcome=None,
        runtime_alert=None,
        commands=[],
        events=[event],
        decision_memos=[],
        upstream_transcript=None,
        report_text=None,
    )

    assert payload["recent_events"]
    assert "custom.event" in payload["recent_events"][0]


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


def test_build_project_dashboard_payload_uses_explicit_profile_serializer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    profile = ProjectProfile(name="operator", cwd=Path("/tmp/operator"))

    def _fail_profile_model_dump(self, *args, **kwargs):
        raise AssertionError(
            "project dashboard payload should not serialize ProjectProfile directly"
        )

    monkeypatch.setattr(ProjectProfile, "model_dump", _fail_profile_model_dump)

    payload = OperationProjectionService().build_project_dashboard_payload(
        profile=profile,
        resolved={},
        profile_path=Path("/tmp/operator-profile.yaml"),
        fleet={"actions": []},
        active_policies=[],
    )

    assert payload["profile"]["name"] == "operator"
    assert payload["profile"]["cwd"] == "/tmp/operator"


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


def test_operation_payload_is_derived_without_truth_model_dump_patchup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    operation = _operation_with_task_session()
    service = OperationProjectionService()

    def _fail_operation_model_dump(self, *args, **kwargs):
        raise AssertionError("operation_payload should not serialize OperationState directly")

    def _fail_session_model_dump(self, *args, **kwargs):
        raise AssertionError("operation_payload should not serialize SessionRecord directly")

    monkeypatch.setattr(OperationState, "model_dump", _fail_operation_model_dump)
    monkeypatch.setattr(SessionRecord, "model_dump", _fail_session_model_dump)

    payload = service.operation_payload(operation)

    assert payload["operation_id"] == "op-1"
    assert payload["goal"]["objective"] == "Ship dashboard"
    assert payload["sessions"][0]["session_id"] == "session-1"
    assert payload["sessions"][0]["adapter_key"] == "codex_acp"
    assert payload["sessions"][0]["waiting_reason"] == "Working"
    assert payload["sessions"][0]["bound_task_ids"] == ["task-1"]


def test_operation_payload_uses_explicit_truth_serializers_for_targeted_objects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    operation = _operation_with_task_session()
    operation.current_focus = FocusState(
        kind=FocusKind.SESSION,
        target_id="session-1",
        mode=FocusMode.ADVISORY,
    )
    operation.goal.external_ticket = ExternalTicketLink(
        provider="github_issues",
        project_key="owner/repo",
        ticket_id="123",
        url="https://github.com/owner/repo/issues/123",
        title="Ship dashboard",
    )
    operation.objective_state.summary = "Dashboard delivery is underway."
    operation.artifacts = [
        ArtifactRecord(
            artifact_id="artifact-1",
            kind="note",
            producer="codex_acp",
            task_id="task-1",
            session_id="session-1",
            content="Captured the implementation plan.",
            raw_ref="log://artifact-1",
        )
    ]
    operation.operator_messages = [
        OperatorMessage(
            message_id="msg-1",
            text="Stay inside the projection boundary.",
            source_command_id="cmd-1",
            dropped_from_context=True,
            planning_cycles_active=2,
        )
    ]
    operation.active_policies = [
        PolicyEntry(
            policy_id="policy-1",
            project_scope="profile:operator",
            title="Use codex",
            category=PolicyCategory.GENERAL,
            rule_text="Prefer codex_acp.",
            status=PolicyStatus.ACTIVE,
        )
    ]
    operation.policy_coverage = PolicyCoverage(
        status=PolicyCoverageStatus.COVERED,
        project_scope="profile:operator",
        scoped_policy_count=1,
        active_policy_count=1,
        summary="1 active policy entry applies now.",
    )

    def _fail_external_ticket_model_dump(self, *args, **kwargs):
        raise AssertionError("operation_payload should not serialize ExternalTicketLink directly")

    def _fail_objective_model_dump(self, *args, **kwargs):
        raise AssertionError("operation_payload should not serialize ObjectiveState directly")

    def _fail_task_model_dump(self, *args, **kwargs):
        raise AssertionError("operation_payload should not serialize TaskState directly")

    def _fail_artifact_model_dump(self, *args, **kwargs):
        raise AssertionError("operation_payload should not serialize ArtifactRecord directly")

    def _fail_memory_model_dump(self, *args, **kwargs):
        raise AssertionError("operation_payload should not serialize MemoryEntry directly")

    def _fail_attention_model_dump(self, *args, **kwargs):
        raise AssertionError("operation_payload should not serialize AttentionRequest directly")

    def _fail_policy_entry_model_dump(self, *args, **kwargs):
        raise AssertionError("operation_payload should not serialize PolicyEntry directly")

    def _fail_policy_coverage_model_dump(self, *args, **kwargs):
        raise AssertionError("operation_payload should not serialize PolicyCoverage directly")

    def _fail_operator_message_model_dump(self, *args, **kwargs):
        raise AssertionError("operation_payload should not serialize OperatorMessage directly")

    def _fail_focus_model_dump(self, *args, **kwargs):
        raise AssertionError("operation_payload should not serialize FocusState directly")

    monkeypatch.setattr(ExternalTicketLink, "model_dump", _fail_external_ticket_model_dump)
    monkeypatch.setattr(type(operation.objective_state), "model_dump", _fail_objective_model_dump)
    monkeypatch.setattr(TaskState, "model_dump", _fail_task_model_dump)
    monkeypatch.setattr(ArtifactRecord, "model_dump", _fail_artifact_model_dump)
    monkeypatch.setattr(MemoryEntry, "model_dump", _fail_memory_model_dump)
    monkeypatch.setattr(AttentionRequest, "model_dump", _fail_attention_model_dump)
    monkeypatch.setattr(PolicyEntry, "model_dump", _fail_policy_entry_model_dump)
    monkeypatch.setattr(PolicyCoverage, "model_dump", _fail_policy_coverage_model_dump)
    monkeypatch.setattr(OperatorMessage, "model_dump", _fail_operator_message_model_dump)
    monkeypatch.setattr(FocusState, "model_dump", _fail_focus_model_dump)

    payload = OperationProjectionService().operation_payload(operation)

    assert payload["goal"]["external_ticket"]["ticket_id"] == "123"
    assert payload["objective"]["summary"] == "Dashboard delivery is underway."
    assert payload["tasks"][0]["task_id"] == "task-1"
    assert payload["artifacts"][0]["artifact_id"] == "artifact-1"
    assert payload["memory_entries"][0]["memory_id"] == "m1"
    assert payload["attention_requests"][0]["attention_id"] == "att-1"
    assert payload["active_policies"][0]["policy_id"] == "policy-1"
    assert payload["policy_coverage"]["status"] == "covered"
    assert payload["operator_messages"][0]["message_id"] == "msg-1"
    assert payload["current_focus"]["target_id"] == "session-1"


def test_operation_payload_uses_explicit_truth_serializers_for_remaining_read_models(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    operation = _operation_with_task_session()
    operation.features = [
        FeatureState(
            feature_id="feature-1",
            title="Dashboard",
            acceptance_criteria="Projection payload is fully derived.",
        )
    ]
    operation.executions = [
        ExecutionState(
            execution_id="exec-1",
            operation_id="op-1",
            adapter_key="codex_acp",
            session_id="session-1",
            task_id="task-1",
        )
    ]
    operation.operation_brief = OperationBrief(
        operation_id="op-1",
        status=OperationStatus.RUNNING,
        objective_brief="Ship dashboard",
    )
    operation.iteration_briefs = [
        IterationBrief(
            iteration=1,
            task_id="task-1",
            session_id="session-1",
            operator_intent_brief="Inspect the current payload path.",
            assignment_brief="Check operation_payload direct serializations.",
            status_brief="running",
        )
    ]
    operation.agent_turn_briefs = [
        AgentTurnBrief(
            operation_id="op-1",
            iteration=1,
            agent_key="codex_acp",
            session_id="session-1",
            assignment_brief="Inspect the payload path.",
            result_brief="Found remaining direct model dumps.",
            status="completed",
        )
    ]
    operation.pending_wakeups = [
        WakeupRef(
            event_id="evt-1",
            event_type="agent.completed",
            task_id="task-1",
            session_id="session-1",
        )
    ]

    def _fail_feature_model_dump(self, *args, **kwargs):
        raise AssertionError("operation_payload should not serialize FeatureState directly")

    def _fail_execution_model_dump(self, *args, **kwargs):
        raise AssertionError("operation_payload should not serialize ExecutionState directly")

    def _fail_operation_brief_model_dump(self, *args, **kwargs):
        raise AssertionError("operation_payload should not serialize OperationBrief directly")

    def _fail_iteration_brief_model_dump(self, *args, **kwargs):
        raise AssertionError("operation_payload should not serialize IterationBrief directly")

    def _fail_agent_turn_brief_model_dump(self, *args, **kwargs):
        raise AssertionError("operation_payload should not serialize AgentTurnBrief directly")

    def _fail_wakeup_model_dump(self, *args, **kwargs):
        raise AssertionError("operation_payload should not serialize WakeupRef directly")

    monkeypatch.setattr(FeatureState, "model_dump", _fail_feature_model_dump)
    monkeypatch.setattr(ExecutionState, "model_dump", _fail_execution_model_dump)
    monkeypatch.setattr(OperationBrief, "model_dump", _fail_operation_brief_model_dump)
    monkeypatch.setattr(IterationBrief, "model_dump", _fail_iteration_brief_model_dump)
    monkeypatch.setattr(AgentTurnBrief, "model_dump", _fail_agent_turn_brief_model_dump)
    monkeypatch.setattr(WakeupRef, "model_dump", _fail_wakeup_model_dump)

    payload = OperationProjectionService().operation_payload(operation)

    assert payload["features"][0]["feature_id"] == "feature-1"
    assert payload["executions"][0]["execution_id"] == "exec-1"
    assert payload["operation_brief"]["objective_brief"] == "Ship dashboard"
    assert payload["iteration_briefs"][0]["assignment_brief"] == (
        "Check operation_payload direct serializations."
    )
    assert payload["agent_turn_briefs"][0]["result_brief"] == "Found remaining direct model dumps."
    assert payload["pending_wakeups"][0]["event_id"] == "evt-1"


def test_operation_payload_uses_derived_iteration_subpayloads(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    operation = _operation_with_task_session()
    operation.iterations = [
        IterationState(
            index=1,
            decision=BrainDecision(
                action_type=BrainActionType.START_AGENT,
                target_agent="codex_acp",
                rationale="Need implementation progress.",
            ),
            task_id="task-1",
            session=AgentSessionHandle(
                adapter_key="codex_acp",
                session_id="session-1",
                session_name="dash",
            ),
            result=AgentResult(
                session_id="session-1",
                status=AgentResultStatus.SUCCESS,
                output_text="Implemented the projection change.",
                artifacts=[
                    AgentArtifact(
                        name="projection-note.md",
                        kind="note",
                        content="Captured the derived serializer update.",
                    )
                ],
            ),
            turn_summary=AgentTurnSummary(
                declared_goal="Remove direct iteration serialization.",
                actual_work_done="Switched to explicit derived payloads.",
                state_delta="Iteration payload no longer uses model_dump directly.",
                verification_status="Targeted tests passed.",
                recommended_next_step="Run the full test suite.",
            ),
            notes=["Keep the projection change local."],
        )
    ]

    def _fail_decision_model_dump(self, *args, **kwargs):
        raise AssertionError("operation_payload should not serialize BrainDecision directly")

    def _fail_session_handle_model_dump(self, *args, **kwargs):
        raise AssertionError("operation_payload should not serialize AgentSessionHandle directly")

    def _fail_result_model_dump(self, *args, **kwargs):
        raise AssertionError("operation_payload should not serialize AgentResult directly")

    def _fail_iteration_model_dump(self, *args, **kwargs):
        raise AssertionError("operation_payload should not serialize IterationState directly")

    monkeypatch.setattr(IterationState, "model_dump", _fail_iteration_model_dump)
    monkeypatch.setattr(BrainDecision, "model_dump", _fail_decision_model_dump)
    monkeypatch.setattr(AgentSessionHandle, "model_dump", _fail_session_handle_model_dump)
    monkeypatch.setattr(AgentResult, "model_dump", _fail_result_model_dump)

    payload = OperationProjectionService().operation_payload(operation)

    iteration_payload = payload["iterations"][0]
    assert iteration_payload["decision"]["action_type"] == "start_agent"
    assert iteration_payload["session"]["session_id"] == "session-1"
    assert iteration_payload["result"]["status"] == "success"
    assert iteration_payload["turn_summary"]["actual_work_done"] == (
        "Switched to explicit derived payloads."
    )


def test_operation_payload_uses_explicit_serializers_for_remaining_nested_read_models(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    operation = _operation_with_task_session()
    operation.memory_entries[0].source_refs = [
        MemorySourceRef(kind="artifact", ref_id="artifact-1")
    ]
    operation.executions = [
        ExecutionState(
            execution_id="exec-1",
            operation_id="op-1",
            adapter_key="codex_acp",
            session_id="session-1",
            task_id="task-1",
            handle_ref=ExecutionHandleRef(
                kind="pid",
                value="1234",
                metadata={"source": "runtime"},
            ),
            progress=BackgroundProgressSnapshot(
                state=SessionStatus.RUNNING,
                message="Streaming",
                updated_at=datetime.now(UTC),
                partial_output="halfway there",
            ),
        )
    ]
    operation.iteration_briefs = [
        IterationBrief(
            iteration=1,
            task_id="task-1",
            session_id="session-1",
            operator_intent_brief="Inspect nested serializer coverage.",
            assignment_brief="Exercise the remaining payload helpers.",
            status_brief="running",
            refs=TypedRefs(
                operation_id="op-1",
                iteration=1,
                task_id="task-1",
                session_id="session-1",
                artifact_id="artifact-1",
            ),
        )
    ]
    operation.iterations = [
        IterationState(
            index=1,
            decision=BrainDecision(
                action_type=BrainActionType.START_AGENT,
                target_agent="codex_acp",
                instruction="Keep serializers explicit.",
                rationale="Need full nested coverage for the remaining payload helpers.",
                new_features=[
                    FeatureDraft(
                        title="Derived payload",
                        acceptance_criteria="No direct nested serialization remains.",
                        notes=["capture coverage"],
                    )
                ],
                feature_updates=[
                    FeaturePatch(
                        feature_id="feature-1",
                        title="Derived payload update",
                        append_notes=["nested serializer path"],
                    )
                ],
                new_tasks=[
                    TaskDraft(
                        title="Add regression",
                        goal="Cover nested payload models",
                        definition_of_done="Regression fails on model_dump fallback",
                        notes=["keep bounded"],
                    )
                ],
                task_updates=[
                    TaskPatch(
                        task_id="task-1",
                        append_notes=["serializer regression added"],
                    )
                ],
                blocking_focus=BlockingFocus(
                    kind=FocusKind.SESSION,
                    target_id="session-1",
                    blocking_reason="Need explicit nested serializer coverage.",
                ),
            ),
            session=AgentSessionHandle(
                adapter_key="codex_acp",
                session_id="session-1",
            ),
            result=AgentResult(
                session_id="session-1",
                status=AgentResultStatus.SUCCESS,
                artifacts=[
                    AgentArtifact(
                        name="note.md",
                        kind="note",
                        metadata={"source": "test"},
                    )
                ],
                error=AgentError(
                    code="none",
                    message="no error",
                    raw={"detail": "synthetic"},
                ),
                usage=AgentUsage(
                    input_tokens=10,
                    output_tokens=20,
                    total_tokens=30,
                    metadata={"model": "gpt-5.4"},
                ),
            ),
            turn_summary=AgentTurnSummary(
                declared_goal="Keep nested serializers explicit.",
                actual_work_done="Covered the remaining nested payload helpers.",
                state_delta="Operation payload stays derived end-to-end.",
                verification_status="Targeted regression exercised.",
                recommended_next_step="Run the full suite.",
            ),
        )
    ]
    operation.agent_turn_briefs = [
        AgentTurnBrief(
            operation_id="op-1",
            iteration=1,
            agent_key="codex_acp",
            session_id="session-1",
            assignment_brief="Verify the nested serializer path.",
            turn_summary=AgentTurnSummary(
                declared_goal="Summarize nested serializer work.",
                actual_work_done="Used explicit helper payloads.",
                state_delta="No nested model_dump fallback remains.",
                verification_status="Regression added.",
                recommended_next_step="Run projection tests.",
            ),
            status="completed",
        )
    ]

    def _fail_memory_source_ref_model_dump(self, *args, **kwargs):
        raise AssertionError("operation_payload should not serialize MemorySourceRef directly")

    def _fail_typed_refs_model_dump(self, *args, **kwargs):
        raise AssertionError("operation_payload should not serialize TypedRefs directly")

    def _fail_execution_handle_ref_model_dump(self, *args, **kwargs):
        raise AssertionError("operation_payload should not serialize ExecutionHandleRef directly")

    def _fail_background_progress_model_dump(self, *args, **kwargs):
        raise AssertionError(
            "operation_payload should not serialize BackgroundProgressSnapshot directly"
        )

    def _fail_feature_draft_model_dump(self, *args, **kwargs):
        raise AssertionError("operation_payload should not serialize FeatureDraft directly")

    def _fail_feature_patch_model_dump(self, *args, **kwargs):
        raise AssertionError("operation_payload should not serialize FeaturePatch directly")

    def _fail_task_draft_model_dump(self, *args, **kwargs):
        raise AssertionError("operation_payload should not serialize TaskDraft directly")

    def _fail_task_patch_model_dump(self, *args, **kwargs):
        raise AssertionError("operation_payload should not serialize TaskPatch directly")

    def _fail_blocking_focus_model_dump(self, *args, **kwargs):
        raise AssertionError("operation_payload should not serialize BlockingFocus directly")

    def _fail_agent_artifact_model_dump(self, *args, **kwargs):
        raise AssertionError("operation_payload should not serialize AgentArtifact directly")

    def _fail_agent_error_model_dump(self, *args, **kwargs):
        raise AssertionError("operation_payload should not serialize AgentError directly")

    def _fail_agent_usage_model_dump(self, *args, **kwargs):
        raise AssertionError("operation_payload should not serialize AgentUsage directly")

    def _fail_agent_turn_summary_model_dump(self, *args, **kwargs):
        raise AssertionError("operation_payload should not serialize AgentTurnSummary directly")

    monkeypatch.setattr(MemorySourceRef, "model_dump", _fail_memory_source_ref_model_dump)
    monkeypatch.setattr(TypedRefs, "model_dump", _fail_typed_refs_model_dump)
    monkeypatch.setattr(ExecutionHandleRef, "model_dump", _fail_execution_handle_ref_model_dump)
    monkeypatch.setattr(
        BackgroundProgressSnapshot,
        "model_dump",
        _fail_background_progress_model_dump,
    )
    monkeypatch.setattr(FeatureDraft, "model_dump", _fail_feature_draft_model_dump)
    monkeypatch.setattr(FeaturePatch, "model_dump", _fail_feature_patch_model_dump)
    monkeypatch.setattr(TaskDraft, "model_dump", _fail_task_draft_model_dump)
    monkeypatch.setattr(TaskPatch, "model_dump", _fail_task_patch_model_dump)
    monkeypatch.setattr(BlockingFocus, "model_dump", _fail_blocking_focus_model_dump)
    monkeypatch.setattr(AgentArtifact, "model_dump", _fail_agent_artifact_model_dump)
    monkeypatch.setattr(AgentError, "model_dump", _fail_agent_error_model_dump)
    monkeypatch.setattr(AgentUsage, "model_dump", _fail_agent_usage_model_dump)
    monkeypatch.setattr(AgentTurnSummary, "model_dump", _fail_agent_turn_summary_model_dump)

    payload = OperationProjectionService().operation_payload(operation)

    assert payload["memory_entries"][0]["source_refs"][0]["ref_id"] == "artifact-1"
    assert payload["executions"][0]["handle_ref"]["kind"] == "pid"
    assert payload["executions"][0]["progress"]["message"] == "Streaming"
    assert payload["iteration_briefs"][0]["refs"]["artifact_id"] == "artifact-1"
    assert payload["iterations"][0]["decision"]["new_features"][0]["title"] == "Derived payload"
    assert payload["iterations"][0]["decision"]["task_updates"][0]["task_id"] == "task-1"
    assert payload["iterations"][0]["decision"]["blocking_focus"]["target_id"] == "session-1"
    assert payload["iterations"][0]["result"]["artifacts"][0]["name"] == "note.md"
    assert payload["iterations"][0]["result"]["error"]["code"] == "none"
    assert payload["iterations"][0]["result"]["usage"]["total_tokens"] == 30
    assert payload["agent_turn_briefs"][0]["turn_summary"]["actual_work_done"] == (
        "Used explicit helper payloads."
    )


def test_build_durable_truth_payload_uses_explicit_truth_serializers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    operation = _operation_with_task_session()
    operation.artifacts = [
        ArtifactRecord(
            artifact_id="artifact-1",
            kind="note",
            producer="codex_acp",
            task_id="task-1",
            session_id="session-1",
            content="Captured the implementation plan.",
        )
    ]

    def _fail_task_model_dump(self, *args, **kwargs):
        raise AssertionError("build_durable_truth_payload should not serialize TaskState directly")

    def _fail_memory_model_dump(self, *args, **kwargs):
        raise AssertionError(
            "build_durable_truth_payload should not serialize MemoryEntry directly"
        )

    def _fail_artifact_model_dump(self, *args, **kwargs):
        raise AssertionError(
            "build_durable_truth_payload should not serialize ArtifactRecord directly"
        )

    monkeypatch.setattr(TaskState, "model_dump", _fail_task_model_dump)
    monkeypatch.setattr(MemoryEntry, "model_dump", _fail_memory_model_dump)
    monkeypatch.setattr(ArtifactRecord, "model_dump", _fail_artifact_model_dump)

    payload = OperationProjectionService().build_durable_truth_payload(
        operation,
        include_inactive_memory=True,
    )

    assert payload["tasks"][0]["task_id"] == "task-1"
    assert payload["memory"]["current"][0]["memory_id"] == "m1"
    assert payload["memory"]["inactive"][0]["memory_id"] == "m2"
    assert payload["artifacts"][0]["artifact_id"] == "artifact-1"


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
    assert snapshot["active_session_execution_profile"]["display"] == "gpt-5.4 / low"

    rendered = service.format_live_snapshot(snapshot)
    assert "state: running" in rendered
    assert "objective=Ship dashboard" in rendered
    assert "alert=rate limit soon" in rendered


def test_build_dashboard_payload_includes_active_session_execution_profile() -> None:
    operation = _operation()
    payload = OperationProjectionService().build_dashboard_payload(
        operation,
        brief=None,
        outcome=None,
        runtime_alert=None,
        commands=[],
        events=[],
        decision_memos=[],
        upstream_transcript=None,
        report_text=None,
    )

    assert payload["active_session"]["execution_profile"]["model"] == "gpt-5.4"
    assert payload["sessions"][0]["execution_profile_stamp"]["effort_value"] == "low"


def test_brief_summary_and_live_snapshot_use_explicit_agent_turn_serializer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    operation = _operation()
    brief = TraceBriefBundle(
        agent_turn_briefs=[
            AgentTurnBrief(
                operation_id="op-1",
                iteration=2,
                agent_key="codex_acp",
                session_id="session-1",
                assignment_brief="Implement the projection serializer.",
                result_brief="Serializer landed cleanly.",
                status="completed",
            )
        ]
    )

    def _fail_agent_turn_brief_model_dump(self, *args, **kwargs):
        raise AssertionError(
            "brief/live snapshot payloads should not serialize AgentTurnBrief directly"
        )

    monkeypatch.setattr(AgentTurnBrief, "model_dump", _fail_agent_turn_brief_model_dump)

    service = OperationProjectionService()
    summary = service.build_brief_summary_payload(operation, brief, runtime_alert=None)
    snapshot = service.build_live_snapshot(operation, brief, runtime_alert=None)

    assert summary["latest_turn"]["iteration"] == 2
    assert summary["latest_turn"]["agent_key"] == "codex_acp"
    assert snapshot["latest_turn"]["session_id"] == "session-1"


def test_render_dashboard_prefers_runtime_alert_over_waiting_reason() -> None:
    console = Console(record=True, width=140, markup=False)
    group = render_dashboard(
        {
            "status": "running",
            "scheduler_state": "active",
            "run_mode": "attached",
            "involvement_level": "auto",
            "objective": "Ship dashboard",
            "harness_instructions": "Keep delivery thin.",
            "focus": None,
            "task_counts": "running:1",
            "active_session": {
                "session_id": "session-1",
                "adapter_key": "codex_acp",
                "status": "running",
                "waiting_reason": "Agent session completed.",
            },
            "recent_events": [],
            "recent_commands": [],
            "control_hints": [],
            "runtime_alert": "2 wakeup(s) are pending reconciliation.",
        },
        shorten_live_text=lambda text: text,
    )

    console.print(group)
    rendered = console.export_text(styles=False)

    assert "alert: 2 wakeup(s) are pending reconciliation." in rendered
    assert "waiting: Agent session completed." not in rendered


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
