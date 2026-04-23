from __future__ import annotations

from datetime import UTC, datetime

import pytest

from agent_operator.application.drive.drive_service import DriveService
from agent_operator.application.drive.lifecycle_gate import LifecycleGate
from agent_operator.application.drive.policy_executor import PolicyExecutor
from agent_operator.application.drive.runtime_reconciler import RuntimeReconciler
from agent_operator.domain import AgentError, AgentResult, AgentResultStatus
from agent_operator.domain.brain import BrainDecision
from agent_operator.domain.checkpoints import OperationCheckpoint
from agent_operator.domain.enums import (
    BrainActionType,
    OperationStatus,
    PolicyCoverageStatus,
    PolicyStatus,
)
from agent_operator.domain.event_sourcing import (
    OperationCheckpointRecord,
    OperationDomainEventDraft,
    StaleEpochError,
    StoredOperationDomainEvent,
)
from agent_operator.domain.events import RunEvent
from agent_operator.domain.operation import RunOptions
from agent_operator.domain.policy import PolicyApplicability, PolicyCategory, PolicyEntry
from agent_operator.dtos.requests import AgentRunRequest


class StubBrain:
    async def decide_next_action(self, state) -> BrainDecision:
        return BrainDecision(
            action_type=BrainActionType.START_AGENT,
            target_agent="codex_acp",
            instruction="inspect",
            rationale="Start immediately.",
        )


class MoreActionsBrain:
    def __init__(self) -> None:
        self.calls = 0

    async def decide_next_action(self, state) -> BrainDecision:
        self.calls += 1
        if self.calls == 1:
            return BrainDecision(
                action_type=BrainActionType.APPLY_POLICY,
                rationale="Take one cheap follow-up step before yielding.",
                more_actions=True,
            )
        return BrainDecision(
            action_type=BrainActionType.STOP,
            rationale="Stop after the continuation sub-call.",
        )


class RecentDecisionsBrain:
    def __init__(self) -> None:
        self.calls = 0
        self.observed_recent_decisions: list[list[tuple[str, bool, str]]] = []

    async def decide_next_action(self, state) -> BrainDecision:
        self.calls += 1
        self.observed_recent_decisions.append(
            [
                (record.action_type, record.more_actions, record.wake_cycle_id)
                for record in state.recent_decisions
            ]
        )
        if self.calls == 1:
            return BrainDecision(
                action_type=BrainActionType.APPLY_POLICY,
                rationale="Continue inside the same wake cycle.",
                more_actions=True,
            )
        return BrainDecision(
            action_type=BrainActionType.STOP,
            rationale="Stop after observing decision history.",
        )


class StubSessionManager:
    def __init__(self) -> None:
        self.collected = False

    async def start(self, adapter_key: str, request: AgentRunRequest):
        from agent_operator.domain import AgentSessionHandle

        assert adapter_key == "codex_acp"
        return AgentSessionHandle(
            adapter_key=adapter_key,
            session_id="sess-1",
            session_name="sess",
            display_name="Codex",
            one_shot=False,
            metadata={"operation_id": "op-1"},
        )

    async def collect(self, handle):
        self.collected = True
        return AgentResult(
            session_id=handle.session_id,
            status=AgentResultStatus.SUCCESS,
            output_text="done",
            completed_at=datetime.now(UTC),
        )

    async def close(self, handle) -> None:
        return None


class IncompleteSessionManager(StubSessionManager):
    async def collect(self, handle):
        self.collected = True
        return AgentResult(
            session_id=handle.session_id,
            status=AgentResultStatus.INCOMPLETE,
            output_text="partial output",
            completed_at=datetime.now(UTC),
            error=AgentError(
                code="agent_waiting_input",
                message="Codex ACP turn is waiting for approval.",
                retryable=False,
                raw={
                    "kind": "permission_escalation",
                    "request": {
                        "adapter_key": "codex_acp",
                        "method": "session/request_permission",
                        "interaction": "approval",
                        "working_directory": "/tmp/repo",
                        "session_id": "sess-1",
                        "title": "Run operator e2e",
                        "command": ["uv", "run", "operator"],
                        "tool_kind": "execute",
                        "skill_name": None,
                    },
                    "signature": {
                        "adapter_key": "codex_acp",
                        "method": "session/request_permission",
                        "interaction": "approval",
                        "title": "Run operator e2e",
                        "tool_kind": "execute",
                        "skill_name": None,
                        "command": ["uv", "run", "operator"],
                    },
                    "rationale": "Need operator decision.",
                    "suggested_options": ["Approve", "Reject"],
                },
            ),
        )


