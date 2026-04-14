from __future__ import annotations

import json
import threading
import time
from datetime import UTC, datetime
from pathlib import Path

import anyio
import pytest

from agent_operator.application.agent_session_manager import AttachedSessionManager
from agent_operator.domain import (
    AgentDescriptor,
    AgentError,
    AgentProgress,
    AgentProgressState,
    AgentResult,
    AgentResultStatus,
    AgentSessionHandle,
    AttentionRequest,
    AttentionStatus,
    AttentionType,
    BackgroundRunStatus,
    CanonicalPersistenceMode,
    CommandStatus,
    CommandTargetScope,
    DecisionMemo,
    EventFileRecord,
    FeatureStatus,
    IterationBrief,
    OperationBrief,
    OperationCommand,
    OperationCommandType,
    OperationGoal,
    OperationOutcome,
    OperationPolicy,
    OperationState,
    OperationStatus,
    PolicyCategory,
    PolicyEntry,
    PolicySourceRef,
    PolicyStatus,
    ProjectProfile,
    ProjectProfileAdapterSettings,
    ProjectProfileMcpServer,
    RunEvent,
    SessionReusePolicy,
    SessionState,
    SessionStatus,
    TraceRecord,
    TypedRefs,
)
from agent_operator.dtos import AgentRunRequest
from agent_operator.runtime import (
    BackgroundRunInspectionStore,
    FileOperationCommandInbox,
    FileOperationStore,
    FilePolicyStore,
    FileTraceStore,
    FileWakeupInbox,
    InProcessAgentRunSupervisor,
    JsonlEventSink,
    apply_project_profile_settings,
    discover_local_project_profile,
    list_project_profiles,
    load_project_profile,
    resolve_operator_data_dir,
    resolve_project_run_config,
    write_project_profile,
)
from agent_operator.runtime.events import parse_event_file_line
from agent_operator.testing.runtime_bindings import build_test_runtime_bindings


class _FakeTestAgent:
    """Minimal fake test agent for in-process supervisor tests.

    Examples:
        >>> adapter = _FakeTestAgent()
        >>> handle = anyio.run(adapter.start, AgentRunRequest(goal="g", instruction="i"))
        >>> handle.adapter_key
        'codex_acp'
    """

    def __init__(self) -> None:
        self._started = 0
        self._progress_by_session: dict[str, AgentProgress] = {}

    async def start(self, request: AgentRunRequest) -> AgentSessionHandle:
        """Start a fake session and seed terminal progress."""
        self._started += 1
        session_id = f"session-{self._started}"
        progress = AgentProgress(
            session_id=session_id,
            state=AgentProgressState.COMPLETED,
            message="Completed.",
            updated_at=datetime.now(UTC),
            partial_output=request.instruction,
        )
        self._progress_by_session[session_id] = progress
        return AgentSessionHandle(adapter_key="codex_acp", session_id=session_id)

    async def send(self, handle: AgentSessionHandle, message: str) -> None:
        """Update fake progress for a reused session."""
        self._progress_by_session[handle.session_id] = AgentProgress(
            session_id=handle.session_id,
            state=AgentProgressState.COMPLETED,
            message="Completed.",
            updated_at=datetime.now(UTC),
            partial_output=message,
        )

    async def poll(self, handle: AgentSessionHandle) -> AgentProgress:
        """Return the latest fake progress snapshot."""
        return self._progress_by_session[handle.session_id]

    async def collect(self, handle: AgentSessionHandle) -> AgentResult:
        """Return a successful terminal result."""
        progress = self._progress_by_session[handle.session_id]
        return AgentResult(
            session_id=handle.session_id,
            status=AgentResultStatus.SUCCESS,
            output_text=progress.partial_output or "",
            completed_at=progress.updated_at,
        )

    async def cancel(self, handle: AgentSessionHandle) -> None:
        """Mark the fake session cancelled."""
        self._progress_by_session[handle.session_id] = AgentProgress(
            session_id=handle.session_id,
            state=AgentProgressState.CANCELLED,
            message="Cancelled.",
            updated_at=datetime.now(UTC),
        )

    async def close(self, handle: AgentSessionHandle) -> None:
        """Close is a no-op for the fake adapter."""
        return None


