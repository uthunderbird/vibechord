"""Unit tests for RuntimeReconciler — event-returning reconciliation (ADR 0195)."""
from __future__ import annotations

from datetime import datetime
from typing import Any

import pytest

from agent_operator.application.drive.agent_run_supervisor import AgentRunSupervisorV2
from agent_operator.application.drive.process_manager_context import ProcessManagerContext
from agent_operator.application.drive.runtime_reconciler import RuntimeReconciler
from agent_operator.domain.aggregate import OperationAggregate
from agent_operator.domain.enums import BackgroundRunStatus, CommandStatus, OperationCommandType
from agent_operator.domain.operation import OperationGoal

# ── In-memory stubs ────────────────────────────────────────────────────────────


class StubWakeupInbox:
    def __init__(self, events: list[Any] | None = None) -> None:
        self._events = events or []
        self.acked: list[str] = []
        self.released: list[str] = []
        self.requeue_called = False

    async def requeue_stale_claims(self) -> int:
        self.requeue_called = True
        return 0

    async def claim(self, operation_id: str, limit: int = 100) -> list[Any]:
        return list(self._events)

    async def ack(self, event_ids: list[str]) -> None:
        self.acked.extend(event_ids)

    async def release(self, event_ids: list[str]) -> None:
        self.released.extend(event_ids)

    async def enqueue(self, event: Any) -> None:
        self._events.append(event)

    async def list_pending(self, operation_id: str) -> list[Any]:
        return list(self._events)


class StubCommandInbox:
    def __init__(self, commands: list[Any] | None = None) -> None:
        self._commands = commands or []
        self.status_updates: list[tuple[str, CommandStatus, dict[str, Any]]] = []

    async def enqueue(self, command: Any) -> None:
        self._commands.append(command)

    async def list(self, operation_id: str) -> list[Any]:
        return list(self._commands)

    async def list_pending(self, operation_id: str) -> list[Any]:
        return list(self._commands)

    async def update_status(self, command_id: str, status: Any, **kwargs: Any) -> Any:
        self.status_updates.append((command_id, status, kwargs))
        return None


class StubCommand:
    def __init__(self, command_id: str) -> None:
        self.command_id = command_id
        self.operation_id = "op-1"
        self.command_type = OperationCommandType.INJECT_OPERATOR_MESSAGE


class StubCommandApplyResult:
    def __init__(
        self,
        *,
        applied: bool,
        stored_events: list[Any],
        rejection_reason: str | None = None,
    ) -> None:
        self.applied = applied
        self.stored_events = stored_events
        self.rejection_reason = rejection_reason


class StubEventSourcedCommandService:
    def __init__(self, results: list[StubCommandApplyResult] | None = None) -> None:
        self.results = results or [
            StubCommandApplyResult(applied=True, stored_events=[object()])
        ]
        self.applied_command_ids: list[str] = []

    async def apply(self, command: Any) -> StubCommandApplyResult:
        self.applied_command_ids.append(command.command_id)
        if len(self.applied_command_ids) <= len(self.results):
            return self.results[len(self.applied_command_ids) - 1]
        return self.results[-1]


class StubRunEvent:
    def __init__(
        self,
        event_id: str,
        event_type: str,
        payload: dict[str, Any] | None = None,
        session_id: str | None = None,
        task_id: str | None = None,
    ) -> None:
        self.event_id = event_id
        self.event_type = event_type
        self.payload = payload or {}
        self.session_id = session_id
        self.task_id = task_id


class StubExecution:
    def __init__(self, run_id: str, status: BackgroundRunStatus) -> None:
        self.run_id = run_id
        self.status = status
        self.session_id: str | None = None
        self.task_id: str | None = None
        self.last_heartbeat_at: datetime | None = None


class StubSupervisor:
    def __init__(self, runs: dict[str, StubExecution] | None = None) -> None:
        self._runs = runs or {}

    async def poll_background_turn(self, run_id: str) -> StubExecution | None:
        return self._runs.get(run_id)

    async def collect_background_turn(self, run_id: str) -> Any:
        return None

    async def cancel_background_turn(self, run_id: str) -> None:
        pass

    async def finalize_background_turn(self, run_id: str, status: Any, **kwargs: Any) -> None:
        pass

    async def list_runs(self, operation_id: str) -> list[Any]:
        return list(self._runs.values())


def _agg(**kwargs: Any) -> OperationAggregate:
    return OperationAggregate.create(
        OperationGoal(objective="test"),
        operation_id=kwargs.get("operation_id"),
    )


def _ctx() -> ProcessManagerContext:
    return ProcessManagerContext()