class PermissionApprovedSessionManager(StubSessionManager):
    async def collect(self, handle):
        self.collected = True
        return AgentResult(
            session_id=handle.session_id,
            status=AgentResultStatus.SUCCESS,
            output_text="approved and completed",
            completed_at=datetime.now(UTC),
            raw={
                "permission_events": [
                    {
                        "event_type": "permission.request.observed",
                        "adapter_key": "codex_acp",
                        "session_id": "sess-1",
                        "request": {"method": "session/request_permission"},
                        "signature": {"adapter_key": "codex_acp"},
                    },
                    {
                        "event_type": "permission.request.decided",
                        "adapter_key": "codex_acp",
                        "session_id": "sess-1",
                        "request": {"method": "session/request_permission"},
                        "signature": {"adapter_key": "codex_acp"},
                        "decision": "approve",
                        "decision_source": "brain",
                        "rationale": "Harness allows this e2e check.",
                    },
                ]
            },
        )


class PermissionRejectedSessionManager(StubSessionManager):
    async def collect(self, handle):
        self.collected = True
        return AgentResult(
            session_id=handle.session_id,
            status=AgentResultStatus.FAILED,
            output_text="",
            completed_at=datetime.now(UTC),
            error=AgentError(
                code="agent_permission_rejected",
                message="Rejected by operator policy.",
                retryable=False,
            ),
            raw={
                "permission_events": [
                    {
                        "event_type": "permission.request.observed",
                        "adapter_key": "codex_acp",
                        "session_id": "sess-1",
                        "request": {"method": "session/request_permission"},
                        "signature": {"adapter_key": "codex_acp"},
                    },
                    {
                        "event_type": "permission.request.decided",
                        "adapter_key": "codex_acp",
                        "session_id": "sess-1",
                        "request": {"method": "session/request_permission"},
                        "signature": {"adapter_key": "codex_acp"},
                        "decision": "reject",
                        "decision_source": "brain",
                        "rationale": "Outside harness scope.",
                    },
                    {
                        "event_type": "permission.request.followup_required",
                        "adapter_key": "codex_acp",
                        "session_id": "sess-1",
                        "request": {"method": "session/request_permission"},
                        "signature": {"adapter_key": "codex_acp"},
                        "required_followup_reason": "Codex needs replacement instructions.",
                    },
                ]
            },
        )


class PermissionFollowupBrain:
    def __init__(self) -> None:
        self.observed_permission_events: list[list[dict[str, object]]] = []

    async def decide_next_action(self, state) -> BrainDecision:
        self.observed_permission_events.append(
            [dict(event) for event in state.permission_events]
        )
        if len(self.observed_permission_events) == 1:
            return BrainDecision(
                action_type=BrainActionType.START_AGENT,
                target_agent="codex_acp",
                instruction="inspect",
                rationale="Start immediately.",
            )
        return BrainDecision(
            action_type=BrainActionType.STOP,
            rationale="Saw rejected permission follow-up evidence.",
        )


class StubEventStore:
    def __init__(self) -> None:
        self.streams: dict[str, list[StoredOperationDomainEvent]] = {}

    async def append(self, operation_id: str, expected_sequence: int, events):
        stream = self.streams.setdefault(operation_id, [])
        stored: list[StoredOperationDomainEvent] = []
        for index, draft in enumerate(events, start=expected_sequence + 1):
            stored.append(
                StoredOperationDomainEvent(
                    operation_id=operation_id,
                    sequence=index,
                    event_type=draft.event_type,
                    payload=draft.payload,
                    timestamp=draft.timestamp,
                )
            )
        stream.extend(stored)
        return stored

    async def load_after(self, operation_id: str, after_sequence: int):
        return [
            event
            for event in self.streams.get(operation_id, [])
            if event.sequence > after_sequence
        ]

    async def load_last_sequence(self, operation_id: str) -> int:
        stream = self.streams.get(operation_id, [])
        return stream[-1].sequence if stream else 0


