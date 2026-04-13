from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from agent_operator.application import (
    LoadedOperation,
    OperationCancellationService,
    OperationEntrypointService,
    OperationLifecycleCoordinator,
)
from agent_operator.application.attached_session_registry import AttachedSessionRuntimeRegistry
from agent_operator.application.event_sourcing.event_sourced_birth import (
    EventSourcedOperationBirthService,
)
from agent_operator.application.event_sourcing.event_sourced_replay import EventSourcedReplayService
from agent_operator.domain import (
    AgentResult,
    AgentResultStatus,
    AgentSessionHandle,
    BackgroundRunStatus,
    BackgroundRuntimeMode,
    CanonicalPersistenceMode,
    ExecutionBudget,
    ExecutionState,
    OperationGoal,
    OperationPolicy,
    OperationState,
    OperationStatus,
    RunEventKind,
    RunMode,
    RunOptions,
    RuntimeHints,
    SessionState,
    SessionStatus,
)
from agent_operator.projectors import DefaultOperationProjector
from agent_operator.runtime import (
    FileOperationCheckpointStore,
    FileOperationEventStore,
    FileOperationStore,
)


class MemoryStore:
    """Minimal in-memory operation store for entrypoint-service tests."""

    def __init__(self) -> None:
        self.operations: dict[str, OperationState] = {}
        self.outcomes = {}

    async def save_operation(self, state) -> None:
        self.operations[state.operation_id] = state

    async def save_outcome(self, outcome) -> None:
        self.outcomes[outcome.operation_id] = outcome

    async def load_operation(self, operation_id: str):
        return self.operations.get(operation_id)

    async def load_outcome(self, operation_id: str):
        return self.outcomes.get(operation_id)

    async def list_operation_ids(self) -> list[str]:
        return list(self.operations)

    async def list_operations(self) -> list:
        return []


class FakeSupervisor:
    """Minimal cancellation-capable supervisor fake."""

    def __init__(self) -> None:
        self.cancelled: list[str] = []

    async def cancel_background_turn(self, run_id: str) -> None:
        self.cancelled.append(run_id)


@pytest.mark.anyio
async def test_operation_entrypoint_service_prepares_run_state() -> None:
    """Run entrypoint preparation owns initial state creation details."""
    store = MemoryStore()
    attached_session = AgentSessionHandle(adapter_key="claude_acp", session_id="session-1")
    service = OperationEntrypointService(store=store)

    state = await service.prepare_run(
        goal=OperationGoal(objective="Inspect the repository."),
        policy=OperationPolicy(allowed_agents=["claude_acp"]),
        budget=ExecutionBudget(),
        runtime_hints=RuntimeHints(),
        options=RunOptions(),
        operation_id="op-1",
        attached_sessions=[attached_session],
        merge_runtime_flags=lambda budget, _options: budget,
        attach_initial_sessions=lambda state, sessions: setattr(
            state, "active_session", sessions[0]
        ),
    )

    assert state.operation_id == "op-1"
    assert state.run_started_at is not None
    assert state.active_session is not None
    assert state.active_session.session_id == "session-1"


@pytest.mark.anyio
async def test_operation_entrypoint_service_loads_recover_state_with_reconciliation() -> None:
    """Recover preparation owns loading and recovery reconciliation."""
    store = MemoryStore()
    state = OperationState(
        operation_id="op-1",
        goal=OperationGoal(objective="Recover me."),
        policy=OperationPolicy(),
    )
    await store.save_operation(state)
    called = False

    async def reconcile(operation: OperationState) -> None:
        nonlocal called
        called = True
        operation.updated_at = datetime.now(UTC) + timedelta(seconds=1)

    service = OperationEntrypointService(store=store)
    loaded = await service.load_for_recover(
        operation_id="op-1",
        options=RunOptions(),
        merge_runtime_flags=lambda budget, _options: budget,
        reconcile_orphaned_recoverable_background_runs=reconcile,
    )

    assert called is True
    assert loaded.operation_id == "op-1"


