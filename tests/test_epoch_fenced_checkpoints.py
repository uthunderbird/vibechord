from __future__ import annotations

from datetime import UTC, datetime

import pytest

from agent_operator.application.drive.drive_service import DriveService
from agent_operator.application.drive.policy_executor import PolicyExecutor
from agent_operator.application.drive.runtime_reconciler import RuntimeReconciler
from agent_operator.domain.brain import BrainDecision
from agent_operator.domain.checkpoints import OperationCheckpoint
from agent_operator.domain.enums import BrainActionType
from agent_operator.domain.event_sourcing import (
    OperationCheckpointRecord,
    OperationDomainEventDraft,
    StaleEpochError,
    StoredOperationDomainEvent,
)
from agent_operator.domain.operation import RunOptions


class MoreActionsBrain:
    async def decide_next_action(self, state) -> BrainDecision:
        del state
        return BrainDecision(
            action_type=BrainActionType.APPLY_POLICY,
            rationale="Continue once inside the same wake cycle.",
            more_actions=True,
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
        del operation_id
        return None, self.loaded_epoch_id

    async def save(self, record: OperationCheckpointRecord) -> None:
        self.saved.append(record)

    async def save_with_epoch(self, record: OperationCheckpointRecord, epoch_id: int) -> None:
        self.saved_epoch_ids.append(epoch_id)
        self.saved.append(record)


class StaleEpochCheckpointStore(StubCheckpointStore):
    async def save_with_epoch(self, record: OperationCheckpointRecord, epoch_id: int) -> None:
        del record
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


class StubWakeupInbox:
    async def requeue_stale_claims(self) -> int:
        return 0

    async def claim(self, operation_id: str, limit: int = 100):
        del operation_id, limit
        return []

    async def ack(self, event_ids: list[str]) -> None:
        del event_ids

    async def release(self, event_ids: list[str]) -> None:
        del event_ids


class StubCommandInbox:
    async def list_pending(self, operation_id: str):
        del operation_id
        return []


def _created_event() -> OperationDomainEventDraft:
    return OperationDomainEventDraft(
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
        timestamp=datetime.now(UTC),
    )


@pytest.mark.anyio
async def test_drive_service_uses_epoch_loaded_from_checkpoint_store() -> None:
    from agent_operator.application.drive.lifecycle_gate import LifecycleGate

    event_store = StubEventStore()
    checkpoint_store = StubCheckpointStore()
    checkpoint_store.loaded_epoch_id = 7
    await event_store.append("op-1", 0, [_created_event()])

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
        max_consecutive_actions=0,
    )

    await drive.drive("op-1", RunOptions(max_cycles=1))

    assert checkpoint_store.saved_epoch_ids
    assert checkpoint_store.saved_epoch_ids == [7] * len(checkpoint_store.saved_epoch_ids)


@pytest.mark.anyio
async def test_drive_service_propagates_stale_epoch_error() -> None:
    from agent_operator.application.drive.lifecycle_gate import LifecycleGate

    event_store = StubEventStore()
    checkpoint_store = StaleEpochCheckpointStore()
    await event_store.append("op-1", 0, [_created_event()])

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
        max_consecutive_actions=0,
    )

    with pytest.raises(StaleEpochError, match="stale epoch"):
        await drive.drive("op-1", RunOptions(max_cycles=1))