class StubCheckpointStore:
    def __init__(self) -> None:
        self.saved: list[OperationCheckpointRecord] = []
        self.loaded_epoch_id = 0
        self.saved_epoch_ids: list[int] = []

    async def load(self, operation_id: str):
        return None, self.loaded_epoch_id

    async def save(self, record: OperationCheckpointRecord) -> None:
        self.saved.append(record)

    async def save_with_epoch(self, record: OperationCheckpointRecord, epoch_id: int) -> None:
        self.saved_epoch_ids.append(epoch_id)
        self.saved.append(record)


class StaleEpochCheckpointStore(StubCheckpointStore):
    async def save_with_epoch(self, record: OperationCheckpointRecord, epoch_id: int) -> None:
        raise StaleEpochError(f"stale epoch {epoch_id}")


class StubReplayService:
    async def load(self, operation_id: str):
        checkpoint = OperationCheckpoint.initial(operation_id)
        return type(
            "ReplayState",
            (),
            {
                "checkpoint": checkpoint,
                "last_applied_sequence": 1,
                "suffix_events": [],
            },
        )()


class ReplayServiceWithPriorDecision:
    async def load(self, operation_id: str):
        checkpoint = OperationCheckpoint.initial(operation_id)
        return type(
            "ReplayState",
            (),
            {
                "checkpoint": checkpoint,
                "last_applied_sequence": 1,
                "suffix_events": [
                    StoredOperationDomainEvent(
                        operation_id=operation_id,
                        sequence=1,
                        event_type="brain.decision.made",
                        payload={
                            "action_type": BrainActionType.START_AGENT.value,
                            "more_actions": False,
                            "wake_cycle_id": "wc-prior",
                        },
                        timestamp=datetime.now(UTC),
                    )
                ],
            },
        )()


class ReplayServiceWithSuffixEvents:
    def __init__(self, suffix_events: list[StoredOperationDomainEvent]) -> None:
        self._suffix_events = suffix_events

    async def load(self, operation_id: str):
        checkpoint = OperationCheckpoint.initial(operation_id)
        return type(
            "ReplayState",
            (),
            {
                "checkpoint": checkpoint,
                "last_applied_sequence": len(self._suffix_events),
                "suffix_events": list(self._suffix_events),
            },
        )()


class RecordingEventSink:
    def __init__(self) -> None:
        self.events: list[RunEvent] = []

    async def emit(self, event: RunEvent) -> None:
        self.events.append(event)


class StubWakeupInbox:
    async def requeue_stale_claims(self) -> int:
        return 0

    async def claim(self, operation_id: str, limit: int = 100):
        return []

    async def ack(self, event_ids: list[str]) -> None:
        return None

    async def release(self, event_ids: list[str]) -> None:
        return None


class StubCommandInbox:
    async def list_pending(self, operation_id: str):
        return []


class StubAdapterRegistry:
    def has(self, adapter_key: str) -> bool:
        return adapter_key == "codex_acp"

    async def describe(self, adapter_key: str):
        from agent_operator.domain.agent import AgentDescriptor

        return AgentDescriptor(key=adapter_key, display_name="Codex ACP")


class StubPolicyStore:
    def __init__(self, entries: list[PolicyEntry]) -> None:
        self._entries = list(entries)

    async def list(
        self,
        *,
        project_scope: str | None = None,
        status: PolicyStatus | None = None,
    ) -> list[PolicyEntry]:
        entries = list(self._entries)
        if project_scope is not None:
            entries = [entry for entry in entries if entry.project_scope == project_scope]
        if status is not None:
            entries = [entry for entry in entries if entry.status is status]
        return entries


