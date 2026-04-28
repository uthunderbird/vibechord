from __future__ import annotations

import ast
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast

import pytest

from agent_operator.application import (
    LoadedOperation,
    OperationCancellationService,
    OperationEntrypointService,
    OperationLifecycleCoordinator,
    OperationLifecycleEntrypointGuard,
)
from agent_operator.application.attached_session_registry import AttachedSessionManager
from agent_operator.application.event_sourcing.event_sourced_birth import (
    EventSourcedOperationBirthService,
)
from agent_operator.application.event_sourcing.event_sourced_replay import (
    EventSourcedReplayService,
)
from agent_operator.application.operation_entrypoints import RecoverReconciler
from agent_operator.domain import (
    AgentResult,
    AgentResultStatus,
    AgentSessionHandle,
    BackgroundRunHandle,
    BackgroundRunStatus,
    BackgroundRuntimeMode,
    CanonicalPersistenceMode,
    ExecutionBudget,
    ExecutionState,
    FocusKind,
    FocusMode,
    FocusState,
    InterruptPolicy,
    OperationGoal,
    OperationPolicy,
    OperationState,
    OperationStatus,
    ResumePolicy,
    RunEventKind,
    RunMode,
    RunOptions,
    RuntimeHints,
    SessionState,
    SessionStatus,
)
from agent_operator.projectors import DefaultOperationProjector
from agent_operator.protocols import AgentRunSupervisor, EventSink
from agent_operator.runtime import (
    FileOperationCheckpointStore,
    FileOperationEventStore,
    FileOperationStore,
)


class MemoryStore:
    """Minimal in-memory operation store for entrypoint-service tests."""

    def __init__(self) -> None:
        self.operations: dict[str, OperationState] = {}
        self.outcomes: dict[str, Any] = {}

    async def save_operation(self, state: OperationState) -> None:
        self.operations[state.operation_id] = state

    async def save_outcome(self, outcome: Any) -> None:
        self.outcomes[outcome.operation_id] = outcome

    async def load_operation(self, operation_id: str) -> OperationState | None:
        return self.operations.get(operation_id)

    async def load_outcome(self, operation_id: str) -> Any:
        return self.outcomes.get(operation_id)

    async def list_operation_ids(self) -> list[str]:
        return list(self.operations)

    async def list_operations(self) -> list[Any]:
        return []


class FakeSupervisor:
    """Minimal cancellation-capable supervisor fake."""

    def __init__(self) -> None:
        self.cancelled: list[str] = []

    async def cancel_background_turn(self, run_id: str) -> None:
        self.cancelled.append(run_id)


def _make_running_session(
    handle: AgentSessionHandle,
    *,
    execution_id: str,
) -> SessionState:
    session = SessionState(handle=handle, current_execution_id=execution_id)
    session.status = SessionStatus.RUNNING
    return session


def _make_running_execution(
    *,
    operation_id: str,
    run_id: str,
    session_id: str,
    adapter_key: str = "claude_acp",
) -> ExecutionState:
    execution = ExecutionState(
        execution_id=run_id,
        operation_id=operation_id,
        adapter_key=adapter_key,
        session_id=session_id,
    )
    execution.status = BackgroundRunStatus.RUNNING
    return execution


async def _noop_emit(
    event_type: str,
    state: OperationState,
    iteration: int,
    payload: dict[str, object],
    *,
    task_id: str | None = None,
    session_id: str | None = None,
    kind: RunEventKind = RunEventKind.TRACE,
) -> None:
    del event_type, state, iteration, payload, task_id, session_id, kind


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
        attach_initial_sessions=lambda state, sessions: state.sessions.append(
            SessionState(handle=sessions[0])
        ),
    )

    assert state.operation_id == "op-1"
    assert state.run_started_at is not None
    assert state.sessions[0].session_id == "session-1"
    assert state.active_session_record is not None
    assert state.active_session_record.session_id == "session-1"