# ── drain_commands ─────────────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_drain_commands_applies_pending_through_event_sourced_service() -> None:
    inbox = StubCommandInbox([StubCommand("cmd-1"), StubCommand("cmd-2")])
    command_service = StubEventSourcedCommandService(
        [
            StubCommandApplyResult(applied=True, stored_events=[object()]),
            StubCommandApplyResult(applied=True, stored_events=[object()]),
        ]
    )
    reconciler = RuntimeReconciler(
        wakeup_inbox=StubWakeupInbox(),
        command_inbox=inbox,
        event_sourced_command_service=command_service,  # type: ignore[arg-type]
    )
    ctx = _ctx()

    events = await reconciler.drain_commands(_agg(operation_id="op-1"), ctx)

    assert events == []
    assert command_service.applied_command_ids == ["cmd-1", "cmd-2"]
    assert [update[:2] for update in inbox.status_updates] == [
        ("cmd-1", CommandStatus.APPLIED),
        ("cmd-2", CommandStatus.APPLIED),
    ]
    assert ctx.canonical_replay_advanced is True


@pytest.mark.anyio
async def test_drain_commands_updates_rejected_intent_status() -> None:
    inbox = StubCommandInbox([StubCommand("cmd-1")])
    command_service = StubEventSourcedCommandService(
        [
            StubCommandApplyResult(
                applied=False,
                stored_events=[object()],
                rejection_reason="invalid command",
            )
        ]
    )
    reconciler = RuntimeReconciler(
        wakeup_inbox=StubWakeupInbox(),
        command_inbox=inbox,
        event_sourced_command_service=command_service,  # type: ignore[arg-type]
    )
    ctx = _ctx()

    events = await reconciler.drain_commands(_agg(operation_id="op-1"), ctx)

    assert events == []
    assert command_service.applied_command_ids == ["cmd-1"]
    assert inbox.status_updates[0][0] == "cmd-1"
    assert inbox.status_updates[0][1] is CommandStatus.REJECTED
    assert inbox.status_updates[0][2]["rejection_reason"] == "invalid command"
    assert ctx.canonical_replay_advanced is True


@pytest.mark.anyio
async def test_drain_commands_skips_already_processed() -> None:
    import dataclasses
    agg = dataclasses.replace(_agg(), processed_command_ids=["cmd-1"])
    inbox = StubCommandInbox([StubCommand("cmd-1"), StubCommand("cmd-2")])
    command_service = StubEventSourcedCommandService()
    reconciler = RuntimeReconciler(
        wakeup_inbox=StubWakeupInbox(),
        command_inbox=inbox,
        event_sourced_command_service=command_service,  # type: ignore[arg-type]
    )
    events = await reconciler.drain_commands(agg, _ctx())
    assert events == []
    assert command_service.applied_command_ids == ["cmd-2"]
    assert [update[:2] for update in inbox.status_updates] == [
        ("cmd-1", CommandStatus.APPLIED),
        ("cmd-2", CommandStatus.APPLIED),
    ]


@pytest.mark.anyio
async def test_drain_commands_returns_empty_when_no_pending() -> None:
    reconciler = RuntimeReconciler(
        wakeup_inbox=StubWakeupInbox(),
        command_inbox=StubCommandInbox(),
    )
    events = await reconciler.drain_commands(_agg(), _ctx())
    assert events == []


# ── drain_wakeups ──────────────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_drain_wakeups_requeues_stale_claims() -> None:
    inbox = StubWakeupInbox()
    reconciler = RuntimeReconciler(wakeup_inbox=inbox, command_inbox=StubCommandInbox())
    await reconciler.drain_wakeups(_agg(), _ctx())
    assert inbox.requeue_called is True


@pytest.mark.anyio
async def test_drain_wakeups_releases_events_without_run_id() -> None:
    event = StubRunEvent("evt-1", "agent.turn.completed", payload={})
    inbox = StubWakeupInbox([event])
    reconciler = RuntimeReconciler(wakeup_inbox=inbox, command_inbox=StubCommandInbox())
    events = await reconciler.drain_wakeups(_agg(), _ctx())
    assert events == []
    assert "evt-1" in inbox.released


@pytest.mark.anyio
async def test_drain_wakeups_acks_completed_run() -> None:
    run = StubExecution("run-1", BackgroundRunStatus.COMPLETED)
    event = StubRunEvent("evt-1", "agent.turn.completed", payload={"run_id": "run-1"})
    inbox = StubWakeupInbox([event])
    supervisor = StubSupervisor({"run-1": run})
    reconciler = RuntimeReconciler(
        wakeup_inbox=inbox,
        command_inbox=StubCommandInbox(),
        supervisor=supervisor,
    )
    events = await reconciler.drain_wakeups(_agg(), _ctx())
    assert any(e.event_type == "execution.observed_state.changed" for e in events)
    assert "evt-1" in inbox.acked


# ── detect_orphaned_sessions ───────────────────────────────────────────────────


@pytest.mark.anyio
async def test_detect_orphaned_sessions_returns_empty_without_supervisor() -> None:
    reconciler = RuntimeReconciler(wakeup_inbox=StubWakeupInbox(), command_inbox=StubCommandInbox())
    events = await reconciler.detect_orphaned_sessions(_agg(), _ctx())
    assert events == []


