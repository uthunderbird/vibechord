"""Tests for OperatorServiceV2 — Layer 4."""
from __future__ import annotations

import asyncio
from collections.abc import Callable
from pathlib import Path
from typing import cast

import pytest

from agent_operator.application.drive.agent_run_supervisor import AgentRunSupervisorV2
from agent_operator.application.drive.drive_service import DriveService
from agent_operator.application.drive.process_manager_context import ProcessManagerContext
from agent_operator.application.event_sourcing.event_sourced_commands import (
    EventSourcedCommandApplicationService,
)
from agent_operator.application.operator_service_v2 import OperatorServiceV2
from agent_operator.domain.enums import OperationStatus
from agent_operator.domain.event_sourcing import (
    OperationDomainEventDraft,
    StoredOperationDomainEvent,
)
from agent_operator.domain.operation import (
    ExecutionBudget,
    OperationGoal,
    OperationOutcome,
    RunOptions,
)
from agent_operator.projectors import DefaultOperationProjector
from agent_operator.protocols import OperationEventStore
from agent_operator.runtime import FileOperationCheckpointStore, FileOperationEventStore
from agent_operator.testing.operator_service_support import MemoryEventSink


class StubEventStore:
    """In-memory event store stub for unit tests."""

    def __init__(self) -> None:
        self._streams: dict[str, list[StoredOperationDomainEvent]] = {}

    async def append(
        self,
        operation_id: str,
        expected_sequence: int,
        events: list[OperationDomainEventDraft],
    ) -> list[StoredOperationDomainEvent]:
        stream = self._streams.setdefault(operation_id, [])
        stored = []
        for i, draft in enumerate(events, start=expected_sequence + 1):
            stored.append(
                StoredOperationDomainEvent(
                    operation_id=operation_id,
                    sequence=i,
                    event_type=draft.event_type,
                    payload=draft.payload,
                )
            )
        stream.extend(stored)
        return stored

    async def load_after(
        self,
        operation_id: str,
        *,
        after_sequence: int = 0,
    ) -> list[StoredOperationDomainEvent]:
        return [e for e in self._streams.get(operation_id, []) if e.sequence > after_sequence]

    async def load_last_sequence(self, operation_id: str) -> int:
        stream = self._streams.get(operation_id, [])
        return stream[-1].sequence if stream else 0


