from __future__ import annotations

import asyncio
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
from agent_operator.domain.operation import (
    ExecutionProfileStamp,
    ObjectiveState,
    RunOptions,
    SessionState,
)
from agent_operator.domain.policy import PolicyApplicability, PolicyCategory, PolicyEntry
from agent_operator.dtos.requests import AgentRunRequest
from agent_operator.runtime import FileFactStore


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


class OneShotBrain:
    async def decide_next_action(self, state) -> BrainDecision:
        return BrainDecision(
            action_type=BrainActionType.START_AGENT,
            target_agent="codex_acp",
            instruction="inspect",
            rationale="Run one bounded one-shot task.",
            one_shot=True,
            focus_task_id="task-1",
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


class DependencyBarrierApplyPolicyBrain:
    def __init__(self) -> None:
        self.calls = 0

    async def decide_next_action(self, state) -> BrainDecision:
        self.calls += 1
        return BrainDecision(
            action_type=BrainActionType.WAIT_FOR_MATERIAL_CHANGE,
            rationale="Runtime execution is unavailable until ACP health changes.",
            blocking_focus={
                "kind": "dependency_barrier",
                "target_id": "task-1",
                "blocking_reason": (
                    "Repeated ACP subprocess-closed failures; "
                    "wait for runtime health change."
                ),
                "interrupt_policy": "material_wakeup",
                "resume_policy": "replan",
            },
        )


class StubSessionManager:
    def __init__(self) -> None:
        self.collected = False
        self.started_requests: list[AgentRunRequest] = []
        self.sent_messages: list[tuple[str, str]] = []

    async def start(self, adapter_key: str, request: AgentRunRequest):
        from agent_operator.domain import AgentSessionHandle

        assert adapter_key == "codex_acp"
        self.started_requests.append(request)
        return AgentSessionHandle(
            adapter_key=adapter_key,
            session_id="sess-1",
            session_name="sess",
            display_name="Codex",
            one_shot=False,
            metadata=dict(request.metadata),
        )

    async def collect(self, handle):
        self.collected = True
        return AgentResult(
            session_id=handle.session_id,
            status=AgentResultStatus.SUCCESS,
            output_text="done",
            completed_at=datetime.now(UTC),
        )

    async def send(self, handle, message: str) -> None:
        self.sent_messages.append((handle.session_id, message))

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


class CancelledSessionManager(StubSessionManager):
    async def collect(self, handle):
        self.collected = True
        return AgentResult(
            session_id=handle.session_id,
            status=AgentResultStatus.CANCELLED,
            output_text="",
            completed_at=datetime.now(UTC),
            error=AgentError(
                code="agent_session_cancelled",
                message="Agent session cancelled.",
                retryable=False,
            ),
        )


class DisconnectedSessionManager(StubSessionManager):
    async def collect(self, handle):
        self.collected = True
        return AgentResult(
            session_id=handle.session_id,
            status=AgentResultStatus.DISCONNECTED,
            output_text="",
            completed_at=datetime.now(UTC),
            error=AgentError(
                code="codex_acp_disconnected",
                message="ACP subprocess closed before completing pending requests.",
                retryable=True,
                raw={"recovery_mode": "same_session"},
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


class HangingCloseSessionManager(StubSessionManager):
    def __init__(self) -> None:
        super().__init__()
        self.close_started = False
        self.close_gate = asyncio.Event()

    async def close(self, handle) -> None:
        self.close_started = True
        await self.close_gate.wait()


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


class ContinueExistingSessionBrain:
    async def decide_next_action(self, state) -> BrainDecision:
        return BrainDecision(
            action_type=BrainActionType.CONTINUE_AGENT,
            target_agent="codex_acp",
            session_id="sess-1",
            instruction="continue after approval",
            rationale="Resume the compatible active session.",
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
                    causation_id=draft.causation_id,
                    correlation_id=draft.correlation_id,
                    metadata=draft.metadata,
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


class ReplayServiceWithExecutionProfileMetadata:
    async def load(self, operation_id: str):
        checkpoint = OperationCheckpoint.initial(operation_id)
        checkpoint.objective = ObjectiveState(
            objective="do the task",
            metadata={
                "effective_adapter_settings": {
                    "codex_acp": {
                        "model": "gpt-5.4",
                        "reasoning_effort": "low",
                        "approval_policy": "auto",
                        "sandbox_mode": "workspace-write",
                    }
                }
            },
        )
        checkpoint.allowed_agents = ["codex_acp"]
        return type(
            "ReplayState",
            (),
            {
                "checkpoint": checkpoint,
                "last_applied_sequence": 1,
                "suffix_events": [],
            },
        )()


class ReplayServiceWithStampedSession:
    async def load(self, operation_id: str):
        checkpoint = OperationCheckpoint.initial(operation_id)
        checkpoint.objective = ObjectiveState(
            objective="do the task",
            metadata={
                "effective_adapter_settings": {
                    "codex_acp": {
                        "model": "gpt-5.4",
                        "reasoning_effort": "low",
                        "approval_policy": "auto",
                        "sandbox_mode": "workspace-write",
                    }
                }
            },
        )
        checkpoint.allowed_agents = ["codex_acp"]
        checkpoint.sessions = [
            SessionState(
                handle={
                    "adapter_key": "codex_acp",
                    "session_id": "sess-1",
                    "session_name": "sess",
                    "display_name": "Codex",
                    "metadata": {
                        "execution_profile_model": "gpt-5.4",
                        "execution_profile_reasoning_effort": "low",
                        "execution_profile_approval_policy": "auto",
                        "execution_profile_sandbox_mode": "workspace-write",
                    },
                },
                execution_profile_stamp=ExecutionProfileStamp(
                    adapter_key="codex_acp",
                    model="gpt-5.4",
                    effort_field_name="reasoning_effort",
                    effort_value="low",
                    approval_policy="auto",
                    sandbox_mode="workspace-write",
                ),
            )
        ]
        return type(
            "ReplayState",
            (),
            {
                "checkpoint": checkpoint,
                "last_applied_sequence": 2,
                "suffix_events": [],
            },
        )()


class ReplayServiceWithUnstampedSession:
    async def load(self, operation_id: str):
        checkpoint = OperationCheckpoint.initial(operation_id)
        checkpoint.objective = ObjectiveState(
            objective="do the task",
            metadata={
                "effective_adapter_settings": {
                    "codex_acp": {
                        "model": "gpt-5.4",
                        "reasoning_effort": "low",
                    }
                }
            },
        )
        checkpoint.allowed_agents = ["codex_acp"]
        checkpoint.sessions = [
            SessionState(
                handle={
                    "adapter_key": "codex_acp",
                    "session_id": "sess-1",
                    "session_name": "sess",
                    "display_name": "Codex",
                    "metadata": {},
                }
            )
        ]
        return type(
            "ReplayState",
            (),
            {
                "checkpoint": checkpoint,
                "last_applied_sequence": 2,
                "suffix_events": [],
            },
        )()


class ReplayServiceWithHandleOnlyStampedSession:
    """Session has execution_profile_model in handle metadata but no stamp field.

    Simulates a session created through the attached path where stamp is stored
    in-memory only and lost when the process restarts.
    """

    async def load(self, operation_id: str):
        checkpoint = OperationCheckpoint.initial(operation_id)
        checkpoint.objective = ObjectiveState(
            objective="do the task",
            metadata={
                "effective_adapter_settings": {
                    "codex_acp": {
                        "model": "gpt-5.4",
                        "reasoning_effort": "low",
                        "approval_policy": "auto",
                        "sandbox_mode": "workspace-write",
                    }
                }
            },
        )
        checkpoint.allowed_agents = ["codex_acp"]
        checkpoint.sessions = [
            SessionState(
                handle={
                    "adapter_key": "codex_acp",
                    "session_id": "sess-1",
                    "session_name": "sess",
                    "display_name": "Codex",
                    "metadata": {
                        "execution_profile_model": "gpt-5.4",
                        "execution_profile_reasoning_effort": "low",
                        "execution_profile_approval_policy": "auto",
                        "execution_profile_sandbox_mode": "workspace-write",
                    },
                },
                # execution_profile_stamp is intentionally absent (None)
            )
        ]
        return type(
            "ReplayState",
            (),
            {
                "checkpoint": checkpoint,
                "last_applied_sequence": 2,
                "suffix_events": [],
            },
        )()


class ReplayServiceWithCheckpointPermissionEvents:
    async def load(self, operation_id: str):
        checkpoint = OperationCheckpoint.initial(operation_id)
        checkpoint.permission_events = [
            {
                "event_type": "permission.request.followup_required",
                "payload": {
                    "adapter_key": "codex_acp",
                    "session_id": "sess-checkpoint",
                    "required_followup_reason": "Checkpoint follow-up needed.",
                },
            }
        ]
        return type(
            "ReplayState",
            (),
            {
                "checkpoint": checkpoint,
                "last_applied_sequence": 3,
                "suffix_events": [],
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
async def test_policy_executor_session_created_carries_effective_execution_profile() -> None:
    """Catches v2 real session launches dropping Codex profile metadata."""

    event_store = StubEventStore()
    checkpoint_store = StubCheckpointStore()
    event_sink = RecordingEventSink()
    session_manager = StubSessionManager()

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
                    "metadata": {
                        "effective_adapter_settings": {
                            "codex_acp": {
                                "model": "gpt-5.4",
                                "reasoning_effort": "low",
                                "approval_policy": "auto",
                                "sandbox_mode": "workspace-write",
                            }
                        }
                    },
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
            session_manager=session_manager,
        ),
        event_store=event_store,
        checkpoint_store=checkpoint_store,
        replay_service=ReplayServiceWithExecutionProfileMetadata(),
        event_sink=event_sink,
    )

    await drive.drive("op-1", RunOptions(max_cycles=1))

    request_metadata = session_manager.started_requests[0].metadata
    assert request_metadata["execution_profile_model"] == "gpt-5.4"
    assert request_metadata["execution_profile_reasoning_effort"] == "low"
    assert request_metadata["execution_profile_approval_policy"] == "auto"
    assert request_metadata["execution_profile_sandbox_mode"] == "workspace-write"

    session_created = next(
        event for event in event_sink.events if event.event_type == "session.created"
    )
    handle_metadata = session_created.payload["handle"]["metadata"]
    assert handle_metadata["execution_profile_model"] == "gpt-5.4"
    assert handle_metadata["execution_profile_reasoning_effort"] == "low"
    assert handle_metadata["execution_profile_approval_policy"] == "auto"
    assert handle_metadata["execution_profile_sandbox_mode"] == "workspace-write"

    session = SessionState(**session_created.payload)
    assert session.execution_profile_stamp is not None
    assert session.execution_profile_stamp.model == "gpt-5.4"
    assert session.execution_profile_stamp.effort_value == "low"
    assert session.execution_profile_stamp.approval_policy == "auto"
    assert session.execution_profile_stamp.sandbox_mode == "workspace-write"


@pytest.mark.anyio
async def test_policy_executor_continue_agent_reuses_compatible_session() -> None:
    """Catches v2 continue-agent decisions incorrectly starting a fresh session."""

    event_store = StubEventStore()
    checkpoint_store = StubCheckpointStore()
    event_sink = RecordingEventSink()
    session_manager = StubSessionManager()

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
            brain=ContinueExistingSessionBrain(),
            session_manager=session_manager,
        ),
        event_store=event_store,
        checkpoint_store=checkpoint_store,
        replay_service=ReplayServiceWithStampedSession(),
        event_sink=event_sink,
    )

    outcome = await drive.drive("op-1", RunOptions(max_cycles=1))

    assert outcome.status in {OperationStatus.RUNNING, OperationStatus.FAILED}
    assert session_manager.started_requests == []
    assert session_manager.sent_messages == [("sess-1", "continue after approval")]
    assert [event.event_type for event in event_sink.events].count("session.created") == 0


@pytest.mark.anyio
async def test_policy_executor_continue_agent_rejects_unstamped_session() -> None:
    """Catches v2 continuation silently reusing sessions without observed profile stamps."""

    event_store = StubEventStore()
    checkpoint_store = StubCheckpointStore()
    event_sink = RecordingEventSink()
    session_manager = StubSessionManager()

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
            brain=ContinueExistingSessionBrain(),
            session_manager=session_manager,
        ),
        event_store=event_store,
        checkpoint_store=checkpoint_store,
        replay_service=ReplayServiceWithUnstampedSession(),
        event_sink=event_sink,
    )

    outcome = await drive.drive("op-1", RunOptions(max_cycles=1))

    assert outcome.status is OperationStatus.FAILED
    assert session_manager.started_requests == []
    assert session_manager.sent_messages == []
    status_event = next(
        event for event in event_sink.events if event.event_type == "operation.status.changed"
    )
    assert "has no observed execution profile" in status_event.payload["final_summary"]