@pytest.mark.anyio
async def test_detect_orphaned_sessions_no_orphans_when_supervisor_knows_run() -> None:
    run = StubExecution("run-1", BackgroundRunStatus.RUNNING)
    supervisor = StubSupervisor({"run-1": run})
    reconciler = RuntimeReconciler(
        wakeup_inbox=StubWakeupInbox(),
        command_inbox=StubCommandInbox(),
        supervisor=supervisor,
    )
    # agg with no executions → nothing to orphan-check
    events = await reconciler.detect_orphaned_sessions(_agg(), _ctx())
    assert events == []


# ── reconcile (integration) ────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_reconcile_combines_all_steps() -> None:
    inbox = StubCommandInbox([StubCommand("cmd-1")])
    command_service = StubEventSourcedCommandService()
    reconciler = RuntimeReconciler(
        wakeup_inbox=StubWakeupInbox(),
        command_inbox=inbox,
        event_sourced_command_service=command_service,  # type: ignore[arg-type]
    )
    ctx = _ctx()
    events = await reconciler.reconcile(_agg(), ctx)
    assert events == []
    assert command_service.applied_command_ids == ["cmd-1"]
    assert ctx.canonical_replay_advanced is True


# ── detect_orphaned_sessions with AgentRunSupervisorV2 (ADR 0201) ─────────────


@pytest.mark.anyio
async def test_detect_orphaned_v2_no_running_sessions_returns_empty() -> None:
    sup = AgentRunSupervisorV2()
    reconciler = RuntimeReconciler(
        wakeup_inbox=StubWakeupInbox(),
        command_inbox=StubCommandInbox(),
        supervisor=sup,
    )
    events = await reconciler.detect_orphaned_sessions(_agg(), _ctx())
    assert events == []


@pytest.mark.anyio
async def test_detect_orphaned_v2_known_session_not_orphaned() -> None:
    import asyncio
    import dataclasses

    sup = AgentRunSupervisorV2()
    # Register session in supervisor (simulates this process spawned it)
    async def _noop() -> None:
        await asyncio.sleep(0)

    task = sup.spawn(_noop(), operation_id="op-1", session_id="s-running")
    await task

    # Build aggregate with a RUNNING session
    from agent_operator.domain.operation import OperationGoal
    base = OperationAggregate.create(OperationGoal(objective="test"), operation_id="op-1")

    class _FakeSession:
        session_id = "s-running"
        status = type("S", (), {"value": "running"})()

    agg_with_session = dataclasses.replace(base, sessions=[_FakeSession()])

    reconciler = RuntimeReconciler(
        wakeup_inbox=StubWakeupInbox(),
        command_inbox=StubCommandInbox(),
        supervisor=sup,
    )
    events = await reconciler.detect_orphaned_sessions(agg_with_session, _ctx())
    assert events == []


@pytest.mark.anyio
async def test_detect_orphaned_v2_unknown_session_generates_crashed_event() -> None:
    import dataclasses

    sup = AgentRunSupervisorV2()
    # Supervisor has NO knowledge of "s-orphan" — simulates crash+restart

    base = OperationAggregate.create(OperationGoal(objective="test"), operation_id="op-1")

    class _FakeSession:
        session_id = "s-orphan"
        status = type("S", (), {"value": "running"})()

    agg_with_session = dataclasses.replace(base, sessions=[_FakeSession()])

    reconciler = RuntimeReconciler(
        wakeup_inbox=StubWakeupInbox(),
        command_inbox=StubCommandInbox(),
        supervisor=sup,
    )
    events = await reconciler.detect_orphaned_sessions(agg_with_session, _ctx())
    assert len(events) == 1
    assert events[0].event_type == "session.crashed"
    assert events[0].payload["session_id"] == "s-orphan"
    assert events[0].payload["reason"] == "ORPHANED_AFTER_RESTART"


@pytest.mark.anyio
async def test_detect_orphaned_v2_runs_once_per_drive_call() -> None:
    import dataclasses

    sup = AgentRunSupervisorV2()
    base = OperationAggregate.create(OperationGoal(objective="test"), operation_id="op-1")

    class _FakeSession:
        session_id = "s-orphan"
        status = type("S", (), {"value": "running"})()

    agg_with_session = dataclasses.replace(base, sessions=[_FakeSession()])
    ctx = _ctx()
    reconciler = RuntimeReconciler(
        wakeup_inbox=StubWakeupInbox(),
        command_inbox=StubCommandInbox(),
        supervisor=sup,
    )

    first = await reconciler.detect_orphaned_sessions(agg_with_session, ctx)
    second = await reconciler.detect_orphaned_sessions(agg_with_session, ctx)

    assert len(first) == 1
    assert second == []