@pytest.mark.anyio
async def test_drive_service_emits_session_created_before_turn_completion() -> None:
    event_store = StubEventStore()
    checkpoint_store = StubCheckpointStore()
    event_sink = RecordingEventSink()
    session_manager = StubSessionManager()

    created = OperationDomainEventDraft(
        event_type="operation.created",
        payload={
            "objective": "do the task",
            "allowed_agents": ["codex_acp"],
            "policy": {"allowed_agents": ["codex_acp"], "involvement_level": "auto"},
            "execution_budget": {
                "max_iterations": 3,
                "timeout_seconds": None,
                "max_task_retries": 2,
            },
            "runtime_hints": {"operator_message_window": 3, "metadata": {}},
        },
    )
    await event_store.append("op-1", 0, [created])

    drive = DriveService(
        lifecycle_gate=LifecycleGate(),
        reconciler=RuntimeReconciler(
            wakeup_inbox=StubWakeupInbox(),
            command_inbox=StubCommandInbox(),
        ),
        executor=PolicyExecutor(
            brain=StubBrain(),
            session_manager=session_manager,
        ),
        event_store=event_store,
        checkpoint_store=checkpoint_store,
        replay_service=StubReplayService(),
        event_sink=event_sink,
    )

    outcome = await drive.drive("op-1", RunOptions(max_cycles=1))

    event_types = [event.event_type for event in event_sink.events]
    assert event_types[:3] == [
        "brain.decision.made",
        "session.created",
        "agent.turn.completed",
    ]
    assert outcome.status in {OperationStatus.RUNNING, OperationStatus.FAILED}


@pytest.mark.anyio
async def test_drive_service_materializes_permission_escalation_as_attention_request() -> None:
    event_store = StubEventStore()
    checkpoint_store = StubCheckpointStore()
    event_sink = RecordingEventSink()
    session_manager = IncompleteSessionManager()

    created = OperationDomainEventDraft(
        event_type="operation.created",
        payload={
            "objective": "do the task",
            "allowed_agents": ["codex_acp"],
            "policy": {"allowed_agents": ["codex_acp"], "involvement_level": "auto"},
            "execution_budget": {
                "max_iterations": 3,
                "timeout_seconds": None,
                "max_task_retries": 2,
            },
            "runtime_hints": {"operator_message_window": 3, "metadata": {}},
        },
    )
    await event_store.append("op-1", 0, [created])

    drive = DriveService(
        lifecycle_gate=LifecycleGate(),
        reconciler=RuntimeReconciler(
            wakeup_inbox=StubWakeupInbox(),
            command_inbox=StubCommandInbox(),
        ),
        executor=PolicyExecutor(
            brain=StubBrain(),
            session_manager=session_manager,
        ),
        event_store=event_store,
        checkpoint_store=checkpoint_store,
        replay_service=StubReplayService(),
        event_sink=event_sink,
    )

    outcome = await drive.drive("op-1", RunOptions(max_cycles=1))

    event_types = [event.event_type for event in event_sink.events]
    assert "attention.request.created" in event_types
    attention_event = next(
        event for event in event_sink.events if event.event_type == "attention.request.created"
    )
    assert attention_event.payload["attention_type"] == "approval_request"
    assert attention_event.payload["target_scope"] == "session"
    assert attention_event.payload["target_id"] == "sess-1"
    assert attention_event.payload["blocking"] is True
    assert attention_event.payload["metadata"]["kind"] == "permission_escalation"
    permission_events = [
        event for event in event_sink.events if event.event_type.startswith("permission.request.")
    ]
    assert [event.event_type for event in permission_events] == [
        "permission.request.observed",
        "permission.request.escalated",
        "permission.request.followup_required",
    ]
    assert permission_events[0].payload["signature"]["adapter_key"] == "codex_acp"
    assert permission_events[1].payload["rationale"] == "Need operator decision."
    assert permission_events[1].payload["involvement_level"] == "auto"
    assert (
        permission_events[1].payload["linked_attention_id"]
        == attention_event.payload["attention_id"]
    )
    assert (
        permission_events[2].payload["required_followup_reason"]
        == "codex_acp requires explicit replacement instructions after a rejected "
        "or escalated permission request."
    )
    assert outcome.status is OperationStatus.NEEDS_HUMAN


