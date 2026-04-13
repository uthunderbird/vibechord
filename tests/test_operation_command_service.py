from __future__ import annotations

from pathlib import Path

import pytest

from agent_operator.acp.permissions import normalize_permission_request
from agent_operator.application import EventSourcedCommandApplicationService
from agent_operator.application.event_sourcing.event_sourced_birth import (
    EventSourcedOperationBirthService,
)
from agent_operator.application.event_sourcing.event_sourced_replay import EventSourcedReplayService
from agent_operator.application.operation_entrypoints import OperationEntrypointService
from agent_operator.domain import (
    AttentionRequest,
    AttentionStatus,
    AttentionType,
    BrainActionType,
    BrainDecision,
    CommandStatus,
    CommandTargetScope,
    FocusKind,
    FocusMode,
    FocusState,
    InvolvementLevel,
    OperationCommand,
    OperationCommandType,
    OperationDomainEventDraft,
    OperationGoal,
    OperationState,
    OperationStatus,
    OperatorMessage,
    PolicyApplicability,
    PolicyCategory,
    PolicyCoverage,
    PolicyCoverageStatus,
    PolicyEntry,
    PolicyStatus,
    RunMode,
    RunOptions,
    SchedulerState,
)
from agent_operator.projectors import DefaultOperationProjector
from agent_operator.providers.permission import ProviderBackedPermissionEvaluator
from agent_operator.providers.prompting import build_decision_prompt
from agent_operator.runtime import FileOperationCheckpointStore, FileOperationEventStore
from agent_operator.testing.operator_service_support import (
    AnswerThenStopBrain,
    FakeAgent,
    MemoryCommandInbox,
    MemoryEventSink,
    MemoryPolicyStore,
    MemoryStore,
    MemoryTraceStore,
    StartThenStopBrain,
    make_service,
    run_settings,
    state_settings,
)
from agent_operator.testing.runtime_bindings import build_test_runtime_bindings