class _TrackingSessionManager:
    """Tiny session-manager double for supervisor lifecycle assertions."""

    def __init__(self) -> None:
        self.handle = AgentSessionHandle(adapter_key="codex_acp", session_id="sess-1")
        self.close_calls = 0
        self.cancel_calls = 0
        self._result = AgentResult(
            session_id="sess-1",
            status=AgentResultStatus.SUCCESS,
            output_text="done",
            completed_at=datetime.now(UTC),
        )

    def keys(self) -> list[str]:
        return ["codex_acp"]

    def has(self, adapter_key: str) -> bool:
        return adapter_key == "codex_acp"

    async def describe(self, adapter_key: str) -> AgentDescriptor:
        return AgentDescriptor(key=adapter_key, display_name=adapter_key)

    async def start(self, adapter_key: str, request: AgentRunRequest) -> AgentSessionHandle:
        return self.handle

    async def send(self, handle: AgentSessionHandle, message: str) -> None:
        return None

    async def poll(self, handle: AgentSessionHandle) -> AgentProgress:
        return AgentProgress(
            session_id=handle.session_id,
            state=AgentProgressState.COMPLETED,
            message="Completed.",
            updated_at=datetime.now(UTC),
            partial_output="done",
        )

    async def collect(self, handle: AgentSessionHandle) -> AgentResult:
        return self._result

    async def cancel(self, handle: AgentSessionHandle) -> None:
        self.cancel_calls += 1

    async def close(self, handle: AgentSessionHandle) -> None:
        self.close_calls += 1


class _StickyRunningSessionManager:
    """Fake session manager that emits stale-progress RUNNING for one poll, then WAITING_INPUT."""

    def __init__(self, *, stale_progress: datetime | None = None) -> None:
        self.handle = AgentSessionHandle(adapter_key="codex_acp", session_id="sticky-session")
        self._stale_progress_at = stale_progress or datetime(2000, 1, 1, tzinfo=UTC)
        self._poll_count = 0
        self._result = AgentResult(
            session_id=self.handle.session_id,
            status=AgentResultStatus.INCOMPLETE,
            output_text="",
            completed_at=self._stale_progress_at,
            error=AgentError(
                code="agent_waiting_input",
                message="waiting input",
                retryable=False,
                raw={},
            ),
        )

    def keys(self) -> list[str]:
        return ["codex_acp"]

    def has(self, adapter_key: str) -> bool:
        return adapter_key == "codex_acp"

    async def describe(self, adapter_key: str) -> AgentDescriptor:
        return AgentDescriptor(key=adapter_key, display_name=adapter_key)

    async def start(self, adapter_key: str, request: AgentRunRequest) -> AgentSessionHandle:
        return self.handle

    async def send(self, handle: AgentSessionHandle, message: str) -> None:
        return None

    async def poll(self, handle: AgentSessionHandle) -> AgentProgress:
        self._poll_count += 1
        state = AgentProgressState.RUNNING
        if self._poll_count > 1:
            state = AgentProgressState.WAITING_INPUT
        return AgentProgress(
            session_id=handle.session_id,
            state=state,
            message="working" if state is AgentProgressState.RUNNING else "waiting input",
            updated_at=self._stale_progress_at,
            partial_output="work",
        )

    async def collect(self, handle: AgentSessionHandle) -> AgentResult:
        return self._result

    async def cancel(self, handle: AgentSessionHandle) -> None:
        return None

    async def close(self, handle: AgentSessionHandle) -> None:
        return None