@pytest.mark.anyio
async def test_prepare_run_persists_continuity_and_invocation_runtime_modes() -> None:
    store = MemoryStore()
    service = OperationEntrypointService(store=store)

    state = await service.prepare_run(
        goal=OperationGoal(objective="Inspect the repository."),
        policy=OperationPolicy(),
        budget=ExecutionBudget(),
        runtime_hints=RuntimeHints(),
        options=RunOptions(
            run_mode=RunMode.ATTACHED,
            background_runtime_mode=BackgroundRuntimeMode.ATTACHED_LIVE,
        ),
        operation_id="op-runtime-modes",
        attached_sessions=None,
        merge_runtime_flags=lambda budget, _options: budget,
        attach_initial_sessions=lambda _state, _sessions: None,
    )

    assert state.runtime_hints.metadata["run_mode"] == "attached"
    assert state.runtime_hints.metadata["background_runtime_mode"] == "attached_live"
    assert state.runtime_hints.metadata["continuity_run_mode"] == "attached"
    assert state.runtime_hints.metadata["continuity_background_runtime_mode"] == "attached_live"
    assert state.runtime_hints.metadata["invocation_run_mode"] == "attached"
    assert (
        state.runtime_hints.metadata["invocation_background_runtime_mode"] == "attached_live"
    )


@pytest.mark.anyio
async def test_resume_preserves_continuity_runtime_modes_for_legacy_operation() -> None:
    store = MemoryStore()
    state = OperationState(
        operation_id="op-legacy-attached",
        goal=OperationGoal(objective="Recover me."),
        policy=OperationPolicy(),
        runtime_hints=RuntimeHints(
            metadata={
                "run_mode": "attached",
                "background_runtime_mode": "attached_live",
            }
        ),
    )
    await store.save_operation(state)
    service = OperationEntrypointService(store=store)

    loaded = await service.load_for_resume(
        operation_id="op-legacy-attached",
        options=RunOptions(
            run_mode=RunMode.RESUMABLE,
            background_runtime_mode=BackgroundRuntimeMode.RESUMABLE_WAKEUP,
        ),
        merge_runtime_flags=lambda budget, _options: budget,
    )

    assert loaded.runtime_hints.metadata["run_mode"] == "attached"
    assert loaded.runtime_hints.metadata["background_runtime_mode"] == "attached_live"
    assert loaded.runtime_hints.metadata["continuity_run_mode"] == "attached"
    assert loaded.runtime_hints.metadata["continuity_background_runtime_mode"] == "attached_live"
    assert loaded.runtime_hints.metadata["invocation_run_mode"] == "resumable"
    assert (
        loaded.runtime_hints.metadata["invocation_background_runtime_mode"]
        == "resumable_wakeup"
    )


@pytest.mark.anyio
async def test_operation_entrypoint_service_replays_event_sourced_run_state(tmp_path) -> None:
    store = MemoryStore()
    event_store = FileOperationEventStore(tmp_path / "operation_events")
    checkpoint_store = FileOperationCheckpointStore(tmp_path / "operation_checkpoints")
    projector = DefaultOperationProjector()
    birth = EventSourcedOperationBirthService(
        event_store=event_store,
        checkpoint_store=checkpoint_store,
        projector=projector,
    )
    replay = EventSourcedReplayService(
        event_store=event_store,
        checkpoint_store=checkpoint_store,
        projector=projector,
    )
    service = OperationEntrypointService(
        store=store,
        event_sourced_operation_birth_service=birth,
        event_sourced_replay_service=replay,
    )

    state = await service.prepare_run(
        goal=OperationGoal(objective="Inspect the repository."),
        policy=OperationPolicy(allowed_agents=["claude_acp"]),
        budget=ExecutionBudget(),
        runtime_hints=RuntimeHints(),
        options=RunOptions(),
        operation_id="op-es-1",
        attached_sessions=None,
        merge_runtime_flags=lambda budget, _options: budget,
        attach_initial_sessions=lambda _state, _sessions: None,
    )

    assert state.operation_id == "op-es-1"
    assert state.canonical_persistence_mode is CanonicalPersistenceMode.EVENT_SOURCED


@pytest.mark.anyio
async def test_operation_entrypoint_service_replays_event_sourced_resume_state(tmp_path) -> None:
    store = MemoryStore()
    event_store = FileOperationEventStore(tmp_path / "operation_events")
    checkpoint_store = FileOperationCheckpointStore(tmp_path / "operation_checkpoints")
    projector = DefaultOperationProjector()
    birth = EventSourcedOperationBirthService(
        event_store=event_store,
        checkpoint_store=checkpoint_store,
        projector=projector,
    )
    replay = EventSourcedReplayService(
        event_store=event_store,
        checkpoint_store=checkpoint_store,
        projector=projector,
    )
    service = OperationEntrypointService(
        store=store,
        event_sourced_operation_birth_service=birth,
        event_sourced_replay_service=replay,
    )
    session = AgentSessionHandle(adapter_key="claude_acp", session_id="session-1")
    state = OperationState(
        operation_id="op-es-2",
        goal=OperationGoal(objective="Recover me."),
    )
    state.sessions.append(SessionState(handle=session))
    state.active_session = session
    await birth.birth(state)
    await store.save_operation(state)

    loaded = await service.load_for_resume(
        operation_id="op-es-2",
        options=RunOptions(),
        merge_runtime_flags=lambda budget, _options: budget,
    )

    assert loaded.operation_id == "op-es-2"
    assert loaded.canonical_persistence_mode is CanonicalPersistenceMode.EVENT_SOURCED
    assert len(loaded.sessions) == 1
    assert loaded.sessions[0].session_id == "session-1"
    assert loaded.active_session is not None
    assert loaded.active_session.session_id == "session-1"