@pytest.mark.anyio
async def test_policy_executor_continue_agent_recovers_stamp_from_handle_metadata() -> None:
    """Session with stamp only in handle metadata (not in stamp field) can be continued.

    Regression test: attached-path sessions store execution_profile_model in
    handle.metadata but may lose the stamp field when the process restarts.
    The continuation guard must fall back to handle.metadata before rejecting.
    """

    event_store = StubEventStore()
    checkpoint_store = StubCheckpointStore()
    event_sink = RecordingEventSink()
    session_manager = StubSessionManager()

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
            brain=ContinueExistingSessionBrain(),
            session_manager=session_manager,
        ),
        event_store=event_store,
        checkpoint_store=checkpoint_store,
        replay_service=ReplayServiceWithHandleOnlyStampedSession(),
        event_sink=event_sink,
    )

    outcome = await drive.drive("op-1", RunOptions(max_cycles=1))

    # Must NOT fail — stamp recovered from handle.metadata
    assert outcome.status in {OperationStatus.RUNNING, OperationStatus.FAILED}
    assert session_manager.started_requests == []
    assert session_manager.sent_messages == [("sess-1", "continue after approval")]
    assert not any(
        "has no observed execution profile" in str(e.payload)
        for e in event_sink.events
        if e.event_type == "operation.status.changed"
    )