@pytest.mark.anyio
async def test_drive_service_materializes_approved_permission_decision_events() -> None:
    event_store = StubEventStore()
    checkpoint_store = StubCheckpointStore()
    event_sink = RecordingEventSink()

    await event_store.append(
        "op-1",
        0,
        [
            OperationDomainEventDraft(
                event_type="operation.created",
                payload={
                    "objective": "do the task",
                    "allowed_agents": ["codex_acp"],
                    "policy": {"allowed_agents": ["codex_acp"], "involvement_level": "auto"},
                    "execution_budget": {
                        "max_iterations": 3,
                        "timeout_seconds": None,
                        "max_task_retries": 2,
                    },
                    "runtime_hints": {"operator_message_window": 3, "metadata": {}},
                },
            )
        ],
    )

    drive = DriveService(
        lifecycle_gate=LifecycleGate(),
        reconciler=RuntimeReconciler(
            wakeup_inbox=StubWakeupInbox(),
            command_inbox=StubCommandInbox(),
        ),
        executor=PolicyExecutor(
            brain=StubBrain(),
            session_manager=PermissionApprovedSessionManager(),
        ),
        event_store=event_store,
        checkpoint_store=checkpoint_store,
        replay_service=StubReplayService(),
        event_sink=event_sink,
    )

    await drive.drive("op-1", RunOptions(max_cycles=1))

    permission_events = [
        event for event in event_sink.events if event.event_type.startswith("permission.request.")
    ]
    assert [event.event_type for event in permission_events] == [
        "permission.request.observed",
        "permission.request.decided",
    ]
    assert permission_events[1].payload["decision"] == "approve"
    assert permission_events[1].payload["decision_source"] == "brain"


@pytest.mark.anyio
async def test_drive_service_materializes_rejected_codex_permission_followup_events() -> None:
    event_store = StubEventStore()
    checkpoint_store = StubCheckpointStore()
    event_sink = RecordingEventSink()

    await event_store.append(
        "op-1",
        0,
        [
            OperationDomainEventDraft(
                event_type="operation.created",
                payload={
                    "objective": "do the task",
                    "allowed_agents": ["codex_acp"],
                    "policy": {"allowed_agents": ["codex_acp"], "involvement_level": "auto"},
                    "execution_budget": {
                        "max_iterations": 3,
                        "timeout_seconds": None,
                        "max_task_retries": 2,
                    },
                    "runtime_hints": {"operator_message_window": 3, "metadata": {}},
                },
            )
        ],
    )

    drive = DriveService(
        lifecycle_gate=LifecycleGate(),
        reconciler=RuntimeReconciler(
            wakeup_inbox=StubWakeupInbox(),
            command_inbox=StubCommandInbox(),
        ),
        executor=PolicyExecutor(
            brain=StubBrain(),
            session_manager=PermissionRejectedSessionManager(),
        ),
        event_store=event_store,
        checkpoint_store=checkpoint_store,
        replay_service=StubReplayService(),
        event_sink=event_sink,
    )

    await drive.drive("op-1", RunOptions(max_cycles=1))

    permission_events = [
        event for event in event_sink.events if event.event_type.startswith("permission.request.")
    ]
    assert [event.event_type for event in permission_events] == [
        "permission.request.observed",
        "permission.request.decided",
        "permission.request.followup_required",
    ]
    assert permission_events[1].payload["decision"] == "reject"
    assert permission_events[2].payload["required_followup_reason"] == (
        "Codex needs replacement instructions."
    )