@pytest.mark.anyio
async def test_file_store_roundtrip(tmp_path: Path) -> None:
    store = FileOperationStore(tmp_path)
    state = OperationState(goal=OperationGoal(objective="hello"), policy=OperationPolicy())
    outcome = OperationOutcome(
        operation_id=state.operation_id,
        status=OperationStatus.COMPLETED,
        summary="done",
    )

    await store.save_operation(state)
    await store.save_outcome(outcome)

    loaded_state = await store.load_operation(state.operation_id)
    loaded_outcome = await store.load_outcome(state.operation_id)
    operation_ids = await store.list_operation_ids()

    assert loaded_state is not None
    assert loaded_state.operation_id == state.operation_id
    assert loaded_state.canonical_persistence_mode is CanonicalPersistenceMode.EVENT_SOURCED
    assert loaded_outcome is not None
    assert loaded_outcome.summary == "done"
    assert state.operation_id in operation_ids


def test_operation_state_defaults_to_event_sourced_mode() -> None:
    """New in-memory operations default to the canonical event-sourced mode."""
    state = OperationState(goal=OperationGoal(objective="hello"), policy=OperationPolicy())

    assert state.canonical_persistence_mode is CanonicalPersistenceMode.EVENT_SOURCED



def test_operation_state_uses_objective_only_for_root_task_goal() -> None:
    state = OperationState(
        goal=OperationGoal(
            objective="Ship the feature",
            harness_instructions="Use swarm when unclear.",
        ),
        policy=OperationPolicy(),
    )

    assert state.objective_state.objective == "Ship the feature"
    assert state.objective_state.harness_instructions == "Use swarm when unclear."
    assert state.tasks[0].goal == "Ship the feature"
    assert "status" not in state.objective_state.model_dump()


def test_legacy_session_status_upgrades_without_desired_state() -> None:
    session = SessionState.model_validate(
        {
            "handle": {
                "adapter_key": "codex_acp",
                "session_id": "session-1",
            },
            "status": "cancelled",
        }
    )

    assert session.status is SessionStatus.CANCELLED
    assert "desired_state" not in session.model_dump()


def test_feature_status_exposes_only_runtime_values() -> None:
    assert {status.value for status in FeatureStatus} == {"in_progress", "accepted"}


@pytest.mark.anyio
async def test_file_store_roundtrips_attention_requests(tmp_path: Path) -> None:
    store = FileOperationStore(tmp_path)
    state = OperationState(goal=OperationGoal(objective="hello"), policy=OperationPolicy())
    state.attention_requests.append(
        AttentionRequest(
            operation_id=state.operation_id,
            attention_id="attention-1",
            attention_type=AttentionType.QUESTION,
            status=AttentionStatus.OPEN,
            blocking=True,
            title="Clarification required",
            question="Which environment should be used?",
            target_scope=CommandTargetScope.OPERATION,
            target_id=state.operation_id,
        )
    )

    await store.save_operation(state)
    loaded_state = await store.load_operation(state.operation_id)

    assert loaded_state is not None
    assert len(loaded_state.attention_requests) == 1
    assert loaded_state.attention_requests[0].attention_id == "attention-1"


def test_jsonl_event_sink_reads_written_events(tmp_path: Path) -> None:
    sink = JsonlEventSink(tmp_path / "events.jsonl")
    event = RunEvent(
        event_type="operation.started",
        operation_id="op-1",
        iteration=0,
        category="trace",
    )

    import anyio

    anyio.run(sink.emit, event)

    loaded = sink.read_events("op-1")
    assert len(loaded) == 1
    assert loaded[0].event_type == "operation.started"

    raw_payload = json.loads((tmp_path / "events.jsonl").read_text(encoding="utf-8").strip())
    assert raw_payload["schema_version"] == 1
    assert raw_payload["event_type"] == "operation.started"
    assert raw_payload["operation_id"] == "op-1"
    assert raw_payload["iteration"] == 0
    assert raw_payload["kind"] == "trace"
    assert raw_payload["category"] == "trace"
    assert raw_payload["payload"] == {}