@pytest.mark.anyio
async def test_policy_executor_records_terminal_success_before_close_returns() -> None:
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
            session_manager=HangingCloseSessionManager(),
        ),
        event_store=event_store,
        checkpoint_store=checkpoint_store,
        replay_service=StubReplayService(),
        event_sink=event_sink,
    )

    outcome = await asyncio.wait_for(drive.drive("op-1", RunOptions(max_cycles=1)), timeout=0.2)

    event_types = [event.event_type for event in event_sink.events]
    assert "agent.turn.completed" in event_types
    assert "session.observed_state.changed" in event_types
    assert outcome.status in {OperationStatus.RUNNING, OperationStatus.FAILED}


@pytest.mark.anyio
async def test_policy_executor_completes_successful_one_shot_turn() -> None:
    """Catches one-shot successes being replanned into duplicate agent starts."""

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
            brain=OneShotBrain(),
            session_manager=StubSessionManager(),
        ),
        event_store=event_store,
        checkpoint_store=checkpoint_store,
        replay_service=StubReplayService(),
        event_sink=event_sink,
    )

    outcome = await drive.drive("op-1", RunOptions(max_cycles=3))
    turn_events = [
        event for event in event_sink.events if event.event_type == "agent.turn.completed"
    ]

    assert outcome.status is OperationStatus.COMPLETED
    assert len(turn_events) == 1
    assert turn_events[0].payload["iteration"] == 0
    assert turn_events[0].payload["task_id"] == "task-1"