@pytest.mark.anyio
async def test_operation_entrypoint_service_rejects_existing_operation_id() -> None:
    store = MemoryStore()
    await store.save_operation(
        OperationState(
            operation_id="op-1",
            goal=OperationGoal(objective="Existing operation"),
            policy=OperationPolicy(),
        )
    )
    service = OperationEntrypointService(
        store=store,
        lifecycle_guard=OperationLifecycleEntrypointGuard(store=store),
    )

    with pytest.raises(RuntimeError, match="already exists"):
        await service.prepare_run(
            goal=OperationGoal(objective="Do not overwrite"),
            policy=OperationPolicy(),
            budget=ExecutionBudget(),
            runtime_hints=RuntimeHints(),
            options=RunOptions(),
            operation_id="op-1",
            attached_sessions=None,
            merge_runtime_flags=lambda budget, _options: budget,
            attach_initial_sessions=lambda _state, _sessions: None,
        )


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
        reconcile_orphaned_recoverable_background_runs=cast(RecoverReconciler, reconcile),
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
async def test_operation_entrypoint_service_replays_event_sourced_run_state(
    tmp_path: Any,
) -> None:
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
async def test_operation_entrypoint_service_replays_event_sourced_resume_state(
    tmp_path: Any,
) -> None:
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
    assert loaded.active_session_record is not None
    assert loaded.active_session_record.session_id == "session-1"


@pytest.mark.anyio
async def test_operation_entrypoint_service_resumes_event_sourced_only_operation(
    tmp_path: Any,
) -> None:
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

    state = OperationState(
        operation_id="op-es-resume-only",
        goal=OperationGoal(objective="Resume event-sourced only operation."),
    )
    await birth.birth(state)

    loaded = await service.load_for_resume(
        operation_id="op-es-resume-only",
        options=RunOptions(),
        merge_runtime_flags=lambda budget, _options: budget,
    )

    assert loaded.operation_id == "op-es-resume-only"
    assert loaded.canonical_persistence_mode is CanonicalPersistenceMode.EVENT_SOURCED
    assert loaded.goal.objective == "Resume event-sourced only operation."


@pytest.mark.anyio
async def test_operation_entrypoint_service_loads_canonical_state_without_snapshot(
    tmp_path: Any,
) -> None:
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
    state = OperationState(
        operation_id="op-es-read-only",
        goal=OperationGoal(objective="Load canonical read state."),
    )
    await birth.birth(state)

    loaded = await service.load_canonical_state("op-es-read-only")

    assert loaded.operation_id == "op-es-read-only"
    assert loaded.canonical_persistence_mode is CanonicalPersistenceMode.EVENT_SOURCED
    assert loaded.goal.objective == "Load canonical read state."


@pytest.mark.anyio
async def test_operation_entrypoint_service_recovers_event_sourced_only_operation(
    tmp_path: Any,
) -> None:
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
    called = False

    async def reconcile(operation: OperationState) -> None:
        nonlocal called
        called = True
        operation.updated_at = datetime.now(UTC)

    state = OperationState(
        operation_id="op-es-recover-only",
        goal=OperationGoal(objective="Recover event-sourced only operation."),
    )
    await birth.birth(state)

    loaded = await service.load_for_recover(
        operation_id="op-es-recover-only",
        options=RunOptions(),
        merge_runtime_flags=lambda budget, _options: budget,
        reconcile_orphaned_recoverable_background_runs=cast(RecoverReconciler, reconcile),
    )

    assert called is True
    assert loaded.operation_id == "op-es-recover-only"
    assert loaded.canonical_persistence_mode is CanonicalPersistenceMode.EVENT_SOURCED
    assert loaded.goal.objective == "Recover event-sourced only operation."


@pytest.mark.anyio
async def test_prepare_run_replays_event_sourced_attached_initial_session(
    tmp_path: Any,
) -> None:
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
    loaded_operation = LoadedOperation(attached_session_registry=AttachedSessionManager({}))
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
    assert state.active_session_record is not None
    assert state.active_session_record.session_id == "session-1"