class StubDriveService:
    """DriveService stub that records calls and returns a fixed outcome."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, RunOptions]] = []

    async def drive(
        self,
        operation_id: str,
        options: RunOptions,
        *,
        context_ready: Callable[[ProcessManagerContext], None] | None = None,
    ) -> OperationOutcome:
        del context_ready
        self.calls.append((operation_id, options))
        from datetime import UTC, datetime
        return OperationOutcome(
            operation_id=operation_id,
            status=OperationStatus.COMPLETED,
            summary="done",
            ended_at=datetime.now(UTC),
        )


class ShutdownAwareDriveService:
    """Drive stub that exits only after shutdown requests drain on its context."""

    def __init__(self) -> None:
        self.started = asyncio.Event()
        self.exited = asyncio.Event()
        self.contexts: list[ProcessManagerContext] = []

    async def drive(
        self,
        operation_id: str,
        options: RunOptions,
        *,
        context_ready: Callable[[ProcessManagerContext], None] | None = None,
    ) -> OperationOutcome:
        del operation_id, options
        ctx = ProcessManagerContext()
        self.contexts.append(ctx)
        if context_ready is not None:
            context_ready(ctx)
        self.started.set()
        while not ctx.draining:
            await asyncio.sleep(0)
        self.exited.set()
        from datetime import UTC, datetime
        return OperationOutcome(
            operation_id="op-shutdown",
            status=OperationStatus.CANCELLED,
            summary="drained",
            ended_at=datetime.now(UTC),
        )


class RecordingSupervisor(AgentRunSupervisorV2):
    def __init__(self) -> None:
        super().__init__()
        self.calls: list[str] = []

    def mark_draining(self) -> None:
        self.calls.append("mark_draining")
        super().mark_draining()

    def cancel_all(self) -> None:
        self.calls.append("cancel_all")
        super().cancel_all()


class OrderingSupervisor(RecordingSupervisor):
    def __init__(self, *, drive_exited: asyncio.Event) -> None:
        super().__init__()
        self._drive_exited = drive_exited

    def cancel_all(self) -> None:
        assert self._drive_exited.is_set() is True
        super().cancel_all()


async def _seed_created_operation(
    command_service: EventSourcedCommandApplicationService,
    operation_id: str,
) -> None:
    await command_service.append_domain_events(
        operation_id,
        [
            OperationDomainEventDraft(
                event_type="operation.created",
                payload={
                    "objective": "Initial objective",
                    "harness_instructions": None,
                    "success_criteria": [],
                    "metadata": {},
                    "allowed_agents": [],
                    "involvement_level": "auto",
                    "created_at": "2026-04-24T00:00:00+00:00",
                },
            )
        ],
    )


def _make_service(
    drive: StubDriveService | None = None,
    store: StubEventStore | None = None,
    event_sink: MemoryEventSink | None = None,
) -> tuple[OperatorServiceV2, StubDriveService, StubEventStore]:
    drive = drive or StubDriveService()
    store = store or StubEventStore()
    svc = OperatorServiceV2(
        drive_service=cast(DriveService, drive),
        event_store=cast(OperationEventStore, store),
        event_sink=event_sink,
    )
    return svc, drive, store


@pytest.mark.anyio
async def test_run_writes_birth_event_then_drives() -> None:
    svc, drive, store = _make_service()
    goal = OperationGoal(objective="do something")
    outcome = await svc.run(goal, operation_id="op-1")

    # Birth event written to event store
    events = store._streams.get("op-1", [])
    assert any(e.event_type == "operation.created" for e in events)

    # DriveService was called
    assert len(drive.calls) == 1
    assert drive.calls[0][0] == "op-1"

    assert outcome.status is OperationStatus.COMPLETED


@pytest.mark.anyio
async def test_run_birth_event_carries_policy_budget_and_runtime_hints() -> None:
    svc, drive, store = _make_service()
    goal = OperationGoal(objective="do something")
    await svc.run(
        goal,
        operation_id="op-1",
        policy=None,
        budget=ExecutionBudget(max_iterations=3),
    )

    created = next(e for e in store._streams["op-1"] if e.event_type == "operation.created")
    assert created.payload["execution_budget"]["max_iterations"] == 3
    assert created.payload["policy"]["allowed_agents"] == []
    assert created.payload["runtime_hints"]["operator_message_window"] == 3


@pytest.mark.anyio
async def test_run_emits_birth_event_to_run_event_sink() -> None:
    event_sink = MemoryEventSink()
    svc, _, _ = _make_service(event_sink=event_sink)

    await svc.run(OperationGoal(objective="do something"), operation_id="op-1")

    assert [event.event_type for event in event_sink.events] == ["operation.created"]
    assert event_sink.events[0].operation_id == "op-1"
    assert event_sink.events[0].category == "domain"

@pytest.mark.anyio
async def test_run_generates_operation_id_when_not_provided() -> None:
    svc, drive, store = _make_service()
    goal = OperationGoal(objective="test")
    await svc.run(goal)

    assert len(drive.calls) == 1
    oid = drive.calls[0][0]
    assert oid  # non-empty
    assert oid in store._streams


@pytest.mark.anyio
async def test_run_passes_budget_as_max_cycles() -> None:
    svc, drive, store = _make_service()
    del store
    goal = OperationGoal(objective="test")
    budget = ExecutionBudget(max_iterations=5)

    await svc.run(goal, budget=budget)

    assert drive.calls[0][1].max_cycles == 5


@pytest.mark.anyio
async def test_resume_calls_drive_without_writing_events() -> None:
    svc, drive, store = _make_service()
    await store.append(
        "op-existing",
        0,
        [OperationDomainEventDraft(event_type="operation.created", payload={})],
    )
    await svc.resume("op-existing")

    assert len(drive.calls) == 1
    assert drive.calls[0][0] == "op-existing"
    # Resume does not append new lifecycle events.
    assert len(store._streams["op-existing"]) == 1


@pytest.mark.anyio
async def test_resume_passes_budget_as_max_cycles() -> None:
    svc, drive, store = _make_service()
    await store.append(
        "op-1",
        0,
        [OperationDomainEventDraft(event_type="operation.created", payload={})],
    )
    budget = ExecutionBudget(max_iterations=42)
    await svc.resume("op-1", budget=budget)

    opts = drive.calls[0][1]
    assert opts.max_cycles == 42


@pytest.mark.anyio
async def test_run_rejects_existing_operation_id() -> None:
    svc, drive, store = _make_service()
    await store.append(
        "op-1",
        0,
        [OperationDomainEventDraft(event_type="operation.created", payload={})],
    )

    with pytest.raises(RuntimeError, match="already exists"):
        await svc.run(OperationGoal(objective="duplicate"), operation_id="op-1")

    assert drive.calls == []


@pytest.mark.anyio
async def test_resume_rejects_missing_operation_id() -> None:
    svc, drive, store = _make_service()
    del store

    with pytest.raises(RuntimeError, match="was not found"):
        await svc.resume("op-missing")

    assert drive.calls == []


@pytest.mark.anyio
async def test_cancel_writes_cancelled_event(tmp_path: Path) -> None:
    event_store = FileOperationEventStore(tmp_path / "events")
    checkpoint_store = FileOperationCheckpointStore(tmp_path / "checkpoints")
    projector = DefaultOperationProjector()
    command_service = EventSourcedCommandApplicationService(
        event_store=event_store,
        checkpoint_store=checkpoint_store,
        projector=projector,
    )
    await _seed_created_operation(command_service, "op-1")
    drive = StubDriveService()
    svc = OperatorServiceV2(
        drive_service=cast(DriveService, drive),
        event_store=cast(OperationEventStore, event_store),
        event_sourced_command_service=command_service,
    )

    outcome = await svc.cancel("op-1", reason="user requested")

    assert outcome.status is OperationStatus.CANCELLED
    assert "user requested" in outcome.summary

    cancel_events = [
        e for e in await event_store.load_after("op-1")
        if e.event_type == "operation.status.changed"
        and e.payload.get("status") == OperationStatus.CANCELLED.value
    ]
    assert len(cancel_events) == 1
    accepted_events = [
        e for e in await event_store.load_after("op-1") if e.event_type == "command.accepted"
    ]
    assert len(accepted_events) == 1
    persisted = await checkpoint_store.load_latest("op-1")
    assert persisted is not None
    assert persisted.checkpoint_payload["status"] == OperationStatus.CANCELLED.value


@pytest.mark.anyio
async def test_cancel_without_reason_uses_default_summary(tmp_path: Path) -> None:
    event_store = FileOperationEventStore(tmp_path / "events")
    checkpoint_store = FileOperationCheckpointStore(tmp_path / "checkpoints")
    projector = DefaultOperationProjector()
    command_service = EventSourcedCommandApplicationService(
        event_store=event_store,
        checkpoint_store=checkpoint_store,
        projector=projector,
    )
    await _seed_created_operation(command_service, "op-1")
    svc = OperatorServiceV2(
        drive_service=cast(DriveService, StubDriveService()),
        event_store=cast(OperationEventStore, event_store),
        event_sourced_command_service=command_service,
    )

    outcome = await svc.cancel("op-1")
    assert outcome.summary == "Operation cancelled."


@pytest.mark.anyio
async def test_cancel_rejects_terminal_operation(tmp_path: Path) -> None:
    event_store = FileOperationEventStore(tmp_path / "events")
    checkpoint_store = FileOperationCheckpointStore(tmp_path / "checkpoints")
    projector = DefaultOperationProjector()
    command_service = EventSourcedCommandApplicationService(
        event_store=event_store,
        checkpoint_store=checkpoint_store,
        projector=projector,
    )
    await _seed_created_operation(command_service, "op-1")
    await command_service.append_domain_events(
        "op-1",
        [
            OperationDomainEventDraft(
                event_type="operation.status.changed",
                payload={
                    "status": OperationStatus.CANCELLED.value,
                    "final_summary": "Operation cancelled.",
                },
            ),
        ],
    )
    svc = OperatorServiceV2(
        drive_service=cast(DriveService, StubDriveService()),
        event_store=cast(OperationEventStore, event_store),
        event_sourced_command_service=command_service,
    )

    with pytest.raises(RuntimeError, match="operation_terminal: operation is already cancelled."):
        await svc.cancel("op-1")


@pytest.mark.anyio
async def test_on_sigterm_requests_drain_before_cancelling_supervisor_tasks() -> None:
    drive = ShutdownAwareDriveService()
    store = StubEventStore()
    supervisor = RecordingSupervisor()
    await store.append(
        "op-shutdown",
        0,
        [OperationDomainEventDraft(event_type="operation.created", payload={})],
    )

    async def _background() -> None:
        await asyncio.sleep(3600)

    background_task = supervisor.spawn(
        _background(),
        operation_id="op-shutdown",
        session_id="session-1",
    )
    svc = OperatorServiceV2(
        drive_service=cast(DriveService, drive),
        event_store=cast(OperationEventStore, store),
        supervisor=supervisor,
    )

    resume_task = asyncio.create_task(svc.resume("op-shutdown"))
    await drive.started.wait()

    await svc._on_sigterm()
    await asyncio.gather(resume_task, background_task, return_exceptions=True)

    assert drive.contexts[0].draining is True
    assert drive.exited.is_set() is True
    assert supervisor.calls == ["mark_draining", "cancel_all"]
    assert background_task.cancelled() is True
    assert svc._drive_tasks == []


@pytest.mark.anyio
async def test_on_sigterm_waits_for_drive_exit_before_cancelling_background_tasks() -> None:
    """Catches the mutation where shutdown cancels background tasks before drive loops exit."""
    drive = ShutdownAwareDriveService()
    store = StubEventStore()
    supervisor = OrderingSupervisor(drive_exited=drive.exited)
    await store.append(
        "op-shutdown",
        0,
        [OperationDomainEventDraft(event_type="operation.created", payload={})],
    )

    async def _background() -> None:
        await asyncio.sleep(3600)

    background_task = supervisor.spawn(
        _background(),
        operation_id="op-shutdown",
        session_id="session-1",
    )
    svc = OperatorServiceV2(
        drive_service=cast(DriveService, drive),
        event_store=cast(OperationEventStore, store),
        supervisor=supervisor,
    )

    resume_task = asyncio.create_task(svc.resume("op-shutdown"))
    await drive.started.wait()

    await svc._on_sigterm()
    await asyncio.gather(resume_task, background_task, return_exceptions=True)

    assert drive.exited.is_set() is True
    assert background_task.cancelled() is True


@pytest.mark.anyio
async def test_run_rejects_new_work_while_service_is_draining() -> None:
    svc, _, _ = _make_service()
    svc._accepting = False

    with pytest.raises(RuntimeError, match="draining"):
        await svc.run(OperationGoal(objective="blocked"))