@pytest.mark.anyio
async def test_policy_executor_records_cancelled_turn_as_cancelled() -> None:
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
            session_manager=CancelledSessionManager(),
        ),
        event_store=event_store,
        checkpoint_store=checkpoint_store,
        replay_service=StubReplayService(),
        event_sink=event_sink,
    )

    await drive.drive("op-1", RunOptions(max_cycles=1))

    turn_event = next(
        event for event in event_sink.events if event.event_type == "agent.turn.completed"
    )
    observed_event = next(
        event
        for event in event_sink.events
        if event.event_type == "session.observed_state.changed"
    )

    assert turn_event.payload["status"] == "cancelled"
    assert observed_event.payload["status"] == "cancelled"


@pytest.mark.anyio
async def test_policy_executor_records_disconnected_turn_as_disconnected(tmp_path) -> None:
    event_store = StubEventStore()
    checkpoint_store = StubCheckpointStore()
    event_sink = RecordingEventSink()
    fact_store = FileFactStore(tmp_path / "facts")

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
            session_manager=DisconnectedSessionManager(),
        ),
        event_store=event_store,
        checkpoint_store=checkpoint_store,
        replay_service=StubReplayService(),
        event_sink=event_sink,
        fact_store=fact_store,
    )

    await drive.drive("op-1", RunOptions(max_cycles=1))

    turn_event = next(
        event for event in event_sink.events if event.event_type == "agent.turn.completed"
    )
    observed_event = next(
        event
        for event in event_sink.events
        if event.event_type == "session.observed_state.changed"
    )
    facts = await fact_store.load_after("op-1")

    assert turn_event.payload["status"] == "disconnected"
    assert observed_event.payload["status"] == "disconnected"
    assert [fact.fact_type for fact in facts] == [
        "session.started",
        "session.discontinuity_observed",
    ]
    assert await fact_store.load_translated_sequence("op-1") == 2