@pytest.mark.anyio
async def test_drive_service_exposes_codex_permission_followup_to_next_brain_call() -> None:
    """Catches dropping materialized permission follow-up events from the v2 brain bridge."""
    event_store = StubEventStore()
    checkpoint_store = StubCheckpointStore()
    brain = PermissionFollowupBrain()

    await event_store.append(
        "op-1",
        0,
        [
            OperationDomainEventDraft(
                event_type="operation.created",
                payload={
                    "objective": "do the task",
                    "allowed_agents": ["codex_acp"],
                    "policy": {"allowed_agents": ["codex_acp"], "involvement_level": "auto"},
                    "execution_budget": {
                        "max_iterations": 3,
                        "timeout_seconds": None,
                        "max_task_retries": 2,
                    },
                    "runtime_hints": {"operator_message_window": 3, "metadata": {}},
                },
            )
        ],
    )

    drive = DriveService(
        lifecycle_gate=LifecycleGate(),
        reconciler=RuntimeReconciler(
            wakeup_inbox=StubWakeupInbox(),
            command_inbox=StubCommandInbox(),
        ),
        executor=PolicyExecutor(
            brain=brain,
            session_manager=PermissionRejectedSessionManager(),
        ),
        event_store=event_store,
        checkpoint_store=checkpoint_store,
        replay_service=StubReplayService(),
    )

    outcome = await drive.drive("op-1", RunOptions(max_cycles=2))

    assert outcome.status is OperationStatus.COMPLETED
    assert brain.observed_permission_events[0] == []
    followup_events = brain.observed_permission_events[1]
    assert [event["event_type"] for event in followup_events] == [
        "permission.request.observed",
        "permission.request.decided",
        "permission.request.followup_required",
    ]
    assert followup_events[1]["payload"]["decision"] == "reject"
    assert followup_events[2]["payload"]["required_followup_reason"] == (
        "Codex needs replacement instructions."
    )


@pytest.mark.anyio
async def test_drive_service_reuses_wake_cycle_and_skips_intermediate_checkpoint_for_more_actions(
) -> None:
    """Catches the mutation where DriveService checkpoints before a `more_actions` sub-call."""
    event_store = StubEventStore()
    checkpoint_store = StubCheckpointStore()
    brain = MoreActionsBrain()

    created = OperationDomainEventDraft(
        event_type="operation.created",
        payload={
            "objective": "do the task",
            "allowed_agents": ["codex_acp"],
            "policy": {"allowed_agents": ["codex_acp"], "involvement_level": "auto"},
            "execution_budget": {
                "max_iterations": 3,
                "timeout_seconds": None,
                "max_task_retries": 2,
            },
            "runtime_hints": {"operator_message_window": 3, "metadata": {}},
        },
    )
    await event_store.append("op-1", 0, [created])

    drive = DriveService(
        lifecycle_gate=LifecycleGate(),
        reconciler=RuntimeReconciler(
            wakeup_inbox=StubWakeupInbox(),
            command_inbox=StubCommandInbox(),
        ),
        executor=PolicyExecutor(brain=brain),
        event_store=event_store,
        checkpoint_store=checkpoint_store,
        replay_service=StubReplayService(),
    )

    outcome = await drive.drive("op-1", RunOptions(max_cycles=3))

    decision_events = [
        event for event in event_store.streams["op-1"] if event.event_type == "brain.decision.made"
    ]
    assert len(decision_events) == 2
    assert decision_events[0].payload["more_actions"] is True
    assert decision_events[1].payload["more_actions"] is False
    assert (
        decision_events[0].payload["wake_cycle_id"]
        == decision_events[1].payload["wake_cycle_id"]
    )
    assert len(checkpoint_store.saved) == 1
    assert brain.calls == 2
    assert outcome.status is OperationStatus.COMPLETED