class _EscalatingPermissionProvider:
    async def evaluate_permission_request(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        from agent_operator.dtos import PermissionDecisionDTO

        return PermissionDecisionDTO(
            decision="escalate",
            rationale="Need human judgment.",
            suggested_options=["Approve once", "Reject"],
        )


class _CountingMemoryStore(MemoryStore):
    def __init__(self) -> None:
        super().__init__()
        self.save_calls = 0

    async def save_operation(self, state) -> None:  # type: ignore[no-untyped-def]
        self.save_calls += 1
        await super().save_operation(state)


@pytest.mark.anyio
async def test_answer_attention_request_resolves_after_replan() -> None:
    store = MemoryStore()
    inbox = MemoryCommandInbox()
    event_sink = MemoryEventSink()
    service = make_service(
        brain=AnswerThenStopBrain(),
        store=store,
        trace_store=MemoryTraceStore(),
        event_sink=event_sink,
        agent_runtime_bindings=build_test_runtime_bindings({"claude_acp": FakeAgent()}),
        command_inbox=inbox,
    )

    blocked = await service.run(
        OperationGoal(objective="pick a deployment target"),
        **run_settings(max_iterations=2, allowed_agents=["claude_acp"]),
    )
    operation = await store.load_operation(blocked.operation_id)
    assert operation is not None
    attention = operation.attention_requests[0]

    command = OperationCommand(
        operation_id=operation.operation_id,
        command_type=OperationCommandType.ANSWER_ATTENTION_REQUEST,
        target_scope=CommandTargetScope.ATTENTION_REQUEST,
        target_id=attention.attention_id,
        payload={"text": "Use staging first."},
    )
    await inbox.enqueue(command)

    outcome = await service.resume(
        operation.operation_id,
        options=RunOptions(run_mode=RunMode.ATTACHED, max_cycles=2),
    )
    resumed = await store.load_operation(operation.operation_id)
    assert resumed is not None

    assert outcome.status is OperationStatus.COMPLETED
    resolved = resumed.attention_requests[0]
    assert resolved.status is AttentionStatus.RESOLVED
    assert resolved.answer_text == "Use staging first."
    stored_command = inbox.commands[command.command_id]
    assert stored_command.status is CommandStatus.APPLIED
    attention_events = [
        event.event_type
        for event in event_sink.events
        if event.event_type.startswith("attention.request.")
    ]
    assert attention_events == [
        "attention.request.created",
        "attention.request.resolved",
    ]


@pytest.mark.anyio
async def test_provider_permission_evaluator_rejects_escalation_for_auto_mode() -> None:
    evaluator = ProviderBackedPermissionEvaluator(
        _EscalatingPermissionProvider(),
        store=MemoryStore(),
    )
    state = OperationState(
        goal=OperationGoal(objective="continue work"),
        **state_settings(allowed_agents=["claude_acp"]),
        involvement_level=InvolvementLevel.AUTO,
    )
    await evaluator._store.save_operation(state)
    request = normalize_permission_request(
        adapter_key="claude_acp",
        working_directory=Path("/tmp/repo"),
        payload={
            "jsonrpc": "2.0",
            "id": 7,
            "method": "session/request_permission",
            "params": {
                "sessionId": "sess-1",
                "toolCall": {
                    "title": "Run git status",
                    "rawInput": {"command": ["git", "status"]},
                },
                "options": [
                    {"optionId": "allow", "kind": "allow_once"},
                    {"optionId": "reject", "kind": "reject_once"},
                ],
            },
        },
    )
    assert request is not None

    result = await evaluator.evaluate(
        operation_id=state.operation_id,
        working_directory=Path("/tmp/repo"),
        request=request,
    )

    assert result.decision is not None
    assert result.decision.value == "reject"


@pytest.mark.anyio
async def test_provider_permission_evaluator_allows_escalation_for_approval_heavy() -> None:
    evaluator = ProviderBackedPermissionEvaluator(
        _EscalatingPermissionProvider(),
        store=MemoryStore(),
    )
    state = OperationState(
        goal=OperationGoal(objective="continue work"),
        **state_settings(allowed_agents=["claude_acp"]),
        involvement_level=InvolvementLevel.APPROVAL_HEAVY,
    )
    await evaluator._store.save_operation(state)
    request = normalize_permission_request(
        adapter_key="claude_acp",
        working_directory=Path("/tmp/repo"),
        payload={
            "jsonrpc": "2.0",
            "id": 7,
            "method": "session/request_permission",
            "params": {
                "sessionId": "sess-1",
                "toolCall": {
                    "title": "Run git status",
                    "rawInput": {"command": ["git", "status"]},
                },
                "options": [
                    {"optionId": "allow", "kind": "allow_once"},
                    {"optionId": "reject", "kind": "reject_once"},
                ],
            },
        },
    )
    assert request is not None

    result = await evaluator.evaluate(
        operation_id=state.operation_id,
        working_directory=Path("/tmp/repo"),
        request=request,
    )

    assert result.decision is not None
    assert result.decision.value == "escalate"


@pytest.mark.anyio
async def test_set_involvement_level_command_updates_state_and_replans() -> None:
    store = MemoryStore()
    inbox = MemoryCommandInbox()
    service = make_service(
        brain=StartThenStopBrain(),
        store=store,
        trace_store=MemoryTraceStore(),
        event_sink=MemoryEventSink(),
        agent_runtime_bindings=build_test_runtime_bindings({"claude_acp": FakeAgent()}),
        command_inbox=inbox,
    )

    operation = OperationState(
        goal=OperationGoal(objective="continue work"),
        **state_settings(allowed_agents=["claude_acp"]),
    )
    await store.save_operation(operation)
    command = OperationCommand(
        operation_id=operation.operation_id,
        command_type=OperationCommandType.SET_INVOLVEMENT_LEVEL,
        target_scope=CommandTargetScope.OPERATION,
        target_id=operation.operation_id,
        payload={"level": InvolvementLevel.APPROVAL_HEAVY.value},
    )
    await inbox.enqueue(command)

    outcome = await service.resume(
        operation.operation_id,
        options=RunOptions(run_mode=RunMode.ATTACHED, max_cycles=2),
    )
    updated = await store.load_operation(operation.operation_id)

    assert outcome.status is OperationStatus.COMPLETED
    assert updated is not None
    assert updated.involvement_level is InvolvementLevel.APPROVAL_HEAVY
    assert updated.policy.involvement_level is InvolvementLevel.APPROVAL_HEAVY
    assert inbox.commands[command.command_id].status is CommandStatus.APPLIED


@pytest.mark.anyio
async def test_record_policy_decision_persists_entry_and_refreshes_active_policy_context() -> None:
    store = MemoryStore()
    inbox = MemoryCommandInbox()
    policy_store = MemoryPolicyStore()
    service = make_service(
        brain=StartThenStopBrain(),
        store=store,
        trace_store=MemoryTraceStore(),
        event_sink=MemoryEventSink(),
        agent_runtime_bindings=build_test_runtime_bindings({"claude_acp": FakeAgent()}),
        command_inbox=inbox,
        policy_store=policy_store,
    )

    operation = OperationState(
        goal=OperationGoal(
            objective="continue work",
            metadata={"project_profile_name": "femtobot", "policy_scope": "profile:femtobot"},
        ),
        **state_settings(allowed_agents=["claude_acp"]),
    )
    await store.save_operation(operation)
    command = OperationCommand(
        operation_id=operation.operation_id,
        command_type=OperationCommandType.RECORD_POLICY_DECISION,
        target_scope=CommandTargetScope.OPERATION,
        target_id=operation.operation_id,
        payload={
            "title": "Manual testing debt must be recorded",
            "text": "Write human-only checks to MANUAL_TESTING_REQUIRED.md before completion.",
            "category": PolicyCategory.TESTING.value,
        },
    )
    await inbox.enqueue(command)

    outcome = await service.resume(
        operation.operation_id,
        options=RunOptions(run_mode=RunMode.ATTACHED, max_cycles=2),
    )
    updated = await store.load_operation(operation.operation_id)
    assert updated is not None

    assert outcome.status is OperationStatus.COMPLETED
    assert len(updated.active_policies) == 1
    assert updated.active_policies[0].title == "Manual testing debt must be recorded"
    assert updated.active_policies[0].category is PolicyCategory.TESTING
    assert inbox.commands[command.command_id].status is CommandStatus.APPLIED
    prompt = build_decision_prompt(updated)
    assert "Active project policy:" in prompt
    assert "MANUAL_TESTING_REQUIRED.md" in prompt


@pytest.mark.anyio
async def test_answered_attention_can_be_promoted_to_policy_in_same_resume() -> None:
    store = MemoryStore()
    inbox = MemoryCommandInbox()
    policy_store = MemoryPolicyStore()
    service = make_service(
        brain=StartThenStopBrain(),
        store=store,
        trace_store=MemoryTraceStore(),
        event_sink=MemoryEventSink(),
        agent_runtime_bindings=build_test_runtime_bindings({"claude_acp": FakeAgent()}),
        command_inbox=inbox,
        policy_store=policy_store,
    )

    operation = OperationState(
        goal=OperationGoal(
            objective="continue work",
            metadata={"project_profile_name": "femtobot", "policy_scope": "profile:femtobot"},
        ),
        **state_settings(allowed_agents=["claude_acp"]),
        status=OperationStatus.NEEDS_HUMAN,
        current_focus=FocusState(
            kind=FocusKind.ATTENTION_REQUEST,
            target_id="attention-policy-gap",
            mode=FocusMode.BLOCKING,
        ),
        attention_requests=[
            AttentionRequest(
                operation_id="op-1",
                attention_id="attention-policy-gap",
                attention_type=AttentionType.POLICY_GAP,
                target_scope=CommandTargetScope.OPERATION,
                target_id="op-1",
                title="Testing policy is missing",
                question="What should we do with manual-only checks?",
                status=AttentionStatus.OPEN,
            )
        ],
    )
    await store.save_operation(operation)
    await inbox.enqueue(
        OperationCommand(
            operation_id=operation.operation_id,
            command_type=OperationCommandType.ANSWER_ATTENTION_REQUEST,
            target_scope=CommandTargetScope.ATTENTION_REQUEST,
            target_id="attention-policy-gap",
            payload={"text": "Always record manual-only checks in MANUAL_TESTING_REQUIRED.md."},
        )
    )
    await inbox.enqueue(
        OperationCommand(
            operation_id=operation.operation_id,
            command_type=OperationCommandType.RECORD_POLICY_DECISION,
            target_scope=CommandTargetScope.ATTENTION_REQUEST,
            target_id="attention-policy-gap",
            payload={"category": PolicyCategory.TESTING.value},
        )
    )

    outcome = await service.resume(
        operation.operation_id,
        options=RunOptions(run_mode=RunMode.ATTACHED, max_cycles=2),
    )
    updated = await store.load_operation(operation.operation_id)

    assert outcome.status is OperationStatus.COMPLETED
    assert updated is not None
    assert len(updated.active_policies) == 1
    policy = updated.active_policies[0]
    assert policy.title == "Testing policy is missing"
    assert policy.category is PolicyCategory.TESTING
    assert policy.rule_text == "Always record manual-only checks in MANUAL_TESTING_REQUIRED.md."
    assert [ref.kind for ref in policy.source_refs] == ["command", "attention_request"]


@pytest.mark.anyio
async def test_answered_approval_attention_auto_records_autonomy_policy() -> None:
    store = MemoryStore()
    inbox = MemoryCommandInbox()
    policy_store = MemoryPolicyStore()
    service = make_service(
        brain=StartThenStopBrain(),
        store=store,
        trace_store=MemoryTraceStore(),
        event_sink=MemoryEventSink(),
        agent_runtime_bindings=build_test_runtime_bindings({"claude_acp": FakeAgent()}),
        command_inbox=inbox,
        policy_store=policy_store,
    )

    operation = OperationState(
        goal=OperationGoal(
            objective="continue work",
            metadata={"project_profile_name": "femtobot", "policy_scope": "profile:femtobot"},
        ),
        **state_settings(allowed_agents=["claude_acp"]),
        status=OperationStatus.NEEDS_HUMAN,
        current_focus=FocusState(
            kind=FocusKind.ATTENTION_REQUEST,
            target_id="attention-approval-gap",
            mode=FocusMode.BLOCKING,
        ),
        attention_requests=[
            AttentionRequest(
                operation_id="op-1",
                attention_id="attention-approval-gap",
                attention_type=AttentionType.APPROVAL_REQUEST,
                target_scope=CommandTargetScope.ATTENTION_REQUEST,
                target_id="op-1",
                title="Approve swarm-nova",
                question="Should the operator approve this exact swarm-nova request?",
                status=AttentionStatus.OPEN,
                metadata={
                    "signature": {
                        "adapter_key": "claude_acp",
                        "method": "session/request_permission",
                        "interaction": "approval",
                        "title": "Run skill",
                        "tool_kind": "skill",
                        "skill_name": "swarm-nova",
                        "command": [],
                    },
                    "policy_title": "Claude swarm-nova approval",
                    "policy_rule_text": (
                        "Decision: approve. Exact-match permission signature replay."
                    ),
                },
            )
        ],
    )
    await store.save_operation(operation)
    await inbox.enqueue(
        OperationCommand(
            operation_id=operation.operation_id,
            command_type=OperationCommandType.ANSWER_ATTENTION_REQUEST,
            target_scope=CommandTargetScope.ATTENTION_REQUEST,
            target_id="attention-approval-gap",
            payload={"text": "Approve this exact request."},
        )
    )

    outcome = await service.resume(
        operation.operation_id,
        options=RunOptions(run_mode=RunMode.ATTACHED, max_cycles=2),
    )

    assert outcome.status is OperationStatus.COMPLETED
    assert len(policy_store.entries) == 1
    stored_policy = next(iter(policy_store.entries.values()))
    assert stored_policy.category is PolicyCategory.AUTONOMY
    assert stored_policy.project_scope == "profile:femtobot"
    assert stored_policy.applicability.agent_keys == ["claude_acp"]
    assert len(stored_policy.applicability.permission_signatures) == 1
    signature = stored_policy.applicability.permission_signatures[0]
    assert signature.adapter_key == "claude_acp"
    assert signature.skill_name == "swarm-nova"
    assert stored_policy.rule_text.startswith("Decision: approve")


@pytest.mark.anyio
async def test_provider_permission_evaluator_replays_exact_signature_policy_without_llm() -> None:
    store = MemoryStore()
    policy_store = MemoryPolicyStore()
    operation = OperationState(
        goal=OperationGoal(
            objective="continue work",
            metadata={"project_profile_name": "femtobot", "policy_scope": "profile:femtobot"},
        ),
        **state_settings(allowed_agents=["claude_acp"]),
    )
    await store.save_operation(operation)
    await policy_store.save(
        PolicyEntry(
            project_scope="profile:femtobot",
            title="Claude swarm-nova approval",
            category=PolicyCategory.AUTONOMY,
            rule_text="Decision: approve. Exact-match permission signature replay.",
            applicability=PolicyApplicability(
                agent_keys=["claude_acp"],
                permission_signatures=[
                    {
                        "adapter_key": "claude_acp",
                        "method": "session/request_permission",
                        "interaction": "approval",
                        "title": "Run skill",
                        "tool_kind": "skill",
                        "skill_name": "swarm-nova",
                        "command": [],
                    }
                ],
            ),
        )
    )

    class FailingPermissionProvider:
        async def evaluate_permission_request(self, *args, **kwargs):  # type: ignore[no-untyped-def]
            raise AssertionError("LLM evaluator should not be called when exact policy matches.")

    evaluator = ProviderBackedPermissionEvaluator(
        FailingPermissionProvider(),  # type: ignore[arg-type]
        store=store,
        policy_store=policy_store,
    )
    request = normalize_permission_request(
        adapter_key="claude_acp",
        working_directory=Path("/tmp/femtobot"),
        payload={
            "jsonrpc": "2.0",
            "id": 17,
            "method": "session/request_permission",
            "params": {
                "sessionId": "sess-1",
                "toolCall": {
                    "kind": "skill",
                    "title": "Run skill",
                    "rawInput": {"skill": "swarm-nova"},
                },
                "options": [
                    {"optionId": "allow_always", "kind": "allow_always"},
                    {"optionId": "reject", "kind": "reject_once"},
                ],
            },
        },
    )

    assert request is not None
    result = await evaluator.evaluate(
        operation_id=operation.operation_id,
        working_directory=Path("/tmp/femtobot"),
        request=request,
    )

    assert result.decision.value == "approve"
    assert "Matched stored autonomy policy" in result.rationale


@pytest.mark.anyio
async def test_revoke_policy_decision_marks_policy_inactive() -> None:
    store = MemoryStore()
    inbox = MemoryCommandInbox()
    policy_store = MemoryPolicyStore()
    existing = PolicyEntry(
        project_scope="profile:femtobot",
        title="Old release rule",
        category=PolicyCategory.RELEASE,
        rule_text="Push from a temporary fork.",
    )
    await policy_store.save(existing)
    service = make_service(
        brain=StartThenStopBrain(),
        store=store,
        trace_store=MemoryTraceStore(),
        event_sink=MemoryEventSink(),
        agent_runtime_bindings=build_test_runtime_bindings({"claude_acp": FakeAgent()}),
        command_inbox=inbox,
        policy_store=policy_store,
    )

    operation = OperationState(
        goal=OperationGoal(
            objective="continue work",
            metadata={"project_profile_name": "femtobot", "policy_scope": "profile:femtobot"},
        ),
        **state_settings(allowed_agents=["claude_acp"]),
    )
    await store.save_operation(operation)
    command = OperationCommand(
        operation_id=operation.operation_id,
        command_type=OperationCommandType.REVOKE_POLICY_DECISION,
        target_scope=CommandTargetScope.OPERATION,
        target_id=operation.operation_id,
        payload={"policy_id": existing.policy_id, "reason": "Main repo now exists."},
    )
    await inbox.enqueue(command)

    outcome = await service.resume(
        operation.operation_id,
        options=RunOptions(run_mode=RunMode.ATTACHED, max_cycles=2),
    )
    updated = await store.load_operation(operation.operation_id)
    revoked = await policy_store.load(existing.policy_id)

    assert outcome.status is OperationStatus.COMPLETED
    assert updated is not None
    assert updated.active_policies == []
    assert revoked is not None
    assert revoked.status is PolicyStatus.REVOKED
    assert revoked.revoked_reason == "Main repo now exists."
    assert inbox.commands[command.command_id].status is CommandStatus.APPLIED


@pytest.mark.anyio
async def test_revoke_policy_decision_command_service_uses_replay_backed_persistence(
    tmp_path: Path,
) -> None:
    store = _CountingMemoryStore()
    inbox = MemoryCommandInbox()
    event_sink = MemoryEventSink()
    policy_store = MemoryPolicyStore()
    existing = PolicyEntry(
        project_scope="profile:femtobot",
        title="Old release rule",
        category=PolicyCategory.RELEASE,
        rule_text="Push from a temporary fork.",
    )
    await policy_store.save(existing)
    event_store = FileOperationEventStore(tmp_path / "events")
    checkpoint_store = FileOperationCheckpointStore(tmp_path / "checkpoints")
    projector = DefaultOperationProjector()
    birth_service = EventSourcedOperationBirthService(
        event_store=event_store,
        checkpoint_store=checkpoint_store,
        projector=projector,
    )
    replay_service = EventSourcedReplayService(
        event_store=event_store,
        checkpoint_store=checkpoint_store,
        projector=projector,
    )
    operation_entrypoints = OperationEntrypointService(
        store=store,
        event_sourced_operation_birth_service=birth_service,
        event_sourced_replay_service=replay_service,
    )
    service = make_service(
        brain=StartThenStopBrain(),
        store=store,
        trace_store=MemoryTraceStore(),
        event_sink=event_sink,
        agent_runtime_bindings=build_test_runtime_bindings({"claude_acp": FakeAgent()}),
        command_inbox=inbox,
        policy_store=policy_store,
        event_sourced_operation_birth_service=birth_service,
        operation_entrypoint_service=operation_entrypoints,
        event_sourced_command_service=EventSourcedCommandApplicationService(
            event_store=event_store,
            checkpoint_store=checkpoint_store,
            projector=projector,
        ),
    )

    operation = OperationState(
        operation_id="op-event-revoke-policy",
        goal=OperationGoal(
            objective="continue work",
            metadata={"project_profile_name": "femtobot", "policy_scope": "profile:femtobot"},
        ),
        active_policies=[existing.model_copy(deep=True)],
        policy_coverage=PolicyCoverage(
            status=PolicyCoverageStatus.COVERED,
            project_scope="profile:femtobot",
            scoped_policy_count=1,
            active_policy_count=1,
            summary="1 active policy entry applies now.",
        ),
        **state_settings(allowed_agents=["claude_acp"]),
    )
    await store.save_operation(operation)
    await event_store.append(
        operation.operation_id,
        0,
        [
            OperationDomainEventDraft(
                event_type="operation.created",
                payload={
                    **operation.objective.model_dump(mode="json"),
                    "allowed_agents": ["claude_acp"],
                    "involvement_level": operation.involvement_level.value,
                    "created_at": operation.created_at.isoformat(),
                },
            ),
            OperationDomainEventDraft(
                event_type="policy.active_set.updated",
                payload={
                    "active_policies": [existing.model_dump(mode="json")],
                },
            ),
            OperationDomainEventDraft(
                event_type="policy.coverage.updated",
                payload=operation.policy_coverage.model_dump(mode="json"),
            ),
        ],
    )
    await replay_service.load(operation.operation_id)

    command = OperationCommand(
        operation_id=operation.operation_id,
        command_type=OperationCommandType.REVOKE_POLICY_DECISION,
        target_scope=CommandTargetScope.OPERATION,
        target_id=operation.operation_id,
        payload={"policy_id": existing.policy_id, "reason": "Main repo now exists."},
    )
    await inbox.enqueue(command)

    outcome = await service.resume(
        operation.operation_id,
        options=RunOptions(run_mode=RunMode.ATTACHED, max_cycles=2),
    )
    assert outcome.status is OperationStatus.COMPLETED

    updated = await store.load_operation(operation.operation_id)
    assert updated is not None
    assert updated.active_policies == []
    assert updated.policy_coverage.active_policy_count == 0
    assert inbox.commands[command.command_id].status is CommandStatus.APPLIED

    events = await event_store.load_after(operation.operation_id, after_sequence=0)
    assert [event.event_type for event in events] == [
        "operation.created",
        "policy.active_set.updated",
        "policy.coverage.updated",
        "command.accepted",
        "policy.active_set.updated",
        "policy.coverage.updated",
    ]

    stale_snapshot = operation.model_copy(deep=True)
    replayed = await operation_entrypoints._load_event_sourced(  # noqa: SLF001 - regression check
        operation.operation_id,
        fallback_state=stale_snapshot,
    )
    assert replayed.active_policies == []
    assert replayed.policy_coverage.active_policy_count == 0
    assert command.command_id in replayed.processed_command_ids

    revoked = await policy_store.load(existing.policy_id)
    assert revoked is not None
    assert revoked.status is PolicyStatus.REVOKED
    assert revoked.revoked_reason == "Main repo now exists."


@pytest.mark.anyio
async def test_patch_objective_command_updates_objective_and_becomes_applied_after_replan() -> None:
    store = MemoryStore()
    command_inbox = MemoryCommandInbox()
    service = make_service(
        brain=StartThenStopBrain(),
        store=store,
        trace_store=MemoryTraceStore(),
        event_sink=MemoryEventSink(),
        agent_runtime_bindings=build_test_runtime_bindings({"claude_acp": FakeAgent()}),
        command_inbox=command_inbox,
    )

    command = OperationCommand(
        operation_id="op-patch-objective",
        command_type=OperationCommandType.PATCH_OBJECTIVE,
        target_scope=CommandTargetScope.OPERATION,
        target_id="op-patch-objective",
        payload={"text": "Audit the release workflow and leave concrete next steps."},
    )
    await command_inbox.enqueue(command)

    outcome = await service.run(
        OperationGoal(objective="do the task"),
        **run_settings(max_iterations=4, allowed_agents=["claude_acp"]),
        options=RunOptions(run_mode=RunMode.ATTACHED),
        operation_id="op-patch-objective",
    )

    operation = await store.load_operation(outcome.operation_id)
    commands = await command_inbox.list(outcome.operation_id)
    assert operation is not None
    assert operation.objective_state.objective == (
        "Audit the release workflow and leave concrete next steps."
    )
    assert commands[0].status is CommandStatus.APPLIED
    assert commands[0].applied_at is not None
    assert command.command_id in operation.processed_command_ids
    assert await command_inbox.list_pending_planning_triggers(outcome.operation_id) == []


@pytest.mark.anyio
async def test_event_sourced_patch_objective_command_appends_canonical_events(
    tmp_path: Path,
) -> None:
    store = MemoryStore()
    command_inbox = MemoryCommandInbox()
    event_store = FileOperationEventStore(tmp_path / "events")
    checkpoint_store = FileOperationCheckpointStore(tmp_path / "checkpoints")
    projector = DefaultOperationProjector()
    birth_service = EventSourcedOperationBirthService(
        event_store=event_store,
        checkpoint_store=checkpoint_store,
        projector=projector,
    )
    replay_service = EventSourcedReplayService(
        event_store=event_store,
        checkpoint_store=checkpoint_store,
        projector=projector,
    )
    service = make_service(
        brain=StartThenStopBrain(),
        store=store,
        trace_store=MemoryTraceStore(),
        event_sink=MemoryEventSink(),
        agent_runtime_bindings=build_test_runtime_bindings({"claude_acp": FakeAgent()}),
        command_inbox=command_inbox,
        event_sourced_operation_birth_service=birth_service,
        operation_entrypoint_service=OperationEntrypointService(
            store=store,
            event_sourced_operation_birth_service=birth_service,
            event_sourced_replay_service=replay_service,
        ),
        event_sourced_command_service=EventSourcedCommandApplicationService(
            event_store=event_store,
            checkpoint_store=checkpoint_store,
            projector=projector,
        ),
    )

    command = OperationCommand(
        operation_id="op-event-patch-objective",
        command_type=OperationCommandType.PATCH_OBJECTIVE,
        target_scope=CommandTargetScope.OPERATION,
        target_id="op-event-patch-objective",
        payload={"text": "Canonical event-sourced objective update."},
    )
    await command_inbox.enqueue(command)

    outcome = await service.run(
        OperationGoal(objective="do the task"),
        **run_settings(max_iterations=4, allowed_agents=["claude_acp"]),
        options=RunOptions(run_mode=RunMode.ATTACHED),
        operation_id="op-event-patch-objective",
    )

    operation = await store.load_operation(outcome.operation_id)
    events = await event_store.load_after(outcome.operation_id, after_sequence=0)
    assert operation is not None
    assert operation.objective_state.objective == "Canonical event-sourced objective update."
    assert [event.event_type for event in events] == [
        "operation.created",
        "command.accepted",
        "objective.updated",
    ]


@pytest.mark.anyio
async def test_event_sourced_patch_objective_persists_processed_command_via_checkpoint_replay(
    tmp_path: Path,
) -> None:
    store = _CountingMemoryStore()
    command_inbox = MemoryCommandInbox()
    event_store = FileOperationEventStore(tmp_path / "events")
    checkpoint_store = FileOperationCheckpointStore(tmp_path / "checkpoints")
    projector = DefaultOperationProjector()
    birth_service = EventSourcedOperationBirthService(
        event_store=event_store,
        checkpoint_store=checkpoint_store,
        projector=projector,
    )
    replay_service = EventSourcedReplayService(
        event_store=event_store,
        checkpoint_store=checkpoint_store,
        projector=projector,
    )
    operation_entrypoints = OperationEntrypointService(
        store=store,
        event_sourced_operation_birth_service=birth_service,
        event_sourced_replay_service=replay_service,
    )
    service = make_service(
        brain=StartThenStopBrain(),
        store=store,
        trace_store=MemoryTraceStore(),
        event_sink=MemoryEventSink(),
        agent_runtime_bindings=build_test_runtime_bindings({"claude_acp": FakeAgent()}),
        command_inbox=command_inbox,
        event_sourced_operation_birth_service=birth_service,
        operation_entrypoint_service=operation_entrypoints,
        event_sourced_command_service=EventSourcedCommandApplicationService(
            event_store=event_store,
            checkpoint_store=checkpoint_store,
            projector=projector,
        ),
    )

    command = OperationCommand(
        operation_id="op-event-processed-replay",
        command_type=OperationCommandType.PATCH_OBJECTIVE,
        target_scope=CommandTargetScope.OPERATION,
        target_id="op-event-processed-replay",
        payload={"text": "Persist processed command ids through canonical replay."},
    )
    await command_inbox.enqueue(command)

    outcome = await service.run(
        OperationGoal(objective="do the task"),
        **run_settings(max_iterations=4, allowed_agents=["claude_acp"]),
        options=RunOptions(run_mode=RunMode.ATTACHED),
        operation_id="op-event-processed-replay",
    )
    save_calls_after_run = store.save_calls

    persisted = await store.load_operation(outcome.operation_id)
    assert persisted is not None
    persisted.processed_command_ids = []

    replayed = await operation_entrypoints._load_event_sourced(  # noqa: SLF001 - regression check
        outcome.operation_id,
        fallback_state=persisted,
    )

    assert command.command_id in replayed.processed_command_ids
    assert store.save_calls == save_calls_after_run


@pytest.mark.anyio
async def test_event_sourced_patch_objective_replay_restores_canonical_state_without_snapshot_write(
    tmp_path: Path,
) -> None:
    store = _CountingMemoryStore()
    command_inbox = MemoryCommandInbox()
    event_store = FileOperationEventStore(tmp_path / "events")
    checkpoint_store = FileOperationCheckpointStore(tmp_path / "checkpoints")
    projector = DefaultOperationProjector()
    birth_service = EventSourcedOperationBirthService(
        event_store=event_store,
        checkpoint_store=checkpoint_store,
        projector=projector,
    )
    replay_service = EventSourcedReplayService(
        event_store=event_store,
        checkpoint_store=checkpoint_store,
        projector=projector,
    )
    operation_entrypoints = OperationEntrypointService(
        store=store,
        event_sourced_operation_birth_service=birth_service,
        event_sourced_replay_service=replay_service,
    )
    service = make_service(
        brain=StartThenStopBrain(),
        store=store,
        trace_store=MemoryTraceStore(),
        event_sink=MemoryEventSink(),
        agent_runtime_bindings=build_test_runtime_bindings({"claude_acp": FakeAgent()}),
        command_inbox=command_inbox,
        event_sourced_operation_birth_service=birth_service,
        operation_entrypoint_service=operation_entrypoints,
        event_sourced_command_service=EventSourcedCommandApplicationService(
            event_store=event_store,
            checkpoint_store=checkpoint_store,
            projector=projector,
        ),
    )

    command = OperationCommand(
        operation_id="op-event-replay-objective",
        command_type=OperationCommandType.PATCH_OBJECTIVE,
        target_scope=CommandTargetScope.OPERATION,
        target_id="op-event-replay-objective",
        payload={"text": "Canonical replay should win over stale snapshot state."},
    )
    await command_inbox.enqueue(command)

    outcome = await service.run(
        OperationGoal(objective="do the task"),
        **run_settings(max_iterations=4, allowed_agents=["claude_acp"]),
        options=RunOptions(run_mode=RunMode.ATTACHED),
        operation_id="op-event-replay-objective",
    )
    save_calls_after_run = store.save_calls

    persisted = await store.load_operation(outcome.operation_id)
    assert persisted is not None
    persisted.goal.objective = "stale snapshot objective"
    persisted.objective.objective = "stale snapshot objective"
    persisted.processed_command_ids = []

    replayed = await operation_entrypoints._load_event_sourced(  # noqa: SLF001 - regression check
        outcome.operation_id,
        fallback_state=persisted,
    )

    assert replayed.objective_state.objective == (
        "Canonical replay should win over stale snapshot state."
    )
    assert command.command_id in replayed.processed_command_ids
    assert store.save_calls == save_calls_after_run


@pytest.mark.anyio
async def test_event_sourced_set_involvement_level_command_updates_runtime_view(
    tmp_path: Path,
) -> None:
    store = MemoryStore()
    command_inbox = MemoryCommandInbox()
    event_store = FileOperationEventStore(tmp_path / "events")
    checkpoint_store = FileOperationCheckpointStore(tmp_path / "checkpoints")
    projector = DefaultOperationProjector()
    birth_service = EventSourcedOperationBirthService(
        event_store=event_store,
        checkpoint_store=checkpoint_store,
        projector=projector,
    )
    replay_service = EventSourcedReplayService(
        event_store=event_store,
        checkpoint_store=checkpoint_store,
        projector=projector,
    )
    service = make_service(
        brain=StartThenStopBrain(),
        store=store,
        trace_store=MemoryTraceStore(),
        event_sink=MemoryEventSink(),
        agent_runtime_bindings=build_test_runtime_bindings({"claude_acp": FakeAgent()}),
        command_inbox=command_inbox,
        event_sourced_operation_birth_service=birth_service,
        operation_entrypoint_service=OperationEntrypointService(
            store=store,
            event_sourced_operation_birth_service=birth_service,
            event_sourced_replay_service=replay_service,
        ),
        event_sourced_command_service=EventSourcedCommandApplicationService(
            event_store=event_store,
            checkpoint_store=checkpoint_store,
            projector=projector,
        ),
    )

    command = OperationCommand(
        operation_id="op-event-set-involvement",
        command_type=OperationCommandType.SET_INVOLVEMENT_LEVEL,
        target_scope=CommandTargetScope.OPERATION,
        target_id="op-event-set-involvement",
        payload={"level": InvolvementLevel.APPROVAL_HEAVY.value},
    )
    await command_inbox.enqueue(command)

    outcome = await service.run(
        OperationGoal(objective="do the task"),
        **run_settings(max_iterations=4, allowed_agents=["claude_acp"]),
        options=RunOptions(run_mode=RunMode.ATTACHED),
        operation_id="op-event-set-involvement",
    )

    operation = await store.load_operation(outcome.operation_id)
    events = await event_store.load_after(outcome.operation_id, after_sequence=0)
    assert operation is not None
    assert operation.involvement_level is InvolvementLevel.APPROVAL_HEAVY
    assert operation.policy.involvement_level is InvolvementLevel.APPROVAL_HEAVY
    assert command.command_id not in operation.pending_replan_command_ids
    assert [event.event_type for event in events] == [
        "operation.created",
        "command.accepted",
        "operation.involvement_level.updated",
    ]


@pytest.mark.anyio
async def test_event_sourced_answer_attention_replays_canonical_answer(
    tmp_path: Path,
) -> None:
    store = _CountingMemoryStore()
    event_store = FileOperationEventStore(tmp_path / "events")
    checkpoint_store = FileOperationCheckpointStore(tmp_path / "checkpoints")
    projector = DefaultOperationProjector()
    birth_service = EventSourcedOperationBirthService(
        event_store=event_store,
        checkpoint_store=checkpoint_store,
        projector=projector,
    )
    replay_service = EventSourcedReplayService(
        event_store=event_store,
        checkpoint_store=checkpoint_store,
        projector=projector,
    )
    operation_entrypoints = OperationEntrypointService(
        store=store,
        event_sourced_operation_birth_service=birth_service,
        event_sourced_replay_service=replay_service,
    )
    event_sourced_command_service = EventSourcedCommandApplicationService(
        event_store=event_store,
        checkpoint_store=checkpoint_store,
        projector=projector,
    )

    operation = OperationState(
        operation_id="op-event-answer-attention",
        goal=OperationGoal(objective="pick a deployment target"),
        **state_settings(allowed_agents=["claude_acp"]),
        status=OperationStatus.NEEDS_HUMAN,
        current_focus=FocusState(
            kind=FocusKind.ATTENTION_REQUEST,
            target_id="attention-1",
            mode=FocusMode.BLOCKING,
        ),
        attention_requests=[
            AttentionRequest(
                operation_id="op-event-answer-attention",
                attention_id="attention-1",
                attention_type=AttentionType.QUESTION,
                target_scope=CommandTargetScope.OPERATION,
                target_id="op-event-answer-attention",
                title="Need direction",
                question="Which path should the operator take?",
                status=AttentionStatus.OPEN,
            )
        ],
    )
    await store.save_operation(operation)
    await event_store.append(
        operation.operation_id,
        0,
        [
            OperationDomainEventDraft(
                event_type="operation.created",
                payload={
                    **operation.objective.model_dump(mode="json"),
                    "allowed_agents": ["claude_acp"],
                    "involvement_level": operation.involvement_level.value,
                    "created_at": operation.created_at.isoformat(),
                },
            ),
        ],
    )
    await event_store.append(
        operation.operation_id,
        1,
        [
            OperationDomainEventDraft(
                event_type="operation.status.changed",
                payload={"status": OperationStatus.NEEDS_HUMAN.value},
            ),
            OperationDomainEventDraft(
                event_type="attention.request.created",
                payload={
                    "attention_id": "attention-1",
                    "operation_id": operation.operation_id,
                    "attention_type": AttentionType.QUESTION.value,
                    "target_scope": CommandTargetScope.OPERATION.value,
                    "target_id": operation.operation_id,
                    "title": "Need direction",
                    "question": "Which path should the operator take?",
                    "blocking": True,
                    "status": AttentionStatus.OPEN.value,
                },
            ),
        ],
    )

    command = OperationCommand(
        operation_id=operation.operation_id,
        command_type=OperationCommandType.ANSWER_ATTENTION_REQUEST,
        target_scope=CommandTargetScope.ATTENTION_REQUEST,
        target_id="attention-1",
        payload={"text": "Use staging first."},
    )
    result = await event_sourced_command_service.apply(command)

    assert result.applied is True
    persisted = operation.model_copy(deep=True)
    persisted.attention_requests[0].status = AttentionStatus.OPEN
    persisted.attention_requests[0].answer_text = None
    persisted.attention_requests[0].answer_source_command_id = None
    persisted.attention_requests[0].answered_at = None
    persisted.processed_command_ids = []

    replayed = await operation_entrypoints._load_event_sourced(  # noqa: SLF001 - regression check
        operation.operation_id,
        fallback_state=persisted,
    )

    replayed_attention = replayed.attention_requests[0]
    assert replayed_attention.status is AttentionStatus.ANSWERED
    assert replayed_attention.answer_text == "Use staging first."
    assert replayed_attention.answer_source_command_id == command.command_id
    assert command.command_id in replayed.processed_command_ids


@pytest.mark.anyio
async def test_answer_attention_request_command_service_uses_replay_backed_persistence(
    tmp_path: Path,
) -> None:
    store = _CountingMemoryStore()
    inbox = MemoryCommandInbox()
    event_sink = MemoryEventSink()
    event_store = FileOperationEventStore(tmp_path / "events")
    checkpoint_store = FileOperationCheckpointStore(tmp_path / "checkpoints")
    projector = DefaultOperationProjector()
    birth_service = EventSourcedOperationBirthService(
        event_store=event_store,
        checkpoint_store=checkpoint_store,
        projector=projector,
    )
    replay_service = EventSourcedReplayService(
        event_store=event_store,
        checkpoint_store=checkpoint_store,
        projector=projector,
    )
    operation_entrypoints = OperationEntrypointService(
        store=store,
        event_sourced_operation_birth_service=birth_service,
        event_sourced_replay_service=replay_service,
    )
    service = make_service(
        brain=StartThenStopBrain(),
        store=store,
        trace_store=MemoryTraceStore(),
        event_sink=event_sink,
        agent_runtime_bindings=build_test_runtime_bindings({"claude_acp": FakeAgent()}),
        command_inbox=inbox,
        event_sourced_operation_birth_service=birth_service,
        operation_entrypoint_service=operation_entrypoints,
        event_sourced_command_service=EventSourcedCommandApplicationService(
            event_store=event_store,
            checkpoint_store=checkpoint_store,
            projector=projector,
        ),
    )

    operation = OperationState(
        operation_id="op-event-answer-command-service",
        goal=OperationGoal(objective="pick a deployment target"),
        **state_settings(allowed_agents=["claude_acp"]),
        status=OperationStatus.NEEDS_HUMAN,
        current_focus=FocusState(
            kind=FocusKind.ATTENTION_REQUEST,
            target_id="attention-1",
            mode=FocusMode.BLOCKING,
        ),
        attention_requests=[
            AttentionRequest(
                operation_id="op-event-answer-command-service",
                attention_id="attention-1",
                attention_type=AttentionType.QUESTION,
                target_scope=CommandTargetScope.OPERATION,
                target_id="op-event-answer-command-service",
                title="Need direction",
                question="Which path should the operator take?",
                status=AttentionStatus.OPEN,
            )
        ],
    )
    await store.save_operation(operation)
    await event_store.append(
        operation.operation_id,
        0,
        [
            OperationDomainEventDraft(
                event_type="operation.created",
                payload={
                    **operation.objective.model_dump(mode="json"),
                    "allowed_agents": ["claude_acp"],
                    "involvement_level": operation.involvement_level.value,
                    "created_at": operation.created_at.isoformat(),
                },
            ),
            OperationDomainEventDraft(
                event_type="operation.status.changed",
                payload={"status": OperationStatus.NEEDS_HUMAN.value},
            ),
            OperationDomainEventDraft(
                event_type="attention.request.created",
                payload={
                    "attention_id": "attention-1",
                    "operation_id": operation.operation_id,
                    "attention_type": AttentionType.QUESTION.value,
                    "target_scope": CommandTargetScope.OPERATION.value,
                    "target_id": operation.operation_id,
                    "title": "Need direction",
                    "question": "Which path should the operator take?",
                    "blocking": True,
                    "status": AttentionStatus.OPEN.value,
                },
            ),
        ],
    )
    await replay_service.load(operation.operation_id)

    command = OperationCommand(
        operation_id=operation.operation_id,
        command_type=OperationCommandType.ANSWER_ATTENTION_REQUEST,
        target_scope=CommandTargetScope.ATTENTION_REQUEST,
        target_id="attention-1",
        payload={"text": "Use staging first."},
    )
    await inbox.enqueue(command)

    outcome = await service.resume(
        operation.operation_id,
        options=RunOptions(run_mode=RunMode.ATTACHED, max_cycles=2),
    )
    assert outcome.status is OperationStatus.COMPLETED

    updated = await store.load_operation(operation.operation_id)
    assert updated is not None
    assert updated.attention_requests[0].status is AttentionStatus.RESOLVED
    assert updated.attention_requests[0].answer_text == "Use staging first."
    assert inbox.commands[command.command_id].status is CommandStatus.APPLIED

    events = await event_store.load_after(operation.operation_id, after_sequence=0)
    assert [event.event_type for event in events] == [
        "operation.created",
        "operation.status.changed",
        "attention.request.created",
        "command.accepted",
        "attention.request.answered",
        "operation.status.changed",
        "attention.request.resolved",
    ]

    stale_snapshot = operation.model_copy(deep=True)
    replayed = await operation_entrypoints._load_event_sourced(  # noqa: SLF001 - regression check
        operation.operation_id,
        fallback_state=stale_snapshot,
    )
    assert replayed.attention_requests[0].status is AttentionStatus.RESOLVED
    assert replayed.attention_requests[0].answer_text == "Use staging first."
    assert replayed.pending_attention_resolution_ids == []
    assert replayed.current_focus is not None
    assert replayed.current_focus.target_id == "attention-1"
    assert command.command_id in replayed.processed_command_ids
    assert [
        event.event_type
        for event in event_sink.events
        if event.event_type.startswith("attention.request.")
    ] == ["attention.request.resolved"]


@pytest.mark.anyio
async def test_record_policy_decision_command_service_uses_replay_backed_persistence(
    tmp_path: Path,
) -> None:
    store = _CountingMemoryStore()
    inbox = MemoryCommandInbox()
    event_sink = MemoryEventSink()
    policy_store = MemoryPolicyStore()
    event_store = FileOperationEventStore(tmp_path / "events")
    checkpoint_store = FileOperationCheckpointStore(tmp_path / "checkpoints")
    projector = DefaultOperationProjector()
    birth_service = EventSourcedOperationBirthService(
        event_store=event_store,
        checkpoint_store=checkpoint_store,
        projector=projector,
    )
    replay_service = EventSourcedReplayService(
        event_store=event_store,
        checkpoint_store=checkpoint_store,
        projector=projector,
    )
    operation_entrypoints = OperationEntrypointService(
        store=store,
        event_sourced_operation_birth_service=birth_service,
        event_sourced_replay_service=replay_service,
    )
    service = make_service(
        brain=StartThenStopBrain(),
        store=store,
        trace_store=MemoryTraceStore(),
        event_sink=event_sink,
        agent_runtime_bindings=build_test_runtime_bindings({"claude_acp": FakeAgent()}),
        command_inbox=inbox,
        policy_store=policy_store,
        event_sourced_operation_birth_service=birth_service,
        operation_entrypoint_service=operation_entrypoints,
        event_sourced_command_service=EventSourcedCommandApplicationService(
            event_store=event_store,
            checkpoint_store=checkpoint_store,
            projector=projector,
        ),
    )

    operation = OperationState(
        operation_id="op-event-record-policy",
        goal=OperationGoal(
            objective="continue work",
            metadata={"project_profile_name": "femtobot", "policy_scope": "profile:femtobot"},
        ),
        **state_settings(allowed_agents=["claude_acp"]),
    )
    await store.save_operation(operation)
    await event_store.append(
        operation.operation_id,
        0,
        [
            OperationDomainEventDraft(
                event_type="operation.created",
                payload={
                    **operation.objective.model_dump(mode="json"),
                    "allowed_agents": ["claude_acp"],
                    "involvement_level": operation.involvement_level.value,
                    "created_at": operation.created_at.isoformat(),
                },
            )
        ],
    )
    await replay_service.load(operation.operation_id)

    command = OperationCommand(
        operation_id=operation.operation_id,
        command_type=OperationCommandType.RECORD_POLICY_DECISION,
        target_scope=CommandTargetScope.OPERATION,
        target_id=operation.operation_id,
        payload={
            "title": "Manual testing debt must be recorded",
            "text": "Write human-only checks to MANUAL_TESTING_REQUIRED.md before completion.",
            "category": PolicyCategory.TESTING.value,
        },
    )
    await inbox.enqueue(command)

    outcome = await service.resume(
        operation.operation_id,
        options=RunOptions(run_mode=RunMode.ATTACHED, max_cycles=2),
    )
    assert outcome.status is OperationStatus.COMPLETED

    updated = await store.load_operation(operation.operation_id)
    assert updated is not None
    assert len(updated.active_policies) == 1
    assert updated.active_policies[0].title == "Manual testing debt must be recorded"
    assert updated.policy_coverage.active_policy_count == 1
    assert inbox.commands[command.command_id].status is CommandStatus.APPLIED

    events = await event_store.load_after(operation.operation_id, after_sequence=0)
    assert [event.event_type for event in events] == [
        "operation.created",
        "command.accepted",
        "policy.active_set.updated",
        "policy.coverage.updated",
    ]

    stale_snapshot = operation.model_copy(deep=True)
    replayed = await operation_entrypoints._load_event_sourced(  # noqa: SLF001 - regression check
        operation.operation_id,
        fallback_state=stale_snapshot,
    )
    assert len(replayed.active_policies) == 1
    assert replayed.active_policies[0].title == "Manual testing debt must be recorded"
    assert replayed.policy_coverage.active_policy_count == 1
    assert command.command_id in replayed.processed_command_ids

    persisted_policy = next(iter(policy_store.entries.values()))
    assert persisted_policy.title == "Manual testing debt must be recorded"


@pytest.mark.anyio
async def test_event_sourced_pause_operator_command_updates_scheduler_without_replan(
    tmp_path: Path,
) -> None:
    store = MemoryStore()
    command_inbox = MemoryCommandInbox()
    event_store = FileOperationEventStore(tmp_path / "events")
    checkpoint_store = FileOperationCheckpointStore(tmp_path / "checkpoints")
    projector = DefaultOperationProjector()
    birth_service = EventSourcedOperationBirthService(
        event_store=event_store,
        checkpoint_store=checkpoint_store,
        projector=projector,
    )
    replay_service = EventSourcedReplayService(
        event_store=event_store,
        checkpoint_store=checkpoint_store,
        projector=projector,
    )
    service = make_service(
        brain=StartThenStopBrain(),
        store=store,
        trace_store=MemoryTraceStore(),
        event_sink=MemoryEventSink(),
        agent_runtime_bindings=build_test_runtime_bindings({"claude_acp": FakeAgent()}),
        command_inbox=command_inbox,
        event_sourced_operation_birth_service=birth_service,
        operation_entrypoint_service=OperationEntrypointService(
            store=store,
            event_sourced_operation_birth_service=birth_service,
            event_sourced_replay_service=replay_service,
        ),
        event_sourced_command_service=EventSourcedCommandApplicationService(
            event_store=event_store,
            checkpoint_store=checkpoint_store,
            projector=projector,
        ),
    )

    command = OperationCommand(
        operation_id="op-event-pause",
        command_type=OperationCommandType.PAUSE_OPERATOR,
        target_scope=CommandTargetScope.OPERATION,
        target_id="op-event-pause",
    )
    await command_inbox.enqueue(command)

    outcome = await service.run(
        OperationGoal(objective="do the task"),
        **run_settings(max_iterations=4, allowed_agents=["claude_acp"]),
        options=RunOptions(run_mode=RunMode.ATTACHED),
        operation_id="op-event-pause",
    )

    operation = await store.load_operation(outcome.operation_id)
    events = await event_store.load_after(outcome.operation_id, after_sequence=0)
    assert operation is not None
    assert operation.scheduler_state is SchedulerState.PAUSED
    assert command.command_id not in operation.pending_replan_command_ids
    assert [event.event_type for event in events] == [
        "operation.created",
        "command.accepted",
        "scheduler.state.changed",
    ]


@pytest.mark.anyio
async def test_patch_harness_command_updates_harness_and_becomes_applied_after_replan() -> None:
    store = MemoryStore()
    command_inbox = MemoryCommandInbox()
    service = make_service(
        brain=StartThenStopBrain(),
        store=store,
        trace_store=MemoryTraceStore(),
        event_sink=MemoryEventSink(),
        agent_runtime_bindings=build_test_runtime_bindings({"claude_acp": FakeAgent()}),
        command_inbox=command_inbox,
    )

    command = OperationCommand(
        operation_id="op-patch-harness",
        command_type=OperationCommandType.PATCH_HARNESS,
        target_scope=CommandTargetScope.OPERATION,
        target_id="op-patch-harness",
        payload={"text": "Prefer swarm when the next actions are unclear."},
    )
    await command_inbox.enqueue(command)

    outcome = await service.run(
        OperationGoal(objective="do the task"),
        **run_settings(max_iterations=4, allowed_agents=["claude_acp"]),
        options=RunOptions(run_mode=RunMode.ATTACHED),
        operation_id="op-patch-harness",
    )

    operation = await store.load_operation(outcome.operation_id)
    commands = await command_inbox.list(outcome.operation_id)
    assert operation is not None
    assert operation.objective_state.harness_instructions == (
        "Prefer swarm when the next actions are unclear."
    )
    assert commands[0].status is CommandStatus.APPLIED
    assert commands[0].applied_at is not None
    assert command.command_id in operation.processed_command_ids
    assert await command_inbox.list_pending_planning_triggers(outcome.operation_id) == []


@pytest.mark.anyio
async def test_patch_success_criteria_command_replaces_criteria_after_replan() -> None:
    store = MemoryStore()
    command_inbox = MemoryCommandInbox()
    service = make_service(
        brain=StartThenStopBrain(),
        store=store,
        trace_store=MemoryTraceStore(),
        event_sink=MemoryEventSink(),
        agent_runtime_bindings=build_test_runtime_bindings({"claude_acp": FakeAgent()}),
        command_inbox=command_inbox,
    )

    command = OperationCommand(
        operation_id="op-patch-success",
        command_type=OperationCommandType.PATCH_SUCCESS_CRITERIA,
        target_scope=CommandTargetScope.OPERATION,
        target_id="op-patch-success",
        payload={
            "success_criteria": [
                "Tests pass.",
                "Docs explain the new control surface.",
            ]
        },
    )
    await command_inbox.enqueue(command)

    outcome = await service.run(
        OperationGoal(objective="do the task", success_criteria=["Old criterion"]),
        **run_settings(max_iterations=4, allowed_agents=["claude_acp"]),
        options=RunOptions(run_mode=RunMode.ATTACHED),
        operation_id="op-patch-success",
    )

    operation = await store.load_operation(outcome.operation_id)
    commands = await command_inbox.list(outcome.operation_id)
    assert operation is not None
    assert operation.objective_state.success_criteria == [
        "Tests pass.",
        "Docs explain the new control surface.",
    ]
    assert commands[0].status is CommandStatus.APPLIED
    assert commands[0].applied_at is not None
    assert command.command_id in operation.processed_command_ids
    assert await command_inbox.list_pending_planning_triggers(outcome.operation_id) == []


@pytest.mark.anyio
async def test_patch_success_criteria_command_can_clear_criteria_after_replan() -> None:
    store = MemoryStore()
    command_inbox = MemoryCommandInbox()
    service = make_service(
        brain=StartThenStopBrain(),
        store=store,
        trace_store=MemoryTraceStore(),
        event_sink=MemoryEventSink(),
        agent_runtime_bindings=build_test_runtime_bindings({"claude_acp": FakeAgent()}),
        command_inbox=command_inbox,
    )

    command = OperationCommand(
        operation_id="op-clear-success",
        command_type=OperationCommandType.PATCH_SUCCESS_CRITERIA,
        target_scope=CommandTargetScope.OPERATION,
        target_id="op-clear-success",
        payload={"success_criteria": []},
    )
    await command_inbox.enqueue(command)

    outcome = await service.run(
        OperationGoal(objective="do the task", success_criteria=["Old criterion"]),
        **run_settings(max_iterations=4, allowed_agents=["claude_acp"]),
        options=RunOptions(run_mode=RunMode.ATTACHED),
        operation_id="op-clear-success",
    )

    operation = await store.load_operation(outcome.operation_id)
    commands = await command_inbox.list(outcome.operation_id)
    assert operation is not None
    assert operation.objective_state.success_criteria == []
    assert commands[0].status is CommandStatus.APPLIED
    assert commands[0].applied_at is not None
    assert command.command_id in operation.processed_command_ids
    assert await command_inbox.list_pending_planning_triggers(outcome.operation_id) == []


@pytest.mark.anyio
async def test_inject_operator_message_is_persisted_and_rendered_in_prompt() -> None:
    store = MemoryStore()
    command_inbox = MemoryCommandInbox()
    service = make_service(
        brain=StartThenStopBrain(),
        store=store,
        trace_store=MemoryTraceStore(),
        event_sink=MemoryEventSink(),
        agent_runtime_bindings=build_test_runtime_bindings({"claude_acp": FakeAgent()}),
        command_inbox=command_inbox,
    )

    command = OperationCommand(
        operation_id="op-message",
        command_type=OperationCommandType.INJECT_OPERATOR_MESSAGE,
        target_scope=CommandTargetScope.OPERATION,
        target_id="op-message",
        payload={"text": "Use the vision to resolve any strategic ambiguity."},
    )
    await command_inbox.enqueue(command)

    outcome = await service.run(
        OperationGoal(objective="do the task"),
        **run_settings(max_iterations=4, allowed_agents=["claude_acp"]),
        options=RunOptions(run_mode=RunMode.ATTACHED),
        operation_id="op-message",
    )

    operation = await store.load_operation(outcome.operation_id)
    commands = await command_inbox.list(outcome.operation_id)
    assert operation is not None
    assert operation.operator_messages
    assert operation.operator_messages[0].text == (
        "Use the vision to resolve any strategic ambiguity."
    )
    prompt = build_decision_prompt(operation)
    assert "Recent Operator Messages" in prompt
    assert "Use the vision to resolve any strategic ambiguity." in prompt
    assert commands[0].status is CommandStatus.APPLIED
    assert commands[0].applied_at is not None
    assert command.command_id in operation.processed_command_ids
    assert await command_inbox.list_pending_planning_triggers(outcome.operation_id) == []


@pytest.mark.anyio
async def test_replay_of_processed_message_command_repairs_status_without_duplicate_message(
) -> None:
    store = MemoryStore()
    command_inbox = MemoryCommandInbox()
    state = OperationState(
        operation_id="op-message-replay",
        goal=OperationGoal(objective="do the task"),
        **state_settings(max_iterations=4, allowed_agents=["claude_acp"]),
        operator_messages=[
            OperatorMessage(
                text="Use the vision to resolve any strategic ambiguity.",
                source_command_id="cmd-message",
            )
        ],
        processed_command_ids=["cmd-message"],
    )
    await store.save_operation(state)
    await command_inbox.enqueue(
        OperationCommand(
            command_id="cmd-message",
            operation_id="op-message-replay",
            command_type=OperationCommandType.INJECT_OPERATOR_MESSAGE,
            target_scope=CommandTargetScope.OPERATION,
            target_id="op-message-replay",
            payload={"text": "Use the vision to resolve any strategic ambiguity."},
        )
    )
    service = make_service(
        brain=StartThenStopBrain(),
        store=store,
        trace_store=MemoryTraceStore(),
        event_sink=MemoryEventSink(),
        agent_runtime_bindings=build_test_runtime_bindings({"claude_acp": FakeAgent()}),
        command_inbox=command_inbox,
    )

    outcome = await service.resume(
        "op-message-replay",
        options=RunOptions(run_mode=RunMode.ATTACHED),
    )

    operation = await store.load_operation(outcome.operation_id)
    commands = await command_inbox.list(outcome.operation_id)
    assert operation is not None
    assert len(operation.operator_messages) == 1
    assert commands[0].status is CommandStatus.APPLIED


@pytest.mark.anyio
async def test_operator_messages_are_capped_in_persisted_state() -> None:
    store = MemoryStore()
    command_inbox = MemoryCommandInbox()
    service = make_service(
        brain=StartThenStopBrain(),
        store=store,
        trace_store=MemoryTraceStore(),
        event_sink=MemoryEventSink(),
        agent_runtime_bindings=build_test_runtime_bindings({"claude_acp": FakeAgent()}),
        command_inbox=command_inbox,
    )

    for index in range(55):
        await command_inbox.enqueue(
            OperationCommand(
                operation_id="op-message-cap",
                command_type=OperationCommandType.INJECT_OPERATOR_MESSAGE,
                target_scope=CommandTargetScope.OPERATION,
                target_id="op-message-cap",
                payload={"text": f"message {index}"},
            )
        )

    outcome = await service.run(
        OperationGoal(objective="do the task"),
        **run_settings(max_iterations=4, allowed_agents=["claude_acp"]),
        options=RunOptions(run_mode=RunMode.ATTACHED),
        operation_id="op-message-cap",
    )

    operation = await store.load_operation(outcome.operation_id)
    assert operation is not None
    assert len(operation.operator_messages) == 50
    assert operation.operator_messages[0].text == "message 5"
    assert operation.operator_messages[-1].text == "message 54"


@pytest.mark.anyio
async def test_resume_command_is_rejected_when_operation_is_not_paused() -> None:
    command_inbox = MemoryCommandInbox()
    service = make_service(
        brain=StartThenStopBrain(),
        store=MemoryStore(),
        trace_store=MemoryTraceStore(),
        event_sink=MemoryEventSink(),
        agent_runtime_bindings=build_test_runtime_bindings({"claude_acp": FakeAgent()}),
        command_inbox=command_inbox,
    )

    command = OperationCommand(
        operation_id="op-resume-reject",
        command_type=OperationCommandType.RESUME_OPERATOR,
        target_scope=CommandTargetScope.OPERATION,
        target_id="op-resume-reject",
        payload={},
    )
    await command_inbox.enqueue(command)

    outcome = await service.run(
        OperationGoal(objective="do the task"),
        **run_settings(max_iterations=4, allowed_agents=["claude_acp"]),
        options=RunOptions(run_mode=RunMode.ATTACHED),
        operation_id="op-resume-reject",
    )

    commands = await command_inbox.list(outcome.operation_id)
    assert commands[0].status is CommandStatus.REJECTED
    assert commands[0].rejection_reason is not None


@pytest.mark.anyio
async def test_set_allowed_agents_command_replaces_policy_allowlist() -> None:
    store = MemoryStore()
    inbox = MemoryCommandInbox()
    service = make_service(
        brain=StartThenStopBrain(),
        store=store,
        trace_store=MemoryTraceStore(),
        event_sink=MemoryEventSink(),
        agent_runtime_bindings=build_test_runtime_bindings({"claude_acp": FakeAgent()}),
        command_inbox=inbox,
    )
    operation = OperationState(
        goal=OperationGoal(objective="continue work"),
        **state_settings(max_iterations=4, allowed_agents=["claude_acp"]),
    )
    await store.save_operation(operation)
    command = OperationCommand(
        operation_id=operation.operation_id,
        command_type=OperationCommandType.SET_ALLOWED_AGENTS,
        target_scope=CommandTargetScope.OPERATION,
        target_id=operation.operation_id,
        payload={"allowed_agents": ["codex_acp", "claude_acp"]},
    )
    await inbox.enqueue(command)

    outcome = await service.resume(
        operation.operation_id,
        options=RunOptions(run_mode=RunMode.ATTACHED, max_cycles=2),
    )
    updated = await store.load_operation(operation.operation_id)

    assert outcome.status is OperationStatus.COMPLETED
    assert updated is not None
    assert updated.policy.allowed_agents == ["codex_acp", "claude_acp"]
    assert updated.execution_budget.max_iterations == 4
    assert inbox.commands[command.command_id].status is CommandStatus.APPLIED


@pytest.mark.anyio
async def test_set_allowed_agents_command_rejects_empty_payload() -> None:
    store = MemoryStore()
    inbox = MemoryCommandInbox()
    service = make_service(
        brain=StartThenStopBrain(),
        store=store,
        trace_store=MemoryTraceStore(),
        event_sink=MemoryEventSink(),
        agent_runtime_bindings=build_test_runtime_bindings({"claude_acp": FakeAgent()}),
        command_inbox=inbox,
    )
    operation = OperationState(
        goal=OperationGoal(objective="continue work"),
        **state_settings(max_iterations=4, allowed_agents=["claude_acp"]),
    )
    await store.save_operation(operation)
    command = OperationCommand(
        operation_id=operation.operation_id,
        command_type=OperationCommandType.SET_ALLOWED_AGENTS,
        target_scope=CommandTargetScope.OPERATION,
        target_id=operation.operation_id,
        payload={},
    )
    await inbox.enqueue(command)

    outcome = await service.resume(
        operation.operation_id,
        options=RunOptions(run_mode=RunMode.ATTACHED, max_cycles=2),
    )
    updated = await store.load_operation(operation.operation_id)

    assert outcome.status is OperationStatus.COMPLETED
    assert updated is not None
    assert inbox.commands[command.command_id].status is CommandStatus.REJECTED


@pytest.mark.anyio
async def test_record_and_revoke_policy_commands_update_store_and_operation() -> None:
    store = MemoryStore()
    inbox = MemoryCommandInbox()
    policy_store = MemoryPolicyStore()
    service = make_service(
        brain=StartThenStopBrain(),
        store=store,
        trace_store=MemoryTraceStore(),
        event_sink=MemoryEventSink(),
        agent_runtime_bindings=build_test_runtime_bindings({"claude_acp": FakeAgent()}),
        command_inbox=inbox,
        policy_store=policy_store,
    )

    operation = OperationState(
        goal=OperationGoal(
            objective="continue work",
            metadata={"policy_scope": "profile:femtobot"},
        ),
        **state_settings(allowed_agents=["claude_acp"]),
    )
    await store.save_operation(operation)
    record = OperationCommand(
        operation_id=operation.operation_id,
        command_type=OperationCommandType.RECORD_POLICY_DECISION,
        target_scope=CommandTargetScope.OPERATION,
        target_id=operation.operation_id,
        payload={
            "title": "Manual testing debt",
            "text": "Document manual-only verification in MANUAL_TESTING_REQUIRED.md.",
            "category": PolicyCategory.TESTING.value,
        },
    )
    await inbox.enqueue(record)

    outcome = await service.resume(
        operation.operation_id,
        options=RunOptions(run_mode=RunMode.ATTACHED, max_cycles=2),
    )
    updated = await store.load_operation(operation.operation_id)
    assert outcome.status is OperationStatus.COMPLETED
    assert updated is not None
    assert len(updated.active_policies) == 1
    stored_policy = updated.active_policies[0]
    assert stored_policy.title == "Manual testing debt"
    assert inbox.commands[record.command_id].status is CommandStatus.APPLIED

    revoke = OperationCommand(
        operation_id=operation.operation_id,
        command_type=OperationCommandType.REVOKE_POLICY_DECISION,
        target_scope=CommandTargetScope.OPERATION,
        target_id=operation.operation_id,
        payload={"policy_id": stored_policy.policy_id, "reason": "Covered by CI now."},
    )
    await inbox.enqueue(revoke)

    resumed = await service.resume(
        operation.operation_id,
        options=RunOptions(run_mode=RunMode.ATTACHED, max_cycles=2),
    )
    final_state = await store.load_operation(operation.operation_id)
    persisted_policy = await policy_store.load(stored_policy.policy_id)

    assert resumed.status is OperationStatus.COMPLETED
    assert final_state is not None
    assert final_state.active_policies == []
    assert persisted_policy is not None
    assert persisted_policy.status is PolicyStatus.REVOKED
    assert persisted_policy.revoked_reason == "Covered by CI now."
    assert inbox.commands[revoke.command_id].status is CommandStatus.APPLIED


@pytest.mark.anyio
async def test_record_policy_decision_persists_applicability_filters() -> None:
    store = MemoryStore()
    inbox = MemoryCommandInbox()
    policy_store = MemoryPolicyStore()

    class StopOnlyBrain(StartThenStopBrain):
        async def decide_next_action(self, state) -> BrainDecision:
            return BrainDecision(
                action_type=BrainActionType.STOP,
                rationale="The task is complete.",
            )

    service = make_service(
        brain=StopOnlyBrain(),
        store=store,
        trace_store=MemoryTraceStore(),
        event_sink=MemoryEventSink(),
        agent_runtime_bindings=build_test_runtime_bindings({"claude_acp": FakeAgent()}),
        command_inbox=inbox,
        policy_store=policy_store,
    )

    operation = OperationState(
        goal=OperationGoal(
            objective="continue work",
            metadata={"project_profile_name": "femtobot", "policy_scope": "profile:femtobot"},
        ),
        **state_settings(  # type: ignore[arg-type]
            allowed_agents=["claude_acp", "codex_acp"],
            involvement_level=InvolvementLevel.AUTO,
            metadata={"run_mode": RunMode.ATTACHED.value},
        ),
    )
    await store.save_operation(operation)
    command = OperationCommand(
        operation_id=operation.operation_id,
        command_type=OperationCommandType.RECORD_POLICY_DECISION,
        target_scope=CommandTargetScope.OPERATION,
        target_id=operation.operation_id,
        payload={
            "title": "Release approval gate",
            "text": "Ask before production release steps.",
            "category": PolicyCategory.RELEASE.value,
            "objective_keywords": ["release"],
            "task_keywords": ["deploy"],
            "agent_keys": ["codex_acp"],
            "run_modes": [RunMode.ATTACHED.value],
            "involvement_levels": [InvolvementLevel.AUTO.value],
        },
    )
    await inbox.enqueue(command)

    outcome = await service.resume(
        operation.operation_id,
        options=RunOptions(run_mode=RunMode.ATTACHED, max_cycles=2),
    )
    updated = await store.load_operation(operation.operation_id)

    assert outcome.status is OperationStatus.COMPLETED
    assert updated is not None
    assert updated.active_policies == []
    stored_policy = next(iter(policy_store.entries.values()))
    assert stored_policy.applicability.objective_keywords == ["release"]
    assert stored_policy.applicability.task_keywords == ["deploy"]
    assert stored_policy.applicability.agent_keys == ["codex_acp"]
    assert stored_policy.applicability.run_modes == [RunMode.ATTACHED]
    assert stored_policy.applicability.involvement_levels == [InvolvementLevel.AUTO]


@pytest.mark.anyio
async def test_concurrent_patch_conflict_rejects_second_same_type_patch() -> None:
    store = MemoryStore()
    command_inbox = MemoryCommandInbox()
    service = make_service(
        brain=StartThenStopBrain(),
        store=store,
        trace_store=MemoryTraceStore(),
        event_sink=MemoryEventSink(),
        agent_runtime_bindings=build_test_runtime_bindings({"claude_acp": FakeAgent()}),
        command_inbox=command_inbox,
    )

    op_id = "op-concurrent-patch"
    first_patch = OperationCommand(
        operation_id=op_id,
        command_type=OperationCommandType.PATCH_OBJECTIVE,
        target_scope=CommandTargetScope.OPERATION,
        target_id=op_id,
        payload={"text": "First objective update."},
    )
    second_patch = OperationCommand(
        operation_id=op_id,
        command_type=OperationCommandType.PATCH_OBJECTIVE,
        target_scope=CommandTargetScope.OPERATION,
        target_id=op_id,
        payload={"text": "Second objective update - should be rejected."},
    )
    await command_inbox.enqueue(first_patch)
    await command_inbox.enqueue(second_patch)

    await service.run(
        OperationGoal(objective="do the task"),
        **run_settings(max_iterations=4, allowed_agents=["claude_acp"]),  # type: ignore[arg-type]
        options=RunOptions(run_mode=RunMode.ATTACHED),
        operation_id=op_id,
    )

    commands = await command_inbox.list(op_id)
    first = next(c for c in commands if c.command_id == first_patch.command_id)
    second = next(c for c in commands if c.command_id == second_patch.command_id)
    assert first.status is CommandStatus.APPLIED
    assert second.status is CommandStatus.REJECTED
    assert second.rejection_reason is not None
    assert "concurrent_patch_conflict" in second.rejection_reason