@pytest.mark.anyio
async def test_drive_service_materializes_runtime_drain_before_exiting() -> None:
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
            session_manager=StubSessionManager(),
        ),
        event_store=event_store,
        checkpoint_store=checkpoint_store,
        replay_service=StubReplayService(),
        event_sink=event_sink,
    )

    outcome = await drive.drive(
        "op-1",
        RunOptions(max_cycles=3),
        context_ready=lambda ctx: ctx.request_drain(),
    )

    parked_event = next(
        event for event in event_sink.events if event.event_type == "operation.parked.updated"
    )

    assert parked_event.payload["parked_execution"]["kind"] == "runtime_drained"
    assert "operator_resumed" in parked_event.payload["parked_execution"]["wake_predicates"]
    assert outcome.status is OperationStatus.RUNNING


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
async def test_drive_service_persists_waiting_input_and_permission_facts(tmp_path) -> None:
    event_store = StubEventStore()
    checkpoint_store = StubCheckpointStore()
    fact_store = FileFactStore(tmp_path / "facts")
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
        fact_store=fact_store,
    )

    await drive.drive("op-1", RunOptions(max_cycles=1))

    facts = await fact_store.load_after("op-1")
    assert [fact.fact_type for fact in facts] == [
        "session.started",
        "session.waiting_input_observed",
        "permission.request.observed",
        "permission.request.escalated",
        "permission.request.followup_required",
    ]
    assert facts[1].payload["status"] == "interrupted"
    assert await fact_store.load_translated_sequence("op-1") == 5
    caused_event_types = [
        event.event_type
        for event in event_store.streams["op-1"]
        if event.causation_id is not None
    ]
    assert caused_event_types == [
        "session.created",
        "agent.turn.completed",
        "permission.request.observed",
        "permission.request.escalated",
        "permission.request.followup_required",
    ]


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
async def test_drive_service_persists_runtime_facts_for_materialized_agent_events(
    tmp_path,
) -> None:
    event_store = StubEventStore()
    checkpoint_store = StubCheckpointStore()
    fact_store = FileFactStore(tmp_path / "facts")

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
        fact_store=fact_store,
    )

    await drive.drive("op-1", RunOptions(max_cycles=1))

    facts = await fact_store.load_after("op-1")
    assert [fact.fact_type for fact in facts] == [
        "session.started",
        "session.completed",
        "permission.request.observed",
        "permission.request.decided",
    ]
    assert await fact_store.load_translated_sequence("op-1") == 4
    materialized_events = event_store.streams["op-1"]
    caused_event_types = [
        event.event_type for event in materialized_events if event.causation_id is not None
    ]
    assert caused_event_types == [
        "session.created",
        "agent.turn.completed",
        "permission.request.observed",
        "permission.request.decided",
    ]


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
async def test_drive_service_exposes_checkpoint_permission_followup_to_brain() -> None:
    """Catches rebuilding the drive aggregate from suffix events only."""
    event_store = StubEventStore()
    checkpoint_store = StubCheckpointStore()
    brain = PermissionFollowupBrain()

    drive = DriveService(
        lifecycle_gate=LifecycleGate(),
        reconciler=RuntimeReconciler(
            wakeup_inbox=StubWakeupInbox(),
            command_inbox=StubCommandInbox(),
        ),
        executor=PolicyExecutor(brain=brain),
        event_store=event_store,
        checkpoint_store=checkpoint_store,
        replay_service=ReplayServiceWithCheckpointPermissionEvents(),
    )

    await drive.drive("op-1", RunOptions(max_cycles=1))

    assert brain.observed_permission_events[0] == [
        {
            "event_type": "permission.request.followup_required",
            "payload": {
                "adapter_key": "codex_acp",
                "session_id": "sess-checkpoint",
                "required_followup_reason": "Checkpoint follow-up needed.",
            },
        }
    ]


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
async def test_drive_service_parks_wait_for_material_change_dependency_barrier_without_spinning(
) -> None:
    event_store = StubEventStore()
    checkpoint_store = StubCheckpointStore()
    brain = DependencyBarrierApplyPolicyBrain()

    created = OperationDomainEventDraft(
        event_type="operation.created",
        payload={
            "objective": "wait for ACP runtime health",
            "allowed_agents": ["codex_acp"],
            "policy": {"allowed_agents": ["codex_acp"], "involvement_level": "auto"},
            "execution_budget": {
                "max_iterations": 10,
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
    )

    outcome = await drive.drive("op-1", RunOptions(max_cycles=10))

    decision_events = [
        event
        for event in event_store.streams["op-1"]
        if event.event_type == "brain.decision.made"
    ]
    focus_events = [
        event
        for event in event_store.streams["op-1"]
        if event.event_type == "operation.focus.updated"
    ]
    parked_events = [
        event
        for event in event_store.streams["op-1"]
        if event.event_type == "operation.parked.updated"
    ]
    status_events = [
        event
        for event in event_store.streams["op-1"]
        if event.event_type == "operation.status.changed"
        and event.payload.get("final_summary") == "Maximum iterations reached."
    ]

    assert len(decision_events) == 1
    assert len(focus_events) == 1
    assert len(parked_events) == 1
    assert focus_events[0].payload["focus"]["kind"] == "dependency_barrier"
    assert parked_events[0].payload["parked_execution"]["kind"] == "dependency_barrier"
    assert (
        parked_events[0].payload["parked_execution"]["reason"]
        == "Runtime execution is unavailable until ACP health changes."
    )
    assert not status_events
    assert brain.calls == 1
    assert outcome.status is OperationStatus.RUNNING


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