@pytest.mark.anyio
async def test_prepare_run_replays_event_sourced_attached_initial_session(tmp_path) -> None:
    store = MemoryStore()
    event_store = FileOperationEventStore(tmp_path / "operation_events")
    checkpoint_store = FileOperationCheckpointStore(tmp_path / "operation_checkpoints")
    projector = DefaultOperationProjector()
    birth = EventSourcedOperationBirthService(
        event_store=event_store,
        checkpoint_store=checkpoint_store,
        projector=projector,
    )
    replay = EventSourcedReplayService(
        event_store=event_store,
        checkpoint_store=checkpoint_store,
        projector=projector,
    )
    service = OperationEntrypointService(
        store=store,
        event_sourced_operation_birth_service=birth,
        event_sourced_replay_service=replay,
    )
    loaded_operation = LoadedOperation(attached_session_registry=AttachedSessionRuntimeRegistry({}))
    attached_session = AgentSessionHandle(adapter_key="claude_acp", session_id="session-1")

    state = await service.prepare_run(
        goal=OperationGoal(objective="Inspect the repository."),
        policy=OperationPolicy(allowed_agents=["claude_acp"]),
        budget=ExecutionBudget(),
        runtime_hints=RuntimeHints(),
        options=RunOptions(),
        operation_id="op-es-3",
        attached_sessions=[attached_session],
        merge_runtime_flags=lambda budget, _options: budget,
        attach_initial_sessions=loaded_operation.attach_initial_sessions,
    )

    assert state.canonical_persistence_mode is CanonicalPersistenceMode.EVENT_SOURCED
    assert len(state.sessions) == 1
    assert state.sessions[0].session_id == "session-1"
    assert state.active_session is not None
    assert state.active_session.session_id == "session-1"


@pytest.mark.anyio
async def test_operation_cancellation_service_cancels_targeted_run() -> None:
    """Cancellation semantics are owned outside the public OperatorService facade."""
    store = MemoryStore()
    supervisor = FakeSupervisor()
    service = OperationCancellationService(store=store, event_sink=None, supervisor=supervisor)
    session = AgentSessionHandle(adapter_key="claude_acp", session_id="session-1")
    state = OperationState(
        operation_id="op-1",
        goal=OperationGoal(objective="Cancel me."),
        policy=OperationPolicy(),
    )
    state.sessions.append(
        SessionState(
            handle=session,
            status=SessionStatus.RUNNING,
            current_execution_id="run-1",
        )
    )
    state.executions.append(
        ExecutionState(
            run_id="run-1",
            operation_id="op-1",
            adapter_key="claude_acp",
            session_id="session-1",
            status=BackgroundRunStatus.RUNNING,
        )
    )
    await store.save_operation(state)
    emitted: list[tuple[str, str, RunEventKind]] = []

    async def emit(
        event_type,
        state,
        iteration,
        payload,
        *,
        task_id=None,
        session_id=None,
        kind=RunEventKind.TRACE,
    ):
        emitted.append((event_type, session_id or "", kind))

    outcome = await service.cancel(
        operation_id="op-1",
        session_id=None,
        run_id="run-1",
        find_background_run=lambda state, run_id: next(
            (run for run in state.executions if run.run_id == run_id),
            None,
        ),
        find_session_record=lambda state, session_id: next(
            (record for record in state.sessions if record.session_id == session_id),
            None,
        ),
        find_latest_result=lambda _state: AgentResult(
            session_id="session-1",
            status=AgentResultStatus.CANCELLED,
            output_text="",
            completed_at=datetime.now(UTC),
        ),
        emit=emit,
    )

    assert outcome.summary == "Cancellation requested."
    assert supervisor.cancelled == ["run-1"]
    assert emitted == [
        ("background_run.cancelled", "session-1", RunEventKind.WAKEUP),
        ("session.observed_state.changed", "session-1", RunEventKind.TRACE),
    ]