def test_jsonl_event_sink_can_follow_appended_events(tmp_path: Path) -> None:
    sink = JsonlEventSink(tmp_path / "events.jsonl")
    first = RunEvent(
        event_type="operation.started",
        operation_id="op-1",
        iteration=0,
        category="trace",
    )
    second = RunEvent(
        event_type="evaluation.completed",
        operation_id="op-1",
        iteration=1,
        category="trace",
    )

    import anyio

    anyio.run(sink.emit, first)
    stream = sink.iter_events("op-1", follow=True, poll_interval=0.01)
    try:
        loaded_first = next(stream)

        def _emit_later() -> None:
            time.sleep(0.05)
            anyio.run(sink.emit, second)

        thread = threading.Thread(target=_emit_later)
        thread.start()
        loaded_second = next(stream)
        thread.join(timeout=1)
    finally:
        stream.close()

    assert loaded_first.event_type == "operation.started"
    assert loaded_second.event_type == "evaluation.completed"


def test_event_file_record_round_trips_run_event() -> None:
    event = RunEvent(
        event_id="evt-1",
        event_type="agent.invocation.completed",
        operation_id="op-1",
        iteration=3,
        task_id="task-1",
        session_id="session-1",
        category="trace",
        payload={"status": "success"},
    )

    record = event.to_event_file_record()

    assert isinstance(record, EventFileRecord)
    assert record.schema_version == 1
    assert record.to_run_event() == event


def test_parse_event_file_line_accepts_legacy_run_event_payload() -> None:
    legacy_line = RunEvent(
        event_type="operation.started",
        operation_id="op-legacy",
        iteration=0,
        category="trace",
        payload={"objective": "Inspect"},
    ).model_dump_json()

    parsed = parse_event_file_line(legacy_line)

    assert parsed.event_type == "operation.started"
    assert parsed.operation_id == "op-legacy"
    assert parsed.payload == {"objective": "Inspect"}


def test_trace_record_refs_accepts_typed_refs() -> None:
    record = TraceRecord(
        operation_id="op-1",
        iteration=1,
        category="decision",
        title="Decision start_agent",
        summary="Started agent.",
        refs=TypedRefs(operation_id="op-1", iteration=1, task_id="t-1"),
    )
    assert record.refs["operation_id"] == "op-1"
    assert record.refs["iteration"] == "1"
    assert record.refs["task_id"] == "t-1"


@pytest.mark.anyio
async def test_file_trace_store_roundtrip(tmp_path: Path) -> None:
    store = FileTraceStore(tmp_path)
    brief = OperationBrief(
        operation_id="op-1",
        status=OperationStatus.RUNNING,
        objective_brief="Test objective",
    )
    iteration = IterationBrief(
        iteration=1,
        operator_intent_brief="Operator started agent.",
        status_brief="Running.",
    )
    memo = DecisionMemo(
        operation_id="op-1",
        iteration=1,
        decision_context_summary="Root task ready.",
        chosen_action="start_agent",
        rationale="Need agent work.",
    )
    trace = TraceRecord(
        operation_id="op-1",
        iteration=1,
        category="iteration",
        title="Iteration 1",
        summary="Operator started agent.",
    )

    await store.save_operation_brief(brief)
    await store.append_iteration_brief("op-1", iteration)
    await store.save_decision_memo("op-1", memo)
    await store.append_trace_record("op-1", trace)
    await store.write_report("op-1", "# Report\n")

    bundle = await store.load_brief_bundle("op-1")
    memos = await store.load_decision_memos("op-1")
    traces = await store.load_trace_records("op-1")
    report = await store.load_report("op-1")

    assert bundle is not None
    assert bundle.operation_brief is not None
    assert bundle.operation_brief.objective_brief == "Test objective"
    assert len(bundle.iteration_briefs) == 1
    assert memos[0].chosen_action == "start_agent"
    assert traces[0].category == "iteration"
    assert report == "# Report\n"