def test_decorate_background_session_reuse_merges_request_execution_profile_metadata() -> None:
    loaded_operation = LoadedOperation(attached_session_registry=AttachedSessionManager({}))
    state = OperationState(
        operation_id="op-1",
        goal=OperationGoal(objective="Continue the session."),
        policy=OperationPolicy(allowed_agents=["codex_acp"]),
    )
    fallback = AgentSessionHandle(
        adapter_key="codex_acp",
        session_id="session-1",
        session_name="codex session",
        metadata={
            "execution_profile_model": "gpt-5.4",
            "execution_profile_reasoning_effort": "low",
        },
    )
    run = BackgroundRunHandle(
        execution_id="run-1",
        operation_id="op-1",
        adapter_key="codex_acp",
        session_id="session-1",
    )

    decorated = loaded_operation.decorate_background_session(
        run,
        "codex session",
        state,
        fallback=fallback,
        request_metadata={
            "execution_profile_model": "gpt-5.4",
            "execution_profile_reasoning_effort": "low",
            "execution_profile_approval_policy": "auto",
            "execution_profile_sandbox_mode": "danger-full-access",
        },
    )

    assert decorated.metadata["execution_profile_approval_policy"] == "auto"
    assert decorated.metadata["execution_profile_sandbox_mode"] == "danger-full-access"


@pytest.mark.anyio
async def test_operation_cancellation_service_cancels_targeted_run() -> None:
    """Cancellation semantics are owned outside the public OperatorService facade."""
    store = MemoryStore()
    supervisor = FakeSupervisor()
    service = OperationCancellationService(
        store=store,
        event_sink=cast(EventSink, None),
        supervisor=cast(AgentRunSupervisor, supervisor),
    )
    session = AgentSessionHandle(adapter_key="claude_acp", session_id="session-1")
    state = OperationState(
        operation_id="op-1",
        goal=OperationGoal(objective="Cancel me."),
        policy=OperationPolicy(),
    )
    state.sessions.append(
        _make_running_session(session, execution_id="run-1")
    )
    state.executions.append(
        _make_running_execution(
            operation_id="op-1",
            run_id="run-1",
            session_id="session-1",
        )
    )
    await store.save_operation(state)
    emitted: list[tuple[str, str, RunEventKind]] = []

    async def emit(
        event_type: str,
        state: OperationState,
        iteration: int,
        payload: dict[str, object],
        *,
        task_id: str | None = None,
        session_id: str | None = None,
        kind: RunEventKind = RunEventKind.TRACE,
    ) -> None:
        del state, iteration, payload, task_id
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
async def test_targeted_cancel_persists_session_status_via_event_sourced_replay(
    tmp_path: Any,
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
        event_sink=cast(EventSink, None),
        supervisor=cast(AgentRunSupervisor, supervisor),
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
        _make_running_session(session, execution_id="run-1")
    )
    state.executions.append(
        _make_running_execution(
            operation_id="op-es-cancel",
            run_id="run-1",
            session_id="session-1",
        )
    )
    await birth.birth(state)
    await store.save_operation(state)

    async def emit(
        event_type: str,
        state: OperationState,
        iteration: int,
        payload: dict[str, object],
        *,
        task_id: str | None = None,
        session_id: str | None = None,
        kind: RunEventKind = RunEventKind.TRACE,
    ) -> None:
        del event_type, state, iteration, payload, task_id, session_id, kind

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
    assert [event.event_type for event in stored_events][-3:] == [
        "session.waiting_reason.updated",
        "session.observed_state.changed",
        "execution.observed_state.changed",
    ]
    assert resumed.sessions[0].status is SessionStatus.CANCELLED
    assert resumed.sessions[0].waiting_reason == "Cancelled by operator."
    assert resumed.sessions[0].model_dump()["status"] == SessionStatus.CANCELLED
    assert "observed_state" not in resumed.sessions[0].model_dump()
    assert "terminal_state" not in resumed.sessions[0].model_dump()
    assert resumed.sessions[0].current_execution_id is None
    assert resumed.sessions[0].last_terminal_execution_id == "run-1"