@pytest.mark.anyio
async def test_targeted_cancel_persists_session_terminal_state_via_event_sourced_replay(
    tmp_path,
) -> None:
    store = FileOperationStore(tmp_path / "operations")
    event_store = FileOperationEventStore(tmp_path / "operation_events")
    checkpoint_store = FileOperationCheckpointStore(tmp_path / "operation_checkpoints")
    projector = DefaultOperationProjector()
    birth = EventSourcedOperationBirthService(
        event_store=event_store,
        checkpoint_store=checkpoint_store,
        projector=projector,
    )
    replay = EventSourcedReplayService(
        event_store=event_store,
        checkpoint_store=checkpoint_store,
        projector=projector,
    )
    supervisor = FakeSupervisor()
    lifecycle = OperationLifecycleCoordinator(
        store=store,
        event_store=event_store,
        replay_service=replay,
    )
    cancellation = OperationCancellationService(
        store=store,
        event_sink=None,
        supervisor=supervisor,
        lifecycle_coordinator=lifecycle,
    )
    entrypoints = OperationEntrypointService(
        store=store,
        event_sourced_replay_service=replay,
    )
    session = AgentSessionHandle(adapter_key="claude_acp", session_id="session-1")
    state = OperationState(
        operation_id="op-es-cancel",
        goal=OperationGoal(objective="Cancel one running session."),
        policy=OperationPolicy(),
    )
    state.sessions.append(
        SessionState(
            handle=session,
            status=SessionStatus.RUNNING,
            current_execution_id="run-1",
        )
    )
    state.executions.append(
        ExecutionState(
            run_id="run-1",
            operation_id="op-es-cancel",
            adapter_key="claude_acp",
            session_id="session-1",
            status=BackgroundRunStatus.RUNNING,
        )
    )
    await birth.birth(state)
    await store.save_operation(state)

    async def emit(
        event_type,
        state,
        iteration,
        payload,
        *,
        task_id=None,
        session_id=None,
        kind=RunEventKind.TRACE,
    ):
        return None

    outcome = await cancellation.cancel(
        operation_id="op-es-cancel",
        session_id=None,
        run_id="run-1",
        find_background_run=lambda loaded, run_id: next(
            (run for run in loaded.executions if run.run_id == run_id),
            None,
        ),
        find_session_record=lambda loaded, session_id: next(
            (record for record in loaded.sessions if record.session_id == session_id),
            None,
        ),
        find_latest_result=lambda _state: AgentResult(
            session_id="session-1",
            status=AgentResultStatus.CANCELLED,
            output_text="",
            completed_at=datetime.now(UTC),
        ),
        emit=emit,
    )

    snapshot_state = await store.load_operation("op-es-cancel")
    resumed = await entrypoints.load_for_resume(
        operation_id="op-es-cancel",
        options=RunOptions(),
        merge_runtime_flags=lambda budget, _options: budget,
    )
    stored_events = await event_store.load_after("op-es-cancel", after_sequence=0)

    assert outcome.summary == "Cancellation requested."
    assert supervisor.cancelled == ["run-1"]
    assert snapshot_state is not None
    assert snapshot_state.sessions[0].status is SessionStatus.RUNNING
    assert [event.event_type for event in stored_events][-1] == "session.observed_state.changed"
    assert resumed.sessions[0].status is SessionStatus.CANCELLED
    assert resumed.sessions[0].terminal_state is not None


@pytest.mark.anyio
async def test_operation_cancellation_service_cancels_whole_operation() -> None:
    """Whole-operation cancellation persists terminal outcome outside the facade."""
    store = MemoryStore()
    service = OperationCancellationService(store=store, event_sink=None, supervisor=None)
    state = OperationState(
        operation_id="op-1",
        goal=OperationGoal(objective="Cancel me completely."),
        policy=OperationPolicy(),
    )
    await store.save_operation(state)

    outcome = await service.cancel(
        operation_id="op-1",
        session_id=None,
        run_id=None,
        find_background_run=lambda state, run_id: None,
        find_session_record=lambda state, session_id: None,
        find_latest_result=lambda _state: None,
        emit=lambda *args, **kwargs: None,
    )

    assert outcome.status is OperationStatus.CANCELLED
    persisted = await store.load_outcome("op-1")
    assert persisted is not None
    assert persisted.status is OperationStatus.CANCELLED