@pytest.mark.anyio
async def test_drive_service_stops_continuation_series_at_max_consecutive_actions() -> None:
    """Catches the mutation where the continuation guardrail is ignored."""
    event_store = StubEventStore()
    checkpoint_store = StubCheckpointStore()

    class LoopingBrain:
        def __init__(self) -> None:
            self.calls = 0

        async def decide_next_action(self, state) -> BrainDecision:
            self.calls += 1
            return BrainDecision(
                action_type=BrainActionType.APPLY_POLICY,
                rationale="Keep going in the same wake cycle.",
                more_actions=True,
            )

    brain = LoopingBrain()
    created = OperationDomainEventDraft(
        event_type="operation.created",
        payload={
            "objective": "do the task",
            "allowed_agents": ["codex_acp"],
            "policy": {"allowed_agents": ["codex_acp"], "involvement_level": "auto"},
            "execution_budget": {
                "max_iterations": 3,
                "timeout_seconds": None,
                "max_task_retries": 2,
            },
            "runtime_hints": {"operator_message_window": 3, "metadata": {}},
        },
    )
    await event_store.append("op-1", 0, [created])

    drive = DriveService(
        lifecycle_gate=LifecycleGate(),
        reconciler=RuntimeReconciler(
            wakeup_inbox=StubWakeupInbox(),
            command_inbox=StubCommandInbox(),
        ),
        executor=PolicyExecutor(brain=brain),
        event_store=event_store,
        checkpoint_store=checkpoint_store,
        replay_service=StubReplayService(),
        max_cycles=10,
        max_consecutive_actions=1,
    )

    outcome = await drive.drive("op-1", RunOptions(max_cycles=10))

    decision_events = [
        event for event in event_store.streams["op-1"] if event.event_type == "brain.decision.made"
    ]
    assert len(decision_events) == 10
    assert checkpoint_store.saved
    assert brain.calls == 10
    assert outcome.status is OperationStatus.FAILED


@pytest.mark.anyio
async def test_drive_service_passes_recent_decisions_to_brain_across_replay_and_continuations(
) -> None:
    """Catches the mutation where the brain loses prior/sub-call decision history."""
    event_store = StubEventStore()
    checkpoint_store = StubCheckpointStore()
    brain = RecentDecisionsBrain()

    created = OperationDomainEventDraft(
        event_type="operation.created",
        payload={
            "objective": "inspect recent decisions",
            "allowed_agents": ["codex_acp"],
            "policy": {"allowed_agents": ["codex_acp"], "involvement_level": "auto"},
            "execution_budget": {
                "max_iterations": 3,
                "timeout_seconds": None,
                "max_task_retries": 2,
            },
            "runtime_hints": {"operator_message_window": 3, "metadata": {}},
        },
    )
    await event_store.append("op-1", 0, [created])

    drive = DriveService(
        lifecycle_gate=LifecycleGate(),
        reconciler=RuntimeReconciler(
            wakeup_inbox=StubWakeupInbox(),
            command_inbox=StubCommandInbox(),
        ),
        executor=PolicyExecutor(brain=brain),
        event_store=event_store,
        checkpoint_store=checkpoint_store,
        replay_service=ReplayServiceWithPriorDecision(),
    )

    await drive.drive("op-1", RunOptions(max_cycles=2))

    assert brain.observed_recent_decisions[0] == [
        (BrainActionType.START_AGENT.value, False, "wc-prior")
    ]
    second_call_history = brain.observed_recent_decisions[1]
    assert second_call_history[0] == (BrainActionType.START_AGENT.value, False, "wc-prior")
    assert second_call_history[1][0] == BrainActionType.APPLY_POLICY.value
    assert second_call_history[1][1] is True
    assert second_call_history[1][2] != "wc-prior"