@pytest.mark.anyio
async def test_background_run_inspection_store_reads_persisted_run_file(tmp_path: Path) -> None:
    store = BackgroundRunInspectionStore(tmp_path / "background")
    run_id = "run-1"
    run_path = tmp_path / "background" / "runs" / f"{run_id}.json"
    run_path.parent.mkdir(parents=True, exist_ok=True)
    run_path.write_text(
        json.dumps(
            {
                "run_id": run_id,
                "operation_id": "op-1",
                "adapter_key": "codex_acp",
                "iteration": 1,
                "status": "running",
                "pid": 123,
                "started_at": datetime.now(UTC).isoformat(),
                "last_heartbeat_at": datetime.now(UTC).isoformat(),
                "completed_at": None,
                "raw_ref": None,
                "error": None,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    updated = await store.poll_background_turn(run_id)
    payload = json.loads(run_path.read_text(encoding="utf-8"))

    assert updated is not None
    assert updated.status is BackgroundRunStatus.RUNNING
    assert updated.completed_at is None
    assert payload["status"] == "running"
    assert payload["error"] is None


@pytest.mark.anyio
async def test_inprocess_supervisor_completes_run_and_enqueues_wakeup(tmp_path: Path) -> None:
    inbox = FileWakeupInbox(tmp_path / "wakeups")
    supervisor = InProcessAgentRunSupervisor(
        tmp_path / "background",
        tmp_path,
        session_manager=AttachedSessionManager.from_bindings(
            build_test_runtime_bindings({"codex_acp": _FakeTestAgent()})
        ),
        wakeup_inbox=inbox,
    )

    run = await supervisor.start_background_turn(
        "op-1",
        1,
        "codex_acp",
        AgentRunRequest(goal="hello", instruction="ship it"),
    )

    deadline = time.time() + 5.0
    result = None
    while time.time() < deadline:
        result = await supervisor.collect_background_turn(run.run_id)
        if result is not None:
            break
        await anyio.sleep(0.05)

    polled = await supervisor.poll_background_turn(run.run_id)
    pending = await inbox.list_pending("op-1")

    assert result is not None
    assert result.status is AgentResultStatus.SUCCESS
    assert result.output_text == "ship it"
    assert polled is not None
    assert polled.status is BackgroundRunStatus.COMPLETED
    assert pending[0].event_type == "background_run.completed"
    assert (tmp_path / "background" / "runs" / f"{run.run_id}.json").exists()
    assert (tmp_path / "background" / "results" / f"{run.run_id}.json").exists()


@pytest.mark.anyio
async def test_inprocess_supervisor_keeps_reusable_session_open_after_success(
    tmp_path: Path,
) -> None:
    inbox = FileWakeupInbox(tmp_path / "wakeups")
    manager = _TrackingSessionManager()
    supervisor = InProcessAgentRunSupervisor(
        tmp_path / "background",
        tmp_path,
        session_manager=manager,
        wakeup_inbox=inbox,
    )

    run = await supervisor.start_background_turn(
        "op-1",
        1,
        "codex_acp",
        AgentRunRequest(goal="hello", instruction="ship it"),
        existing_session=manager.handle,
    )

    deadline = time.time() + 2.0
    result = None
    while time.time() < deadline:
        result = await supervisor.collect_background_turn(run.run_id)
        if result is not None:
            break
        await anyio.sleep(0.05)

    assert result is not None
    assert result.status is AgentResultStatus.SUCCESS
    assert manager.close_calls == 0
    assert manager.cancel_calls == 0


@pytest.mark.anyio
async def test_inprocess_supervisor_refreshes_stale_background_run_heartbeat(
    tmp_path: Path,
) -> None:
    inbox = FileWakeupInbox(tmp_path / "wakeups")
    stale_progress = datetime(2000, 1, 1, tzinfo=UTC)
    manager = _StickyRunningSessionManager(stale_progress=stale_progress)
    supervisor = InProcessAgentRunSupervisor(
        tmp_path / "background",
        tmp_path,
        session_manager=manager,
        wakeup_inbox=inbox,
    )

    run = await supervisor.start_background_turn(
        "op-1",
        1,
        "codex_acp",
        AgentRunRequest(goal="hello", instruction="hold"),
    )

    deadline = time.time() + 3.0
    heartbeat_advanced = False
    while time.time() < deadline:
        polled = await supervisor.poll_background_turn(run.run_id)
        if polled is not None and polled.last_heartbeat_at is not None:
            heartbeat_advanced = heartbeat_advanced or polled.last_heartbeat_at > stale_progress
            if polled.status is BackgroundRunStatus.COMPLETED:
                break
        await anyio.sleep(0.05)

    result = await supervisor.collect_background_turn(run.run_id)
    final = await supervisor.poll_background_turn(run.run_id)

    assert result is not None
    assert result.status is AgentResultStatus.INCOMPLETE
    assert heartbeat_advanced is True
    assert final is not None
    assert final.status is BackgroundRunStatus.COMPLETED


@pytest.mark.anyio
async def test_file_command_inbox_sets_applied_at_only_for_applied_status(tmp_path: Path) -> None:
    inbox = FileOperationCommandInbox(tmp_path / "commands")
    command = OperationCommand(
        operation_id="op-1",
        command_type=OperationCommandType.PATCH_HARNESS,
        target_scope=CommandTargetScope.OPERATION,
        target_id="op-1",
        payload={"text": "Prefer swarm when unclear."},
    )

    await inbox.enqueue(command)
    await inbox.update_status(command.command_id, CommandStatus.PENDING)
    staged = (await inbox.list("op-1"))[0]
    applied_at = datetime.now(UTC)
    await inbox.update_status(
        command.command_id,
        CommandStatus.APPLIED,
        applied_at=applied_at,
    )
    applied = (await inbox.list("op-1"))[0]

    assert staged.status is CommandStatus.PENDING
    assert staged.applied_at is None
    assert applied.status is CommandStatus.APPLIED
    assert applied.applied_at == applied_at


def test_project_profile_loader_and_resolver(tmp_path: Path) -> None:
    projects_dir = tmp_path / "profiles"
    projects_dir.mkdir(parents=True, exist_ok=True)
    (projects_dir / "femtobot.yaml").write_text(
        "\n".join(
            [
                "name: femtobot",
                "cwd: /tmp/femtobot",
                "default_agents:",
                "  - codex_acp",
                "default_harness_instructions: Continue most of the time.",
                "default_success_criteria:",
                "  - backlog stays above 100",
                "default_max_iterations: 12",
                "default_involvement_level: unattended",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    from agent_operator.config import OperatorSettings

    settings = OperatorSettings()
    settings.data_dir = tmp_path

    assert list_project_profiles(settings) == ["femtobot"]
    profile = load_project_profile(settings, "femtobot")
    resolved = resolve_project_run_config(
        settings,
        profile=profile,
        objective=None,
        harness=None,
        success_criteria=None,
        allowed_agents=None,
        max_iterations=None,
        run_mode=None,
        involvement_level=None,
    )

    assert profile.cwd == Path("/tmp/femtobot")
    assert resolved.default_agents == ["codex_acp"]
    assert resolved.max_iterations == 12
    assert resolved.involvement_level.value == "unattended"


def test_resolve_operator_data_dir_uses_git_root_when_no_local_dir_exists(tmp_path: Path) -> None:
    from agent_operator.config import OperatorSettings

    repo_root = tmp_path / "repo"
    nested = repo_root / "src" / "agent_operator"
    nested.mkdir(parents=True)
    (repo_root / ".git").mkdir()

    settings = OperatorSettings()
    resolution = resolve_operator_data_dir(settings, cwd=nested)

    assert resolution.path == repo_root / ".operator"
    assert resolution.source == "discovered_git_root"


def test_discover_local_project_profile_finds_local_profile_file(tmp_path: Path) -> None:
    from agent_operator.config import OperatorSettings

    cwd = tmp_path / "myproject"
    cwd.mkdir(parents=True)
    (cwd / "operator-profile.yaml").write_text("name: myproject\n", encoding="utf-8")

    settings = OperatorSettings()
    settings.data_dir = tmp_path / ".operator"

    selection = discover_local_project_profile(settings, cwd=cwd)

    assert selection.profile is not None
    assert selection.profile.name == "myproject"
    assert selection.source == "local_profile_file"


def test_resolve_project_run_config_applies_success_criteria_override(tmp_path: Path) -> None:
    from agent_operator.config import OperatorSettings

    settings = OperatorSettings()
    settings.data_dir = tmp_path
    profile = ProjectProfile(
        name="femtobot",
        default_success_criteria=["Leave a clear summary."],
    )

    resolved = resolve_project_run_config(
        settings,
        profile=profile,
        objective=None,
        harness=None,
        success_criteria=["CI stays green", "Backlog stays below 50"],
        allowed_agents=None,
        max_iterations=None,
        run_mode=None,
        involvement_level=None,
    )

    assert resolved.success_criteria == ["CI stays green", "Backlog stays below 50"]
    assert resolved.overrides == ["success_criteria"]


def test_resolve_project_run_config_includes_history_ledger_and_session_reuse_policy(
    tmp_path: Path,
) -> None:
    from agent_operator.config import OperatorSettings

    settings = OperatorSettings()
    settings.data_dir = tmp_path
    profile = ProjectProfile(
        name="femtobot",
        history_ledger=False,
        session_reuse_policy=SessionReusePolicy.REUSE_IF_IDLE,
    )

    resolved = resolve_project_run_config(
        settings,
        profile=profile,
        objective=None,
        harness=None,
        success_criteria=None,
        allowed_agents=None,
        max_iterations=None,
        run_mode=None,
        involvement_level=None,
    )

    assert resolved.history_ledger is False
    assert resolved.session_reuse_policy is SessionReusePolicy.REUSE_IF_IDLE


def test_write_project_profile_roundtrips_and_requires_force(tmp_path: Path) -> None:
    from agent_operator.config import OperatorSettings

    settings = OperatorSettings()
    settings.data_dir = tmp_path
    path = write_project_profile(
        settings,
        ProjectProfile(
            name="femtobot",
            cwd=Path("/tmp/femtobot"),
            default_agents=["codex_acp"],
            default_harness_instructions="Stay attached.",
            default_success_criteria=["Leave a clear summary."],
            default_max_iterations=9,
        ),
    )
    loaded = load_project_profile(settings, "femtobot")

    assert path == tmp_path / "profiles" / "femtobot.yaml"
    assert loaded.cwd == Path("/tmp/femtobot")
    assert loaded.default_agents == ["codex_acp"]
    assert loaded.default_max_iterations == 9
    assert "adapter_settings" not in path.read_text(encoding="utf-8")
    with pytest.raises(RuntimeError, match="already exists"):
        write_project_profile(settings, loaded)


def test_list_project_profiles_merges_local_and_committed_profiles(
    tmp_path: Path, monkeypatch
) -> None:
    from agent_operator.config import OperatorSettings

    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    (repo_root / ".git").mkdir()
    (repo_root / "operator-profiles").mkdir()
    (repo_root / "operator-profiles" / "committed.yaml").write_text(
        "name: committed\n",
        encoding="utf-8",
    )
    (tmp_path / "profiles").mkdir(parents=True, exist_ok=True)
    (tmp_path / "profiles" / "local.yaml").write_text(
        "name: local\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(repo_root)

    settings = OperatorSettings()
    settings.data_dir = tmp_path

    assert list_project_profiles(settings) == ["committed", "local"]


def test_apply_project_profile_settings_updates_adapter_defaults(tmp_path: Path) -> None:
    projects_dir = tmp_path / "profiles"
    projects_dir.mkdir(parents=True, exist_ok=True)
    (projects_dir / "femtobot.yaml").write_text(
        "\n".join(
            [
                "name: femtobot",
                "cwd: /tmp/femtobot",
                "adapter_settings:",
                "  codex_acp:",
                "    command: npm exec --yes @zed-industries/codex-acp --",
                "    approval_policy: never",
                "    sandbox_mode: danger-full-access",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    from agent_operator.config import OperatorSettings

    settings = OperatorSettings()
    settings.data_dir = tmp_path
    profile = load_project_profile(settings, "femtobot")
    apply_project_profile_settings(settings, profile)

    assert settings.codex_acp.command == "npm exec --yes @zed-industries/codex-acp --"
    assert settings.codex_acp.approval_policy == "never"
    assert settings.codex_acp.sandbox_mode == "danger-full-access"
    assert settings.codex_acp.working_directory == Path("/tmp/femtobot")

    profile = load_project_profile(settings, "femtobot")
    profile.adapter_settings = {
        "opencode_acp": {
            "command": "opencode acp --cwd /tmp/opencode",
        }
    }
    apply_project_profile_settings(settings, profile)

    assert settings.opencode_acp.command == "opencode acp --cwd /tmp/opencode"
    assert settings.opencode_acp.working_directory == Path("/tmp/femtobot")


def test_apply_project_profile_settings_updates_mcp_servers_and_timeout_seconds(
    tmp_path: Path,
) -> None:
    from agent_operator.config import OperatorSettings

    settings = OperatorSettings()
    settings.data_dir = tmp_path
    profile = ProjectProfile(
        name="femtobot",
        adapter_settings={
            "codex_acp": ProjectProfileAdapterSettings(
                timeout_seconds=45.0,
                mcp_servers=[
                    ProjectProfileMcpServer(
                        name="filesystem",
                        command="npx",
                        args=["-y", "@modelcontextprotocol/server-filesystem", "."],
                    )
                ],
                command="npm exec --yes @zed-industries/codex-acp --",
            )
        },
    )

    apply_project_profile_settings(settings, profile)

    assert settings.codex_acp.timeout_seconds == 45.0
    assert settings.codex_acp.command == "npm exec --yes @zed-industries/codex-acp --"
    assert settings.codex_acp.mcp_servers == [
        {
            "name": "filesystem",
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-filesystem", "."],
            "env": {},
        }
    ]


def test_load_project_profile_validates_session_reuse_policy(tmp_path: Path) -> None:
    from agent_operator.config import OperatorSettings

    settings = OperatorSettings()
    settings.data_dir = tmp_path
    (tmp_path / "profiles").mkdir(parents=True, exist_ok=True)
    (tmp_path / "profiles" / "operator.yaml").write_text(
        "name: operator\nsession_reuse_policy: reuse_if_idle\n",
        encoding="utf-8",
    )

    profile = load_project_profile(settings, "operator")

    assert profile.session_reuse_policy is SessionReusePolicy.REUSE_IF_IDLE


def test_load_project_profile_rejects_unknown_session_reuse_policy(tmp_path: Path) -> None:
    from agent_operator.config import OperatorSettings

    settings = OperatorSettings()
    settings.data_dir = tmp_path
    (tmp_path / "profiles").mkdir(parents=True, exist_ok=True)
    (tmp_path / "profiles" / "operator.yaml").write_text(
        "name: operator\nsession_reuse_policy: later\n",
        encoding="utf-8",
    )

    with pytest.raises(Exception, match="session_reuse_policy"):
        load_project_profile(settings, "operator")


@pytest.mark.anyio
async def test_file_policy_store_roundtrip_and_active_filter(tmp_path: Path) -> None:
    store = FilePolicyStore(tmp_path / "policies")
    active = PolicyEntry(
        project_scope="profile:femtobot",
        title="Testing gate",
        category=PolicyCategory.TESTING,
        rule_text="Document any manual-only verification debt in MANUAL_TESTING_REQUIRED.md.",
        rationale="Keeps automation gaps inspectable.",
        source_refs=[PolicySourceRef(kind="attention_request", ref_id="attention-1")],
    )
    revoked = PolicyEntry(
        project_scope="profile:femtobot",
        title="Old release rule",
        category=PolicyCategory.RELEASE,
        rule_text="Push from a temporary fork.",
        status=PolicyStatus.REVOKED,
    )

    await store.save(active)
    await store.save(revoked)

    loaded = await store.load(active.policy_id)
    active_entries = await store.list(
        project_scope="profile:femtobot",
        status=PolicyStatus.ACTIVE,
    )
    all_entries = await store.list(project_scope="profile:femtobot")

    assert loaded is not None
    assert loaded.title == "Testing gate"
    assert [item.policy_id for item in active_entries] == [active.policy_id]
    assert {item.policy_id for item in all_entries} == {active.policy_id, revoked.policy_id}