@pytest.mark.anyio
async def test_targeted_cancel_seeds_snapshot_only_session_before_replay_persistence(
    tmp_path: Any,
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
        event_sink=cast(EventSink, None),
        supervisor=cast(AgentRunSupervisor, supervisor),
        lifecycle_coordinator=lifecycle,
    )
    entrypoints = OperationEntrypointService(
        store=store,
        event_sourced_replay_service=replay,
    )
    state = OperationState(
        operation_id="op-es-snapshot-session-cancel",
        goal=OperationGoal(objective="Cancel one snapshot-only running session."),
        policy=OperationPolicy(),
    )
    await birth.birth(state)
    session = AgentSessionHandle(adapter_key="claude_acp", session_id="session-1")
    state.sessions.append(
        _make_running_session(session, execution_id="run-1")
    )
    await store.save_operation(state)

    async def emit(
        event_type: str,
        state: OperationState,
        iteration: int,
        payload: dict[str, object],
        *,
        task_id: str | None = None,
        session_id: str | None = None,
        kind: RunEventKind = RunEventKind.TRACE,
    ) -> None:
        del event_type, state, iteration, payload, task_id, session_id, kind

    outcome = await cancellation.cancel(
        operation_id="op-es-snapshot-session-cancel",
        session_id="session-1",
        run_id=None,
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

    resumed = await entrypoints.load_for_resume(
        operation_id="op-es-snapshot-session-cancel",
        options=RunOptions(),
        merge_runtime_flags=lambda budget, _options: budget,
    )
    stored_events = await event_store.load_after(
        "op-es-snapshot-session-cancel",
        after_sequence=0,
    )

    assert outcome.summary == "Cancellation requested."
    assert [event.event_type for event in stored_events][-3:] == [
        "session.created",
        "session.waiting_reason.updated",
        "session.observed_state.changed",
    ]
    assert resumed.sessions[0].status is SessionStatus.CANCELLED
    assert resumed.sessions[0].waiting_reason == "Cancelled by operator."


@pytest.mark.anyio
async def test_whole_operation_cancel_persists_canonical_state_via_event_sourced_replay(
    tmp_path: Any,
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
        event_sink=cast(EventSink, None),
        supervisor=cast(AgentRunSupervisor, supervisor),
        lifecycle_coordinator=lifecycle,
    )
    entrypoints = OperationEntrypointService(
        store=store,
        event_sourced_replay_service=replay,
    )
    session = AgentSessionHandle(adapter_key="claude_acp", session_id="session-1")
    state = OperationState(
        operation_id="op-es-whole-cancel",
        goal=OperationGoal(objective="Cancel the whole operation."),
        policy=OperationPolicy(),
        status=OperationStatus.RUNNING,
        current_focus=FocusState(
            kind=FocusKind.SESSION,
            target_id="session-1",
            mode=FocusMode.BLOCKING,
            blocking_reason="Waiting for completion.",
            interrupt_policy=InterruptPolicy.TERMINAL_ONLY,
            resume_policy=ResumePolicy.REPLAN,
        ),
    )
    state.sessions.append(
        _make_running_session(session, execution_id="run-1")
    )
    state.executions.append(
        _make_running_execution(
            operation_id=state.operation_id,
            run_id="run-1",
            session_id="session-1",
        )
    )
    await birth.birth(state)
    await store.save_operation(state)

    outcome = await cancellation.cancel(
        operation_id=state.operation_id,
        session_id=None,
        run_id=None,
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
        emit=_noop_emit,
    )

    resumed = await entrypoints.load_for_resume(
        operation_id=state.operation_id,
        options=RunOptions(),
        merge_runtime_flags=lambda budget, _options: budget,
    )
    stored_events = await event_store.load_after(state.operation_id, after_sequence=0)

    assert outcome.status is OperationStatus.CANCELLED
    assert supervisor.cancelled == ["run-1"]
    event_types = [event.event_type for event in stored_events]
    for event_type in (
        "session.waiting_reason.updated",
        "session.observed_state.changed",
        "execution.observed_state.changed",
        "operation.focus.updated",
        "operation.status.changed",
    ):
        assert event_type in event_types
    assert resumed.status is OperationStatus.CANCELLED
    assert resumed.current_focus is None
    assert resumed.sessions[0].status is SessionStatus.CANCELLED
    assert resumed.background_runs[0].status is BackgroundRunStatus.CANCELLED


@pytest.mark.anyio
async def test_finalize_outcome_persists_terminal_status_via_event_sourced_replay(
    tmp_path: Any,
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
    lifecycle = OperationLifecycleCoordinator(
        store=store,
        event_store=event_store,
        replay_service=replay,
    )
    entrypoints = OperationEntrypointService(
        store=store,
        event_sourced_replay_service=replay,
    )
    state = OperationState(
        operation_id="op-es-terminal",
        goal=OperationGoal(objective="Finish cleanly."),
        policy=OperationPolicy(),
    )
    await birth.birth(state)
    await store.save_operation(state)

    lifecycle.mark_completed(state, summary="Task completed canonically.")
    outcome = await lifecycle.finalize_outcome(state)

    snapshot_state = await store.load_operation("op-es-terminal")
    resumed = await entrypoints.load_for_resume(
        operation_id="op-es-terminal",
        options=RunOptions(),
        merge_runtime_flags=lambda budget, _options: budget,
    )
    stored_events = await event_store.load_after("op-es-terminal", after_sequence=0)
    persisted_outcome = await store.load_outcome("op-es-terminal")

    assert outcome.status is OperationStatus.COMPLETED
    assert outcome.summary == "Task completed canonically."
    assert snapshot_state is not None
    assert snapshot_state.status is OperationStatus.RUNNING
    assert [event.event_type for event in stored_events][-1] == "operation.status.changed"
    assert resumed.status is OperationStatus.COMPLETED
    assert resumed.final_summary == "Task completed canonically."
    assert persisted_outcome is not None
    assert persisted_outcome.status is OperationStatus.COMPLETED


@pytest.mark.anyio
async def test_operation_cancellation_service_cancels_whole_operation() -> None:
    """Whole-operation cancellation persists terminal outcome outside the facade."""
    store = MemoryStore()
    service = OperationCancellationService(
        store=store,
        event_sink=cast(EventSink, None),
        supervisor=None,
    )
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
        emit=_noop_emit,
    )

    assert outcome.status is OperationStatus.CANCELLED
    persisted = await store.load_outcome("op-1")
    assert persisted is not None
    assert persisted.status is OperationStatus.CANCELLED


def test_operation_entrypoint_service_isolates_snapshot_reads_to_named_fallback() -> None:
    source = Path("src/agent_operator/application/operation_entrypoints.py").read_text(
        encoding="utf-8"
    )
    tree = ast.parse(source)
    callers = sorted(
        {
            node.name
            for node in ast.walk(tree)
            if isinstance(node, ast.AsyncFunctionDef)
            and any(
                isinstance(child, ast.Attribute) and child.attr == "load_operation"
                for child in ast.walk(node)
            )
        }
    )

    assert callers == ["_load_snapshot_fallback"]

    helper_calls = sorted(
        {
            node.name
            for node in ast.walk(tree)
            if isinstance(node, ast.AsyncFunctionDef)
            and any(
                isinstance(child, ast.Attribute) and child.attr == "_load_snapshot_fallback"
                for child in ast.walk(node)
            )
        }
    )

    assert helper_calls == ["_load_resume_ready_state", "load_canonical_state"]