@pytest.mark.anyio
async def test_drive_service_rebuilds_policy_coverage_for_brain_context() -> None:
    """Catches the mutation where DriveService keeps using stale aggregate policy coverage."""

    class PolicyCoverageBrain:
        def __init__(self) -> None:
            self.seen_status: PolicyCoverageStatus | None = None

        async def decide_next_action(self, state) -> BrainDecision:
            self.seen_status = state.policy_coverage.status
            return BrainDecision(
                action_type=BrainActionType.STOP,
                rationale="Stop after observing policy coverage.",
            )

    event_store = StubEventStore()
    checkpoint_store = StubCheckpointStore()
    brain = PolicyCoverageBrain()

    created = OperationDomainEventDraft(
        event_type="operation.created",
        payload={
            "objective": "Prepare the release checklist",
            "metadata": {"policy_scope": "profile:test"},
            "allowed_agents": ["codex_acp"],
            "policy": {"allowed_agents": ["codex_acp"], "involvement_level": "auto"},
            "execution_budget": {
                "max_iterations": 3,
                "timeout_seconds": None,
                "max_task_retries": 2,
            },
            "runtime_hints": {"operator_message_window": 3, "metadata": {}},
        },
    )
    stored_created = await event_store.append("op-1", 0, [created])

    drive = DriveService(
        lifecycle_gate=LifecycleGate(),
        reconciler=RuntimeReconciler(
            wakeup_inbox=StubWakeupInbox(),
            command_inbox=StubCommandInbox(),
        ),
        executor=PolicyExecutor(brain=brain),
        event_store=event_store,
        checkpoint_store=checkpoint_store,
        replay_service=ReplayServiceWithSuffixEvents(stored_created),
        policy_store=StubPolicyStore(
            [
                PolicyEntry(
                    policy_id="policy-1",
                    project_scope="profile:test",
                    title="Release policy",
                    category=PolicyCategory.RELEASE,
                    rule_text="Require review for release work.",
                    applicability=PolicyApplicability(objective_keywords=["release"]),
                )
            ]
        ),
        adapter_registry=StubAdapterRegistry(),
    )

    await drive.drive("op-1", RunOptions(max_cycles=1))

    assert brain.seen_status is PolicyCoverageStatus.COVERED


@pytest.mark.anyio
async def test_drive_service_uses_epoch_loaded_from_checkpoint_store() -> None:
    event_store = StubEventStore()
    checkpoint_store = StubCheckpointStore()
    checkpoint_store.loaded_epoch_id = 7

    created = OperationDomainEventDraft(
        event_type="operation.created",
        payload={
            "objective": "do the task",
            "allowed_agents": ["codex_acp"],
            "policy": {"allowed_agents": ["codex_acp"], "involvement_level": "auto"},
            "execution_budget": {
                "max_iterations": 1,
                "timeout_seconds": None,
                "max_task_retries": 2,
            },
            "runtime_hints": {"operator_message_window": 3, "metadata": {}},
        },
    )
    await event_store.append("op-1", 0, [created])

    drive = DriveService(
        lifecycle_gate=LifecycleGate(),
        reconciler=RuntimeReconciler(
            wakeup_inbox=StubWakeupInbox(),
            command_inbox=StubCommandInbox(),
        ),
        executor=PolicyExecutor(brain=MoreActionsBrain()),
        event_store=event_store,
        checkpoint_store=checkpoint_store,
        replay_service=StubReplayService(),
    )

    await drive.drive("op-1", RunOptions(max_cycles=2))

    assert checkpoint_store.saved_epoch_ids == [7]


@pytest.mark.anyio
async def test_drive_service_propagates_stale_epoch_error() -> None:
    event_store = StubEventStore()
    checkpoint_store = StaleEpochCheckpointStore()

    created = OperationDomainEventDraft(
        event_type="operation.created",
        payload={
            "objective": "do the task",
            "allowed_agents": ["codex_acp"],
            "policy": {"allowed_agents": ["codex_acp"], "involvement_level": "auto"},
            "execution_budget": {
                "max_iterations": 1,
                "timeout_seconds": None,
                "max_task_retries": 2,
            },
            "runtime_hints": {"operator_message_window": 3, "metadata": {}},
        },
    )
    await event_store.append("op-1", 0, [created])

    drive = DriveService(
        lifecycle_gate=LifecycleGate(),
        reconciler=RuntimeReconciler(
            wakeup_inbox=StubWakeupInbox(),
            command_inbox=StubCommandInbox(),
        ),
        executor=PolicyExecutor(brain=MoreActionsBrain()),
        event_store=event_store,
        checkpoint_store=checkpoint_store,
        replay_service=StubReplayService(),
    )

    with pytest.raises(StaleEpochError, match="stale epoch"):
        await drive.drive("op-1", RunOptions(max_cycles=2))
