from __future__ import annotations

import json
import threading
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import anyio
import httpx
from typer.testing import CliRunner

import agent_operator.cli.commands as cli_commands_pkg
import agent_operator.cli.commands.operation_detail as commands_operation_detail
import agent_operator.cli.helpers as cli_helpers_pkg
import agent_operator.cli.workflows as cli_workflows
from agent_operator.application.event_sourcing.event_sourced_birth import (
    EventSourcedOperationBirthService,
)
from agent_operator.bootstrap import build_replay_service
from agent_operator.cli.helpers.rendering import render_watch_snapshot
from agent_operator.cli.main import _format_live_snapshot, app
from agent_operator.config import OperatorSettings, load_global_config
from agent_operator.domain import (
    AgentResult,
    AgentResultStatus,
    AgentSessionHandle,
    AgentTurnBrief,
    AgentTurnSummary,
    ArtifactRecord,
    AttentionRequest,
    AttentionStatus,
    AttentionType,
    BackgroundRunHandle,
    BackgroundRunStatus,
    BrainActionType,
    BrainDecision,
    CommandStatus,
    CommandTargetScope,
    DecisionMemo,
    ExecutionBudget,
    ExternalTicketLink,
    FeatureDraft,
    FeaturePatch,
    FeatureStatus,
    FocusKind,
    FocusState,
    InvolvementLevel,
    IterationBrief,
    IterationState,
    MemoryEntry,
    MemoryFreshness,
    MemoryScope,
    MemorySourceRef,
    ObjectiveState,
    OperationBrief,
    OperationCheckpoint,
    OperationCheckpointRecord,
    OperationCommand,
    OperationCommandType,
    OperationGoal,
    OperationOutcome,
    OperationPolicy,
    OperationState,
    OperationStatus,
    OperationSummary,
    PolicyApplicability,
    PolicyCategory,
    PolicyEntry,
    PolicyStatus,
    RunEvent,
    RunEventKind,
    RunMode,
    RuntimeHints,
    SchedulerState,
    SessionPolicy,
    SessionRecord,
    SessionRecordStatus,
    StoredControlIntent,
    TaskPatch,
    TaskState,
    TaskStatus,
    TraceRecord,
)
from agent_operator.dtos import ConverseTurnDTO
from agent_operator.projectors import DefaultOperationProjector
from agent_operator.runtime import (
    FileOperationCheckpointStore,
    FileOperationCommandInbox,
    FileOperationEventStore,
    FileOperationStore,
    FilePolicyStore,
    FileTraceStore,
    FileWakeupInbox,
    JsonlEventSink,
    discover_projects,
)

runner = CliRunner()


def test_workflows_facade_reexports_package_entrypoints() -> None:
    assert cli_workflows.run_async is not None
    assert cli_workflows.fleet_async is not None
    assert cli_workflows.clear_async is not None
    assert "run_async" in cli_workflows.__all__
    assert "fleet_async" in cli_workflows.__all__
    assert "clear_async" in cli_workflows.__all__


def test_run_cli_startup_connect_error_marks_operation_failed(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    data_dir = tmp_path / ".operator"
    runs_dir = data_dir / "runs"
    store = FileOperationStore(runs_dir)
    captured: dict[str, str] = {}
    lifecycle_calls: list[tuple[str, str]] = []

    settings = SimpleNamespace(
        data_dir=data_dir,
        claude_acp=SimpleNamespace(
            command="npx @agentclientprotocol/claude-agent-acp",
            model=None,
            reasoning_effort=None,
            permission_mode="bypassPermissions",
            timeout_seconds=None,
            mcp_servers=[],
            substrate_backend="sdk",
            stdio_limit_bytes=1048576,
            working_directory=str(tmp_path),
        ),
    )

    class _ResolvedRunConfig:
        objective_text = "Investigate ADR closure."
        harness_instructions = "Follow AGENTS.md."
        success_criteria: list[str] = []
        default_agents = ["claude_acp"]
        max_iterations = 4
        run_mode = RunMode.ATTACHED
        involvement_level = InvolvementLevel.AUTO
        cwd = tmp_path
        message_window = 3

        def model_dump(self, mode: str = "json") -> dict[str, object]:
            return {
                "profile_name": "operator",
                "cwd": str(tmp_path),
                "default_agents": ["claude_acp"],
                "objective_text": self.objective_text,
                "harness_instructions": self.harness_instructions,
                "success_criteria": [],
                "max_iterations": self.max_iterations,
                "run_mode": self.run_mode.value,
                "involvement_level": self.involvement_level.value,
                "message_window": self.message_window,
            }

    async def _save_ready_operation(operation_id: str) -> None:
        state = OperationState(
            operation_id=operation_id,
            goal=OperationGoal(objective="Investigate ADR closure."),
            **state_settings(
                allowed_agents=["claude_acp"],
                involvement_level=InvolvementLevel.AUTO,
                max_iterations=4,
                metadata={"run_mode": "attached"},
            ),
            status=OperationStatus.RUNNING,
        )
        await store.save_operation(state)

    class _LifecycleCoordinator:
        def mark_failed(self, state, *, summary: str) -> None:
            lifecycle_calls.append(("mark_failed", summary))
            state.status = OperationStatus.FAILED
            state.final_summary = summary
            state.objective_state.summary = summary

        async def finalize_outcome(self, state) -> OperationOutcome:
            lifecycle_calls.append(("finalize_outcome", state.final_summary or ""))
            await store.save_operation(state)
            outcome = OperationOutcome(
                operation_id=state.operation_id,
                status=state.status,
                summary=state.final_summary or "",
                ended_at=state.updated_at,
            )
            await store.save_outcome(outcome)
            return outcome

    class _ExplodingService:
        _store = store
        _operation_lifecycle_coordinator = _LifecycleCoordinator()

        async def run(self, goal, **kwargs):
            operation_id = kwargs["operation_id"]
            captured["operation_id"] = operation_id
            await _save_ready_operation(operation_id)
            raise httpx.ConnectError(
                "[Errno 8] nodename nor servname provided, or not known",
                request=httpx.Request("POST", "https://api.anthropic.com/v1/messages"),
            )

    monkeypatch.setattr(
        "agent_operator.cli.workflows.control.load_settings_with_data_dir",
        lambda: (settings, "test"),
    )
    monkeypatch.setattr(
        "agent_operator.cli.workflows.control.resolve_project_profile_selection",
        lambda settings, name=None: (
            SimpleNamespace(name="operator"),
            tmp_path / "operator-profile.yaml",
            "test_profile",
        ),
    )
    monkeypatch.setattr(
        "agent_operator.cli.workflows.control.apply_project_profile_settings",
        lambda settings, profile: None,
    )
    monkeypatch.setattr(
        "agent_operator.cli.workflows.control.resolve_project_run_config",
        lambda *args, **kwargs: _ResolvedRunConfig(),
    )
    monkeypatch.setattr(
        "agent_operator.cli.workflows.control._build_run_goal_metadata",
        lambda **kwargs: ([], {}),
    )
    monkeypatch.setattr(
        "agent_operator.cli.workflows.control.build_projected_service",
        lambda settings, operation_id, projector: _ExplodingService(),
    )

    result = runner.invoke(app, ["run"])

    assert result.exit_code != 0
    operation_id = captured["operation_id"]
    persisted = anyio.run(store.load_operation, operation_id)
    assert persisted is not None
    assert persisted.status is OperationStatus.FAILED
    assert lifecycle_calls[0][0] == "mark_failed"
    assert lifecycle_calls[1][0] == "finalize_outcome"
    persisted_outcome = anyio.run(store.load_outcome, operation_id)
    assert persisted_outcome is not None
    assert persisted_outcome.status is OperationStatus.FAILED


def test_run_cli_startup_exception_does_not_overwrite_completed_operation(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)

    data_dir = tmp_path / ".operator"
    runs_dir = data_dir / "runs"
    store = FileOperationStore(runs_dir)
    captured: dict[str, str] = {}
    lifecycle_calls: list[tuple[str, str]] = []

    settings = SimpleNamespace(
        data_dir=data_dir,
        claude_acp=SimpleNamespace(
            command="npx @agentclientprotocol/claude-agent-acp",
            model=None,
            reasoning_effort=None,
            permission_mode="bypassPermissions",
            timeout_seconds=None,
            mcp_servers=[],
            substrate_backend="sdk",
            stdio_limit_bytes=1048576,
            working_directory=str(tmp_path),
        ),
    )

    class _ResolvedRunConfig:
        objective_text = "Investigate ADR closure."
        harness_instructions = "Follow AGENTS.md."
        success_criteria: list[str] = []
        default_agents = ["claude_acp"]
        max_iterations = 4
        run_mode = RunMode.ATTACHED
        involvement_level = InvolvementLevel.AUTO
        cwd = tmp_path
        message_window = 3

        def model_dump(self, mode: str = "json") -> dict[str, object]:
            return {
                "profile_name": "operator",
                "cwd": str(tmp_path),
                "default_agents": ["claude_acp"],
                "objective_text": self.objective_text,
                "harness_instructions": self.harness_instructions,
                "success_criteria": [],
                "max_iterations": self.max_iterations,
                "run_mode": self.run_mode.value,
                "involvement_level": self.involvement_level.value,
                "message_window": self.message_window,
            }

    async def _save_completed_operation(operation_id: str) -> None:
        state = OperationState(
            operation_id=operation_id,
            goal=OperationGoal(objective="Investigate ADR closure."),
            **state_settings(
                allowed_agents=["claude_acp"],
                involvement_level=InvolvementLevel.AUTO,
                max_iterations=4,
                metadata={"run_mode": "attached"},
            ),
            status=OperationStatus.COMPLETED,
            final_summary="Attached turn completed successfully.",
        )
        state.tasks[0].status = TaskStatus.COMPLETED
        state.tasks[0].updated_at = datetime.now(UTC)
        await store.save_operation(state)

    class _LifecycleCoordinator:
        def mark_failed(self, state, *, summary: str) -> None:
            lifecycle_calls.append(("mark_failed", summary))
            state.status = OperationStatus.FAILED
            state.final_summary = summary
            state.objective_state.summary = summary

        async def finalize_outcome(self, state) -> OperationOutcome:
            lifecycle_calls.append(("finalize_outcome", state.final_summary or ""))
            await store.save_operation(state)
            outcome = OperationOutcome(
                operation_id=state.operation_id,
                status=state.status,
                summary=state.final_summary or "",
                ended_at=state.updated_at,
            )
            await store.save_outcome(outcome)
            return outcome

    class _ExplodingService:
        _store = store
        _operation_lifecycle_coordinator = _LifecycleCoordinator()

        async def run(self, goal, **kwargs):
            operation_id = kwargs["operation_id"]
            captured["operation_id"] = operation_id
            await _save_completed_operation(operation_id)
            raise httpx.ConnectError(
                "[Errno 8] nodename nor servname provided, or not known",
                request=httpx.Request("POST", "https://api.anthropic.com/v1/messages"),
            )

    monkeypatch.setattr(
        "agent_operator.cli.workflows.control.load_settings_with_data_dir",
        lambda: (settings, "test"),
    )
    monkeypatch.setattr(
        "agent_operator.cli.workflows.control.resolve_project_profile_selection",
        lambda settings, name=None: (
            SimpleNamespace(name="operator"),
            tmp_path / "operator-profile.yaml",
            "test_profile",
        ),
    )
    monkeypatch.setattr(
        "agent_operator.cli.workflows.control.apply_project_profile_settings",
        lambda settings, profile: None,
    )
    monkeypatch.setattr(
        "agent_operator.cli.workflows.control.resolve_project_run_config",
        lambda *args, **kwargs: _ResolvedRunConfig(),
    )
    monkeypatch.setattr(
        "agent_operator.cli.workflows.control._build_run_goal_metadata",
        lambda **kwargs: ([], {}),
    )
    monkeypatch.setattr(
        "agent_operator.cli.workflows.control.build_projected_service",
        lambda settings, operation_id, projector: _ExplodingService(),
    )

    result = runner.invoke(app, ["run"])

    assert result.exit_code != 0
    operation_id = captured["operation_id"]
    persisted = anyio.run(store.load_operation, operation_id)
    assert persisted is not None
    assert persisted.tasks[0].status is TaskStatus.COMPLETED
    assert persisted.status is OperationStatus.COMPLETED
    assert persisted.final_summary == "Attached turn completed successfully."
    assert lifecycle_calls == []


def test_cli_package_exports_command_and_helper_families() -> None:
    assert "fleet" in cli_commands_pkg.__all__
    assert "operation_detail" in cli_commands_pkg.__all__
    assert "rendering" in cli_helpers_pkg.__all__
    assert "services" in cli_helpers_pkg.__all__


def state_settings(
    *,
    allowed_agents: list[str] | None = None,
    involvement_level: InvolvementLevel = InvolvementLevel.AUTO,
    max_iterations: int = 100,
    timeout_seconds: int | None = None,
    metadata: dict[str, object] | None = None,
    max_task_retries: int = 2,
    operator_message_window: int = 3,
) -> dict[str, object]:
    """Build split operation-state settings for CLI tests."""

    return {
        "policy": OperationPolicy(
            allowed_agents=list(allowed_agents or []),
            involvement_level=involvement_level,
        ),
        "execution_budget": ExecutionBudget(
            max_iterations=max_iterations,
            timeout_seconds=timeout_seconds,
            max_task_retries=max_task_retries,
        ),
        "runtime_hints": RuntimeHints(
            operator_message_window=operator_message_window,
            metadata=dict(metadata or {}),
        ),
    }


def _read_control_intent(tmp_path: Path) -> StoredControlIntent:
    path = next((tmp_path / "commands").glob("*.json"))
    return StoredControlIntent.model_validate_json(path.read_text(encoding="utf-8"))


def _read_control_intents(tmp_path: Path) -> list[StoredControlIntent]:
    return [
        StoredControlIntent.model_validate_json(path.read_text(encoding="utf-8"))
        for path in sorted((tmp_path / "commands").glob("*.json"))
    ]


def _install_patch_delivery_stub(
    monkeypatch,
    *,
    tmp_path: Path,
    command_type: OperationCommandType,
    status: CommandStatus = CommandStatus.APPLIED,
    rejection_reason: str | None = None,
) -> None:
    inbox = FileOperationCommandInbox(tmp_path / "commands")
    store = FileOperationStore(tmp_path / "runs")

    class FakeDeliveryService:
        def __init__(self) -> None:
            self.command_inbox = inbox
            self.store = store

        async def enqueue_command(
            self,
            operation_id: str,
            received_type: OperationCommandType,
            payload: dict[str, object],
            *,
            target_scope: CommandTargetScope,
            target_id: str,
            auto_resume_when_paused: bool = False,
            auto_resume_blocked_attention_id: str | None = None,
        ):
            command = OperationCommand(
                operation_id=operation_id,
                command_type=received_type,
                target_scope=target_scope,
                target_id=target_id,
                payload=payload,
            )
            await inbox.enqueue(command)
            return command, None, None

        async def tick(self, operation_id: str) -> OperationOutcome:
            commands = await inbox.list(operation_id)
            assert len(commands) == 1
            await inbox.update_status(
                commands[0].command_id,
                status,
                rejection_reason=rejection_reason,
            )
            return OperationOutcome(
                operation_id=operation_id,
                status=OperationStatus.RUNNING,
                summary="processed patch command",
            )

        def build_command_payload(
            self,
            received_type: OperationCommandType,
            text: str | None,
            success_criteria: list[str] | None = None,
            clear_success_criteria: bool = False,
            allowed_agents: list[str] | None = None,
            max_iterations: int | None = None,
        ) -> dict[str, object]:
            assert received_type is command_type
            if received_type is OperationCommandType.PATCH_SUCCESS_CRITERIA:
                if clear_success_criteria:
                    return {"success_criteria": []}
                return {"success_criteria": list(success_criteria or [])}
            assert text is not None
            return {"text": text}

    monkeypatch.setattr(
        "agent_operator.cli.workflows.control.delivery_commands_service",
        lambda: FakeDeliveryService(),
    )


def _seed_operation(tmp_path: Path) -> str:
    operation_id = "op-cli-1"
    runs_dir = tmp_path / "runs"
    store = FileOperationStore(runs_dir)
    trace_store = FileTraceStore(runs_dir)
    event_sink = JsonlEventSink(tmp_path, operation_id)

    async def _seed() -> None:
        state = OperationState(
            operation_id=operation_id,
            goal=OperationGoal(
                objective="Test objective",
                harness_instructions="Use swarm when unclear.",
            ),
            **state_settings(),
            status=OperationStatus.COMPLETED,
            final_summary="Completed successfully.",
            tasks=[
                TaskState(
                    task_id="task-1",
                    title="Primary objective",
                    goal="Test objective",
                    definition_of_done="Return the final report.",
                    status=TaskStatus.COMPLETED,
                    brain_priority=100,
                    effective_priority=100,
                    assigned_agent="codex_acp",
                    linked_session_id="session-1",
                    memory_refs=["memory-1"],
                    artifact_refs=["artifact-1"],
                )
            ],
            sessions=[
                SessionRecord(
                    handle=AgentSessionHandle(
                        adapter_key="codex_acp",
                        session_id="session-1",
                        session_name="repo-audit",
                    )
                )
            ],
            artifacts=[
                ArtifactRecord(
                    artifact_id="artifact-1",
                    kind="final_note",
                    producer="codex_acp",
                    task_id="task-1",
                    session_id="session-1",
                    content="Returned two integration points with a concise final note.",
                    raw_ref=str(tmp_path / "artifact-1.md"),
                )
            ],
            memory_entries=[
                MemoryEntry(
                    memory_id="memory-1",
                    scope=MemoryScope.TASK,
                    scope_id="task-1",
                    summary=(
                        "The repo's strongest extension points are the ACP adapter and "
                        "runtime events."
                    ),
                    freshness=MemoryFreshness.CURRENT,
                    source_refs=[MemorySourceRef(kind="artifact", ref_id="artifact-1")],
                )
            ],
        )
        outcome = OperationOutcome(
            operation_id=operation_id,
            status=OperationStatus.COMPLETED,
            summary="Completed successfully.",
        )
        await store.save_operation(state)
        await store.save_outcome(outcome)
        await trace_store.save_operation_brief(
            OperationBrief(
                operation_id=operation_id,
                status=OperationStatus.COMPLETED,
                objective_brief="Test objective",
                harness_brief="Use swarm when unclear.",
                latest_outcome_brief="Completed successfully.",
            )
        )
        await trace_store.append_iteration_brief(
            operation_id,
            IterationBrief(
                iteration=1,
                operator_intent_brief="Operator asked the agent to inspect the repo.",
                assignment_brief="Asked codex_acp to inspect the repo.",
                result_brief="Returned two integration points.",
                status_brief="Operation completed.",
            ),
        )
        await trace_store.append_agent_turn_brief(
            operation_id,
            AgentTurnBrief(
                operation_id=operation_id,
                iteration=1,
                agent_key="codex_acp",
                session_id="session-1",
                session_display_name="repo-audit [codex_acp]",
                assignment_brief="Asked codex_acp to inspect the repo.",
                result_brief="Returned two integration points.",
                status="success",
                raw_log_refs=[str(tmp_path / "raw.log")],
            ),
        )
        await trace_store.save_decision_memo(
            operation_id,
            DecisionMemo(
                operation_id=operation_id,
                iteration=1,
                decision_context_summary="Root task ready.",
                chosen_action="start_agent",
                rationale="Need repo inspection.",
            ),
        )
        await trace_store.append_trace_record(
            operation_id,
            TraceRecord(
                operation_id=operation_id,
                iteration=1,
                category="iteration",
                title="Iteration 1",
                summary="Operator asked the agent to inspect the repo.",
            ),
        )
        await trace_store.write_report(
            operation_id,
            "# Operation op-cli-1\n\nStatus: completed\nObjective: Test objective\n"
            "Harness Instructions: Use swarm when unclear.\nGoal Input Mode: structured\n\n"
            "## Summary\n\nCompleted successfully.\n\n"
            "## Tasks\n\n"
            "- Primary objective [completed] priority=100 agent=codex_acp session=session-1\n"
            "  goal: Test objective\n"
            "  done: Return the final report.\n"
            "  memory_refs: memory-1\n"
            "  artifact_refs: artifact-1\n\n"
            "## Current Memory\n\n"
            "- memory-1 [task:task-1] The repo's strongest extension points are the ACP "
            "adapter and runtime events.\n\n"
            "## Artifacts\n\n"
            "- artifact-1 [final_note] producer=codex_acp task=task-1 session=session-1\n"
            "  content: Returned two integration points with a concise final note.\n",
        )
        await event_sink.emit(
            RunEvent(
                event_type="operation.cycle_finished",
                operation_id=operation_id,
                iteration=1,
                category="trace",
            )
        )
        inbox = FileWakeupInbox(tmp_path / "wakeups")
        await inbox.enqueue(
            RunEvent(
                event_type="background_run.completed",
                kind=RunEventKind.WAKEUP,
                operation_id=operation_id,
                iteration=1,
                session_id="session-1",
                dedupe_key="run-1:completed",
                payload={"run_id": "run-1"},
            )
        )
        background_dir = tmp_path / "background" / "runs"
        background_dir.mkdir(parents=True, exist_ok=True)
        run = BackgroundRunHandle(
            run_id="run-1",
            operation_id=operation_id,
            adapter_key="codex_acp",
            session_id="session-1",
            iteration=1,
            status=BackgroundRunStatus.RUNNING,
        )
        (background_dir / "run-1.json").write_text(run.model_dump_json(indent=2), encoding="utf-8")

    anyio.run(_seed)
    return operation_id


def test_ask_cli_renders_text_output(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("OPERATOR_DATA_DIR", str(tmp_path))
    operation_id = _seed_operation(tmp_path)
    captured: list[tuple[str, str]] = []

    class _Service:
        async def answer_question(self, resolved_operation_id: str, question: str) -> str:
            captured.append((resolved_operation_id, question))
            return "It is completed."

    monkeypatch.setattr(
        "agent_operator.cli.workflows.control._build_cli_service",
        lambda settings: _Service(),
    )

    result = runner.invoke(app, ["ask", "last", "What is the current status?"])

    assert result.exit_code == 0
    assert captured == [(operation_id, "What is the current status?")]
    assert result.stdout == "Question: What is the current status?\n\nIt is completed.\n"


def test_ask_cli_json_output_contract(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("OPERATOR_DATA_DIR", str(tmp_path))
    _seed_operation(tmp_path)

    class _Service:
        async def answer_question(self, resolved_operation_id: str, question: str) -> str:
            assert resolved_operation_id == "op-cli-1"
            assert question == "Summarize the result."
            return "Completed successfully."

    monkeypatch.setattr(
        "agent_operator.cli.workflows.control._build_cli_service",
        lambda settings: _Service(),
    )

    result = runner.invoke(app, ["ask", "op-cli-1", "Summarize the result.", "--json"])

    assert result.exit_code == 0
    assert json.loads(result.stdout) == {
        "question": "Summarize the result.",
        "answer": "Completed successfully.",
    }


def test_ask_cli_resolves_profile_name_to_latest_operation(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("OPERATOR_DATA_DIR", str(tmp_path))
    store = FileOperationStore(tmp_path / "runs")

    async def _seed() -> None:
        await store.save_operation(
            OperationState(
                operation_id="op-profile-old",
                goal=OperationGoal(
                    objective="Older profile operation",
                    metadata={"project_profile_name": "femtobot"},
                ),
                created_at=datetime.now(UTC) - timedelta(hours=1),
                **state_settings(),
            )
        )
        await store.save_operation(
            OperationState(
                operation_id="op-profile-new",
                goal=OperationGoal(
                    objective="Newest profile operation",
                    metadata={"project_profile_name": "femtobot"},
                ),
                created_at=datetime.now(UTC),
                **state_settings(),
            )
        )

    anyio.run(_seed)
    captured: list[str] = []

    class _Service:
        async def answer_question(self, resolved_operation_id: str, question: str) -> str:
            captured.append(resolved_operation_id)
            return "Newest profile operation."

    monkeypatch.setattr(
        "agent_operator.cli.workflows.control._build_cli_service",
        lambda settings: _Service(),
    )

    result = runner.invoke(app, ["ask", "femtobot", "Which operation is current?"])

    assert result.exit_code == 0
    assert captured == ["op-profile-new"]
    assert "Newest profile operation." in result.stdout


def test_ask_cli_missing_operation_exits_code_4(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("OPERATOR_DATA_DIR", str(tmp_path))

    class _Service:
        async def answer_question(self, resolved_operation_id: str, question: str) -> str:
            raise AssertionError("service should not be called when operation resolution fails")

    monkeypatch.setattr(
        "agent_operator.cli.workflows.control._build_cli_service",
        lambda settings: _Service(),
    )

    result = runner.invoke(app, ["ask", "missing-op", "What happened?"])

    assert result.exit_code == 4
    assert "Operation 'missing-op' was not found." in result.output


def test_resolution_accepts_event_sourced_operation_id(tmp_path: Path, monkeypatch) -> None:
    from agent_operator.cli.helpers.resolution import resolve_operation_id

    monkeypatch.setenv("OPERATOR_DATA_DIR", str(tmp_path))
    event_dir = tmp_path / "operation_events"
    event_dir.mkdir()
    operation_id = "op-v2-resolution"
    (event_dir / f"{operation_id}.jsonl").write_text("", encoding="utf-8")

    assert resolve_operation_id(operation_id) == operation_id
    assert resolve_operation_id("op-v2") == operation_id


def test_resolution_last_accepts_event_sourced_operation_without_runs_dir(
    tmp_path: Path, monkeypatch
) -> None:
    from agent_operator.cli.helpers.resolution import resolve_operation_id

    monkeypatch.setenv("OPERATOR_DATA_DIR", str(tmp_path))
    operation_id = "op-v2-last"
    checkpoint = OperationCheckpoint.initial(operation_id)
    checkpoint.objective = ObjectiveState(
        objective="Resume canonical v2 truth.",
        metadata={"project_profile_name": "demo"},
    )
    checkpoint.created_at = datetime(2026, 4, 23, tzinfo=UTC)
    checkpoint.updated_at = datetime(2026, 4, 23, tzinfo=UTC)
    checkpoint_record = OperationCheckpointRecord(
        operation_id=operation_id,
        checkpoint_payload=checkpoint.model_dump(mode="json"),
        last_applied_sequence=0,
        checkpoint_format_version=1,
    )
    checkpoint_path = tmp_path / "operation_checkpoints" / f"{operation_id}.json"
    checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
    checkpoint_path.write_text(
        json.dumps({**checkpoint_record.model_dump(mode="json"), "epoch_id": 0}, indent=2),
        encoding="utf-8",
    )
    (tmp_path / "operation_events").mkdir()
    (tmp_path / "operation_events" / f"{operation_id}.jsonl").write_text("", encoding="utf-8")

    assert resolve_operation_id("last") == operation_id


def _seed_event_sourced_checkpoint(
    tmp_path: Path,
    operation_id: str,
    *,
    objective: str,
    status: OperationStatus = OperationStatus.RUNNING,
    profile_name: str | None = None,
    attention_requests: list[AttentionRequest] | None = None,
    tasks: list[TaskState] | None = None,
) -> None:
    checkpoint = OperationCheckpoint.initial(operation_id)
    metadata = {"project_profile_name": profile_name} if profile_name is not None else {}
    checkpoint.objective = ObjectiveState(objective=objective, metadata=metadata)
    checkpoint.status = status
    checkpoint.tasks = tasks or []
    checkpoint.attention_requests = attention_requests or []
    checkpoint.created_at = datetime(2026, 4, 24, tzinfo=UTC)
    checkpoint.updated_at = checkpoint.created_at
    checkpoint_record = OperationCheckpointRecord(
        operation_id=operation_id,
        checkpoint_payload=checkpoint.model_dump(mode="json"),
        last_applied_sequence=0,
        checkpoint_format_version=1,
    )
    checkpoint_path = tmp_path / "operation_checkpoints" / f"{operation_id}.json"
    checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
    checkpoint_path.write_text(
        json.dumps({**checkpoint_record.model_dump(mode="json"), "epoch_id": 0}, indent=2),
        encoding="utf-8",
    )
    event_path = tmp_path / "operation_events" / f"{operation_id}.jsonl"
    event_path.parent.mkdir(parents=True, exist_ok=True)
    event_path.write_text("", encoding="utf-8")


def test_converse_cli_loads_event_sourced_operation_without_runs_dir(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("OPERATOR_DATA_DIR", str(tmp_path))
    operation_id = "op-converse-v2-only"
    _seed_event_sourced_checkpoint(
        tmp_path,
        operation_id,
        objective="Canonical event-sourced converse objective",
    )
    prompts: list[str] = []

    class _Brain:
        async def converse(self, prompt: str) -> ConverseTurnDTO:
            prompts.append(prompt)
            return ConverseTurnDTO(answer="Canonical state loaded.")

    monkeypatch.setattr(
        "agent_operator.cli.workflows.control.build_brain",
        lambda settings: _Brain(),
    )

    result = runner.invoke(app, ["converse", operation_id], input="Status?\nquit\n")

    assert result.exit_code == 0
    assert "Canonical state loaded." in result.stdout
    assert len(prompts) == 1
    assert f"Operation id: {operation_id}" in prompts[0]
    assert "Canonical event-sourced converse objective" in prompts[0]


def test_converse_cli_fleet_includes_event_sourced_operation_without_runs_dir(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("OPERATOR_DATA_DIR", str(tmp_path))
    _seed_event_sourced_checkpoint(
        tmp_path,
        "op-converse-fleet-v2",
        objective="Canonical fleet objective",
        profile_name="demo",
    )
    _seed_event_sourced_checkpoint(
        tmp_path,
        "op-converse-fleet-done",
        objective="Completed fleet objective",
        status=OperationStatus.COMPLETED,
        profile_name="demo",
    )
    prompts: list[str] = []

    class _Brain:
        async def converse(self, prompt: str) -> ConverseTurnDTO:
            prompts.append(prompt)
            return ConverseTurnDTO(answer="Fleet canonical state loaded.")

    monkeypatch.setattr(
        "agent_operator.cli.workflows.control.build_brain",
        lambda settings: _Brain(),
    )

    result = runner.invoke(app, ["converse", "--project", "demo"], input="Fleet?\nquit\n")

    assert result.exit_code == 0
    assert "Fleet canonical state loaded." in result.stdout
    assert len(prompts) == 1
    assert "op-converse-fleet-v2" in prompts[0]
    assert "Canonical fleet objective" in prompts[0]
    assert "op-converse-fleet-done" not in prompts[0]


def test_attention_command_reads_event_sourced_operation_without_runs_dir(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("OPERATOR_DATA_DIR", str(tmp_path))
    operation_id = "op-detail-v2-attention"
    _seed_event_sourced_checkpoint(
        tmp_path,
        operation_id,
        objective="Canonical detail objective",
        attention_requests=[
            AttentionRequest(
                attention_id="attn-1",
                operation_id=operation_id,
                attention_type=AttentionType.QUESTION,
                title="Need answer",
                question="Which branch?",
                blocking=True,
            )
        ],
    )

    result = runner.invoke(app, ["attention", operation_id, "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["operation_id"] == operation_id
    assert payload["attention_requests"][0]["attention_id"] == "attn-1"
    assert payload["attention_requests"][0]["question"] == "Which branch?"


def test_converse_cli_read_only_query_renders_answer_without_executing_commands(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("OPERATOR_DATA_DIR", str(tmp_path))
    operation_id = _seed_operation(tmp_path)
    prompts: list[str] = []

    class _Brain:
        async def converse(self, prompt: str) -> ConverseTurnDTO:
            prompts.append(prompt)
            return ConverseTurnDTO(answer="The operation is currently running.")

    async def _unexpected_write(*args, **kwargs) -> None:
        raise AssertionError("read-only converse turn must not execute a write path")

    monkeypatch.setattr(
        "agent_operator.cli.workflows.control.build_brain",
        lambda settings: _Brain(),
    )
    monkeypatch.setattr("agent_operator.cli.workflows.control.answer_async", _unexpected_write)
    monkeypatch.setattr(
        "agent_operator.cli.workflows.control.enqueue_command_async",
        _unexpected_write,
    )
    monkeypatch.setattr("agent_operator.cli.workflows.control.cancel_async", _unexpected_write)
    monkeypatch.setattr("agent_operator.cli.workflows.control.stop_turn_async", _unexpected_write)

    result = runner.invoke(
        app,
        ["converse", "last"],
        input="What is the current status?\nquit\n",
    )

    assert result.exit_code == 0
    assert "Operator ›" in result.stdout
    assert "iter 0/100" in result.stdout
    assert "The operation is currently running." in result.stdout
    assert len(prompts) == 1
    assert f"Operation id: {operation_id}" in prompts[0]
    assert "Context level: brief" in prompts[0]


def test_converse_cli_write_proposal_executes_only_on_yes(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("OPERATOR_DATA_DIR", str(tmp_path))
    operation_id = _seed_operation(tmp_path)
    enqueued: list[tuple[str, OperationCommandType, str | None]] = []

    class _Brain:
        async def converse(self, prompt: str) -> ConverseTurnDTO:
            return ConverseTurnDTO(
                answer="I can record that as an operator message.",
                proposed_command=f'operator message {operation_id} "Use a branch."',
            )

    async def _capture_enqueue(
        operation_id_: str,
        command_type: OperationCommandType,
        text: str | None,
        *args,
        **kwargs,
    ) -> None:
        enqueued.append((operation_id_, command_type, text))

    monkeypatch.setattr(
        "agent_operator.cli.workflows.control.build_brain",
        lambda settings: _Brain(),
    )
    monkeypatch.setattr(
        "agent_operator.cli.workflows.control.enqueue_command_async",
        _capture_enqueue,
    )

    result = runner.invoke(
        app,
        ["converse", operation_id],
        input="Record the preferred workflow.\ny\nquit\n",
    )

    assert result.exit_code == 0
    assert f'→ Proposed action: operator message {operation_id} "Use a branch."' in result.stdout
    assert enqueued == [
        (
            operation_id,
            OperationCommandType.INJECT_OPERATOR_MESSAGE,
            "Use a branch.",
        )
    ]


def test_converse_cli_declining_proposal_continues_session(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("OPERATOR_DATA_DIR", str(tmp_path))
    operation_id = _seed_operation(tmp_path)
    prompts: list[str] = []
    enqueued: list[tuple[str, OperationCommandType, str | None]] = []
    turns = iter(
        [
            ConverseTurnDTO(
                answer="I can record that as an operator message.",
                proposed_command=f'operator message {operation_id} "Use swarm mode first."',
            ),
            ConverseTurnDTO(answer="No command executed. The session is still open."),
        ]
    )

    class _Brain:
        async def converse(self, prompt: str) -> ConverseTurnDTO:
            prompts.append(prompt)
            return next(turns)

    async def _capture_enqueue(
        operation_id_: str,
        command_type: OperationCommandType,
        text: str | None,
        *args,
        **kwargs,
    ) -> None:
        enqueued.append((operation_id_, command_type, text))

    monkeypatch.setattr(
        "agent_operator.cli.workflows.control.build_brain",
        lambda settings: _Brain(),
    )
    monkeypatch.setattr(
        "agent_operator.cli.workflows.control.enqueue_command_async",
        _capture_enqueue,
    )

    result = runner.invoke(
        app,
        ["converse", operation_id],
        input="Record a note.\nN\nWhat happened?\nquit\n",
    )

    assert result.exit_code == 0
    assert enqueued == []
    assert "No command executed. The session is still open." in result.stdout
    assert len(prompts) == 2
    assert "Proposed command declined." in prompts[1]


def test_converse_cli_without_operation_loads_fleet_context(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("OPERATOR_DATA_DIR", str(tmp_path))
    store = FileOperationStore(tmp_path / "runs")
    prompts: list[str] = []

    async def _seed() -> None:
        await store.save_operation(
            OperationState(
                operation_id="op-fleet-active-1",
                goal=OperationGoal(objective="Active operation 1"),
                status=OperationStatus.RUNNING,
                **state_settings(),
            )
        )
        await store.save_operation(
            OperationState(
                operation_id="op-fleet-active-2",
                goal=OperationGoal(objective="Active operation 2"),
                status=OperationStatus.RUNNING,
                **state_settings(),
            )
        )
        await store.save_operation(
            OperationState(
                operation_id="op-fleet-completed",
                goal=OperationGoal(objective="Completed operation"),
                status=OperationStatus.COMPLETED,
                **state_settings(),
            )
        )

    class _Brain:
        async def converse(self, prompt: str) -> ConverseTurnDTO:
            prompts.append(prompt)
            return ConverseTurnDTO(answer="Fleet context loaded.")

    anyio.run(_seed)
    monkeypatch.setattr(
        "agent_operator.cli.workflows.control.build_brain",
        lambda settings: _Brain(),
    )

    result = runner.invoke(app, ["converse"], input="Which operation is active?\nquit\n")

    assert result.exit_code == 0
    assert "Fleet context loaded." in result.stdout
    assert len(prompts) == 1
    assert "Conversation mode: fleet" in prompts[0]
    assert "op-fleet-active-1" in prompts[0]
    assert "op-fleet-active-2" in prompts[0]
    assert "op-fleet-completed" not in prompts[0]


def _seed_operation_without_linked_session(tmp_path: Path) -> str:
    operation_id = "op-cli-no-session"
    runs_dir = tmp_path / "runs"
    store = FileOperationStore(runs_dir)

    async def _seed() -> None:
        state = OperationState(
            operation_id=operation_id,
            goal=OperationGoal(objective="Inspect unlinked task workflow"),
            **state_settings(),
            status=OperationStatus.RUNNING,
            tasks=[
                TaskState(
                    task_id="task-nolink",
                    title="Unlinked task",
                    goal="Prepare documentation update",
                    definition_of_done="Task can be referenced without a linked session.",
                    status=TaskStatus.READY,
                    brain_priority=30,
                    effective_priority=30,
                    assigned_agent="codex_acp",
                )
            ],
        )
        await store.save_operation(state)

    anyio.run(_seed)
    return operation_id


def _seed_operation_with_context(tmp_path: Path) -> str:
    operation_id = "op-cli-context"
    runs_dir = tmp_path / "runs"
    store = FileOperationStore(runs_dir)

    async def _seed() -> None:
        state = OperationState(
            operation_id=operation_id,
            goal=OperationGoal(
                objective="Ship the feature",
                harness_instructions="Use swarm when strategic direction is unclear.",
                success_criteria=["Tests pass", "Docs updated"],
                metadata={
                    "project_profile_name": "femtobot",
                    "policy_scope": "profile:femtobot",
                    "resolved_project_profile": {
                        "profile_name": "femtobot",
                        "cwd": "/tmp/femtobot",
                        "default_agents": ["codex_acp"],
                        "harness_instructions": "Continue most of the time.",
                        "success_criteria": ["Tests pass", "Docs updated"],
                        "max_iterations": 12,
                        "involvement_level": "unattended",
                        "overrides": ["harness"],
                    },
                },
            ),
            **state_settings(
                allowed_agents=["codex_acp"],
                max_iterations=12,
            ),
            involvement_level="collaborative",
            status=OperationStatus.RUNNING,
            scheduler_state=SchedulerState.ACTIVE,
            active_policies=[
                PolicyEntry(
                    policy_id="policy-1",
                    project_scope="profile:femtobot",
                    title="Manual testing debt",
                    category=PolicyCategory.TESTING,
                    rule_text="Document manual-only verification in MANUAL_TESTING_REQUIRED.md.",
                    rationale="Keeps unresolved checks visible.",
                )
            ],
            sessions=[
                SessionRecord(
                    handle=AgentSessionHandle(
                        adapter_key="codex_acp",
                        session_id="session-context",
                        session_name="feature-slice",
                    ),
                    status=SessionRecordStatus.RUNNING,
                    waiting_reason="Agent is applying the selected slice.",
                )
            ],
            attention_requests=[
                AttentionRequest(
                    attention_id="attention-context",
                    operation_id=operation_id,
                    attention_type=AttentionType.POLICY_GAP,
                    status=AttentionStatus.OPEN,
                    blocking=False,
                    title="Testing policy gap",
                    question="Should manual-only checks always be recorded?",
                    target_scope=CommandTargetScope.OPERATION,
                    target_id=operation_id,
                )
            ],
        )
        state.current_focus = FocusState.model_validate(
            {
                "kind": "session",
                "target_id": "session-context",
                "mode": "blocking",
                "blocking_reason": "Waiting for the current attached turn.",
                "interrupt_policy": "terminal_only",
                "resume_policy": "replan",
            }
        )
        state.runtime_hints.metadata["run_mode"] = "attached"
        state.runtime_hints.metadata["available_agent_descriptors"] = [
            {
                "key": "codex_acp",
                "display_name": "Codex via ACP",
                "capabilities": [
                    {"name": "acp", "description": "ACP session over stdio"},
                    {"name": "follow_up", "description": "Can resume prior Codex sessions"},
                    {"name": "read_files", "description": "Can read repository files."},
                    {"name": "run_shell_commands", "description": "Can run shell commands."},
                ],
                "supports_follow_up": True,
                "supports_cancellation": True,
                "metadata": {},
            }
        ]
        await store.save_operation(state)

    anyio.run(_seed)
    return operation_id


def _seed_dashboard_operation(tmp_path: Path) -> tuple[str, Path]:
    operation_id = "op-cli-dashboard"
    runs_dir = tmp_path / "runs"
    store = FileOperationStore(runs_dir)
    trace_store = FileTraceStore(runs_dir)
    event_sink = JsonlEventSink(tmp_path / "events" / "events.jsonl")
    command_inbox = FileOperationCommandInbox(tmp_path / "commands")
    codex_home = tmp_path / "codex-home"

    async def _seed() -> None:
        state = OperationState(
            operation_id=operation_id,
            goal=OperationGoal(
                objective="Ship the dashboard slice",
                harness_instructions="Keep the dashboard thin over persisted truth.",
                metadata={
                    "project_profile_name": "operator",
                    "policy_scope": "profile:operator",
                    "resolved_project_profile": {
                        "profile_name": "operator",
                        "cwd": "/tmp/operator",
                        "default_agents": ["codex_acp", "claude_acp"],
                    },
                },
            ),
            **state_settings(
                allowed_agents=["codex_acp", "claude_acp"],
                max_iterations=10,
            ),
            involvement_level="collaborative",
            status=OperationStatus.RUNNING,
            scheduler_state=SchedulerState.ACTIVE,
            current_focus=FocusState(
                kind=FocusKind.SESSION,
                target_id="session-dashboard",
                mode="blocking",
                blocking_reason="Waiting on the current attached turn.",
            ),
            active_policies=[
                PolicyEntry(
                    policy_id="policy-dashboard",
                    project_scope="profile:operator",
                    title="Manual checks stay visible",
                    category=PolicyCategory.TESTING,
                    rule_text="Write human-only checks to MANUAL_TESTING_REQUIRED.md.",
                )
            ],
            tasks=[
                TaskState(
                    task_id="task-dashboard",
                    title="Implement dashboard command",
                    goal="Add a live operation workbench.",
                    definition_of_done="Users can inspect one operation in a single surface.",
                    status=TaskStatus.RUNNING,
                    brain_priority=90,
                    effective_priority=90,
                    assigned_agent="codex_acp",
                    linked_session_id="session-dashboard",
                ),
                TaskState(
                    task_id="task-docs",
                    title="Update ADR and architecture docs",
                    goal="Keep the source-of-truth docs aligned.",
                    definition_of_done="ADR and architecture text mention the dashboard surface.",
                    status=TaskStatus.READY,
                    brain_priority=70,
                    effective_priority=70,
                    assigned_agent="claude_acp",
                ),
            ],
            sessions=[
                SessionRecord(
                    handle=AgentSessionHandle(
                        adapter_key="codex_acp",
                        session_id="session-dashboard",
                        session_name="dashboard-workbench",
                    ),
                    status=SessionRecordStatus.RUNNING,
                    waiting_reason="Rendering the control-plane workbench.",
                    bound_task_ids=["task-dashboard"],
                )
            ],
            attention_requests=[
                AttentionRequest(
                    attention_id="attention-dashboard",
                    operation_id=operation_id,
                    attention_type=AttentionType.NOVEL_STRATEGIC_FORK,
                    status=AttentionStatus.OPEN,
                    blocking=False,
                    title="Choose dashboard landing surface",
                    question="Should the first dashboard be operation-first or fleet-first?",
                    target_scope=CommandTargetScope.OPERATION,
                    target_id=operation_id,
                )
            ],
        )
        state.runtime_hints.metadata["run_mode"] = "attached"
        state.runtime_hints.metadata["available_agent_descriptors"] = [
            {
                "key": "codex_acp",
                "display_name": "Codex via ACP",
                "capabilities": [
                    {"name": "acp", "description": "ACP session over stdio"},
                    {"name": "follow_up", "description": "Can resume prior Codex sessions"},
                    {"name": "read_files", "description": "Can read repository files."},
                    {"name": "write_files", "description": "Can create new files."},
                    {"name": "run_shell_commands", "description": "Can run shell commands."},
                ],
                "supports_follow_up": True,
                "supports_cancellation": True,
                "metadata": {},
            },
            {
                "key": "claude_acp",
                "display_name": "Claude Code via ACP",
                "capabilities": [
                    {"name": "acp", "description": "ACP session over stdio"},
                    {"name": "follow_up", "description": "Can resume Claude ACP sessions"},
                    {"name": "read_files", "description": "Can read repository files."},
                    {"name": "grep_search", "description": "Can search repository text."},
                ],
                "supports_follow_up": True,
                "supports_cancellation": True,
                "metadata": {},
            },
        ]
        await store.save_operation(state)
        await store.save_outcome(
            OperationOutcome(
                operation_id=operation_id,
                status=OperationStatus.RUNNING,
                summary="Dashboard slice is still in progress.",
            )
        )
        await trace_store.save_operation_brief(
            OperationBrief(
                operation_id=operation_id,
                status=OperationStatus.RUNNING,
                objective_brief="Ship the dashboard slice",
                focus_brief="session:session-dashboard",
                latest_outcome_brief="Dashboard slice is still in progress.",
            )
        )
        await event_sink.emit(
            RunEvent(
                event_type="brain.decision.made",
                operation_id=operation_id,
                iteration=2,
                payload={
                    "action_type": "start_agent",
                    "target_agent": "codex_acp",
                    "rationale": "Need a cohesive live workbench surface.",
                },
                category="trace",
            )
        )
        await event_sink.emit(
            RunEvent(
                event_type="agent.invocation.started",
                operation_id=operation_id,
                iteration=2,
                session_id="session-dashboard",
                payload={
                    "adapter_key": "codex_acp",
                    "session_name": "dashboard-workbench",
                },
                category="trace",
            )
        )
        await command_inbox.enqueue(
            OperationCommand(
                operation_id=operation_id,
                command_type=OperationCommandType.PAUSE_OPERATOR,
                target_scope=CommandTargetScope.OPERATION,
                target_id=operation_id,
            )
        )
        await command_inbox.enqueue(
            OperationCommand(
                operation_id=operation_id,
                command_type=OperationCommandType.INJECT_OPERATOR_MESSAGE,
                target_scope=CommandTargetScope.OPERATION,
                target_id=operation_id,
                payload={"text": "Favor the thinnest honest slice."},
            )
        )
        session_dir = codex_home / "sessions" / "2026" / "03" / "30"
        session_dir.mkdir(parents=True, exist_ok=True)
        transcript = session_dir / "rollout-session-dashboard.jsonl"
        transcript.write_text(
            "\n".join(
                [
                    json.dumps(
                        {
                            "timestamp": "2026-03-30T08:00:00Z",
                            "type": "event_msg",
                            "payload": {
                                "type": "agent_message",
                                "phase": "analysis",
                                "message": "Inspecting the persisted control-plane surfaces.",
                            },
                        }
                    ),
                    json.dumps(
                        {
                            "timestamp": "2026-03-30T08:00:05Z",
                            "type": "event_msg",
                            "payload": {
                                "type": "task_complete",
                                "last_agent_message": "Prepared the dashboard workbench plan.",
                            },
                        }
                    ),
                ]
            )
            + "\n",
            encoding="utf-8",
        )

    anyio.run(_seed)
    return operation_id, codex_home


def _seed_running_operation_with_terminal_background_run(tmp_path: Path) -> str:
    operation_id = "op-cli-running"
    runs_dir = tmp_path / "runs"
    store = FileOperationStore(runs_dir)
    trace_store = FileTraceStore(runs_dir)
    inbox = FileWakeupInbox(tmp_path / "wakeups")

    async def _seed() -> None:
        state = OperationState(
            operation_id=operation_id,
            goal=OperationGoal(objective="Running objective"),
            **state_settings(),
            status=OperationStatus.RUNNING,
            sessions=[
                SessionRecord(
                    handle=AgentSessionHandle(
                        adapter_key="codex_acp",
                        session_id="session-running",
                        session_name="stale-session",
                    )
                )
            ],
        )
        state.current_focus = FocusState.model_validate(
            {
                "kind": "session",
                "target_id": "session-running",
                "mode": "blocking",
                "blocking_reason": "Waiting for the background agent turn to complete.",
                "interrupt_policy": "terminal_only",
                "resume_policy": "replan",
            }
        )
        await store.save_operation(state)
        await store.save_outcome(
            OperationOutcome(
                operation_id=operation_id,
                status=OperationStatus.RUNNING,
                summary="Operation is waiting on a background agent turn.",
            )
        )
        await trace_store.save_operation_brief(
            OperationBrief(
                operation_id=operation_id,
                status=OperationStatus.RUNNING,
                objective_brief="Running objective",
                blocker_brief="Waiting on a background agent turn.",
            )
        )
        await inbox.enqueue(
            RunEvent(
                event_type="background_run.completed",
                kind=RunEventKind.WAKEUP,
                operation_id=operation_id,
                iteration=1,
                session_id="session-running",
                dedupe_key="run-stale:completed",
                payload={"run_id": "run-stale"},
            )
        )
        background_dir = tmp_path / "background" / "runs"
        background_dir.mkdir(parents=True, exist_ok=True)
        run = BackgroundRunHandle(
            run_id="run-stale",
            operation_id=operation_id,
            adapter_key="codex_acp",
            session_id="session-running",
            iteration=1,
            status=BackgroundRunStatus.COMPLETED,
        )
        (background_dir / "run-stale.json").write_text(
            run.model_dump_json(indent=2),
            encoding="utf-8",
        )

    anyio.run(_seed)
    return operation_id


def _seed_paused_operation(tmp_path: Path) -> str:
    operation_id = "op-cli-paused"
    runs_dir = tmp_path / "runs"
    store = FileOperationStore(runs_dir)
    trace_store = FileTraceStore(runs_dir)

    async def _seed() -> None:
        state = OperationState(
            operation_id=operation_id,
            goal=OperationGoal(objective="Paused objective"),
            **state_settings(),
            status=OperationStatus.RUNNING,
            scheduler_state=SchedulerState.PAUSED,
        )
        await store.save_operation(state)
        await store.save_outcome(
            OperationOutcome(
                operation_id=operation_id,
                status=OperationStatus.RUNNING,
                summary="Operation is paused.",
            )
        )
        await trace_store.save_operation_brief(
            OperationBrief(
                operation_id=operation_id,
                status=OperationStatus.RUNNING,
                objective_brief="Paused objective",
                blocker_brief="Operator is paused.",
                scheduler_state=SchedulerState.PAUSED,
            )
        )

    anyio.run(_seed)
    return operation_id


def _seed_claude_headless_operation(tmp_path: Path) -> tuple[str, Path]:
    operation_id = "op-cli-claude-log"
    runs_dir = tmp_path / "runs"
    store = FileOperationStore(runs_dir)
    log_path = tmp_path / ".operator" / "claude" / "session-claude.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)

    async def _seed() -> None:
        state = OperationState(
            operation_id=operation_id,
            goal=OperationGoal(objective="Inspect the Claude transcript"),
            **state_settings(),
            sessions=[
                SessionRecord(
                    handle=AgentSessionHandle(
                        adapter_key="claude_acp",
                        session_id="session-claude",
                        session_name="claude-headless",
                        metadata={"log_path": str(log_path)},
                    )
                )
            ],
        )
        await store.save_operation(state)

    log_path.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "timestamp": "2026-03-20T17:56:51.288Z",
                        "type": "system",
                        "subtype": "init",
                        "cwd": "/repo",
                        "model": "claude-sonnet-4-6",
                        "tools": ["Bash", "Read", "Write"],
                    }
                ),
                json.dumps(
                    {
                        "timestamp": "2026-03-20T17:56:53.288Z",
                        "type": "user",
                        "message": {
                            "content": [{"type": "text", "text": "Inspect the repository."}]
                        },
                    }
                ),
                json.dumps(
                    {
                        "timestamp": "2026-03-20T17:56:55.288Z",
                        "type": "assistant",
                        "message": {
                            "content": [{"type": "text", "text": "Reviewing the runtime seam."}]
                        },
                    }
                ),
                json.dumps(
                    {
                        "timestamp": "2026-03-20T17:56:57.288Z",
                        "type": "tool_use",
                        "name": "Bash",
                        "input": {"command": "git status --short", "description": "check repo"},
                    }
                ),
                json.dumps(
                    {
                        "timestamp": "2026-03-20T17:56:59.288Z",
                        "type": "tool_use",
                        "name": "Bash",
                        "input": {
                            "command": "cp design/VISION.md ../backup/",
                            "with_escalated_permissions": True,
                            "justification": "Need to preserve the canonical vision copy.",
                        },
                    }
                ),
                json.dumps(
                    {
                        "timestamp": "2026-03-20T17:57:01.288Z",
                        "type": "result",
                        "subtype": "success",
                        "result": "Drafted the Claude log parser plan.",
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    anyio.run(_seed)
    return operation_id, log_path


def _seed_opencode_headless_operation(tmp_path: Path) -> tuple[str, Path]:
    operation_id = "op-cli-opencode-log"
    runs_dir = tmp_path / "runs"
    store = FileOperationStore(runs_dir)
    log_path = tmp_path / ".operator" / "opencode" / "session-opencode.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)

    async def _seed() -> None:
        state = OperationState(
            operation_id=operation_id,
            goal=OperationGoal(objective="Inspect the OpenCode transcript"),
            **state_settings(),
            sessions=[
                SessionRecord(
                    handle=AgentSessionHandle(
                        adapter_key="opencode_acp",
                        session_id="session-opencode",
                        session_name="opencode-headless",
                        metadata={"log_path": str(log_path)},
                    )
                )
            ],
        )
        await store.save_operation(state)

    log_path.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "timestamp": "2026-03-20T17:56:51.288Z",
                        "type": "session",
                        "message": "OpenCode session started.",
                    }
                ),
                json.dumps(
                    {
                        "timestamp": "2026-03-20T17:56:53.288Z",
                        "message": "Inspecting the runtime seam.",
                    }
                ),
                json.dumps(
                    {
                        "timestamp": "2026-03-20T17:56:57.288Z",
                        "type": "tool_use",
                        "message": "exec_command: git status --short",
                    }
                ),
                json.dumps(
                    {
                        "timestamp": "2026-03-20T17:57:01.288Z",
                        "summary": "Task completed: Drafted the OpenCode log parser plan.",
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    anyio.run(_seed)
    return operation_id, log_path


def _seed_blocked_attention_operation(tmp_path: Path) -> tuple[str, str]:
    operation_id = "op-cli-attention"
    attention_id = "attention-1"
    runs_dir = tmp_path / "runs"
    store = FileOperationStore(runs_dir)

    async def _seed() -> None:
        state = OperationState(
            operation_id=operation_id,
            goal=OperationGoal(objective="Need human answer"),
            **state_settings(),
            status=OperationStatus.NEEDS_HUMAN,
            attention_requests=[
                AttentionRequest(
                    attention_id=attention_id,
                    operation_id=operation_id,
                    attention_type=AttentionType.QUESTION,
                    status=AttentionStatus.OPEN,
                    blocking=True,
                    title="Clarification required",
                    question="Which environment should be used?",
                    target_scope=CommandTargetScope.OPERATION,
                    target_id=operation_id,
                )
            ],
        )
        state.current_focus = FocusState.model_validate(
            {
                "kind": "attention_request",
                "target_id": attention_id,
                "mode": "blocking",
                "blocking_reason": "Which environment should be used?",
                "interrupt_policy": "material_wakeup",
                "resume_policy": "replan",
            }
        )
        await store.save_operation(state)
        await store.save_outcome(
            OperationOutcome(
                operation_id=operation_id,
                status=OperationStatus.NEEDS_HUMAN,
                summary="Blocked on attention request.",
            )
        )

    anyio.run(_seed)
    return operation_id, attention_id


def _seed_command(tmp_path: Path, operation_id: str) -> None:
    inbox = FileOperationCommandInbox(tmp_path / "commands")

    async def _seed() -> None:
        await inbox.enqueue(
            OperationCommand(
                operation_id=operation_id,
                command_type=OperationCommandType.INJECT_OPERATOR_MESSAGE,
                target_scope=CommandTargetScope.OPERATION,
                target_id=operation_id,
                payload={"text": "Use swarm when strategic direction is unclear."},
            )
        )

    anyio.run(_seed)


def _seed_project_profile(tmp_path: Path, *, name: str = "femtobot") -> None:
    projects_dir = tmp_path / "profiles"
    projects_dir.mkdir(parents=True, exist_ok=True)
    (projects_dir / f"{name}.yaml").write_text(
        "\n".join(
            [
                f"name: {name}",
                "cwd: /tmp/femtobot",
                "default_agents:",
                "  - codex_acp",
                "default_harness_instructions: Continue most of the time.",
                "default_success_criteria:",
                "  - backlog stays above 100",
                "default_max_iterations: 12",
                "default_involvement_level: unattended",
                "adapter_settings:",
                "  codex_acp:",
                "    command: npm exec --yes @zed-industries/codex-acp --",
                "    approval_policy: never",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def _seed_agenda_operations(tmp_path: Path) -> None:
    runs_dir = tmp_path / "runs"
    store = FileOperationStore(runs_dir)
    trace_store = FileTraceStore(runs_dir)

    async def _seed() -> None:
        blocked = OperationState(
            operation_id="op-agenda-blocked",
            goal=OperationGoal(
                objective="Choose deployment target",
                metadata={
                    "project_profile_name": "femtobot",
                    "policy_scope": "profile:femtobot",
                },
            ),
            **state_settings(),
            status=OperationStatus.NEEDS_HUMAN,
            final_summary="Waiting for approval.",
            attention_requests=[
                AttentionRequest(
                    attention_id="attention-deploy",
                    operation_id="op-agenda-blocked",
                    attention_type=AttentionType.APPROVAL_REQUEST,
                    status=AttentionStatus.OPEN,
                    title="Approve staging deploy",
                    question="Should the operator deploy to staging now?",
                    blocking=True,
                    target_scope=CommandTargetScope.OPERATION,
                )
            ],
        )
        blocked.current_focus = FocusState.model_validate(
            {
                "kind": "attention_request",
                "target_id": "attention-deploy",
                "mode": "blocking",
                "blocking_reason": "Waiting for deployment approval.",
            }
        )
        paused = OperationState(
            operation_id="op-agenda-paused",
            goal=OperationGoal(
                objective="Refactor the release script",
                metadata={
                    "project_profile_name": "femtobot",
                    "policy_scope": "profile:femtobot",
                },
            ),
            **state_settings(),
            status=OperationStatus.RUNNING,
            scheduler_state=SchedulerState.PAUSED,
        )
        active = OperationState(
            operation_id="op-agenda-active",
            goal=OperationGoal(
                objective="Audit the billing worker",
                metadata={
                    "project_profile_name": "opsbot",
                    "policy_scope": "profile:opsbot",
                },
            ),
            **state_settings(),
            status=OperationStatus.RUNNING,
            tasks=[
                TaskState(
                    task_id="task-active",
                    title="Inspect worker retries",
                    goal="Audit the billing worker",
                    definition_of_done="Summarize retry risks.",
                    status=TaskStatus.READY,
                )
            ],
            sessions=[
                SessionRecord(
                    handle=AgentSessionHandle(
                        adapter_key="codex_acp",
                        session_id="session-active",
                        session_name="billing-worker",
                    ),
                    status=SessionRecordStatus.RUNNING,
                )
            ],
        )
        completed = OperationState(
            operation_id="op-agenda-completed",
            goal=OperationGoal(
                objective="Summarize last week's incidents",
                metadata={
                    "project_profile_name": "femtobot",
                    "policy_scope": "profile:femtobot",
                },
            ),
            **state_settings(),
            status=OperationStatus.COMPLETED,
            final_summary="Incident summary complete.",
        )
        await store.save_operation(blocked)
        await store.save_operation(paused)
        await store.save_operation(active)
        await store.save_operation(completed)
        await trace_store.save_operation_brief(
            OperationBrief(
                operation_id="op-agenda-blocked",
                status=OperationStatus.NEEDS_HUMAN,
                objective_brief="Choose deployment target",
                focus_brief="attention_request:attention-deploy",
                blocker_brief="Waiting for deployment approval.",
            )
        )
        await trace_store.save_operation_brief(
            OperationBrief(
                operation_id="op-agenda-paused",
                status=OperationStatus.RUNNING,
                scheduler_state=SchedulerState.PAUSED,
                objective_brief="Refactor the release script",
                latest_outcome_brief="Operator is paused.",
            )
        )
        await trace_store.save_operation_brief(
            OperationBrief(
                operation_id="op-agenda-active",
                status=OperationStatus.RUNNING,
                objective_brief="Audit the billing worker",
                focus_brief="session:session-active",
                latest_outcome_brief="Inspecting retry paths.",
            )
        )
        await trace_store.save_operation_brief(
            OperationBrief(
                operation_id="op-agenda-completed",
                status=OperationStatus.COMPLETED,
                objective_brief="Summarize last week's incidents",
                latest_outcome_brief="Incident summary complete.",
            )
        )

    anyio.run(_seed)


def test_list_default_is_human_readable_brief(tmp_path: Path, monkeypatch) -> None:
    _seed_operation(tmp_path)
    monkeypatch.setenv("OPERATOR_DATA_DIR", str(tmp_path))

    result = runner.invoke(app, ["list"])

    assert result.exit_code == 0
    assert "[completed]" in result.stdout
    assert "Test objective" in result.stdout
    assert "op-cli-1" in result.stdout
    assert '"operation_id"' not in result.stdout


def test_list_json_emits_machine_readable_objects(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("OPERATOR_DATA_DIR", str(tmp_path))
    store = FileOperationStore(tmp_path / "runs")

    anyio.run(
        store.save_operation,
        OperationState(
            operation_id="op-list-fallback",
            goal=OperationGoal(objective="Fallback list objective"),
            **state_settings(),
            status=OperationStatus.COMPLETED,
            final_summary="Fallback list completed.",
        ),
    )

    def _fail_operation_summary_model_dump(self, *args, **kwargs):
        raise AssertionError("list json should not serialize OperationSummary directly")

    monkeypatch.setattr(OperationSummary, "model_dump", _fail_operation_summary_model_dump)

    result = runner.invoke(app, ["list", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["operation_id"] == "op-list-fallback"
    assert payload["status"] == "completed"
    assert payload["objective_brief"] == "Fallback list objective"


def test_list_json_emits_event_sourced_objects_without_runs_dir(
    tmp_path: Path, monkeypatch
) -> None:
    operation_id = "op-list-v2"
    checkpoint = OperationCheckpoint.initial(operation_id)
    checkpoint.objective = ObjectiveState(
        objective="Canonical event-sourced listing",
        summary="Checkpoint-only listing works.",
    )
    checkpoint.status = OperationStatus.COMPLETED
    checkpoint.final_summary = "Checkpoint-only listing works."
    checkpoint.created_at = datetime(2026, 4, 23, tzinfo=UTC)
    checkpoint.updated_at = datetime(2026, 4, 23, tzinfo=UTC)
    checkpoint_record = OperationCheckpointRecord(
        operation_id=operation_id,
        checkpoint_payload=checkpoint.model_dump(mode="json"),
        last_applied_sequence=0,
        checkpoint_format_version=1,
    )
    checkpoint_path = tmp_path / "operation_checkpoints" / f"{operation_id}.json"
    checkpoint_path.parent.mkdir(parents=True)
    checkpoint_path.write_text(
        json.dumps({**checkpoint_record.model_dump(mode="json"), "epoch_id": 0}, indent=2),
        encoding="utf-8",
    )
    (tmp_path / "operation_events").mkdir()
    (tmp_path / "operation_events" / f"{operation_id}.jsonl").write_text("", encoding="utf-8")
    monkeypatch.setenv("OPERATOR_DATA_DIR", str(tmp_path))

    result = runner.invoke(app, ["list", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["operation_id"] == operation_id
    assert payload["status"] == "completed"
    assert payload["objective_brief"] == "Canonical event-sourced listing"


def test_history_default_reads_committed_ledger(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "operator-history.jsonl").write_text(
        (
            '{"op_id":"op-hist-1","goal":"Fix flaky tests","profile":"default",'
            '"started":"2026-04-03T10:00:00Z","ended":"2026-04-03T11:00:00Z",'
            '"status":"completed","stop_reason":"explicit_success"}\n'
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("OPERATOR_DATA_DIR", str(tmp_path))

    result = runner.invoke(app, ["history"])

    assert result.exit_code == 0
    assert "op-hist-1 COMPLETED Fix flaky tests [reason=explicit_success]" in result.stdout


def test_history_json_and_last_reference(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "operator-history.jsonl").write_text(
        "\n".join(
            [
                '{"op_id":"op-hist-1","goal":"First","profile":"default","started":"2026-04-03T10:00:00Z","ended":"2026-04-03T11:00:00Z","status":"failed","stop_reason":"iteration_limit_exhausted"}',
                '{"op_id":"op-hist-2","goal":"Second","profile":"default","started":"2026-04-03T12:00:00Z","ended":"2026-04-03T13:00:00Z","status":"completed","stop_reason":"explicit_success"}',
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("OPERATOR_DATA_DIR", str(tmp_path))

    result = runner.invoke(app, ["history", "last", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert len(payload) == 1
    assert payload[0]["op_id"] == "op-hist-2"
    assert payload[0]["stop_reason"] == "explicit_success"


def test_history_reports_when_committed_ledger_is_disabled(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "operator-profile.yaml").write_text(
        "name: default\nhistory_ledger: false\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OPERATOR_DATA_DIR", str(tmp_path))

    result = runner.invoke(app, ["history"])

    assert result.exit_code == 0
    assert "Committed history ledger is disabled for this project." in result.stdout


def test_clear_yes_removes_runtime_state_and_preserves_profiles(
    tmp_path: Path,
    monkeypatch,
) -> None:
    repo_root = tmp_path / "operator"
    repo_root.mkdir()
    (repo_root / ".git").mkdir()
    data_dir = repo_root / ".operator"
    monkeypatch.chdir(repo_root)
    monkeypatch.delenv("OPERATOR_DATA_DIR", raising=False)

    _seed_operation(data_dir)
    for relative in (
        "events/op-cli-1.jsonl",
        "commands/cmd-1.json",
        "control_intents/intent-1.json",
        "wakeups/wakeup-1.json",
        "operation_events/op-cli-1.jsonl",
        "operation_checkpoints/op-cli-1.json",
        "background/runs/run-1.json",
        "background/results/run-1.json",
        "project_memory/project/entry-1.json",
        "policies/policy-1.json",
        "acp/session.log",
        "claude/session.log",
        "monitor/pid",
        "projects/legacy.yaml",
    ):
        path = data_dir / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{}", encoding="utf-8")
    (data_dir / "last").write_text("op-cli-1\n", encoding="utf-8")
    (repo_root / "operator-history.jsonl").write_text('{"op_id":"op-cli-1"}\n', encoding="utf-8")
    (repo_root / "operator-profile.yaml").write_text("name: default\n", encoding="utf-8")
    (repo_root / "operator-profiles").mkdir()
    (repo_root / "operator-profiles" / "opsbot.yaml").write_text("name: opsbot\n", encoding="utf-8")
    (data_dir / "profiles").mkdir(parents=True)
    (data_dir / "profiles" / "local.yaml").write_text("name: local\n", encoding="utf-8")
    (data_dir / "uv-cache").mkdir(parents=True)
    (data_dir / "uv-cache" / "cache.txt").write_text("cached\n", encoding="utf-8")

    result = runner.invoke(app, ["clear", "--yes"])

    assert result.exit_code == 0
    assert "Cleared operator state for" in result.stdout
    assert not (data_dir / "runs").exists()
    assert not (data_dir / "events").exists()
    assert not (data_dir / "commands").exists()
    assert not (data_dir / "control_intents").exists()
    assert not (data_dir / "wakeups").exists()
    assert not (data_dir / "operation_events").exists()
    assert not (data_dir / "operation_checkpoints").exists()
    assert not (data_dir / "background").exists()
    assert not (data_dir / "project_memory").exists()
    assert not (data_dir / "policies").exists()
    assert not (data_dir / "acp").exists()
    assert not (data_dir / "claude").exists()
    assert not (data_dir / "monitor").exists()
    assert not (data_dir / "projects").exists()
    assert not (data_dir / "last").exists()
    assert not (repo_root / "operator-history.jsonl").exists()
    assert (repo_root / "operator-profile.yaml").exists()
    assert (repo_root / "operator-profiles" / "opsbot.yaml").exists()
    assert (data_dir / "profiles" / "local.yaml").exists()
    assert (data_dir / "uv-cache" / "cache.txt").exists()


def test_clear_refuses_when_running_operation_exists(tmp_path: Path, monkeypatch) -> None:
    repo_root = tmp_path / "operator"
    repo_root.mkdir()
    (repo_root / ".git").mkdir()
    data_dir = repo_root / ".operator"
    monkeypatch.chdir(repo_root)
    monkeypatch.delenv("OPERATOR_DATA_DIR", raising=False)

    store = FileOperationStore(data_dir / "runs")

    async def _seed() -> None:
        state = OperationState(
            operation_id="op-live-1",
            goal=OperationGoal(objective="Keep running", harness_instructions=""),
            **state_settings(),
            status=OperationStatus.RUNNING,
        )
        await store.save_operation(state)

    anyio.run(_seed)

    result = runner.invoke(app, ["clear", "--yes"])

    assert result.exit_code == 1
    assert (
        "Refusing to clear operator state while active or recoverable operations still exist"
        in result.stderr
    )
    assert (data_dir / "runs" / "op-live-1.operation.json").exists()


def test_clear_force_yes_discards_blockers_and_preserves_profiles(
    tmp_path: Path,
    monkeypatch,
) -> None:
    repo_root = tmp_path / "operator"
    repo_root.mkdir()
    (repo_root / ".git").mkdir()
    data_dir = repo_root / ".operator"
    monkeypatch.chdir(repo_root)
    monkeypatch.delenv("OPERATOR_DATA_DIR", raising=False)

    store = FileOperationStore(data_dir / "runs")

    async def _seed() -> None:
        state = OperationState(
            operation_id="op-live-1",
            goal=OperationGoal(objective="Keep running", harness_instructions=""),
            **state_settings(),
            status=OperationStatus.RUNNING,
        )
        await store.save_operation(state)

    anyio.run(_seed)
    (data_dir / "background" / "runs").mkdir(parents=True, exist_ok=True)
    (data_dir / "background" / "runs" / "run-1.json").write_text(
        json.dumps(
            {
                "run_id": "run-1",
                "operation_id": "op-live-1",
                "status": BackgroundRunStatus.RUNNING.value,
            }
        ),
        encoding="utf-8",
    )
    (repo_root / "operator-history.jsonl").write_text('{"op_id":"op-live-1"}\n', encoding="utf-8")
    (repo_root / "operator-profile.yaml").write_text("name: default\n", encoding="utf-8")
    (repo_root / "operator-profiles").mkdir()
    (repo_root / "operator-profiles" / "opsbot.yaml").write_text("name: opsbot\n", encoding="utf-8")
    (data_dir / "profiles").mkdir(parents=True, exist_ok=True)
    (data_dir / "profiles" / "local.yaml").write_text("name: local\n", encoding="utf-8")
    (data_dir / "uv-cache").mkdir(parents=True, exist_ok=True)
    (data_dir / "uv-cache" / "cache.txt").write_text("cached\n", encoding="utf-8")

    result = runner.invoke(app, ["clear", "--force", "--yes"])

    assert result.exit_code == 0
    assert "Forced clear discarded live or recoverable operator state." in result.stdout
    assert not (data_dir / "runs").exists()
    assert not (data_dir / "background").exists()
    assert not (repo_root / "operator-history.jsonl").exists()
    assert (repo_root / "operator-profile.yaml").exists()
    assert (repo_root / "operator-profiles" / "opsbot.yaml").exists()
    assert (data_dir / "profiles" / "local.yaml").exists()
    assert (data_dir / "uv-cache" / "cache.txt").exists()


def test_clear_without_yes_prompts_and_can_cancel(tmp_path: Path, monkeypatch) -> None:
    repo_root = tmp_path / "operator"
    repo_root.mkdir()
    (repo_root / ".git").mkdir()
    data_dir = repo_root / ".operator"
    monkeypatch.chdir(repo_root)
    monkeypatch.delenv("OPERATOR_DATA_DIR", raising=False)

    (data_dir / "events").mkdir(parents=True)
    (data_dir / "events" / "event.jsonl").write_text("{}", encoding="utf-8")

    result = runner.invoke(app, ["clear"], input="n\n")

    assert result.exit_code == 0
    assert "cancelled" in result.stdout
    assert (data_dir / "events" / "event.jsonl").exists()


def test_clear_force_without_yes_prompts_with_force_warning(
    tmp_path: Path,
    monkeypatch,
) -> None:
    repo_root = tmp_path / "operator"
    repo_root.mkdir()
    (repo_root / ".git").mkdir()
    data_dir = repo_root / ".operator"
    monkeypatch.chdir(repo_root)
    monkeypatch.delenv("OPERATOR_DATA_DIR", raising=False)

    (data_dir / "events").mkdir(parents=True)
    (data_dir / "events" / "event.jsonl").write_text("{}", encoding="utf-8")

    result = runner.invoke(app, ["clear", "--force"], input="n\n")

    assert result.exit_code == 0
    assert "Force-clear operator runtime state for this workspace?" in result.stdout
    assert "cancelled" in result.stdout
    assert (data_dir / "events" / "event.jsonl").exists()


def test_agenda_groups_attention_active_and_recent_operations(tmp_path: Path, monkeypatch) -> None:
    _seed_agenda_operations(tmp_path)
    monkeypatch.setenv("OPERATOR_DATA_DIR", str(tmp_path))

    result = runner.invoke(app, ["agenda", "--all"])

    assert result.exit_code == 0
    assert "Needs attention:" in result.stdout
    assert "op-agenda-blocked [needs_human] Choose deployment target" in result.stdout
    assert "attention=1" in result.stdout
    assert "attention: [approval_request] Approve staging deploy" in result.stdout
    assert "scheduler=paused" in result.stdout
    assert "Active:" in result.stdout
    assert "op-agenda-active [running] Audit the billing worker" in result.stdout
    assert "tasks=1 sessions=1" in result.stdout
    assert "Recent:" in result.stdout
    assert "op-agenda-completed [completed] Summarize last week's incidents" in result.stdout


def test_agenda_json_can_filter_by_project(tmp_path: Path, monkeypatch) -> None:
    _seed_agenda_operations(tmp_path)
    monkeypatch.setenv("OPERATOR_DATA_DIR", str(tmp_path))

    result = runner.invoke(app, ["agenda", "--project", "femtobot", "--json"])

    assert result.exit_code == 0
    assert '"total_operations": 3' in result.stdout
    assert '"operation_id": "op-agenda-blocked"' in result.stdout
    assert '"operation_id": "op-agenda-paused"' in result.stdout
    assert '"operation_id": "op-agenda-active"' not in result.stdout
    assert '"recent": []' in result.stdout


def test_fleet_once_renders_cross_operation_dashboard(tmp_path: Path, monkeypatch) -> None:
    _seed_agenda_operations(tmp_path)
    monkeypatch.setenv("OPERATOR_DATA_DIR", str(tmp_path))

    result = runner.invoke(app, ["fleet", "--all", "--once"])

    assert result.exit_code == 0
    assert "Fleet Dashboard" in result.stdout
    assert "needs_attention=2 active=1 recent=1" in result.stdout
    assert "status_mix=running=2, completed=1, needs_human=1" in result.stdout
    assert "scheduler_mix=active=3, paused=1" in result.stdout
    assert "involvement_mix=auto=4" in result.stdout
    assert "op-agenda-blocked" in result.stdout
    assert "op-agenda-active" in result.stdout
    assert "op-agenda-completed" in result.stdout
    assert "operator dashboard op-agenda-blocked" in result.stdout


def test_no_args_non_tty_renders_fleet_snapshot_when_operations_exist(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _seed_agenda_operations(tmp_path)
    monkeypatch.setenv("OPERATOR_DATA_DIR", str(tmp_path))

    result = runner.invoke(app, [])

    assert result.exit_code == 0
    assert "Fleet Dashboard" in result.stdout
    assert "op-agenda-blocked" in result.stdout


def test_no_args_non_tty_falls_back_to_help_when_no_operations_exist(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("OPERATOR_DATA_DIR", str(tmp_path))

    result = runner.invoke(app, [])

    assert result.exit_code == 0
    assert "Usage:" in result.stdout
    assert "fleet" in result.stdout


def test_list_is_inventory_shaped_not_supervisory_snapshot(tmp_path: Path, monkeypatch) -> None:
    _seed_agenda_operations(tmp_path)
    monkeypatch.setenv("OPERATOR_DATA_DIR", str(tmp_path))

    list_result = runner.invoke(app, ["list"])
    fleet_result = runner.invoke(app, ["fleet", "--all", "--once"])

    assert list_result.exit_code == 0
    assert fleet_result.exit_code == 0
    # list is inventory: plain id/status rows, no dashboard header
    assert "Fleet Dashboard" not in list_result.stdout
    assert "needs_attention" not in list_result.stdout
    # fleet is supervisory snapshot: has dashboard header
    assert "Fleet Dashboard" in fleet_result.stdout
    assert "needs_attention" in fleet_result.stdout


def test_fleet_json_can_filter_by_project(tmp_path: Path, monkeypatch) -> None:
    _seed_agenda_operations(tmp_path)
    monkeypatch.setenv("OPERATOR_DATA_DIR", str(tmp_path))

    result = runner.invoke(app, ["fleet", "--project", "femtobot", "--json"])

    assert result.exit_code == 0
    assert '"project": "femtobot"' in result.stdout
    assert '"total_operations": 3' in result.stdout
    assert '"mix"' in result.stdout
    assert '"status_counts"' in result.stdout
    assert '"operation_id": "op-agenda-blocked"' in result.stdout
    assert '"operation_id": "op-agenda-paused"' in result.stdout
    assert '"operation_id": "op-agenda-active"' not in result.stdout
    assert '"control_hints"' in result.stdout


def test_discover_projects_skips_hidden_dirs_symlinks_and_nested_projects(tmp_path: Path) -> None:
    root = tmp_path / "roots"
    alpha = root / "alpha"
    nested = alpha / "nested"
    hidden = root / ".hidden" / "ghost"
    symlink_target = tmp_path / "external-target"
    symlink_path = root / "linked"

    (alpha / ".operator").mkdir(parents=True)
    (nested / ".operator").mkdir(parents=True)
    (hidden / ".operator").mkdir(parents=True)
    (symlink_target / ".operator").mkdir(parents=True)
    symlink_path.symlink_to(symlink_target, target_is_directory=True)

    discovered = discover_projects([root], max_depth=3)

    assert discovered == [alpha.resolve()]


def test_list_aggregates_across_configured_project_roots(tmp_path: Path, monkeypatch) -> None:
    config_path = tmp_path / "config.yaml"
    fleet_root = tmp_path / "projects"
    alpha = fleet_root / "alpha"
    beta = fleet_root / "beta"
    alpha.mkdir(parents=True)
    beta.mkdir(parents=True)
    (alpha / "operator-profile.yaml").write_text("name: alpha\n", encoding="utf-8")
    _seed_agenda_operations(alpha / ".operator")
    _seed_agenda_operations(beta / ".operator")
    config_path.write_text(f"project_roots:\n  - {fleet_root}\n", encoding="utf-8")
    monkeypatch.setenv("OPERATOR_GLOBAL_CONFIG", str(config_path))
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["list", "--json"])

    assert result.exit_code == 0
    assert result.stdout.count('"operation_id": "op-agenda-blocked"') == 2
    assert '"project": "alpha"' in result.stdout
    assert '"project": "beta"' in result.stdout


def test_fleet_first_run_prompt_accepts_and_writes_parent_roots(
    tmp_path: Path, monkeypatch
) -> None:
    config_path = tmp_path / "config.yaml"
    home = tmp_path / "home"
    workspace = tmp_path / "workspace"
    project_parent = home / "Projects"
    project_root = project_parent / "alpha"
    monkeypatch.setenv("OPERATOR_GLOBAL_CONFIG", str(config_path))
    workspace.mkdir()
    monkeypatch.chdir(workspace)
    project_root.mkdir(parents=True)
    (project_root / ".operator").mkdir()
    (project_root / "operator-profile.yaml").write_text("name: alpha\n", encoding="utf-8")
    monkeypatch.setattr("agent_operator.cli.workflows.views.Path.home", staticmethod(lambda: home))

    result = runner.invoke(app, ["fleet", "--once"], input="y\n")

    assert result.exit_code == 0
    assert "Found 1 projects with operator data:" in result.stdout
    assert load_global_config(config_path).project_roots == [project_parent.resolve()]


def test_fleet_discover_add_writes_parent_roots(tmp_path: Path, monkeypatch) -> None:
    config_path = tmp_path / "config.yaml"
    home = tmp_path / "home"
    project_parent = home / "Projects"
    project_root = project_parent / "alpha"
    project_root.mkdir(parents=True)
    (project_root / ".operator").mkdir()
    monkeypatch.setenv("OPERATOR_GLOBAL_CONFIG", str(config_path))
    monkeypatch.setattr("agent_operator.cli.workflows.views.Path.home", staticmethod(lambda: home))

    result = runner.invoke(app, ["fleet", "--discover", "--add", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["added"] is True
    assert payload["discovered_projects"] == [str(project_root.resolve())]
    assert load_global_config(config_path).project_roots == [project_parent.resolve()]


def test_default_help_hides_debug_commands(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("OPERATOR_DATA_DIR", str(tmp_path))

    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "debug" not in result.stdout
    assert "resume" not in result.stdout
    assert "trace" not in result.stdout
    assert "inspect" not in result.stdout
    assert "codex-log" not in result.stdout
    assert "claude-log" not in result.stdout


def test_debug_help_lists_hidden_runtime_commands(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("OPERATOR_DATA_DIR", str(tmp_path))

    result = runner.invoke(app, ["debug"])

    assert result.exit_code == 0
    assert "resume" in result.stdout
    assert "tick" in result.stdout
    assert "daemon" in result.stdout
    assert "recover" in result.stdout
    assert "wakeups" in result.stdout
    assert "sessions" in result.stdout
    assert "command" in result.stdout
    assert "context" in result.stdout
    assert "trace" in result.stdout
    assert "inspect" in result.stdout
    assert "log" not in result.stdout


def test_help_all_reveals_hidden_debug_commands(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("OPERATOR_DATA_DIR", str(tmp_path))

    result = runner.invoke(app, ["--help", "--all"])

    assert result.exit_code == 0
    assert "debug" in result.stdout
    assert "smoke" in result.stdout
    assert "Hidden Commands:" in result.stdout
    assert "resume" in result.stdout
    assert "tick" in result.stdout
    assert "daemon" in result.stdout
    assert "recover" in result.stdout
    assert "wakeups" in result.stdout
    assert "sessions" in result.stdout
    assert "command" in result.stdout
    assert "context" in result.stdout
    assert "trace" in result.stdout
    assert "inspect" in result.stdout


def test_fleet_surfaces_resume_hint_for_runtime_alert_operations(
    tmp_path: Path,
    monkeypatch,
) -> None:
    operation_id = "op-fleet-runtime-alert"
    runs_dir = tmp_path / "runs"
    store = FileOperationStore(runs_dir)
    trace_store = FileTraceStore(runs_dir)
    inbox = FileWakeupInbox(tmp_path / "wakeups")

    async def _seed() -> None:
        state = OperationState(
            operation_id=operation_id,
            goal=OperationGoal(objective="Recover the stale background run"),
            **state_settings(),
            status=OperationStatus.RUNNING,
        )
        await store.save_operation(state)
        await trace_store.save_operation_brief(
            OperationBrief(
                operation_id=operation_id,
                status=OperationStatus.RUNNING,
                objective_brief="Recover the stale background run",
                latest_outcome_brief="Background reconciliation is pending.",
            )
        )
        await inbox.enqueue(
            RunEvent(
                event_type="background_run.completed",
                kind=RunEventKind.WAKEUP,
                operation_id=operation_id,
                iteration=1,
                dedupe_key="run-stale:completed",
                payload={"run_id": "run-stale"},
            )
        )

    anyio.run(_seed)
    monkeypatch.setenv("OPERATOR_DATA_DIR", str(tmp_path))

    result = runner.invoke(app, ["fleet", "--once"])

    assert result.exit_code == 0
    assert "Needs Attention (1)" in result.stdout
    assert "operator resume op-fleet-runtime-alert" in result.stdout


def test_run_with_attach_session_requires_attach_agent(tmp_path: Path, monkeypatch) -> None:
    project_dir = tmp_path / "project"
    project_dir.mkdir(parents=True)
    (project_dir / "operator-profile.yaml").write_text(
        "\n".join(
            [
                "name: project",
                "default_objective: continue work",
                "cwd: .",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(project_dir)
    monkeypatch.delenv("OPERATOR_DATA_DIR", raising=False)

    result = runner.invoke(app, ["run", "continue work", "--attach-session", "sess-1"])

    assert result.exit_code != 0
    assert "--attach-agent is required" in (result.stdout + result.stderr)


def test_inspect_default_is_brief_first(tmp_path: Path, monkeypatch) -> None:
    operation_id = _seed_operation(tmp_path)
    _seed_command(tmp_path, operation_id)
    monkeypatch.setenv("OPERATOR_DATA_DIR", str(tmp_path))

    result = runner.invoke(app, ["inspect", operation_id])

    assert result.exit_code == 0
    assert "Objective" in result.stdout
    assert "Report:" in result.stdout
    assert "Commands:" in result.stdout
    assert "Trace:" not in result.stdout
    assert "Decision memos:" not in result.stdout
    assert "Events:" not in result.stdout


def test_inspect_full_shows_forensic_details(tmp_path: Path, monkeypatch) -> None:
    operation_id = _seed_operation(tmp_path)
    monkeypatch.setenv("OPERATOR_DATA_DIR", str(tmp_path))

    result = runner.invoke(app, ["inspect", operation_id, "--full"])

    assert result.exit_code == 0
    assert "Trace:" in result.stdout
    assert "Decision memos:" in result.stdout
    assert "Events:" in result.stdout
    assert "Iteration 1" in result.stdout
    assert "start_agent" in result.stdout
    assert "operation.cycle_finished" in result.stdout


def test_inspect_full_derives_attention_request_payloads(tmp_path: Path, monkeypatch) -> None:
    operation_id = _seed_operation(tmp_path)
    monkeypatch.setenv("OPERATOR_DATA_DIR", str(tmp_path))
    store = FileOperationStore(tmp_path / "runs")
    persisted = anyio.run(store.load_operation, operation_id)
    assert persisted is not None
    persisted.attention_requests = [
        AttentionRequest(
            attention_id="att-inspect",
            operation_id=operation_id,
            attention_type=AttentionType.POLICY_GAP,
            target_scope=CommandTargetScope.OPERATION,
            target_id=operation_id,
            title="Need policy clarification",
            question="Should this path stay read-only?",
            status=AttentionStatus.OPEN,
        )
    ]
    anyio.run(store.save_operation, persisted)

    def _fail_attention_model_dump(self, *args, **kwargs):
        raise AssertionError("debug inspect should not serialize AttentionRequest directly")

    monkeypatch.setattr(AttentionRequest, "model_dump", _fail_attention_model_dump)

    result = runner.invoke(app, ["inspect", operation_id, "--full"])

    assert result.exit_code == 0
    assert '"attention_id": "att-inspect"' in result.stdout
    assert '"attention_type": "policy_gap"' in result.stdout


def test_inspect_full_derives_forensic_payloads_without_serializing_truth_models(
    tmp_path: Path, monkeypatch
) -> None:
    from agent_operator.domain.operation import ExecutionState

    operation_id = _seed_operation(tmp_path)
    monkeypatch.setenv("OPERATOR_DATA_DIR", str(tmp_path))

    def _fail_execution_model_dump(self, *args, **kwargs):
        raise AssertionError("debug inspect --full should not serialize ExecutionState directly")

    def _fail_decision_memo_model_dump(self, *args, **kwargs):
        raise AssertionError("debug inspect --full should not serialize DecisionMemo directly")

    def _fail_run_event_model_dump(self, *args, **kwargs):
        raise AssertionError("debug inspect --full should not serialize RunEvent directly")

    def _fail_trace_record_model_dump(self, *args, **kwargs):
        raise AssertionError("debug inspect --full should not serialize TraceRecord directly")

    monkeypatch.setattr(ExecutionState, "model_dump", _fail_execution_model_dump)
    monkeypatch.setattr(DecisionMemo, "model_dump", _fail_decision_memo_model_dump)
    monkeypatch.setattr(RunEvent, "model_dump", _fail_run_event_model_dump)
    monkeypatch.setattr(TraceRecord, "model_dump", _fail_trace_record_model_dump)

    result = runner.invoke(app, ["inspect", operation_id, "--full"])

    assert result.exit_code == 0
    assert "Trace:" in result.stdout
    assert "Decision memos:" in result.stdout
    assert "Events:" in result.stdout
    assert "Background runs:" in result.stdout


def test_inspect_json_emits_aggregate_payload(tmp_path: Path, monkeypatch) -> None:
    from agent_operator.domain.traceability import TraceBriefBundle

    operation_id = _seed_operation(tmp_path)
    _seed_command(tmp_path, operation_id)
    monkeypatch.setenv("OPERATOR_DATA_DIR", str(tmp_path))

    def _fail_outcome_model_dump(self, *args, **kwargs):
        raise AssertionError("debug inspect should not serialize OperationOutcome directly")

    def _fail_brief_model_dump(self, *args, **kwargs):
        raise AssertionError("debug inspect should not serialize TraceBriefBundle directly")

    def _fail_command_model_dump(self, *args, **kwargs):
        raise AssertionError("debug inspect should not serialize OperationCommand directly")

    monkeypatch.setattr(TraceBriefBundle, "model_dump", _fail_brief_model_dump)
    monkeypatch.setattr(OperationOutcome, "model_dump", _fail_outcome_model_dump)
    monkeypatch.setattr(OperationCommand, "model_dump", _fail_command_model_dump)

    result = runner.invoke(app, ["inspect", operation_id, "--json"])

    assert result.exit_code == 0
    assert '"brief"' in result.stdout
    assert '"report"' in result.stdout
    assert '"commands"' in result.stdout
    assert '"durable_truth"' in result.stdout
    assert '"tasks"' in result.stdout
    assert '"memory"' in result.stdout
    assert '"artifacts"' in result.stdout
    assert '"trace_records"' not in result.stdout


def test_inspect_json_replays_v2_permission_events_into_durable_truth(
    tmp_path: Path, monkeypatch
) -> None:
    """Catches inspect falling back to legacy-only state or dropping v2 permission events."""
    operation_id = "op-cli-v2-permission"
    checkpoint = OperationCheckpoint.initial(operation_id)
    checkpoint.permission_events = [
        {
            "event_type": "permission.request.followup_required",
            "sequence": 12,
            "timestamp": "2026-04-23T00:00:00+00:00",
            "payload": {
                "adapter_key": "codex_acp",
                "session_id": "sess-1",
                "required_followup_reason": "Codex needs replacement instructions.",
            },
        }
    ]
    checkpoint_record = OperationCheckpointRecord(
        operation_id=operation_id,
        checkpoint_payload=checkpoint.model_dump(mode="json"),
        last_applied_sequence=0,
        checkpoint_format_version=1,
    )
    checkpoint_path = tmp_path / "operation_checkpoints" / f"{operation_id}.json"
    checkpoint_path.parent.mkdir(parents=True)
    checkpoint_path.write_text(
        json.dumps({**checkpoint_record.model_dump(mode="json"), "epoch_id": 0}, indent=2),
        encoding="utf-8",
    )
    monkeypatch.setenv("OPERATOR_DATA_DIR", str(tmp_path))

    result = runner.invoke(app, ["inspect", operation_id, "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    permission_events = payload["durable_truth"]["permission_events"]
    assert permission_events[0]["event_type"] == "permission.request.followup_required"
    assert permission_events[0]["payload"]["required_followup_reason"] == (
        "Codex needs replacement instructions."
    )


def test_inspect_full_json_includes_forensic_arrays(tmp_path: Path, monkeypatch) -> None:
    from agent_operator.domain.operation import ExecutionState

    operation_id = _seed_operation(tmp_path)
    monkeypatch.setenv("OPERATOR_DATA_DIR", str(tmp_path))

    def _fail_execution_model_dump(self, *args, **kwargs):
        raise AssertionError("debug inspect should not serialize ExecutionState directly")

    def _fail_decision_memo_model_dump(self, *args, **kwargs):
        raise AssertionError("debug inspect should not serialize DecisionMemo directly")

    def _fail_run_event_model_dump(self, *args, **kwargs):
        raise AssertionError("debug inspect should not serialize RunEvent directly")

    def _fail_trace_record_model_dump(self, *args, **kwargs):
        raise AssertionError("debug inspect should not serialize TraceRecord directly")

    monkeypatch.setattr(ExecutionState, "model_dump", _fail_execution_model_dump)
    monkeypatch.setattr(DecisionMemo, "model_dump", _fail_decision_memo_model_dump)
    monkeypatch.setattr(RunEvent, "model_dump", _fail_run_event_model_dump)
    monkeypatch.setattr(TraceRecord, "model_dump", _fail_trace_record_model_dump)

    result = runner.invoke(app, ["inspect", operation_id, "--json", "--full"])

    assert result.exit_code == 0
    assert '"trace_records"' in result.stdout
    assert '"decision_memos"' in result.stdout
    assert '"events"' in result.stdout


def test_report_prints_report_body(tmp_path: Path, monkeypatch) -> None:
    operation_id = _seed_operation(tmp_path)
    monkeypatch.setenv("OPERATOR_DATA_DIR", str(tmp_path))

    result = runner.invoke(app, ["report", operation_id])

    assert result.exit_code == 0
    assert "# Operation op-cli-1" in result.stdout
    assert "Harness Instructions: Use swarm when unclear." in result.stdout
    assert "Goal Input Mode: structured" in result.stdout
    assert "Completed successfully." in result.stdout
    assert "## Tasks" in result.stdout
    assert "## Current Memory" in result.stdout
    assert "## Artifacts" in result.stdout


def test_report_resolves_last_operation_reference(tmp_path: Path, monkeypatch) -> None:
    _seed_operation(tmp_path)
    monkeypatch.setenv("OPERATOR_DATA_DIR", str(tmp_path))

    result = runner.invoke(app, ["report", "last"])

    assert result.exit_code == 0
    assert "# Operation op-cli-1" in result.stdout


def test_report_json_emits_payload(tmp_path: Path, monkeypatch) -> None:
    operation_id = _seed_operation(tmp_path)
    monkeypatch.setenv("OPERATOR_DATA_DIR", str(tmp_path))

    result = runner.invoke(app, ["report", operation_id, "--json"])

    assert result.exit_code == 0
    assert '"operation_id": "op-cli-1"' in result.stdout
    assert '"brief"' in result.stdout
    assert '"outcome"' in result.stdout
    assert '"report"' in result.stdout
    assert '"durable_truth"' in result.stdout
    assert '"task_counts"' in result.stdout
    assert '"tasks"' in result.stdout
    assert '"memory"' in result.stdout
    assert '"artifacts"' in result.stdout


def test_report_json_derives_payload_without_serializing_brief_or_outcome_models(
    tmp_path: Path, monkeypatch
) -> None:
    from agent_operator.domain.traceability import TraceBriefBundle

    operation_id = _seed_operation(tmp_path)
    monkeypatch.setenv("OPERATOR_DATA_DIR", str(tmp_path))

    def _fail_outcome_model_dump(self, *args, **kwargs):
        raise AssertionError("report json should not serialize OperationOutcome directly")

    def _fail_brief_model_dump(self, *args, **kwargs):
        raise AssertionError("report json should not serialize TraceBriefBundle directly")

    monkeypatch.setattr(TraceBriefBundle, "model_dump", _fail_brief_model_dump)
    monkeypatch.setattr(OperationOutcome, "model_dump", _fail_outcome_model_dump)

    class _FakeDashboardQueries:
        async def load_payload(self, operation_id: str) -> dict[str, object]:
            assert operation_id == "op-cli-1"
            return {
                "brief": {"operation_brief": {"objective_brief": "from dashboard"}},
                "outcome": {"summary": "from dashboard"},
                "report": "dashboard report body",
                "durable_truth": {"tasks": [{"task_id": "task-from-dashboard"}]},
            }

    monkeypatch.setattr(
        commands_operation_detail,
        "build_operation_dashboard_query_service",
        lambda settings, *, operation_id, codex_home: _FakeDashboardQueries(),
    )

    result = runner.invoke(app, ["report", operation_id, "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["operation_id"] == "op-cli-1"
    assert payload["brief"] == {"operation_brief": {"objective_brief": "from dashboard"}}
    assert payload["outcome"] == {"summary": "from dashboard"}
    assert payload["report"] == "dashboard report body"
    assert payload["durable_truth"] == {"tasks": [{"task_id": "task-from-dashboard"}]}


def test_report_ticket_retries_pm_reporting(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("OPERATOR_DATA_DIR", str(tmp_path))
    store = FileOperationStore(tmp_path / "runs")
    anyio.run(
        store.save_operation,
        OperationState(
            operation_id="op-ticket",
            goal=OperationGoal(
                objective="Ship the change.",
                external_ticket=ExternalTicketLink(
                    provider="github_issues",
                    project_key="owner/repo",
                    ticket_id="123",
                ),
            ),
        ),
    )
    anyio.run(
        store.save_outcome,
        OperationOutcome(
            operation_id="op-ticket",
            status=OperationStatus.COMPLETED,
            summary="Completed cleanly.",
        ),
    )

    async def fake_retry(self, state, outcome):
        state.goal.external_ticket.reported = True
        return True

    monkeypatch.setattr(
        "agent_operator.cli.commands.operation_detail.TicketReportingService.retry",
        fake_retry,
    )

    result = runner.invoke(app, ["report", "op-ticket", "--ticket", "--json"])

    assert result.exit_code == 0
    assert '"ticket_reported": true' in result.stdout
    assert '"changed": true' in result.stdout


def test_context_command_prints_effective_control_plane_context(
    tmp_path: Path,
    monkeypatch,
) -> None:
    operation_id = _seed_operation_with_context(tmp_path)
    monkeypatch.setenv("OPERATOR_DATA_DIR", str(tmp_path))

    result = runner.invoke(app, ["context", operation_id])

    assert result.exit_code == 0
    assert "Operation op-cli-context" in result.stdout
    assert "Goal:" in result.stdout
    assert "Harness: Use swarm when strategic direction is unclear." in result.stdout
    assert "Runtime:" in result.stdout
    assert "Run mode: attached" in result.stdout
    assert "Current focus: session:session-context mode=blocking" in result.stdout
    assert "Active session: session-context [codex_acp] status=running name=feature-slice" in (
        result.stdout
    )
    assert "Agent capabilities:" in result.stdout
    assert (
        "codex_acp (Codex via ACP): capabilities=acp, follow_up, read_files, run_shell_commands"
        in result.stdout
    )
    assert "follow_up=yes" in result.stdout
    assert "Project context:" in result.stdout
    assert "Profile: femtobot" in result.stdout
    assert "Policy scope: profile:femtobot" in result.stdout
    assert "Resolved cwd: /tmp/femtobot" in result.stdout
    assert "CLI/profile overrides: harness" in result.stdout
    assert "Active policy:" in result.stdout
    assert "policy-1 [testing] Manual testing debt" in result.stdout
    assert "applies: active for current operation" in result.stdout


def test_context_command_json_emits_effective_context_payload(
    tmp_path: Path,
    monkeypatch,
) -> None:
    operation_id = _seed_operation_with_context(tmp_path)
    monkeypatch.setenv("OPERATOR_DATA_DIR", str(tmp_path))

    result = runner.invoke(app, ["context", operation_id, "--json"])

    assert result.exit_code == 0
    assert '"operation_id": "op-cli-context"' in result.stdout
    assert '"run_mode": "attached"' in result.stdout
    assert '"profile_name": "femtobot"' in result.stdout
    assert '"policy_scope": "profile:femtobot"' in result.stdout
    assert '"available_agent_descriptors"' in result.stdout
    assert '"display_name": "Codex via ACP"' in result.stdout
    assert '"name": "read_files"' in result.stdout
    assert '"active_policies"' in result.stdout
    assert '"policy_id": "policy-1"' in result.stdout
    assert '"applicability_summary": "active for current operation"' in result.stdout
    assert '"open_attention"' in result.stdout


def test_dashboard_command_prints_human_readable_workbench(
    tmp_path: Path,
    monkeypatch,
) -> None:
    operation_id, codex_home = _seed_dashboard_operation(tmp_path)
    monkeypatch.setenv("OPERATOR_DATA_DIR", str(tmp_path))

    result = runner.invoke(
        app,
        ["dashboard", operation_id, "--once", "--codex-home", str(codex_home)],
    )

    assert result.exit_code == 0
    assert f"Operation Dashboard: {operation_id}" in result.stdout
    assert "status=running scheduler=active run_mode=attached involvement=collaborative" in (
        result.stdout
    )
    assert "Control Context" in result.stdout
    assert "agent: codex_acp | follow_up=yes" in result.stdout
    assert "write_files, run_shell_commands" in result.stdout
    assert "agent: claude_acp | follow_up=yes" in result.stdout
    assert "read_files, grep_search" in result.stdout
    assert "Recent Commands" in result.stdout
    assert "pause_operator" in result.stdout
    assert "Codex Log" in result.stdout
    assert "Prepared the dashboard workbench plan." in result.stdout
    assert "Control Hints" in result.stdout
    assert f"operator interrupt {operation_id}" in result.stdout


def test_dashboard_command_resolves_last_operation_reference(
    tmp_path: Path,
    monkeypatch,
) -> None:
    operation_id, codex_home = _seed_dashboard_operation(tmp_path)
    monkeypatch.setenv("OPERATOR_DATA_DIR", str(tmp_path))

    result = runner.invoke(
        app,
        ["dashboard", "last", "--once", "--codex-home", str(codex_home)],
    )

    assert result.exit_code == 0
    assert f"Operation Dashboard: {operation_id}" in result.stdout


def test_dashboard_command_json_emits_machine_readable_snapshot(
    tmp_path: Path,
    monkeypatch,
) -> None:
    operation_id, codex_home = _seed_dashboard_operation(tmp_path)
    monkeypatch.setenv("OPERATOR_DATA_DIR", str(tmp_path))

    result = runner.invoke(
        app,
        ["dashboard", operation_id, "--json", "--codex-home", str(codex_home)],
    )

    assert result.exit_code == 0
    assert f'"operation_id": "{operation_id}"' in result.stdout
    assert '"recent_commands"' in result.stdout
    assert '"control_hints"' in result.stdout
    assert '"codex_log"' in result.stdout
    assert '"available_agent_descriptors"' in result.stdout
    assert '"key": "claude_acp"' in result.stdout
    assert '"attention_type": "novel_strategic_fork"' in result.stdout
    assert '"command_type": "pause_operator"' in result.stdout


def test_tasks_command_prints_human_readable_task_graph(tmp_path: Path, monkeypatch) -> None:
    operation_id = _seed_operation(tmp_path)
    monkeypatch.setenv("OPERATOR_DATA_DIR", str(tmp_path))

    result = runner.invoke(app, ["tasks", operation_id])

    assert result.exit_code == 0
    assert "Tasks:" in result.stdout
    assert "Primary objective [completed]" in result.stdout
    assert "memory_refs: memory-1" in result.stdout
    assert "artifact_refs: artifact-1" in result.stdout


def test_tasks_command_json_emits_tasks_payload(tmp_path: Path, monkeypatch) -> None:
    operation_id = _seed_operation(tmp_path)
    monkeypatch.setenv("OPERATOR_DATA_DIR", str(tmp_path))

    result = runner.invoke(app, ["tasks", operation_id, "--json"])

    assert result.exit_code == 0
    assert '"tasks"' in result.stdout
    assert '"task_id": "task-1"' in result.stdout


def test_tasks_command_json_derives_tasks_without_serializing_task_models(
    tmp_path: Path, monkeypatch
) -> None:
    operation_id = _seed_operation(tmp_path)
    monkeypatch.setenv("OPERATOR_DATA_DIR", str(tmp_path))

    def _fail_task_model_dump(self, *args, **kwargs):
        raise AssertionError("tasks command should not serialize TaskState directly")

    monkeypatch.setattr(TaskState, "model_dump", _fail_task_model_dump)

    result = runner.invoke(app, ["tasks", operation_id, "--json"])

    assert result.exit_code == 0
    assert '"tasks"' in result.stdout
    assert '"task_id": "task-1"' in result.stdout


def test_memory_command_defaults_to_current_entries(tmp_path: Path, monkeypatch) -> None:
    operation_id = _seed_operation(tmp_path)
    monkeypatch.setenv("OPERATOR_DATA_DIR", str(tmp_path))

    result = runner.invoke(app, ["memory", operation_id])

    assert result.exit_code == 0
    assert "Memory:" in result.stdout
    assert "memory-1 [task:task-1] current" in result.stdout
    assert "sources: artifact:artifact-1" in result.stdout


def test_memory_command_json_emits_memory_payload(tmp_path: Path, monkeypatch) -> None:
    operation_id = _seed_operation(tmp_path)
    monkeypatch.setenv("OPERATOR_DATA_DIR", str(tmp_path))

    result = runner.invoke(app, ["memory", operation_id, "--json"])

    assert result.exit_code == 0
    assert '"memory_entries"' in result.stdout
    assert '"memory_id": "memory-1"' in result.stdout


def test_memory_command_json_derives_entries_without_serializing_memory_models(
    tmp_path: Path, monkeypatch
) -> None:
    operation_id = _seed_operation(tmp_path)
    monkeypatch.setenv("OPERATOR_DATA_DIR", str(tmp_path))

    def _fail_memory_model_dump(self, *args, **kwargs):
        raise AssertionError("memory command should not serialize MemoryEntry directly")

    monkeypatch.setattr(MemoryEntry, "model_dump", _fail_memory_model_dump)

    result = runner.invoke(app, ["memory", operation_id, "--json"])

    assert result.exit_code == 0
    assert '"memory_entries"' in result.stdout
    assert '"memory_id": "memory-1"' in result.stdout


def test_artifacts_command_prints_human_readable_artifacts(tmp_path: Path, monkeypatch) -> None:
    operation_id = _seed_operation(tmp_path)
    monkeypatch.setenv("OPERATOR_DATA_DIR", str(tmp_path))

    result = runner.invoke(app, ["artifacts", operation_id])

    assert result.exit_code == 0
    assert "Artifacts:" in result.stdout
    assert "artifact-1 [final_note] producer=codex_acp" in result.stdout
    assert "raw_ref:" in result.stdout


def test_artifacts_command_json_emits_artifact_payload(tmp_path: Path, monkeypatch) -> None:
    operation_id = _seed_operation(tmp_path)
    monkeypatch.setenv("OPERATOR_DATA_DIR", str(tmp_path))

    result = runner.invoke(app, ["artifacts", operation_id, "--json"])

    assert result.exit_code == 0
    assert '"artifacts"' in result.stdout
    assert '"artifact_id": "artifact-1"' in result.stdout


def test_artifacts_command_json_derives_artifacts_without_serializing_models(
    tmp_path: Path, monkeypatch
) -> None:
    operation_id = _seed_operation(tmp_path)
    monkeypatch.setenv("OPERATOR_DATA_DIR", str(tmp_path))

    def _fail_artifact_model_dump(self, *args, **kwargs):
        raise AssertionError("artifacts command should not serialize ArtifactRecord directly")

    monkeypatch.setattr(ArtifactRecord, "model_dump", _fail_artifact_model_dump)

    result = runner.invoke(app, ["artifacts", operation_id, "--json"])

    assert result.exit_code == 0
    assert '"artifacts"' in result.stdout
    assert '"artifact_id": "artifact-1"' in result.stdout


def test_trace_default_shows_forensic_sections(tmp_path: Path, monkeypatch) -> None:
    operation_id = _seed_operation(tmp_path)
    monkeypatch.setenv("OPERATOR_DATA_DIR", str(tmp_path))

    result = runner.invoke(app, ["trace", operation_id])

    assert result.exit_code == 0
    assert "Trace:" in result.stdout
    assert "Decision memos:" in result.stdout
    assert "Events:" in result.stdout
    assert "Raw log refs:" in result.stdout
    assert "Iteration 1" in result.stdout
    assert "start_agent" in result.stdout


def test_inspect_surfaces_runtime_alert_for_unreconciled_background_completion(
    tmp_path: Path, monkeypatch
) -> None:
    operation_id = _seed_running_operation_with_terminal_background_run(tmp_path)
    monkeypatch.setenv("OPERATOR_DATA_DIR", str(tmp_path))

    result = runner.invoke(app, ["inspect", operation_id])

    assert result.exit_code == 0
    assert "alert=" in result.stdout or "alert:" in result.stdout
    assert "pending reconciliation" in result.stdout


def test_list_surfaces_runtime_alert_for_unreconciled_background_completion(
    tmp_path: Path, monkeypatch
) -> None:
    _seed_running_operation_with_terminal_background_run(tmp_path)
    monkeypatch.setenv("OPERATOR_DATA_DIR", str(tmp_path))

    result = runner.invoke(app, ["list"])

    assert result.exit_code == 0
    assert "alert=" in result.stdout
    assert "pending reconciliation" in result.stdout


def test_list_and_agenda_json_derive_runtime_alert_inputs_without_serializing_execution_models(
    tmp_path: Path, monkeypatch
) -> None:
    from agent_operator.domain.operation import ExecutionState

    _seed_running_operation_with_terminal_background_run(tmp_path)
    monkeypatch.setenv("OPERATOR_DATA_DIR", str(tmp_path))

    def _fail_execution_model_dump(self, *args, **kwargs):
        raise AssertionError("list/agenda json should not serialize ExecutionState directly")

    monkeypatch.setattr(ExecutionState, "model_dump", _fail_execution_model_dump)

    list_result = runner.invoke(app, ["list", "--json"])

    assert list_result.exit_code == 0
    list_payload = json.loads(list_result.stdout)
    assert list_payload["operation_id"] == "op-cli-running"
    assert "pending reconciliation" in str(list_payload["runtime_alert"])

    agenda_result = runner.invoke(app, ["agenda", "--json"])

    assert agenda_result.exit_code == 0
    agenda_payload = json.loads(agenda_result.stdout)
    assert agenda_payload["total_operations"] == 1
    assert "pending reconciliation" in str(agenda_payload["needs_attention"][0]["runtime_alert"])


def test_trace_json_emits_payload(tmp_path: Path, monkeypatch) -> None:
    operation_id = _seed_operation(tmp_path)
    _seed_command(tmp_path, operation_id)
    monkeypatch.setenv("OPERATOR_DATA_DIR", str(tmp_path))

    result = runner.invoke(app, ["trace", operation_id, "--json"])

    assert result.exit_code == 0
    assert '"trace_records"' in result.stdout
    assert '"decision_memos"' in result.stdout
    assert '"events"' in result.stdout
    assert '"raw_log_refs"' in result.stdout
    assert '"commands"' in result.stdout


def test_trace_json_derives_forensic_payloads_without_serializing_truth_models(
    tmp_path: Path, monkeypatch
) -> None:
    from agent_operator.domain.operation import ExecutionState

    operation_id = _seed_operation(tmp_path)
    _seed_command(tmp_path, operation_id)
    monkeypatch.setenv("OPERATOR_DATA_DIR", str(tmp_path))

    def _fail_execution_model_dump(self, *args, **kwargs):
        raise AssertionError("trace json should not serialize ExecutionState directly")

    def _fail_decision_memo_model_dump(self, *args, **kwargs):
        raise AssertionError("trace json should not serialize DecisionMemo directly")

    def _fail_run_event_model_dump(self, *args, **kwargs):
        raise AssertionError("trace json should not serialize RunEvent directly")

    def _fail_trace_record_model_dump(self, *args, **kwargs):
        raise AssertionError("trace json should not serialize TraceRecord directly")

    def _fail_attention_model_dump(self, *args, **kwargs):
        raise AssertionError("trace json should not serialize AttentionRequest directly")

    def _fail_command_model_dump(self, *args, **kwargs):
        raise AssertionError("trace json should not serialize OperationCommand directly")

    monkeypatch.setattr(ExecutionState, "model_dump", _fail_execution_model_dump)
    monkeypatch.setattr(DecisionMemo, "model_dump", _fail_decision_memo_model_dump)
    monkeypatch.setattr(RunEvent, "model_dump", _fail_run_event_model_dump)
    monkeypatch.setattr(TraceRecord, "model_dump", _fail_trace_record_model_dump)
    monkeypatch.setattr(AttentionRequest, "model_dump", _fail_attention_model_dump)
    monkeypatch.setattr(OperationCommand, "model_dump", _fail_command_model_dump)

    result = runner.invoke(app, ["trace", operation_id, "--json"])

    assert result.exit_code == 0
    assert '"trace_records"' in result.stdout
    assert '"decision_memos"' in result.stdout
    assert '"events"' in result.stdout
    assert '"background_runs"' in result.stdout
    assert '"attention_requests"' in result.stdout
    assert '"commands"' in result.stdout


def test_log_prints_condensed_human_readable_codex_events(tmp_path: Path, monkeypatch) -> None:
    operation_id = _seed_operation(tmp_path)
    monkeypatch.setenv("OPERATOR_DATA_DIR", str(tmp_path))
    codex_home = tmp_path / "codex-home"
    session_dir = codex_home / "sessions" / "2026" / "03" / "20"
    session_dir.mkdir(parents=True, exist_ok=True)
    transcript = session_dir / "rollout-2026-03-20T22-56-00-session-1.jsonl"
    entries = [
        {
            "timestamp": "2026-03-20T17:56:51.288Z",
            "type": "session_meta",
            "payload": {"id": "session-1", "cwd": "/repo", "model_provider": "openai"},
        },
        {
            "timestamp": "2026-03-20T17:56:51.289Z",
            "type": "event_msg",
            "payload": {"type": "user_message", "message": "Continue."},
        },
        {
            "timestamp": "2026-03-20T17:56:52.885Z",
            "type": "event_msg",
            "payload": {
                "type": "agent_message",
                "message": "Investigating the next card.",
                "phase": "commentary",
            },
        },
        {
            "timestamp": "2026-03-20T17:56:57.330Z",
            "type": "response_item",
            "payload": {
                "type": "function_call",
                "name": "exec_command",
                "arguments": '{"cmd":"git status --short","workdir":"/repo"}',
            },
        },
        {
            "timestamp": "2026-03-20T17:57:57.330Z",
            "type": "response_item",
            "payload": {
                "type": "function_call",
                "name": "exec_command",
                "arguments": (
                    '{"cmd":"cp file ../personal/x","sandbox_permissions":"require_escalated",'
                    '"justification":"Need to sync canonical docs"}'
                ),
            },
        },
        {
            "timestamp": "2026-03-20T17:58:57.330Z",
            "type": "event_msg",
            "payload": {
                "type": "task_complete",
                "turn_id": "turn-1",
                "last_agent_message": "Blocked on external docs sync.",
            },
        },
    ]
    transcript.write_text(
        "\n".join(json.dumps(item, ensure_ascii=False) for item in entries) + "\n",
        encoding="utf-8",
    )

    result = runner.invoke(
        app,
        ["log", operation_id, "--agent", "codex", "--codex-home", str(codex_home), "--limit", "10"],
    )

    assert result.exit_code == 0
    assert "# Codex log for operation op-cli-1" in result.stdout
    assert "Session session-1 started in /repo via openai" in result.stdout
    assert "[user] Continue." in result.stdout
    assert "[agent/commentary] Investigating the next card." in result.stdout
    assert "[tool] exec_command: git status --short" in result.stdout
    assert "[escalation] Escalation requested: Need to sync canonical docs" in result.stdout
    assert "[task] Task completed: Blocked on external docs sync." in result.stdout


def test_log_json_emits_machine_readable_codex_payload(tmp_path: Path, monkeypatch) -> None:
    operation_id = _seed_operation(tmp_path)
    monkeypatch.setenv("OPERATOR_DATA_DIR", str(tmp_path))
    codex_home = tmp_path / "codex-home"
    session_dir = codex_home / "sessions" / "2026" / "03" / "20"
    session_dir.mkdir(parents=True, exist_ok=True)
    transcript = session_dir / "rollout-2026-03-20T22-56-00-session-1.jsonl"
    transcript.write_text(
        '{"timestamp":"2026-03-20T17:56:51.289Z","type":"event_msg","payload":{"type":"user_message","message":"Continue."}}\n',
        encoding="utf-8",
    )

    result = runner.invoke(
        app,
        ["log", operation_id, "--agent", "codex", "--codex-home", str(codex_home), "--json"],
    )

    assert result.exit_code == 0
    assert '"operation_id": "op-cli-1"' in result.stdout
    assert '"session_id": "session-1"' in result.stdout
    assert '"agent": "codex"' in result.stdout
    assert '"category": "user"' in result.stdout


def test_log_prints_condensed_human_readable_claude_events(tmp_path: Path, monkeypatch) -> None:
    operation_id, log_path = _seed_claude_headless_operation(tmp_path)
    monkeypatch.setenv("OPERATOR_DATA_DIR", str(tmp_path))

    result = runner.invoke(app, ["log", operation_id, "--agent", "claude", "--limit", "10"])

    assert result.exit_code == 0
    assert "# Claude log for operation op-cli-claude-log" in result.stdout
    assert f"# file={log_path}" in result.stdout
    assert "[session] Session started in /repo | model=claude-sonnet-4-6 | tools=3" in (
        result.stdout
    )
    assert "[user] Inspect the repository." in result.stdout
    assert "[assistant] Reviewing the runtime seam." in result.stdout
    assert "[tool] Bash: git status --short" in result.stdout
    assert "[escalation] Escalation requested: Need to preserve the canonical vision copy." in (
        result.stdout
    )
    assert "[task] Task completed: Drafted the Claude log parser plan." in result.stdout


def test_log_json_emits_machine_readable_claude_payload(tmp_path: Path, monkeypatch) -> None:
    operation_id, _ = _seed_claude_headless_operation(tmp_path)
    monkeypatch.setenv("OPERATOR_DATA_DIR", str(tmp_path))

    result = runner.invoke(app, ["log", operation_id, "--agent", "claude", "--json"])

    assert result.exit_code == 0
    assert '"operation_id": "op-cli-claude-log"' in result.stdout
    assert '"session_id": "session-claude"' in result.stdout
    assert '"agent": "claude"' in result.stdout
    assert '"category": "assistant"' in result.stdout
    assert '"category": "escalation"' in result.stdout


def test_log_prints_condensed_human_readable_opencode_events(tmp_path: Path, monkeypatch) -> None:
    operation_id, log_path = _seed_opencode_headless_operation(tmp_path)
    monkeypatch.setenv("OPERATOR_DATA_DIR", str(tmp_path))

    result = runner.invoke(
        app,
        ["log", operation_id, "--agent", "opencode", "--limit", "10"],
    )

    assert result.exit_code == 0
    assert "# OpenCode log for operation op-cli-opencode-log" in result.stdout
    assert f"# file={log_path}" in result.stdout
    assert "[session] OpenCode session started." in result.stdout
    assert "[event] Inspecting the runtime seam." in result.stdout
    assert "[tool_use] exec_command: git status --short" in result.stdout
    assert "[event] Task completed: Drafted the OpenCode log parser plan." in result.stdout


def test_log_json_emits_machine_readable_opencode_payload(tmp_path: Path, monkeypatch) -> None:
    operation_id, _ = _seed_opencode_headless_operation(tmp_path)
    monkeypatch.setenv("OPERATOR_DATA_DIR", str(tmp_path))

    result = runner.invoke(app, ["log", operation_id, "--agent", "opencode", "--json"])

    assert result.exit_code == 0
    assert '"operation_id": "op-cli-opencode-log"' in result.stdout
    assert '"session_id": "session-opencode"' in result.stdout
    assert '"agent": "opencode"' in result.stdout
    assert '"category": "session"' in result.stdout


def test_session_command_prints_session_snapshot_for_task_short_id(
    tmp_path: Path, monkeypatch
) -> None:
    operation_id = _seed_operation(tmp_path)
    monkeypatch.setenv("OPERATOR_DATA_DIR", str(tmp_path))

    result = runner.invoke(app, ["session", operation_id, "--task", "task-1", "--once"])

    assert result.exit_code == 0
    assert "Session for Primary objective" in result.stdout
    assert "Operation: op-cli-1" in result.stdout
    assert "Task: task-1" in result.stdout
    assert "Session: session-1" in result.stdout
    assert "Now:" in result.stdout
    assert "Wait:" in result.stdout or "Attention:" in result.stdout
    assert "Latest:" in result.stdout
    assert "Recent:" in result.stdout
    assert "Event detail:" in result.stdout
    assert "Transcript: operator log op-cli-1 --agent codex" in result.stdout


def test_session_command_json_emits_machine_readable_payload(tmp_path: Path, monkeypatch) -> None:
    operation_id = _seed_operation(tmp_path)
    monkeypatch.setenv("OPERATOR_DATA_DIR", str(tmp_path))

    result = runner.invoke(app, ["session", operation_id, "--task", "task-1", "--json"])

    assert result.exit_code == 0
    assert '"operation_id": "op-cli-1"' in result.stdout
    assert '"task": {' in result.stdout
    assert '"session_id": "session-1"' in result.stdout
    assert '"session": {' in result.stdout
    assert '"session_brief": {' in result.stdout
    assert '"timeline_events":' in result.stdout
    assert '"transcript_hint": {' in result.stdout


def test_session_command_json_derives_task_payload_without_serializing_task_model(
    tmp_path: Path, monkeypatch
) -> None:
    operation_id = _seed_operation(tmp_path)
    monkeypatch.setenv("OPERATOR_DATA_DIR", str(tmp_path))

    def _fail_task_model_dump(self, *args, **kwargs):
        raise AssertionError("session command should not serialize TaskState directly")

    monkeypatch.setattr(TaskState, "model_dump", _fail_task_model_dump)

    result = runner.invoke(app, ["session", operation_id, "--task", "task-1", "--json"])

    assert result.exit_code == 0
    assert '"task": {' in result.stdout
    assert '"task_id": "task-1"' in result.stdout


def test_session_command_follow_once_prints_single_live_snapshot(
    tmp_path: Path, monkeypatch
) -> None:
    operation_id = _seed_operation(tmp_path)
    monkeypatch.setenv("OPERATOR_DATA_DIR", str(tmp_path))

    result = runner.invoke(app, ["session", operation_id, "--task", "task-1", "--follow", "--once"])

    assert result.exit_code == 0
    assert result.stdout.count("Session for Primary objective") == 1
    assert "Latest:" in result.stdout
    assert "Event detail:" not in result.stdout
    assert "Transcript: operator log op-cli-1 --agent codex --follow" in result.stdout
    assert result.stdout.count("  - iter=") <= 2


def test_session_command_follow_uses_live_redraw_in_tty(
    tmp_path: Path, monkeypatch
) -> None:
    operation_id = _seed_operation(tmp_path)
    monkeypatch.setenv("OPERATOR_DATA_DIR", str(tmp_path))

    captured: dict[str, object] = {}

    class _FakeLive:
        def __init__(self, renderable, *, console, refresh_per_second) -> None:
            captured["initial_renderable"] = renderable
            captured["refresh_per_second"] = refresh_per_second
            captured["console"] = console
            captured["updates"] = []

        def __enter__(self):
            captured["entered"] = True
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            captured["exited"] = True

        def update(self, renderable, *, refresh) -> None:
            captured["updates"].append((renderable, refresh))

    fake_tty = SimpleNamespace(isatty=lambda: True)
    monkeypatch.setattr(
        commands_operation_detail,
        "sys",
        SimpleNamespace(stdout=fake_tty, stdin=fake_tty),
    )
    monkeypatch.setattr(commands_operation_detail, "RichConsole", lambda: "console")
    monkeypatch.setattr(commands_operation_detail, "Live", _FakeLive)

    result = runner.invoke(app, ["session", operation_id, "--task", "task-1", "--follow", "--once"])

    assert result.exit_code == 0
    assert result.stdout == ""
    assert captured["entered"] is True
    assert captured["exited"] is True
    assert captured["refresh_per_second"] == 4
    assert "Session for Primary objective" in str(captured["initial_renderable"])
    assert "Transcript: operator log op-cli-1 --agent codex --follow" in str(
        captured["initial_renderable"]
    )
    assert captured["updates"] == []


def test_session_command_prints_selected_event_summary_when_present(
    tmp_path: Path, monkeypatch
) -> None:
    operation_id = _seed_operation(tmp_path)
    monkeypatch.setenv("OPERATOR_DATA_DIR", str(tmp_path))

    class _FakeDashboardQueries:
        async def load_payload(self, operation_id: str) -> dict[str, object]:
            return {
                "session_views": [
                    {
                        "task_id": "task-1",
                        "session": {
                            "session_id": "session-1",
                            "adapter_key": "codex_acp",
                            "status": "running",
                            "bound_task_ids": ["task-1"],
                        },
                        "session_brief": {
                            "now": "Running the task board migration",
                            "wait": "waiting for review",
                            "attention": "-",
                            "review": "Review the non-blocking note",
                            "latest_output": "agent completed: success",
                        },
                        "timeline": [
                            {
                                "event_type": "agent.invocation.completed",
                                "iteration": 1,
                                "task_id": "task-1",
                                "session_id": "session-1",
                                "summary": "[iter 1] agent completed: success",
                            }
                        ],
                        "selected_event": {
                            "event_type": "agent.invocation.completed",
                            "iteration": 1,
                            "task_id": "task-1",
                            "session_id": "session-1",
                            "timestamp": "2026-04-12T09:30:00+00:00",
                            "summary": "[iter 1] agent completed: success",
                            "detail": {
                                "status": "success",
                                "output_text": "Implemented the task board migration.",
                                "artifacts": [
                                    {
                                        "name": "task-board-plan.md",
                                        "kind": "note",
                                        "content": "Captured the migration notes.",
                                    }
                                ],
                            },
                        },
                        "transcript_hint": {"command": "operator log op-cli-1 --agent codex"},
                    }
                ]
            }

    monkeypatch.setattr(
        commands_operation_detail,
        "build_operation_dashboard_query_service",
        lambda settings, operation_id, codex_home: _FakeDashboardQueries(),
    )

    result = runner.invoke(app, ["session", operation_id, "--task", "task-1", "--once"])

    assert result.exit_code == 0
    assert "Attention: -" not in result.stdout
    assert "Wait: waiting for review" in result.stdout
    assert "time: 2026-04-12T09:30:00+00:00" in result.stdout
    assert "summary: [iter 1] agent completed: success" in result.stdout
    assert "status: success" in result.stdout
    assert "output: Implemented the task board migration." in result.stdout
    assert "artifacts:" in result.stdout
    assert "task-board-plan.md [note]: Captured the migration notes." in result.stdout
    assert "Review: Review the non-blocking note" in result.stdout


def test_session_command_prefers_attention_over_wait_when_attention_is_present(
    tmp_path: Path, monkeypatch
) -> None:
    operation_id = _seed_operation(tmp_path)
    monkeypatch.setenv("OPERATOR_DATA_DIR", str(tmp_path))

    class _FakeDashboardQueries:
        async def load_payload(self, operation_id: str) -> dict[str, object]:
            return {
                "session_views": [
                    {
                        "task_id": "task-1",
                        "session": {
                            "session_id": "session-1",
                            "adapter_key": "codex_acp",
                            "status": "running",
                            "bound_task_ids": ["task-1"],
                        },
                        "session_brief": {
                            "now": "Waiting on operator guidance",
                            "wait": "waiting for a policy answer",
                            "attention": "Need approval for the generated migration plan",
                            "latest_output": "Plan draft is ready for review",
                        },
                        "timeline": [],
                        "selected_event": None,
                        "transcript_hint": {"command": "operator log op-cli-1 --agent codex"},
                    }
                ]
            }

    monkeypatch.setattr(
        commands_operation_detail,
        "build_operation_dashboard_query_service",
        lambda settings, operation_id, codex_home: _FakeDashboardQueries(),
    )

    result = runner.invoke(app, ["session", operation_id, "--task", "task-1", "--once"])

    assert result.exit_code == 0
    assert "Attention: Need approval for the generated migration plan" in result.stdout
    assert "Wait:" not in result.stdout


def test_session_command_errors_when_task_has_no_linked_session(
    tmp_path: Path, monkeypatch
) -> None:
    operation_id = _seed_operation_without_linked_session(tmp_path)
    monkeypatch.setenv("OPERATOR_DATA_DIR", str(tmp_path))

    result = runner.invoke(app, ["session", operation_id, "--task", "task-nolink"])

    assert result.exit_code == 2
    assert "is not linked to a session" in result.stderr


def test_wakeups_default_shows_pending_and_claimed(tmp_path: Path, monkeypatch) -> None:
    operation_id = _seed_operation(tmp_path)
    monkeypatch.setenv("OPERATOR_DATA_DIR", str(tmp_path))

    result = runner.invoke(app, ["wakeups", operation_id])

    assert result.exit_code == 0
    assert "Pending wakeups:" in result.stdout
    assert "background_run.completed" in result.stdout


def test_debug_wakeups_json_derives_claimed_wakeups_without_serializing_wakeup_refs(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from agent_operator.domain.operation import WakeupRef

    operation_id = _seed_operation(tmp_path)
    monkeypatch.setenv("OPERATOR_DATA_DIR", str(tmp_path))
    store = FileOperationStore(tmp_path / "runs")
    persisted = anyio.run(store.load_operation, operation_id)
    assert persisted is not None
    persisted.pending_wakeups = [
        WakeupRef(
            event_id="evt-claimed-1",
            event_type="background_run.completed",
            session_id="session-1",
        )
    ]
    anyio.run(store.save_operation, persisted)

    def _fail_wakeup_model_dump(self, *args, **kwargs):
        raise AssertionError("debug wakeups should not serialize WakeupRef directly")

    monkeypatch.setattr(WakeupRef, "model_dump", _fail_wakeup_model_dump)

    result = runner.invoke(app, ["debug", "wakeups", operation_id, "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["operation_id"] == operation_id
    assert payload["claimed"][0]["event_type"] == "background_run.completed"
    assert payload["claimed"][0]["session_id"] == "session-1"


def test_debug_wakeups_json_derives_pending_wakeups_without_serializing_run_events(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from agent_operator.domain.events import RunEvent

    operation_id = _seed_operation(tmp_path)
    monkeypatch.setenv("OPERATOR_DATA_DIR", str(tmp_path))

    def _fail_run_event_model_dump(self, *args, **kwargs):
        raise AssertionError("debug wakeups should not serialize RunEvent directly")

    monkeypatch.setattr(RunEvent, "model_dump", _fail_run_event_model_dump)

    result = runner.invoke(app, ["debug", "wakeups", operation_id, "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["operation_id"] == operation_id
    assert payload["pending"][0]["event_type"] == "background_run.completed"
    assert payload["pending"][0]["session_id"] == "session-1"


def test_sessions_json_shows_sessions_and_background_runs(tmp_path: Path, monkeypatch) -> None:
    operation_id = _seed_operation(tmp_path)
    monkeypatch.setenv("OPERATOR_DATA_DIR", str(tmp_path))

    result = runner.invoke(app, ["sessions", operation_id, "--json"])

    assert result.exit_code == 0
    assert '"sessions"' in result.stdout
    assert '"background_runs"' in result.stdout
    assert '"run-1"' in result.stdout


def test_sessions_json_derives_live_progress_without_overlaying_session_models(
    tmp_path: Path,
    monkeypatch,
) -> None:
    import agent_operator.cli.helpers.rendering as rendering_helpers
    from agent_operator.domain.operation import ExecutionState

    operation_id = _seed_operation(tmp_path)
    monkeypatch.setenv("OPERATOR_DATA_DIR", str(tmp_path))
    store = FileOperationStore(tmp_path / "runs")
    persisted = anyio.run(store.load_operation, operation_id)
    assert persisted is not None
    persisted.sessions[0].current_execution_id = "run-1"
    anyio.run(store.save_operation, persisted)

    def _fail_execution_model_dump(self, *args, **kwargs):
        raise AssertionError("debug sessions should not serialize ExecutionState directly")

    monkeypatch.setattr(ExecutionState, "model_dump", _fail_execution_model_dump)

    class _FakeSupervisor:
        async def list_runs(self, requested_operation_id: str):
            assert requested_operation_id == operation_id
            return [
                ExecutionState.model_validate(
                    {
                        "execution_id": "run-1",
                        "operation_id": operation_id,
                        "adapter_key": "codex_acp",
                        "session_id": "session-1",
                        "observed_state": "running",
                        "started_at": "2026-04-14T12:00:00+00:00",
                        "progress": {
                            "state": "running",
                            "updated_at": "2026-04-14T12:05:00+00:00",
                            "last_event_at": "2026-04-14T12:06:00+00:00",
                            "message": "Applying the next repository slice.",
                            "partial_output": "Touched planning notes.",
                        },
                    }
                )
            ]

    monkeypatch.setattr(
        "agent_operator.cli.commands.debug.build_background_run_inspection_store",
        lambda settings: _FakeSupervisor(),
    )

    result = runner.invoke(app, ["debug", "sessions", operation_id, "--json"])

    assert result.exit_code == 0
    assert not hasattr(rendering_helpers, "overlay_live_background_progress")
    payload = json.loads(result.stdout)
    assert payload["background_runs"][0]["run_id"] == "run-1"
    assert payload["background_runs"][0]["status"] == "running"
    assert payload["sessions"][0]["session_id"] == "session-1"
    assert payload["sessions"][0]["live_progress_message"] == "Applying the next repository slice."
    assert payload["sessions"][0]["live_progress_partial_output"] == "Touched planning notes."
    assert payload["sessions"][0]["live_progress_updated_at"] == "2026-04-14T12:05:00+00:00"
    assert payload["sessions"][0]["live_progress_last_event_at"] == "2026-04-14T12:06:00+00:00"

    persisted = anyio.run(FileOperationStore(tmp_path / "runs").load_operation, operation_id)
    assert persisted is not None
    assert persisted.sessions[0].updated_at.isoformat() != "2026-04-14T12:05:00+00:00"
    assert persisted.sessions[0].last_event_at is None


def test_debug_namespace_surfaces_recovery_runtime_and_forensic_commands(
    tmp_path: Path,
    monkeypatch,
) -> None:
    operation_id = _seed_operation(tmp_path)
    monkeypatch.setenv("OPERATOR_DATA_DIR", str(tmp_path))

    wakeups_result = runner.invoke(app, ["debug", "wakeups", operation_id])
    sessions_result = runner.invoke(app, ["debug", "sessions", operation_id, "--json"])
    trace_result = runner.invoke(app, ["debug", "trace", operation_id, "--json"])

    assert wakeups_result.exit_code == 0
    assert "Pending wakeups:" in wakeups_result.stdout

    assert sessions_result.exit_code == 0
    assert '"sessions"' in sessions_result.stdout
    assert '"background_runs"' in sessions_result.stdout

    assert trace_result.exit_code == 0
    assert '"trace_records"' in trace_result.stdout
    assert '"decision_memos"' in trace_result.stdout
    assert '"events"' in trace_result.stdout


def test_debug_event_append_dry_run_previews_v2_repair(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("OPERATOR_DATA_DIR", str(tmp_path))
    checkpoint = OperationCheckpoint.initial("op-debug-repair")
    checkpoint.objective = ObjectiveState(objective="Repair canonical state")
    checkpoint.created_at = datetime(2026, 4, 24, tzinfo=UTC)
    checkpoint.updated_at = checkpoint.created_at
    checkpoint_record = OperationCheckpointRecord(
        operation_id="op-debug-repair",
        checkpoint_payload=checkpoint.model_dump(mode="json"),
        last_applied_sequence=0,
        checkpoint_format_version=1,
    )
    checkpoint_path = tmp_path / "operation_checkpoints" / "op-debug-repair.json"
    checkpoint_path.parent.mkdir(parents=True)
    checkpoint_path.write_text(
        json.dumps({**checkpoint_record.model_dump(mode="json"), "epoch_id": 0}, indent=2),
        encoding="utf-8",
    )
    event_dir = tmp_path / "operation_events"
    event_dir.mkdir()
    (event_dir / "op-debug-repair.jsonl").write_text("", encoding="utf-8")

    result = runner.invoke(
        app,
        [
            "debug",
            "event",
            "append",
            "op-debug",
            "--event-type",
            "operation.status.changed",
            "--payload-json",
            '{"status":"cancelled","final_summary":"Manual repair."}',
            "--json",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["dry_run"] is True
    assert payload["operation_id"] == "op-debug-repair"
    assert payload["projected_status"] == "cancelled"


def test_debug_event_append_applies_event_and_updates_checkpoint(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("OPERATOR_DATA_DIR", str(tmp_path))
    checkpoint = OperationCheckpoint.initial("op-debug-repair-apply")
    checkpoint.objective = ObjectiveState(objective="Repair canonical state")
    checkpoint.created_at = datetime(2026, 4, 24, tzinfo=UTC)
    checkpoint.updated_at = checkpoint.created_at
    checkpoint_record = OperationCheckpointRecord(
        operation_id="op-debug-repair-apply",
        checkpoint_payload=checkpoint.model_dump(mode="json"),
        last_applied_sequence=0,
        checkpoint_format_version=1,
    )
    checkpoint_path = tmp_path / "operation_checkpoints" / "op-debug-repair-apply.json"
    checkpoint_path.parent.mkdir(parents=True)
    checkpoint_path.write_text(
        json.dumps({**checkpoint_record.model_dump(mode="json"), "epoch_id": 0}, indent=2),
        encoding="utf-8",
    )
    event_dir = tmp_path / "operation_events"
    event_dir.mkdir()
    (event_dir / "op-debug-repair-apply.jsonl").write_text("", encoding="utf-8")

    result = runner.invoke(
        app,
        [
            "debug",
            "event",
            "append",
            "op-debug-repair-apply",
            "--event-type",
            "operation.status.changed",
            "--payload-json",
            '{"status":"cancelled","final_summary":"Manual repair."}',
            "--reason",
            "manual test repair",
            "--yes",
            "--json",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["dry_run"] is False
    assert payload["projected_status"] == "cancelled"
    assert payload["stored_events"][0]["metadata"]["repair_reason"] == "manual test repair"

    status_result = runner.invoke(app, ["status", "op-debug-repair-apply", "--json"])
    assert status_result.exit_code == 0
    status_payload = json.loads(status_result.stdout)
    assert status_payload["status"] == "cancelled"


def test_debug_event_append_rejects_invalid_json_payload(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("OPERATOR_DATA_DIR", str(tmp_path))
    result = runner.invoke(
        app,
        [
            "debug",
            "event",
            "append",
            "missing-op",
            "--event-type",
            "operation.status.changed",
            "--payload-json",
            "{not-json}",
        ],
    )

    assert result.exit_code != 0
    assert "Invalid JSON payload" in result.output


def test_debug_event_append_requires_reason_for_non_dry_run(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("OPERATOR_DATA_DIR", str(tmp_path))
    checkpoint = OperationCheckpoint.initial("op-debug-reason")
    checkpoint.objective = ObjectiveState(objective="Repair canonical state")
    checkpoint_record = OperationCheckpointRecord(
        operation_id="op-debug-reason",
        checkpoint_payload=checkpoint.model_dump(mode="json"),
        last_applied_sequence=0,
        checkpoint_format_version=1,
    )
    checkpoint_path = tmp_path / "operation_checkpoints" / "op-debug-reason.json"
    checkpoint_path.parent.mkdir(parents=True)
    checkpoint_path.write_text(
        json.dumps({**checkpoint_record.model_dump(mode="json"), "epoch_id": 0}, indent=2),
        encoding="utf-8",
    )
    event_dir = tmp_path / "operation_events"
    event_dir.mkdir()
    (event_dir / "op-debug-reason.jsonl").write_text("", encoding="utf-8")

    result = runner.invoke(
        app,
        [
            "debug",
            "event",
            "append",
            "op-debug-reason",
            "--event-type",
            "operation.status.changed",
            "--payload-json",
            '{"status":"cancelled"}',
            "--yes",
        ],
    )

    assert result.exit_code != 0
    assert "--reason is required" in result.output


def test_debug_event_append_rejects_unsupported_event_type(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("OPERATOR_DATA_DIR", str(tmp_path))
    checkpoint = OperationCheckpoint.initial("op-debug-unsupported")
    checkpoint.objective = ObjectiveState(objective="Repair canonical state")
    checkpoint_record = OperationCheckpointRecord(
        operation_id="op-debug-unsupported",
        checkpoint_payload=checkpoint.model_dump(mode="json"),
        last_applied_sequence=0,
        checkpoint_format_version=1,
    )
    checkpoint_path = tmp_path / "operation_checkpoints" / "op-debug-unsupported.json"
    checkpoint_path.parent.mkdir(parents=True)
    checkpoint_path.write_text(
        json.dumps({**checkpoint_record.model_dump(mode="json"), "epoch_id": 0}, indent=2),
        encoding="utf-8",
    )
    event_dir = tmp_path / "operation_events"
    event_dir.mkdir()
    (event_dir / "op-debug-unsupported.jsonl").write_text("", encoding="utf-8")

    result = runner.invoke(
        app,
        [
            "debug",
            "event",
            "append",
            "op-debug-unsupported",
            "--event-type",
            "operation.created",
            "--payload-json",
            '{"status":"running"}',
            "--json",
        ],
    )

    assert result.exit_code != 0
    assert "Unsupported repair event type" in result.output


def test_pause_command_enqueues_pause_operator(tmp_path: Path, monkeypatch) -> None:
    operation_id = _seed_operation(tmp_path)
    monkeypatch.setenv("OPERATOR_DATA_DIR", str(tmp_path))

    result = runner.invoke(app, ["pause", operation_id])

    assert result.exit_code == 0
    assert "enqueued: pause_operator" in result.stdout
    record = _read_control_intent(tmp_path)
    assert record.operation_id == operation_id
    assert record.command is not None
    assert record.command.command_type is OperationCommandType.PAUSE_OPERATOR


def test_status_command_prints_human_readable_summary(tmp_path: Path, monkeypatch) -> None:
    operation_id = _seed_operation(tmp_path)
    monkeypatch.setenv("OPERATOR_DATA_DIR", str(tmp_path))

    result = runner.invoke(app, ["status", operation_id])

    assert result.exit_code == 0
    assert "COMPLETED · iter 0/100" in result.stdout
    assert "Operation\n- op-cli-1 · Test objective" in result.stdout
    assert "Now\n- Completed successfully." in result.stdout
    assert "Attention\n- none" in result.stdout
    assert "Progress\n- Done: Completed successfully." in result.stdout


def test_status_brief_prints_single_line_summary(tmp_path: Path, monkeypatch) -> None:
    operation_id = _seed_operation(tmp_path)
    monkeypatch.setenv("OPERATOR_DATA_DIR", str(tmp_path))

    result = runner.invoke(app, ["status", operation_id, "--brief"])

    assert result.exit_code == 0
    assert f"{operation_id} COMPLETED" in result.stdout
    assert "iter=" in result.stdout


def test_status_shows_action_line_when_attention_is_open(tmp_path: Path, monkeypatch) -> None:
    operation_id, attention_id = _seed_blocked_attention_operation(tmp_path)
    monkeypatch.setenv("OPERATOR_DATA_DIR", str(tmp_path))

    result = runner.invoke(app, ["status", operation_id])

    assert result.exit_code == 0
    assert "Action" in result.stdout
    assert f"- operator answer {operation_id} {attention_id} --text '...'" in result.stdout


def test_status_open_attention_section_uses_positional_answer_syntax(
    tmp_path: Path, monkeypatch
) -> None:
    operation_id, attention_id = _seed_blocked_attention_operation(tmp_path)
    monkeypatch.setenv("OPERATOR_DATA_DIR", str(tmp_path))

    result = runner.invoke(app, ["status", operation_id])

    assert result.exit_code == 0
    assert "Attention" in result.stdout
    assert "[!!1] [question] Clarification required" in result.stdout
    assert f"- operator answer {operation_id} {attention_id} --text '...'" in result.stdout
    assert "--attention" not in result.stdout


def test_cancel_requires_confirmation_by_default(tmp_path: Path, monkeypatch) -> None:
    operation_id = _seed_operation(tmp_path)
    monkeypatch.setenv("OPERATOR_DATA_DIR", str(tmp_path))

    class FakeService:
        async def cancel(self, operation_id: str, *, session_id=None, run_id=None):
            return OperationOutcome(
                operation_id=operation_id,
                status=OperationStatus.CANCELLED,
                summary="Cancelled operation.",
            )

    monkeypatch.setattr(
        "agent_operator.cli.main.build_service",
        lambda settings, event_sink=None: FakeService(),
    )

    result = runner.invoke(app, ["cancel", operation_id], input="n\n")

    assert result.exit_code == 0
    assert "Cancel operation" in result.stdout
    assert "cancelled" in result.stdout


def test_cancel_yes_skips_confirmation(tmp_path: Path, monkeypatch) -> None:
    operation_id = _seed_operation(tmp_path)
    monkeypatch.setenv("OPERATOR_DATA_DIR", str(tmp_path))

    class FakeService:
        async def cancel(self, operation_id: str, *, session_id=None, run_id=None):
            return OperationOutcome(
                operation_id=operation_id,
                status=OperationStatus.CANCELLED,
                summary="Cancelled operation.",
            )

    monkeypatch.setattr(
        "agent_operator.cli.main.build_service",
        lambda settings, event_sink=None: FakeService(),
    )

    result = runner.invoke(app, ["cancel", operation_id, "--yes"])

    assert result.exit_code == 3
    assert "cancelled: Cancelled operation." in result.stdout


def test_cancel_json_emits_machine_readable_payload(tmp_path: Path, monkeypatch) -> None:
    operation_id = _seed_operation(tmp_path)
    monkeypatch.setenv("OPERATOR_DATA_DIR", str(tmp_path))

    class FakeService:
        async def cancel(self, operation_id: str, *, session_id=None, run_id=None):
            return OperationOutcome(
                operation_id=operation_id,
                status=OperationStatus.CANCELLED,
                summary="Cancelled operation.",
                metadata={"source": "test"},
            )

    monkeypatch.setattr(
        "agent_operator.cli.main.build_service",
        lambda settings, event_sink=None: FakeService(),
    )

    result = runner.invoke(app, ["cancel", operation_id, "--yes", "--json"])

    assert result.exit_code == 3
    payload = json.loads(result.stdout)
    assert payload["operation_id"] == operation_id
    assert payload["status"] == "cancelled"
    assert payload["metadata"]["source"] == "test"


def test_cancel_run_scope_json_returns_requested_status_and_zero_exit_code(
    tmp_path: Path, monkeypatch
) -> None:
    operation_id = _seed_operation(tmp_path)
    monkeypatch.setenv("OPERATOR_DATA_DIR", str(tmp_path))

    class FakeService:
        async def cancel(self, operation_id: str, *, session_id=None, run_id=None):
            assert session_id is None
            assert run_id == "run-1"
            return OperationOutcome(
                operation_id=operation_id,
                status=OperationStatus.RUNNING,
                summary="Cancellation requested.",
            )

    monkeypatch.setattr(
        "agent_operator.cli.main.build_service",
        lambda settings, event_sink=None: FakeService(),
    )

    result = runner.invoke(app, ["cancel", operation_id, "--run", "run-1", "--yes", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["operation_id"] == operation_id
    assert payload["status"] == "running"
    assert payload["summary"] == "Cancellation requested."


def test_cancel_session_scope_success_prints_requested_status(tmp_path: Path, monkeypatch) -> None:
    operation_id = _seed_operation(tmp_path)
    monkeypatch.setenv("OPERATOR_DATA_DIR", str(tmp_path))

    class FakeService:
        async def cancel(self, operation_id: str, *, session_id=None, run_id=None):
            assert session_id == "session-1"
            assert run_id is None
            return OperationOutcome(
                operation_id=operation_id,
                status=OperationStatus.RUNNING,
                summary="Cancellation requested.",
            )

    monkeypatch.setattr(
        "agent_operator.cli.main.build_service",
        lambda settings, event_sink=None: FakeService(),
    )

    result = runner.invoke(app, ["cancel", operation_id, "--session", "session-1", "--yes"])

    assert result.exit_code == 0
    assert "running: Cancellation requested." in result.stdout


def test_message_command_enqueues_operator_message(tmp_path: Path, monkeypatch) -> None:
    operation_id = _seed_operation(tmp_path)
    monkeypatch.setenv("OPERATOR_DATA_DIR", str(tmp_path))

    result = runner.invoke(app, ["message", operation_id, "Use swarm before deciding."])

    assert result.exit_code == 0
    record = _read_control_intent(tmp_path)
    assert record.command is not None
    assert record.command.command_type is OperationCommandType.INJECT_OPERATOR_MESSAGE
    assert record.command.payload["text"] == "Use swarm before deciding."


def test_ask_command_answers_question(tmp_path: Path, monkeypatch) -> None:
    operation_id = _seed_operation(tmp_path)
    monkeypatch.setenv("OPERATOR_DATA_DIR", str(tmp_path))

    class FakeBrain:
        async def answer_question(self, state: OperationState, question: str) -> str:
            assert state.operation_id == operation_id
            assert question == "what is the current status?"
            return "The operation is completed."

    class FakeService:
        async def answer_question(self, operation_id_: str, question: str) -> str:
            assert operation_id_ == operation_id
            return await FakeBrain().answer_question(
                OperationState(
                    operation_id=operation_id_,
                    goal=OperationGoal(objective="Test objective"),
                    status=OperationStatus.COMPLETED,
                    **state_settings(),
                ),
                question,
            )

    monkeypatch.setattr(
        "agent_operator.cli.main.build_service",
        lambda settings, event_sink=None: FakeService(),
    )

    result = runner.invoke(app, ["ask", "last", "what is the current status?"])

    assert result.exit_code == 0
    assert "Question: what is the current status?" in result.stdout
    assert "The operation is completed." in result.stdout


def test_ask_command_json_emits_machine_readable_payload(tmp_path: Path, monkeypatch) -> None:
    operation_id = _seed_operation(tmp_path)
    monkeypatch.setenv("OPERATOR_DATA_DIR", str(tmp_path))

    class FakeBrain:
        async def answer_question(self, state: OperationState, question: str) -> str:
            return f"{state.status.value}: {question}"

    class FakeService:
        async def answer_question(self, operation_id_: str, question: str) -> str:
            assert operation_id_ == operation_id
            return await FakeBrain().answer_question(
                OperationState(
                    operation_id=operation_id_,
                    goal=OperationGoal(objective="Test objective"),
                    status=OperationStatus.COMPLETED,
                    **state_settings(),
                ),
                question,
            )

    monkeypatch.setattr(
        "agent_operator.cli.main.build_service",
        lambda settings, event_sink=None: FakeService(),
    )

    result = runner.invoke(app, ["ask", operation_id, "what happened?", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload == {
        "question": "what happened?",
        "answer": "completed: what happened?",
    }


def test_ask_command_missing_operation_exits_with_internal_error_code(monkeypatch) -> None:
    monkeypatch.setenv("OPERATOR_DATA_DIR", "/tmp/does-not-exist-for-ask-test")

    result = runner.invoke(app, ["ask", "missing-op", "what happened?"])

    assert result.exit_code == 4
    assert "was not found" in result.stderr


def test_converse_command_answers_question_for_operation(tmp_path: Path, monkeypatch) -> None:
    operation_id = _seed_operation(tmp_path)
    monkeypatch.setenv("OPERATOR_DATA_DIR", str(tmp_path))

    class FakeBrain:
        async def converse(self, prompt: str) -> SimpleNamespace:
            assert "Conversation mode: operation" in prompt
            assert f"Operation id: {operation_id}" in prompt
            assert "Context level: brief" in prompt
            assert "User message:\nWhat is the current status?" in prompt
            return SimpleNamespace(answer="The operation is completed.", proposed_command=None)

    monkeypatch.setattr(
        "agent_operator.cli.workflows.control.build_brain",
        lambda settings: FakeBrain(),
    )

    result = runner.invoke(app, ["converse", "last"], input="What is the current status?\nquit\n")

    assert result.exit_code == 0
    assert f"Operator › {operation_id}" in result.stdout
    assert "The operation is completed." in result.stdout


def test_converse_command_full_context_derives_recent_events_and_iteration_payloads(
    tmp_path: Path, monkeypatch
) -> None:
    operation_id = _seed_operation(tmp_path)
    monkeypatch.setenv("OPERATOR_DATA_DIR", str(tmp_path))
    store = FileOperationStore(tmp_path / "runs")
    persisted = anyio.run(store.load_operation, operation_id)
    assert persisted is not None
    persisted.iterations = [
        IterationState(
            index=1,
            task_id="task-1",
            decision=BrainDecision(
                action_type=BrainActionType.START_AGENT,
                target_agent="codex_acp",
                instruction="Inspect the working tree.",
                rationale="Need current repository truth.",
                new_features=[
                    FeatureDraft(
                        title="Repository audit",
                        acceptance_criteria="Capture the current working-tree state.",
                        notes=["Include staged and unstaged changes."],
                    )
                ],
                feature_updates=[
                    FeaturePatch(
                        feature_id="feature-1",
                        title="Repository audit",
                        acceptance_criteria="Record the audit in the operation context.",
                        status=FeatureStatus.IN_PROGRESS,
                        append_notes=["Audit started from converse full-context mode."],
                    )
                ],
                task_updates=[
                    TaskPatch(
                        task_id="task-1",
                        title="Inspect the repository",
                        goal="Capture the current repository state.",
                        definition_of_done="The prompt shows the current repository truth.",
                        brain_priority=60,
                        assigned_agent="codex_acp",
                        linked_session_id="session-1",
                        session_policy=SessionPolicy.PREFER_REUSE,
                        append_notes=["Started through full-context converse."],
                        add_memory_refs=["memory-1"],
                        add_artifact_refs=["artifact-1"],
                        add_dependencies=["task-0"],
                        remove_dependencies=["task-old"],
                        dependency_removal_reason="Replaced by the newer audit prerequisite.",
                    )
                ],
            ),
            session=AgentSessionHandle(
                adapter_key="codex_acp",
                session_id="session-1",
                session_name="repo-audit",
                display_name="Repo Audit",
            ),
            result=AgentResult(
                session_id="session-1",
                status=AgentResultStatus.SUCCESS,
                output_text="Inspected repository state.",
            ),
            turn_summary=AgentTurnSummary(
                declared_goal="Inspect the repository",
                actual_work_done="Checked the tracked files.",
                state_delta="No durable state changes.",
                verification_status="Not verified.",
                recommended_next_step="Review the changed files.",
            ),
            notes=["Captured the current repository state."],
        )
    ]
    anyio.run(store.save_operation, persisted)

    def _fail_run_event_model_dump(self, *args, **kwargs):
        raise AssertionError("converse full-context prompt should not serialize RunEvent directly")

    def _fail_decision_model_dump(self, *args, **kwargs):
        raise AssertionError(
            "converse full-context prompt should not serialize BrainDecision directly"
        )

    def _fail_session_model_dump(self, *args, **kwargs):
        raise AssertionError(
            "converse full-context prompt should not serialize AgentSessionHandle directly"
        )

    def _fail_result_model_dump(self, *args, **kwargs):
        raise AssertionError(
            "converse full-context prompt should not serialize AgentResult directly"
        )

    def _fail_turn_summary_model_dump(self, *args, **kwargs):
        raise AssertionError(
            "converse full-context prompt should not serialize AgentTurnSummary directly"
        )

    monkeypatch.setattr(RunEvent, "model_dump", _fail_run_event_model_dump)
    monkeypatch.setattr(BrainDecision, "model_dump", _fail_decision_model_dump)
    monkeypatch.setattr(AgentSessionHandle, "model_dump", _fail_session_model_dump)
    monkeypatch.setattr(AgentResult, "model_dump", _fail_result_model_dump)
    monkeypatch.setattr(AgentTurnSummary, "model_dump", _fail_turn_summary_model_dump)

    class _FakeEventSink:
        def iter_events(self, requested_operation_id: str):
            assert requested_operation_id == operation_id
            return [
                RunEvent(
                    event_id="evt-converse-1",
                    event_type="operation.note",
                    kind=RunEventKind.TRACE,
                    category="trace",
                    operation_id=operation_id,
                    iteration=1,
                    task_id="task-1",
                    session_id="session-1",
                    payload={"summary": "Inspected the repository state."},
                )
            ]

    class FakeBrain:
        async def converse(self, prompt: str) -> SimpleNamespace:
            assert "Context level: full" in prompt
            assert '"event_id": "evt-converse-1"' in prompt
            assert '"action_type": "start_agent"' in prompt
            assert '"session_id": "session-1"' in prompt
            assert '"acceptance_criteria": "Capture the current working-tree state."' in prompt
            assert '"append_notes": ["Started through full-context converse."]' in prompt
            assert '"add_memory_refs": ["memory-1"]' in prompt
            assert '"status": "success"' in prompt
            assert '"declared_goal": "Inspect the repository"' in prompt
            return SimpleNamespace(
                answer="The operation inspected the repository.",
                proposed_command=None,
            )

    monkeypatch.setattr(
        "agent_operator.cli.workflows.control.build_brain",
        lambda settings: FakeBrain(),
    )
    monkeypatch.setattr(
        "agent_operator.cli.workflows.control.build_event_sink",
        lambda settings, requested_operation_id: _FakeEventSink(),
    )

    result = runner.invoke(
        app,
        ["converse", operation_id, "--context", "full"],
        input="What changed?\nquit\n",
    )

    assert result.exit_code == 0
    assert "The operation inspected the repository." in result.stdout


def test_converse_command_executes_proposed_write_on_yes(tmp_path: Path, monkeypatch) -> None:
    operation_id, attention_id = _seed_blocked_attention_operation(tmp_path)
    monkeypatch.setenv("OPERATOR_DATA_DIR", str(tmp_path))
    captured: dict[str, object] = {}

    class FakeBrain:
        async def converse(self, prompt: str) -> SimpleNamespace:
            assert "Conversation mode: operation" in prompt
            return SimpleNamespace(
                answer="I can answer the blocking attention for you.",
                proposed_command=(
                    f'operator answer {operation_id} {attention_id} --text "use a branch"'
                ),
            )

    async def fake_answer_async(
        operation_id_: str,
        attention_id_: str | None,
        text: str,
        promote: bool,
        policy_title: str | None,
        policy_text: str | None,
        policy_category: str,
        policy_objective_keyword: list[str] | None,
        policy_task_keyword: list[str] | None,
        policy_agent: list[str] | None,
        policy_run_mode: list[RunMode] | None,
        policy_involvement: list[InvolvementLevel] | None,
        policy_rationale: str | None,
        json_mode: bool,
    ) -> None:
        captured["operation_id"] = operation_id_
        captured["attention_id"] = attention_id_
        captured["text"] = text

    monkeypatch.setattr(
        "agent_operator.cli.workflows.control.build_brain",
        lambda settings: FakeBrain(),
    )
    monkeypatch.setattr("agent_operator.cli.workflows.control.answer_async", fake_answer_async)

    result = runner.invoke(app, ["converse", operation_id], input="Use a branch\ny\nquit\n")

    assert result.exit_code == 0
    assert (
        f'→ Proposed action: operator answer {operation_id} {attention_id} --text "use a branch"'
        in result.stdout
    )
    assert captured == {
        "operation_id": operation_id,
        "attention_id": attention_id,
        "text": "use a branch",
    }


def test_converse_command_declined_write_continues_session(tmp_path: Path, monkeypatch) -> None:
    operation_id, attention_id = _seed_blocked_attention_operation(tmp_path)
    monkeypatch.setenv("OPERATOR_DATA_DIR", str(tmp_path))
    call_count = {"count": 0}
    executed: list[str] = []

    class FakeBrain:
        async def converse(self, prompt: str) -> SimpleNamespace:
            call_count["count"] += 1
            if call_count["count"] == 1:
                return SimpleNamespace(
                    answer="I can answer the blocking attention for you.",
                    proposed_command=(
                        f'operator answer {operation_id} {attention_id} --text "use a branch"'
                    ),
                )
            assert "Proposed command declined." in prompt
            return SimpleNamespace(
                answer="The operation is still waiting on that policy decision.",
                proposed_command=None,
            )

    async def fake_answer_async(*args, **kwargs) -> None:
        executed.append("called")

    monkeypatch.setattr(
        "agent_operator.cli.workflows.control.build_brain",
        lambda settings: FakeBrain(),
    )
    monkeypatch.setattr("agent_operator.cli.workflows.control.answer_async", fake_answer_async)

    result = runner.invoke(
        app,
        ["converse", operation_id],
        input="Use a branch\nn\nWhat is blocked now?\nquit\n",
    )

    assert result.exit_code == 0
    assert executed == []
    assert "The operation is still waiting on that policy decision." in result.stdout


def test_converse_command_loads_fleet_context_when_operation_is_omitted(
    tmp_path: Path, monkeypatch
) -> None:
    store = FileOperationStore(tmp_path / "runs")
    operations = [
        OperationState(
            operation_id="op-fleet-1",
            goal=OperationGoal(objective="Ship alpha"),
            status=OperationStatus.RUNNING,
            **state_settings(),
        ),
        OperationState(
            operation_id="op-fleet-2",
            goal=OperationGoal(
                objective="Investigate failure",
                metadata={"project_profile_name": "femtobot"},
            ),
            status=OperationStatus.NEEDS_HUMAN,
            **state_settings(),
        ),
    ]
    for operation in operations:
        anyio.run(store.save_operation, operation)
    monkeypatch.setenv("OPERATOR_DATA_DIR", str(tmp_path))

    class FakeBrain:
        async def converse(self, prompt: str) -> SimpleNamespace:
            assert "Conversation mode: fleet" in prompt
            assert '"operation_id": "op-fleet-1"' in prompt
            assert '"operation_id": "op-fleet-2"' in prompt
            return SimpleNamespace(
                answer="op-fleet-2 is the blocked operation.",
                proposed_command=None,
            )

    monkeypatch.setattr(
        "agent_operator.cli.workflows.control.build_brain",
        lambda settings: FakeBrain(),
    )

    result = runner.invoke(app, ["converse"], input="Which operation is blocked?\nquit\n")

    assert result.exit_code == 0
    assert "Operator › fleet" in result.stdout
    assert "op-fleet-2 is the blocked operation." in result.stdout


def test_attention_command_shows_attention_requests(tmp_path: Path, monkeypatch) -> None:
    operation_id, attention_id = _seed_blocked_attention_operation(tmp_path)
    monkeypatch.setenv("OPERATOR_DATA_DIR", str(tmp_path))

    result = runner.invoke(app, ["attention", operation_id])

    assert result.exit_code == 0
    assert "Attention requests:" in result.stdout
    assert attention_id in result.stdout
    assert "Clarification required" in result.stdout


def test_attention_command_shows_context_and_options(tmp_path: Path, monkeypatch) -> None:
    operation_id = "op-cli-policy-gap"
    store = FileOperationStore(tmp_path / "runs")
    state = OperationState(
        operation_id=operation_id,
        goal=OperationGoal(objective="Set the testing workflow"),
        **state_settings(),
        attention_requests=[
            AttentionRequest(
                attention_id="attention-policy-gap",
                operation_id=operation_id,
                attention_type=AttentionType.POLICY_GAP,
                title="Testing policy is missing",
                question="Should manual-only checks always be recorded?",
                context_brief="No active testing policy covers manual-only verification.",
                suggested_options=[
                    "Always record them in MANUAL_TESTING_REQUIRED.md.",
                    "Only record them for release-facing work.",
                ],
            )
        ],
    )
    anyio.run(store.save_operation, state)
    monkeypatch.setenv("OPERATOR_DATA_DIR", str(tmp_path))

    result = runner.invoke(app, ["attention", operation_id])

    assert result.exit_code == 0
    assert "type=policy_gap" in result.stdout
    assert "context: No active testing policy covers manual-only verification." in result.stdout
    assert "options: Always record them in MANUAL_TESTING_REQUIRED.md." in result.stdout


def test_attention_command_shows_novel_strategic_fork_type(tmp_path: Path, monkeypatch) -> None:
    operation_id = "op-cli-fork"
    store = FileOperationStore(tmp_path / "runs")
    state = OperationState(
        operation_id=operation_id,
        goal=OperationGoal(objective="Choose a release strategy"),
        **state_settings(),
        attention_requests=[
            AttentionRequest(
                attention_id="attention-fork",
                operation_id=operation_id,
                attention_type=AttentionType.NOVEL_STRATEGIC_FORK,
                title="Release strategy fork needs a decision",
                question="Should the repo adopt staged releases or continuous deployment?",
                context_brief="Current project policy does not set a default release strategy.",
                suggested_options=[
                    "Adopt staged releases with explicit cut windows.",
                    "Keep continuous deployment with stronger rollback guardrails.",
                ],
            )
        ],
    )
    anyio.run(store.save_operation, state)
    monkeypatch.setenv("OPERATOR_DATA_DIR", str(tmp_path))

    result = runner.invoke(app, ["attention", operation_id])

    assert result.exit_code == 0
    assert "type=novel_strategic_fork" in result.stdout
    assert "Release strategy fork needs a decision" in result.stdout
    assert "context: Current project policy does not set a default release strategy." in (
        result.stdout
    )


def test_attention_command_json_emits_attention_payload(tmp_path: Path, monkeypatch) -> None:
    operation_id, attention_id = _seed_blocked_attention_operation(tmp_path)
    monkeypatch.setenv("OPERATOR_DATA_DIR", str(tmp_path))

    result = runner.invoke(app, ["attention", operation_id, "--json"])

    assert result.exit_code == 0
    assert f'"attention_id": "{attention_id}"' in result.stdout
    assert '"attention_requests"' in result.stdout


def test_attention_command_json_derives_requests_without_serializing_models(
    tmp_path: Path, monkeypatch
) -> None:
    operation_id, attention_id = _seed_blocked_attention_operation(tmp_path)
    monkeypatch.setenv("OPERATOR_DATA_DIR", str(tmp_path))

    def _fail_attention_model_dump(self, *args, **kwargs):
        raise AssertionError("attention command should not serialize AttentionRequest directly")

    monkeypatch.setattr(AttentionRequest, "model_dump", _fail_attention_model_dump)

    result = runner.invoke(app, ["attention", operation_id, "--json"])

    assert result.exit_code == 0
    assert f'"attention_id": "{attention_id}"' in result.stdout
    assert '"attention_requests"' in result.stdout


def test_answer_command_enqueues_attention_answer(tmp_path: Path, monkeypatch) -> None:
    operation_id, attention_id = _seed_blocked_attention_operation(tmp_path)
    monkeypatch.setenv("OPERATOR_DATA_DIR", str(tmp_path))

    class FakeService:
        async def resume(self, operation_id: str, options=None) -> OperationOutcome:
            return OperationOutcome(
                operation_id=operation_id,
                status=OperationStatus.RUNNING,
                summary="Resumed after attention answer.",
            )

    monkeypatch.setattr(
        "agent_operator.cli.main.build_service",
        lambda settings, event_sink=None: FakeService(),
    )

    result = runner.invoke(
        app,
        ["answer", operation_id, attention_id, "--text", "Use staging."],
    )

    assert result.exit_code == 0
    record = _read_control_intent(tmp_path)
    assert record.command is not None
    assert record.command.command_type is OperationCommandType.ANSWER_ATTENTION_REQUEST
    assert record.command.target_scope is CommandTargetScope.ATTENTION_REQUEST
    assert record.command.target_id == attention_id
    assert record.command.payload["text"] == "Use staging."


def test_answer_command_json_emits_machine_readable_payload(tmp_path: Path, monkeypatch) -> None:
    operation_id, attention_id = _seed_blocked_attention_operation(tmp_path)
    monkeypatch.setenv("OPERATOR_DATA_DIR", str(tmp_path))

    class FakeService:
        async def resume(self, operation_id: str, options=None) -> OperationOutcome:
            return OperationOutcome(
                operation_id=operation_id,
                status=OperationStatus.RUNNING,
                summary="Resumed after attention answer.",
            )

    monkeypatch.setattr(
        "agent_operator.cli.main.build_service",
        lambda settings, event_sink=None: FakeService(),
    )

    result = runner.invoke(
        app,
        ["answer", operation_id, attention_id, "--text", "Use staging.", "--json"],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["operation_id"] == operation_id
    assert payload["answer_command"]["target_id"] == attention_id
    assert payload["outcome"]["status"] == "running"


def test_answer_command_can_enqueue_policy_promotion(tmp_path: Path, monkeypatch) -> None:
    operation_id, attention_id = _seed_blocked_attention_operation(tmp_path)
    monkeypatch.setenv("OPERATOR_DATA_DIR", str(tmp_path))

    class FakeService:
        async def resume(self, operation_id: str, options=None) -> OperationOutcome:
            return OperationOutcome(
                operation_id=operation_id,
                status=OperationStatus.RUNNING,
                summary="Resumed after attention answer.",
            )

    monkeypatch.setattr(
        "agent_operator.cli.main.build_service",
        lambda settings, event_sink=None: FakeService(),
    )

    result = runner.invoke(
        app,
        [
            "answer",
            operation_id,
            attention_id,
            "--text",
            "Use staging.",
            "--promote",
            "--policy-category",
            "testing",
            "--policy-objective-keyword",
            "release",
            "--policy-agent",
            "codex_acp",
            "--policy-rationale",
            "Reusable release answers should become durable policy.",
        ],
    )

    assert result.exit_code == 0
    records = _read_control_intents(tmp_path)
    records.sort(key=lambda item: item.submitted_at)
    assert [item.command.command_type.value for item in records if item.command is not None] == [
        OperationCommandType.ANSWER_ATTENTION_REQUEST.value,
        OperationCommandType.RECORD_POLICY_DECISION.value,
    ]
    assert records[0].command is not None
    assert records[1].command is not None
    assert records[0].command.target_scope is CommandTargetScope.ATTENTION_REQUEST
    assert records[0].command.target_id == attention_id
    assert records[1].command.target_scope is CommandTargetScope.ATTENTION_REQUEST
    assert records[1].command.target_id == attention_id
    assert records[1].command.payload["category"] == "testing"
    assert records[1].command.payload["objective_keywords"] == ["release"]
    assert records[1].command.payload["agent_keys"] == ["codex_acp"]
    assert (
        records[1].command.payload["rationale"]
        == "Reusable release answers should become durable policy."
    )


def test_command_enqueues_stop_operation(tmp_path: Path, monkeypatch) -> None:
    operation_id = _seed_operation(tmp_path)
    monkeypatch.setenv("OPERATOR_DATA_DIR", str(tmp_path))

    result = runner.invoke(app, ["command", operation_id, "--type", "stop_operation"])

    assert result.exit_code == 0
    record = _read_control_intent(tmp_path)
    assert record.command is not None
    assert record.command.command_type is OperationCommandType.STOP_OPERATION
    assert record.command.payload == {}


def test_command_requires_text_for_patch_harness(tmp_path: Path, monkeypatch) -> None:
    operation_id = _seed_operation(tmp_path)
    monkeypatch.setenv("OPERATOR_DATA_DIR", str(tmp_path))

    result = runner.invoke(app, ["command", operation_id, "--type", "patch_harness"])

    assert result.exit_code != 0
    rendered = result.stdout + result.stderr
    assert "--text is required" in rendered


def test_command_enqueues_patch_objective(tmp_path: Path, monkeypatch) -> None:
    operation_id = _seed_operation(tmp_path)
    monkeypatch.setenv("OPERATOR_DATA_DIR", str(tmp_path))

    result = runner.invoke(
        app,
        [
            "command",
            operation_id,
            "--type",
            "patch_objective",
            "--text",
            "Audit the release workflow and leave concrete next steps.",
        ],
    )

    assert result.exit_code == 0
    record = _read_control_intent(tmp_path)
    assert record.command is not None
    assert record.command.command_type is OperationCommandType.PATCH_OBJECTIVE
    assert (
        record.command.payload["text"]
        == "Audit the release workflow and leave concrete next steps."
    )


def test_command_requires_success_criteria_for_patch_success_criteria(
    tmp_path: Path, monkeypatch
) -> None:
    operation_id = _seed_operation(tmp_path)
    monkeypatch.setenv("OPERATOR_DATA_DIR", str(tmp_path))

    result = runner.invoke(app, ["command", operation_id, "--type", "patch_success_criteria"])

    assert result.exit_code != 0
    rendered = result.stdout + result.stderr
    assert "--success-criterion or --clear-success-criteria is required" in rendered


def test_command_enqueues_patch_success_criteria(tmp_path: Path, monkeypatch) -> None:
    operation_id = _seed_operation(tmp_path)
    monkeypatch.setenv("OPERATOR_DATA_DIR", str(tmp_path))

    result = runner.invoke(
        app,
        [
            "command",
            operation_id,
            "--type",
            "patch_success_criteria",
            "--success-criterion",
            "Tests pass",
            "--success-criterion",
            "Docs updated",
        ],
    )

    assert result.exit_code == 0
    record = _read_control_intent(tmp_path)
    assert record.command is not None
    assert record.command.command_type is OperationCommandType.PATCH_SUCCESS_CRITERIA
    assert record.command.payload["success_criteria"] == ["Tests pass", "Docs updated"]


def test_command_can_clear_success_criteria(tmp_path: Path, monkeypatch) -> None:
    operation_id = _seed_operation(tmp_path)
    monkeypatch.setenv("OPERATOR_DATA_DIR", str(tmp_path))

    result = runner.invoke(
        app,
        [
            "command",
            operation_id,
            "--type",
            "patch_success_criteria",
            "--clear-success-criteria",
        ],
    )

    assert result.exit_code == 0
    record = _read_control_intent(tmp_path)
    assert record.command is not None
    assert record.command.command_type is OperationCommandType.PATCH_SUCCESS_CRITERIA
    assert record.command.payload["success_criteria"] == []


def test_patch_objective_command_enqueues_patch_objective(tmp_path: Path, monkeypatch) -> None:
    operation_id = _seed_operation(tmp_path)
    monkeypatch.setenv("OPERATOR_DATA_DIR", str(tmp_path))
    _install_patch_delivery_stub(
        monkeypatch,
        tmp_path=tmp_path,
        command_type=OperationCommandType.PATCH_OBJECTIVE,
    )

    result = runner.invoke(
        app,
        ["patch-objective", operation_id, "Audit the release flow and trim dead steps."],
    )

    assert result.exit_code == 0
    assert "accepted: patch_objective [" in result.stdout
    record = _read_control_intent(tmp_path)
    assert record.command is not None
    assert record.command.command_type is OperationCommandType.PATCH_OBJECTIVE
    assert record.command.payload["text"] == "Audit the release flow and trim dead steps."


def test_patch_harness_command_enqueues_patch_harness(tmp_path: Path, monkeypatch) -> None:
    operation_id = _seed_operation(tmp_path)
    monkeypatch.setenv("OPERATOR_DATA_DIR", str(tmp_path))
    _install_patch_delivery_stub(
        monkeypatch,
        tmp_path=tmp_path,
        command_type=OperationCommandType.PATCH_HARNESS,
    )

    result = runner.invoke(
        app,
        ["patch-harness", operation_id, "Prefer the smallest verifiable change."],
    )

    assert result.exit_code == 0
    assert "accepted: patch_harness [" in result.stdout
    record = _read_control_intent(tmp_path)
    assert record.command is not None
    assert record.command.command_type is OperationCommandType.PATCH_HARNESS
    assert record.command.payload["text"] == "Prefer the smallest verifiable change."


def test_patch_objective_command_reports_acceptance_after_immediate_tick(
    tmp_path: Path, monkeypatch
) -> None:
    operation_id = _seed_operation(tmp_path)
    monkeypatch.setenv("OPERATOR_DATA_DIR", str(tmp_path))
    inbox = FileOperationCommandInbox(tmp_path / "commands")
    store = FileOperationStore(tmp_path / "runs")

    class FakeDeliveryService:
        def __init__(self) -> None:
            self.command_inbox = inbox
            self.store = store

        async def enqueue_command(
            self,
            operation_id: str,
            command_type: OperationCommandType,
            payload: dict[str, object],
            *,
            target_scope: CommandTargetScope,
            target_id: str,
            auto_resume_when_paused: bool = False,
            auto_resume_blocked_attention_id: str | None = None,
        ):
            command = OperationCommand(
                operation_id=operation_id,
                command_type=command_type,
                target_scope=target_scope,
                target_id=target_id,
                payload=payload,
            )
            await inbox.enqueue(command)
            return command, None, None

        async def tick(self, operation_id: str) -> OperationOutcome:
            commands = await inbox.list(operation_id)
            assert len(commands) == 1
            await inbox.update_status(commands[0].command_id, CommandStatus.APPLIED)
            return OperationOutcome(
                operation_id=operation_id,
                status=OperationStatus.RUNNING,
                summary="processed patch command",
            )

        def build_command_payload(
            self,
            command_type: OperationCommandType,
            text: str | None,
            success_criteria: list[str] | None = None,
            clear_success_criteria: bool = False,
            allowed_agents: list[str] | None = None,
            max_iterations: int | None = None,
        ) -> dict[str, object]:
            assert command_type is OperationCommandType.PATCH_OBJECTIVE
            assert text is not None
            return {"text": text}

    monkeypatch.setattr(
        "agent_operator.cli.workflows.control.delivery_commands_service",
        lambda: FakeDeliveryService(),
    )

    result = runner.invoke(
        app,
        ["patch-objective", operation_id, "Audit the release flow and trim dead steps."],
    )

    assert result.exit_code == 0
    assert "accepted: patch_objective [" in result.stdout


def test_patch_criteria_command_enqueues_patch_success_criteria(
    tmp_path: Path, monkeypatch
) -> None:
    operation_id = _seed_operation(tmp_path)
    monkeypatch.setenv("OPERATOR_DATA_DIR", str(tmp_path))
    _install_patch_delivery_stub(
        monkeypatch,
        tmp_path=tmp_path,
        command_type=OperationCommandType.PATCH_SUCCESS_CRITERIA,
    )

    result = runner.invoke(
        app,
        [
            "patch-criteria",
            operation_id,
            "--criteria",
            "Tests pass",
            "--criteria",
            "Docs updated",
        ],
    )

    assert result.exit_code == 0
    assert "accepted: patch_success_criteria [" in result.stdout
    record = _read_control_intent(tmp_path)
    assert record.command is not None
    assert record.command.command_type is OperationCommandType.PATCH_SUCCESS_CRITERIA
    assert record.command.payload["success_criteria"] == ["Tests pass", "Docs updated"]


def test_patch_objective_command_reports_terminal_rejection_after_immediate_tick(
    tmp_path: Path, monkeypatch
) -> None:
    operation_id = _seed_operation(tmp_path)
    monkeypatch.setenv("OPERATOR_DATA_DIR", str(tmp_path))
    inbox = FileOperationCommandInbox(tmp_path / "commands")
    store = FileOperationStore(tmp_path / "runs")

    class FakeDeliveryService:
        def __init__(self) -> None:
            self.command_inbox = inbox
            self.store = store

        async def enqueue_command(
            self,
            operation_id: str,
            command_type: OperationCommandType,
            payload: dict[str, object],
            *,
            target_scope: CommandTargetScope,
            target_id: str,
            auto_resume_when_paused: bool = False,
            auto_resume_blocked_attention_id: str | None = None,
        ):
            command = OperationCommand(
                operation_id=operation_id,
                command_type=command_type,
                target_scope=target_scope,
                target_id=target_id,
                payload=payload,
            )
            await inbox.enqueue(command)
            return command, None, None

        async def tick(self, operation_id: str) -> OperationOutcome:
            commands = await inbox.list(operation_id)
            assert len(commands) == 1
            await inbox.update_status(
                commands[0].command_id,
                CommandStatus.REJECTED,
                rejection_reason="operation_terminal",
            )
            return OperationOutcome(
                operation_id=operation_id,
                status=OperationStatus.COMPLETED,
                summary="already completed",
            )

        def build_command_payload(
            self,
            command_type: OperationCommandType,
            text: str | None,
            success_criteria: list[str] | None = None,
            clear_success_criteria: bool = False,
            allowed_agents: list[str] | None = None,
            max_iterations: int | None = None,
        ) -> dict[str, object]:
            assert command_type is OperationCommandType.PATCH_OBJECTIVE
            assert text is not None
            return {"text": text}

    monkeypatch.setattr(
        "agent_operator.cli.workflows.control.delivery_commands_service",
        lambda: FakeDeliveryService(),
    )

    result = runner.invoke(
        app,
        ["patch-objective", operation_id, "Audit the release flow and trim dead steps."],
    )

    assert result.exit_code == 1
    assert "Error: patch rejected - operation_terminal" in result.stdout


def test_patch_criteria_command_can_clear_criteria(tmp_path: Path, monkeypatch) -> None:
    operation_id = _seed_operation(tmp_path)
    monkeypatch.setenv("OPERATOR_DATA_DIR", str(tmp_path))
    _install_patch_delivery_stub(
        monkeypatch,
        tmp_path=tmp_path,
        command_type=OperationCommandType.PATCH_SUCCESS_CRITERIA,
    )

    result = runner.invoke(app, ["patch-criteria", operation_id, "--clear"])

    assert result.exit_code == 0
    assert "accepted: patch_success_criteria [" in result.stdout
    record = _read_control_intent(tmp_path)
    assert record.command is not None
    assert record.command.command_type is OperationCommandType.PATCH_SUCCESS_CRITERIA
    assert record.command.payload["success_criteria"] == []


def test_command_requires_allowed_agent_for_set_allowed_agents(tmp_path: Path, monkeypatch) -> None:
    operation_id = _seed_operation(tmp_path)
    monkeypatch.setenv("OPERATOR_DATA_DIR", str(tmp_path))

    result = runner.invoke(
        app,
        ["command", operation_id, "--type", "set_allowed_agents"],
    )

    assert result.exit_code != 0
    rendered = result.stdout + result.stderr
    assert "--agent is required" in rendered


def test_command_enqueues_set_allowed_agents(tmp_path: Path, monkeypatch) -> None:
    operation_id = _seed_operation(tmp_path)
    monkeypatch.setenv("OPERATOR_DATA_DIR", str(tmp_path))

    result = runner.invoke(
        app,
        [
            "command",
            operation_id,
            "--type",
            "set_allowed_agents",
            "--agent",
            "codex_acp",
            "--agent",
            "claude_acp",
        ],
    )

    assert result.exit_code == 0
    record = _read_control_intent(tmp_path)
    assert record.command is not None
    assert record.command.command_type is OperationCommandType.SET_ALLOWED_AGENTS
    assert record.command.payload["allowed_agents"] == ["codex_acp", "claude_acp"]


def test_command_rejects_max_iterations_for_set_allowed_agents(tmp_path: Path, monkeypatch) -> None:
    operation_id = _seed_operation(tmp_path)
    monkeypatch.setenv("OPERATOR_DATA_DIR", str(tmp_path))

    result = runner.invoke(
        app,
        [
            "command",
            operation_id,
            "--type",
            "set_allowed_agents",
            "--max-iterations",
            "11",
        ],
    )

    assert result.exit_code != 0
    rendered = result.stdout + result.stderr
    assert "--max-iterations is not supported" in rendered


def test_command_rejects_mixed_allowed_agents_and_max_iterations(
    tmp_path: Path, monkeypatch
) -> None:
    operation_id = _seed_operation(tmp_path)
    monkeypatch.setenv("OPERATOR_DATA_DIR", str(tmp_path))

    result = runner.invoke(
        app,
        [
            "command",
            operation_id,
            "--type",
            "set_allowed_agents",
            "--agent",
            "codex_acp",
            "--max-iterations",
            "14",
        ],
    )

    assert result.exit_code != 0
    rendered = result.stdout + result.stderr
    assert "--max-iterations is not supported" in rendered


def test_involvement_command_enqueues_level_change(tmp_path: Path, monkeypatch) -> None:
    operation_id = _seed_operation(tmp_path)
    monkeypatch.setenv("OPERATOR_DATA_DIR", str(tmp_path))

    result = runner.invoke(app, ["involvement", operation_id, "--level", "approval_heavy"])

    assert result.exit_code == 0
    record = _read_control_intent(tmp_path)
    assert record.command is not None
    assert record.command.command_type is OperationCommandType.SET_INVOLVEMENT_LEVEL
    assert record.command.payload["level"] == "approval_heavy"


def test_project_list_inspect_and_resolve(tmp_path: Path, monkeypatch) -> None:
    _seed_project_profile(tmp_path)
    monkeypatch.setenv("OPERATOR_DATA_DIR", str(tmp_path))

    listed = runner.invoke(app, ["project", "list"])
    inspected = runner.invoke(app, ["project", "inspect", "femtobot", "--json"])
    resolved = runner.invoke(app, ["project", "resolve", "femtobot", "--json"])

    assert listed.exit_code == 0
    assert "femtobot" in listed.stdout
    assert inspected.exit_code == 0
    assert '"default_harness_instructions": "Continue most of the time."' in inspected.stdout
    assert resolved.exit_code == 0
    assert '"profile_name": "femtobot"' in resolved.stdout
    assert '"involvement_level": "unattended"' in resolved.stdout


def test_project_list_is_inventory_shaped_by_default_and_supports_json(
    tmp_path: Path, monkeypatch
) -> None:
    _seed_project_profile(tmp_path)
    monkeypatch.setenv("OPERATOR_DATA_DIR", str(tmp_path))

    listed = runner.invoke(app, ["project", "list"])
    listed_json = runner.invoke(app, ["project", "list", "--json"])

    assert listed.exit_code == 0
    assert listed.stdout == "Projects\n- femtobot\n"

    assert listed_json.exit_code == 0
    payload = json.loads(listed_json.stdout)
    assert payload["project_profiles"][0]["name"] == "femtobot"
    assert payload["project_profiles"][0]["scope"] == "local"
    assert payload["project_profiles"][0]["cwd"] == "/tmp/femtobot"


def test_project_inspect_and_resolve_are_human_readable_by_default(
    tmp_path: Path, monkeypatch
) -> None:
    _seed_project_profile(tmp_path)
    monkeypatch.setenv("OPERATOR_DATA_DIR", str(tmp_path))

    inspected = runner.invoke(app, ["project", "inspect", "femtobot"])
    resolved = runner.invoke(app, ["project", "resolve", "femtobot"])

    assert inspected.exit_code == 0
    assert "Profile: femtobot" in inspected.stdout
    assert "Harness:" in inspected.stdout
    assert "Continue most of the time." in inspected.stdout
    assert '"default_harness_instructions"' not in inspected.stdout

    assert resolved.exit_code == 0
    assert "Resolved run defaults:" in resolved.stdout
    assert "- Objective: -" in resolved.stdout
    assert "- Involvement: unattended" in resolved.stdout
    assert '"profile_name"' not in resolved.stdout


def test_workspace_help_frames_lifecycle_family() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "init" in result.output
    assert "run" in result.output
    assert "clear" in result.output
    # Help describes the workspace lifecycle coherently
    output_lower = result.output.lower()
    assert "workspace" in output_lower or "lifecycle" in output_lower


def test_init_creates_committed_project_profile_and_gitignore(tmp_path: Path, monkeypatch) -> None:
    repo_root = tmp_path / "operator"
    nested = repo_root / "src"
    nested.mkdir(parents=True)
    (repo_root / ".git").mkdir()
    monkeypatch.chdir(nested)
    monkeypatch.delenv("OPERATOR_DATA_DIR", raising=False)

    result = runner.invoke(
        app,
        [
            "init",
            "--objective",
            "Prove the assigned theorem completely.",
            "--agent",
            "codex_acp",
            "--run-mode",
            "resumable",
            "--message-window",
            "6",
            "--json",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["project_root"] == str(repo_root)
    assert payload["profile_path"] == str(repo_root / "operator-profile.yaml")
    assert payload["profile"]["default_run_mode"] == "resumable"
    assert payload["profile"]["default_message_window"] == 6
    assert (repo_root / "operator-profile.yaml").exists()
    assert (repo_root / "operator-profiles").is_dir()
    assert ".operator/" in (repo_root / ".gitignore").read_text(encoding="utf-8")


def test_project_create_writes_committed_named_profile(tmp_path: Path, monkeypatch) -> None:
    repo_root = tmp_path / "operator"
    repo_root.mkdir(parents=True)
    (repo_root / ".git").mkdir()
    monkeypatch.chdir(repo_root)
    monkeypatch.delenv("OPERATOR_DATA_DIR", raising=False)

    result = runner.invoke(
        app,
        [
            "project",
            "create",
            "opsbot",
            "--objective",
            "Prove the assigned theorem completely.",
            "--agent",
            "codex_acp",
            "--json",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["profile_scope"] == "committed"
    assert payload["profile_path"] == str(repo_root / "operator-profiles" / "opsbot.yaml")
    assert (repo_root / "operator-profiles" / "opsbot.yaml").exists()


def test_project_create_local_writes_to_operator_profiles(tmp_path: Path, monkeypatch) -> None:
    repo_root = tmp_path / "operator"
    repo_root.mkdir(parents=True)
    (repo_root / ".git").mkdir()
    monkeypatch.chdir(repo_root)
    monkeypatch.delenv("OPERATOR_DATA_DIR", raising=False)

    result = runner.invoke(
        app,
        [
            "project",
            "create",
            "opsbot",
            "--local",
            "--json",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["profile_scope"] == "local"
    assert payload["profile_path"] == str(repo_root / ".operator" / "profiles" / "opsbot.yaml")
    assert (repo_root / ".operator" / "profiles" / "opsbot.yaml").exists()


def test_project_init_uses_repo_root_operator_dir_from_nested_git_checkout(
    tmp_path: Path,
    monkeypatch,
) -> None:
    repo_root = tmp_path / "operator"
    nested = repo_root / "src" / "agent_operator"
    nested.mkdir(parents=True)
    (repo_root / ".git").mkdir()
    monkeypatch.chdir(nested)
    monkeypatch.delenv("OPERATOR_DATA_DIR", raising=False)

    result = runner.invoke(app, ["project", "create", "operator", "--local", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    expected_path = repo_root / ".operator" / "profiles" / "operator.yaml"
    assert payload["profile_path"] == str(expected_path)
    assert expected_path.exists()


def test_project_init_writes_profile_and_emits_json(tmp_path: Path, monkeypatch) -> None:
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    monkeypatch.setenv("OPERATOR_DATA_DIR", str(tmp_path))

    result = runner.invoke(
        app,
        [
            "project",
            "create",
            "opsbot",
            "--local",
            "--cwd",
            str(repo_dir),
            "--path",
            "src",
            "--path",
            "tests",
            "--agent",
            "codex_acp",
            "--agent",
            "claude_acp",
            "--objective",
            "Prove the assigned theorem completely.",
            "--harness",
            "Stay attached and use swarm when unclear.",
            "--success-criterion",
            "Leave a concise report.",
            "--max-iterations",
            "11",
            "--involvement",
            "collaborative",
            "--json",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["profile"]["name"] == "opsbot"
    assert payload["profile"]["cwd"] == str(repo_dir)
    assert payload["profile"]["paths"] == ["src", "tests"]
    assert payload["profile"]["default_objective"] == "Prove the assigned theorem completely."
    assert payload["profile"]["default_agents"] == ["codex_acp", "claude_acp"]
    assert payload["profile"]["default_involvement_level"] == "collaborative"
    written = (tmp_path / "profiles" / "opsbot.yaml").read_text(encoding="utf-8")
    assert "name: opsbot" in written
    assert f"cwd: {repo_dir}" in written
    assert "- codex_acp" in written
    assert "default_max_iterations: 11" in written


def test_project_init_requires_force_to_overwrite(tmp_path: Path, monkeypatch) -> None:
    _seed_project_profile(tmp_path)
    monkeypatch.setenv("OPERATOR_DATA_DIR", str(tmp_path))

    first = runner.invoke(app, ["project", "create", "femtobot", "--local"])
    forced = runner.invoke(
        app,
        [
            "project",
            "create",
            "femtobot",
            "--local",
            "--harness",
            "Prefer attached execution.",
            "--force",
        ],
    )

    assert first.exit_code != 0
    assert "already exists" in (first.stdout + first.stderr)
    assert forced.exit_code == 0
    written = (tmp_path / "profiles" / "femtobot.yaml").read_text(encoding="utf-8")
    assert "default_harness_instructions: Prefer attached execution." in written


def test_policy_record_list_inspect_and_revoke(tmp_path: Path, monkeypatch) -> None:
    operation_id = _seed_operation(tmp_path)
    monkeypatch.setenv("OPERATOR_DATA_DIR", str(tmp_path))

    recorded = runner.invoke(
        app,
        [
            "policy",
            "record",
            operation_id,
            "--title",
            "Manual testing debt",
            "--category",
            "testing",
            "--text",
            "Document manual-only verification in MANUAL_TESTING_REQUIRED.md.",
            "--objective-keyword",
            "manual testing",
            "--task-keyword",
            "verify",
            "--agent",
            "codex_acp",
            "--run-mode",
            "attached",
            "--when-involvement",
            "auto",
            "--rationale",
            "Keeps unresolved human checks visible.",
        ],
    )

    assert recorded.exit_code == 0
    record = _read_control_intent(tmp_path)
    assert record.command is not None
    assert record.command.command_type is OperationCommandType.RECORD_POLICY_DECISION
    assert record.command.payload["category"] == "testing"
    assert record.command.payload["objective_keywords"] == ["manual testing"]
    assert record.command.payload["task_keywords"] == ["verify"]
    assert record.command.payload["agent_keys"] == ["codex_acp"]
    assert record.command.payload["run_modes"] == ["attached"]
    assert record.command.payload["involvement_levels"] == ["auto"]

    revoke = runner.invoke(
        app,
        [
            "policy",
            "revoke",
            operation_id,
            "--policy",
            "policy-123",
            "--reason",
            "Superseded by CI coverage.",
            "--yes",
        ],
    )
    assert revoke.exit_code == 0
    records = _read_control_intents(tmp_path)
    assert {item.command.command_type.value for item in records if item.command is not None} == {
        OperationCommandType.RECORD_POLICY_DECISION.value,
        OperationCommandType.REVOKE_POLICY_DECISION.value,
    }


def test_policy_revoke_requires_confirmation_by_default(tmp_path: Path, monkeypatch) -> None:
    operation_id = _seed_operation(tmp_path)
    monkeypatch.setenv("OPERATOR_DATA_DIR", str(tmp_path))

    result = runner.invoke(
        app,
        ["policy", "revoke", operation_id, "--policy", "policy-123"],
        input="n\n",
    )

    assert result.exit_code == 0
    assert "Revoke policy policy-123 for operation" in result.stdout
    assert "cancelled" in result.stdout
    assert _read_control_intents(tmp_path) == []


def test_policy_revoke_yes_skips_confirmation(tmp_path: Path, monkeypatch) -> None:
    operation_id = _seed_operation(tmp_path)
    monkeypatch.setenv("OPERATOR_DATA_DIR", str(tmp_path))

    result = runner.invoke(
        app,
        ["policy", "revoke", operation_id, "--policy", "policy-123", "--yes"],
    )

    assert result.exit_code == 0
    record = _read_control_intent(tmp_path)
    assert record.command is not None
    assert record.command.command_type is OperationCommandType.REVOKE_POLICY_DECISION
    assert record.command.payload["policy_id"] == "policy-123"


def test_policy_projects_is_inventory_shaped_by_default_and_supports_json(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("OPERATOR_DATA_DIR", str(tmp_path))
    store = FilePolicyStore(tmp_path / "policies")

    async def _seed() -> None:
        await store.save(
            PolicyEntry(
                policy_id="policy-1",
                project_scope="profile:femtobot",
                title="Manual testing debt",
                category=PolicyCategory.TESTING,
                rule_text="Document manual-only verification in MANUAL_TESTING_REQUIRED.md.",
            )
        )
        await store.save(
            PolicyEntry(
                policy_id="policy-2",
                project_scope="profile:femtobot",
                title="Security review",
                category=PolicyCategory.RELEASE,
                rule_text="Run red team review before release.",
                status=PolicyStatus.REVOKED,
            )
        )

    anyio.run(_seed)

    projects = runner.invoke(app, ["policy", "projects"])
    projects_json = runner.invoke(app, ["policy", "projects", "--json"])

    assert projects.exit_code == 0
    assert projects.stdout == "Projects With Policies\n- femtobot\n"

    assert projects_json.exit_code == 0
    payload = json.loads(projects_json.stdout)
    assert payload["policy_projects"][0]["project"] == "femtobot"
    assert payload["policy_projects"][0]["project_scope"] == "profile:femtobot"
    assert payload["policy_projects"][0]["active_policy_count"] == 1
    assert payload["policy_projects"][0]["policy_count"] == 2
    assert payload["policy_projects"][0]["categories"] == ["release", "testing"]


def test_policy_record_allows_attention_promotion_without_title_or_text(
    tmp_path: Path,
    monkeypatch,
) -> None:
    operation_id = _seed_operation(tmp_path)
    monkeypatch.setenv("OPERATOR_DATA_DIR", str(tmp_path))

    recorded = runner.invoke(
        app,
        [
            "policy",
            "record",
            operation_id,
            "--attention",
            "attention-123",
            "--category",
            "testing",
        ],
    )

    assert recorded.exit_code == 0
    record = _read_control_intent(tmp_path)
    assert record.command is not None
    assert record.command.command_type is OperationCommandType.RECORD_POLICY_DECISION
    assert record.command.target_scope is CommandTargetScope.ATTENTION_REQUEST
    assert record.command.target_id == "attention-123"
    assert "title" not in record.command.payload or record.command.payload["title"] in {None, ""}
    assert record.command.payload.get("text", "") == ""
    assert record.command.payload["category"] == "testing"


def test_policy_list_and_inspect(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("OPERATOR_DATA_DIR", str(tmp_path))
    store = FilePolicyStore(tmp_path / "policies")

    async def _seed() -> None:
        await store.save(
            PolicyEntry(
                policy_id="policy-1",
                project_scope="profile:femtobot",
                title="Manual testing debt",
                category=PolicyCategory.TESTING,
                rule_text="Document manual-only verification in MANUAL_TESTING_REQUIRED.md.",
                applicability=PolicyApplicability(
                    objective_keywords=["manual testing"],
                    agent_keys=["codex_acp"],
                    run_modes=[RunMode.ATTACHED],
                    involvement_levels=[InvolvementLevel.AUTO],
                ),
                rationale="Keeps unresolved checks visible.",
            )
        )

    anyio.run(_seed)

    listed = runner.invoke(app, ["policy", "list", "--project", "femtobot", "--json"])
    inspected = runner.invoke(app, ["policy", "inspect", "policy-1", "--json"])

    assert listed.exit_code == 0
    assert '"project_scope": "profile:femtobot"' in listed.stdout
    assert '"policy_id": "policy-1"' in listed.stdout
    assert '"applicability_summary"' in listed.stdout
    assert '"objective_keywords": [' in listed.stdout
    assert inspected.exit_code == 0
    assert '"category": "testing"' in inspected.stdout
    assert '"run_modes": [' in inspected.stdout


def test_policy_inspect_is_human_readable_by_default(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("OPERATOR_DATA_DIR", str(tmp_path))
    store = FilePolicyStore(tmp_path / "policies")

    async def _seed() -> None:
        await store.save(
            PolicyEntry(
                policy_id="policy-1",
                project_scope="profile:femtobot",
                title="Manual testing debt",
                category=PolicyCategory.TESTING,
                rule_text="Document manual-only verification in MANUAL_TESTING_REQUIRED.md.",
                applicability=PolicyApplicability(
                    objective_keywords=["manual testing"],
                    agent_keys=["codex_acp"],
                    run_modes=[RunMode.ATTACHED],
                    involvement_levels=[InvolvementLevel.AUTO],
                ),
                rationale="Keeps unresolved checks visible.",
            )
        )

    anyio.run(_seed)

    inspected = runner.invoke(app, ["policy", "inspect", "policy-1"])

    assert inspected.exit_code == 0
    assert "Policy: policy-1" in inspected.stdout
    assert "Category: testing" in inspected.stdout
    assert "Applicability details:" in inspected.stdout
    assert "Run modes: attached" in inspected.stdout
    assert '"category": "testing"' not in inspected.stdout


def test_run_with_project_uses_profile_defaults_and_cli_overrides(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _seed_project_profile(tmp_path)
    monkeypatch.setenv("OPERATOR_DATA_DIR", str(tmp_path))

    captured: dict[str, object] = {}

    class FakeService:
        async def run(
            self,
            goal,
            options,
            *,
            operation_id=None,
            attached_sessions=None,
            policy=None,
            budget=None,
            runtime_hints=None,
        ):
            captured["goal"] = goal
            captured["policy"] = policy
            captured["budget"] = budget
            captured["runtime_hints"] = runtime_hints
            captured["options"] = options
            return OperationOutcome(
                operation_id="op-project-run",
                status=OperationStatus.RUNNING,
                summary="Started from project profile.",
            )

    monkeypatch.setattr(
        "agent_operator.cli.main.build_service",
        lambda settings, event_sink=None: FakeService(),
    )

    result = runner.invoke(
        app,
        [
            "run",
            "Close open cards",
            "--project",
            "femtobot",
            "--harness",
            "Use swarm when unclear.",
            "--involvement",
            "collaborative",
        ],
    )

    assert result.exit_code == 0
    goal = captured["goal"]
    policy = captured["policy"]
    budget = captured["budget"]
    assert goal.harness_instructions == "Use swarm when unclear."
    assert goal.success_criteria == ["backlog stays above 100"]
    assert goal.metadata["project_profile_name"] == "femtobot"
    assert goal.metadata["policy_scope"] == "profile:femtobot"
    assert policy.allowed_agents == ["codex_acp"]
    assert budget.max_iterations == 12
    assert policy.involvement_level.value == "collaborative"


def test_run_auto_discovers_operator_profile_yaml_from_cwd(tmp_path: Path, monkeypatch) -> None:
    project_dir = tmp_path / "operator"
    project_dir.mkdir(parents=True)
    profile_path = project_dir / "operator-profile.yaml"
    profile_path.write_text(
        "\n".join(
            [
                "name: operator-local",
                "cwd: .",
                "default_objective: Prove the theorem.",
                "default_agents:",
                "  - codex_acp",
                "default_harness_instructions: Stay attached.",
                "default_success_criteria:",
                "  - Leave a concise report.",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(project_dir)
    monkeypatch.delenv("OPERATOR_DATA_DIR", raising=False)

    captured: dict[str, object] = {}

    class FakeService:
        async def run(
            self,
            goal,
            options,
            *,
            operation_id=None,
            attached_sessions=None,
            policy=None,
            budget=None,
            runtime_hints=None,
        ):
            captured["goal"] = goal
            return OperationOutcome(
                operation_id="op-project-run",
                status=OperationStatus.RUNNING,
                summary="Started from discovered project profile.",
            )

    monkeypatch.setattr(
        "agent_operator.cli.main.build_service",
        lambda settings, event_sink=None: FakeService(),
    )

    result = runner.invoke(app, ["run", "Close open cards"])

    assert result.exit_code == 0
    goal = captured["goal"]
    assert goal.objective == "Close open cards"
    assert goal.metadata["project_profile_name"] == "operator-local"
    assert goal.metadata["project_profile_source"] == "local_profile_file"
    assert goal.metadata["project_profile_path"] == str(profile_path)
    assert goal.metadata["data_dir_source"] == "cwd_default"


def test_run_enters_free_mode_stub_when_no_profile_exists(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("OPERATOR_DATA_DIR", raising=False)

    result = runner.invoke(app, ["run", "Close open cards"])

    assert result.exit_code == 0
    combined = result.stdout + result.stderr
    assert "free_mode_stub" in combined
    assert "operator-profile.yaml" in combined
    assert "planned but not implemented yet" in combined


def test_run_records_effective_adapter_settings_in_goal_metadata(
    tmp_path: Path,
    monkeypatch,
) -> None:
    project_dir = tmp_path / "repo"
    project_dir.mkdir(parents=True)
    (project_dir / "operator-profile.yaml").write_text(
        "\n".join(
            [
                "name: repo",
                "cwd: .",
                "default_objective: Close cards.",
                "default_agents:",
                "  - codex_acp",
                "adapter_settings:",
                "  codex_acp:",
                "    command: npx @zed-industries/codex-acp --",
                "    model: gpt-5.4",
                "    reasoning_effort: high",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.chdir(project_dir)
    monkeypatch.delenv("OPERATOR_DATA_DIR", raising=False)
    captured: dict[str, object] = {}

    class FakeService:
        async def run(
            self,
            goal,
            options,
            *,
            operation_id=None,
            attached_sessions=None,
            policy=None,
            budget=None,
            runtime_hints=None,
        ):
            captured["goal"] = goal
            return OperationOutcome(
                operation_id="op-effective-settings",
                status=OperationStatus.RUNNING,
                summary="Started.",
            )

    monkeypatch.setattr(
        "agent_operator.cli.main.build_service",
        lambda settings, event_sink=None: FakeService(),
    )

    result = runner.invoke(app, ["run", "Close cards"])

    assert result.exit_code == 0
    goal = captured["goal"]
    snapshot = goal.metadata["effective_adapter_settings"]
    assert snapshot["codex_acp"]["command"] == "npx @zed-industries/codex-acp --"
    assert snapshot["codex_acp"]["model"] == "gpt-5.4"
    assert snapshot["codex_acp"]["reasoning_effort"] == "high"


def test_run_uses_profile_default_objective_when_cli_objective_is_omitted(
    tmp_path: Path,
    monkeypatch,
) -> None:
    project_dir = tmp_path / "erdos-461"
    project_dir.mkdir(parents=True)
    (project_dir / "operator-profile.yaml").write_text(
        "\n".join(
            [
                "name: erdos-461",
                "cwd: .",
                "default_objective: Prove problem 461 completely.",
                "default_agents:",
                "  - claude_acp",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(project_dir)
    monkeypatch.delenv("OPERATOR_DATA_DIR", raising=False)

    captured: dict[str, object] = {}

    class FakeService:
        async def run(
            self,
            goal,
            options,
            *,
            operation_id=None,
            attached_sessions=None,
            policy=None,
            budget=None,
            runtime_hints=None,
        ):
            captured["goal"] = goal
            return OperationOutcome(
                operation_id="op-project-run",
                status=OperationStatus.RUNNING,
                summary="Started from discovered project profile.",
            )

    monkeypatch.setattr(
        "agent_operator.cli.main.build_service",
        lambda settings, event_sink=None: FakeService(),
    )

    result = runner.invoke(app, ["run"])

    assert result.exit_code == 0
    goal = captured["goal"]
    assert goal.objective == "Prove problem 461 completely."


def test_run_from_ticket_populates_goal_and_ticket_metadata(tmp_path: Path, monkeypatch) -> None:
    project_dir = tmp_path / "repo"
    project_dir.mkdir(parents=True)
    (project_dir / "operator-profile.yaml").write_text("name: repo\ncwd: .\n", encoding="utf-8")
    monkeypatch.chdir(project_dir)
    monkeypatch.delenv("OPERATOR_DATA_DIR", raising=False)

    async def fake_resolve(self, ticket_ref: str, *, profile):
        assert ticket_ref == "github:owner/repo#123"
        return SimpleNamespace(
            goal_text="Imported title\n\nImported body",
            ticket=ExternalTicketLink(
                provider="github_issues",
                project_key="owner/repo",
                ticket_id="123",
                url="https://github.com/owner/repo/issues/123",
                title="Imported title",
            ),
        )

    captured: dict[str, object] = {}

    class FakeService:
        async def run(
            self,
            goal,
            options,
            *,
            operation_id=None,
            attached_sessions=None,
            policy=None,
            budget=None,
            runtime_hints=None,
        ):
            captured["goal"] = goal
            return OperationOutcome(
                operation_id="op-ticket-run",
                status=OperationStatus.RUNNING,
                summary="Started from ticket.",
            )

    monkeypatch.setattr(
        "agent_operator.cli.workflows.control.TicketIntakeService.resolve",
        fake_resolve,
    )
    monkeypatch.setattr(
        "agent_operator.cli.main.build_service",
        lambda settings, event_sink=None: FakeService(),
    )

    result = runner.invoke(app, ["run", "--from", "github:owner/repo#123"])

    assert result.exit_code == 0
    goal = captured["goal"]
    assert goal.objective == "Imported title\n\nImported body"
    assert goal.external_ticket.ticket_id == "123"


def test_run_cli_objective_overrides_ticket_goal_text(tmp_path: Path, monkeypatch) -> None:
    project_dir = tmp_path / "repo"
    project_dir.mkdir(parents=True)
    (project_dir / "operator-profile.yaml").write_text("name: repo\ncwd: .\n", encoding="utf-8")
    monkeypatch.chdir(project_dir)
    monkeypatch.delenv("OPERATOR_DATA_DIR", raising=False)

    async def fake_resolve(self, ticket_ref: str, *, profile):
        return SimpleNamespace(
            goal_text="Imported title\n\nImported body",
            ticket=ExternalTicketLink(
                provider="github_issues",
                project_key="owner/repo",
                ticket_id="123",
                url="https://github.com/owner/repo/issues/123",
                title="Imported title",
            ),
        )

    captured: dict[str, object] = {}

    class FakeService:
        async def run(
            self,
            goal,
            options,
            *,
            operation_id=None,
            attached_sessions=None,
            policy=None,
            budget=None,
            runtime_hints=None,
        ):
            captured["goal"] = goal
            return OperationOutcome(
                operation_id="op-ticket-run",
                status=OperationStatus.RUNNING,
                summary="Started from ticket.",
            )

    monkeypatch.setattr(
        "agent_operator.cli.workflows.control.TicketIntakeService.resolve",
        fake_resolve,
    )
    monkeypatch.setattr(
        "agent_operator.cli.main.build_service",
        lambda settings, event_sink=None: FakeService(),
    )

    result = runner.invoke(app, ["run", "Use local override", "--from", "github:owner/repo#123"])

    assert result.exit_code == 0
    goal = captured["goal"]
    assert goal.objective == "Use local override"
    assert goal.metadata["external_ticket_context"] == "Imported title\n\nImported body"


def test_run_prompts_for_objective_when_profile_has_no_default_objective(
    tmp_path: Path,
    monkeypatch,
) -> None:
    project_dir = tmp_path / "erdos-461"
    project_dir.mkdir(parents=True)
    (project_dir / "operator-profile.yaml").write_text(
        "name: erdos-461\ncwd: .\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(project_dir)
    monkeypatch.delenv("OPERATOR_DATA_DIR", raising=False)

    captured: dict[str, object] = {}

    class FakeService:
        async def run(
            self,
            goal,
            options,
            *,
            operation_id=None,
            attached_sessions=None,
            policy=None,
            budget=None,
            runtime_hints=None,
        ):
            captured["goal"] = goal
            return OperationOutcome(
                operation_id="op-project-run",
                status=OperationStatus.RUNNING,
                summary="Started from prompted objective.",
            )

    monkeypatch.setattr(
        "agent_operator.cli.main.build_service",
        lambda settings, event_sink=None: FakeService(),
    )

    result = runner.invoke(app, ["run"], input="Prompted objective\n")

    assert result.exit_code == 0
    assert captured["goal"].objective == "Prompted objective"


def test_project_inspect_reads_local_operator_profile_yaml(tmp_path: Path, monkeypatch) -> None:
    project_dir = tmp_path / "erdos-461"
    project_dir.mkdir(parents=True)
    (project_dir / "operator-profile.yaml").write_text(
        "\n".join(
            [
                "name: erdos-461",
                "cwd: .",
                "default_harness_instructions: Stay attached.",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(project_dir)
    monkeypatch.delenv("OPERATOR_DATA_DIR", raising=False)

    result = runner.invoke(app, ["project", "inspect"])

    assert result.exit_code == 0
    assert "Profile: erdos-461" in result.stdout
    assert "Harness:" in result.stdout
    assert "Stay attached." in result.stdout


def test_project_resolve_reads_local_operator_profile_yaml(tmp_path: Path, monkeypatch) -> None:
    project_dir = tmp_path / "erdos-461"
    project_dir.mkdir(parents=True)
    profile_path = project_dir / "operator-profile.yaml"
    profile_path.write_text(
        "\n".join(
            [
                "name: erdos-461",
                "cwd: .",
                "default_success_criteria:",
                "  - Keep proof current.",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(project_dir)
    monkeypatch.delenv("OPERATOR_DATA_DIR", raising=False)

    result = runner.invoke(app, ["project", "resolve", "--json"])

    assert result.exit_code == 0
    assert '"profile_source": "local_profile_file"' in result.stdout
    assert str(profile_path) in result.stdout


def test_run_success_criteria_override_replaces_project_defaults(
    tmp_path: Path, monkeypatch
) -> None:
    _seed_project_profile(tmp_path)
    monkeypatch.setenv("OPERATOR_DATA_DIR", str(tmp_path))

    captured: dict[str, object] = {}

    class FakeService:
        async def run(
            self,
            goal,
            options,
            *,
            operation_id=None,
            attached_sessions=None,
            policy=None,
            budget=None,
            runtime_hints=None,
        ):
            captured["goal"] = goal
            captured["policy"] = policy
            captured["budget"] = budget
            captured["options"] = options
            return OperationOutcome(
                operation_id="op-project-run-success-override",
                status=OperationStatus.RUNNING,
                summary="Started from project profile.",
            )

    monkeypatch.setattr(
        "agent_operator.cli.main.build_service",
        lambda settings, event_sink=None: FakeService(),
    )

    result = runner.invoke(
        app,
        [
            "run",
            "Close open cards",
            "--project",
            "femtobot",
            "--success-criterion",
            "CI stays green",
            "--success-criterion",
            "Backlog stays below 50",
        ],
    )

    assert result.exit_code == 0
    goal = captured["goal"]
    assert goal.success_criteria == ["CI stays green", "Backlog stays below 50"]
    assert goal.metadata["resolved_project_profile"]["overrides"] == ["success_criteria"]


def test_run_with_project_sets_policy_scope_in_goal_metadata(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _seed_project_profile(tmp_path)
    monkeypatch.setenv("OPERATOR_DATA_DIR", str(tmp_path))

    captured: dict[str, object] = {}

    class FakeService:
        async def run(
            self,
            goal,
            options,
            *,
            operation_id=None,
            attached_sessions=None,
            policy=None,
            budget=None,
            runtime_hints=None,
        ):
            captured["goal"] = goal
            return OperationOutcome(
                operation_id="op-project-run",
                status=OperationStatus.RUNNING,
                summary="Started from project profile.",
            )

    monkeypatch.setattr(
        "agent_operator.cli.main.build_service",
        lambda settings, event_sink=None: FakeService(),
    )

    result = runner.invoke(app, ["run", "Close open cards", "--project", "femtobot"])

    assert result.exit_code == 0
    goal = captured["goal"]
    assert goal.metadata["policy_scope"] == "profile:femtobot"


def test_run_with_project_applies_profile_adapter_settings(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _seed_project_profile(tmp_path)
    monkeypatch.setenv("OPERATOR_DATA_DIR", str(tmp_path))

    captured: dict[str, object] = {}

    class FakeService:
        async def run(
            self,
            goal,
            options,
            *,
            operation_id=None,
            attached_sessions=None,
            policy=None,
            budget=None,
            runtime_hints=None,
        ):
            return OperationOutcome(
                operation_id="op-project-run",
                status=OperationStatus.RUNNING,
                summary="Started from project profile.",
            )

    def _fake_build_service(settings, event_sink=None):
        captured["codex_command"] = settings.codex_acp.command
        captured["codex_approval_policy"] = settings.codex_acp.approval_policy
        return FakeService()

    monkeypatch.setattr("agent_operator.cli.main.build_service", _fake_build_service)

    result = runner.invoke(
        app,
        [
            "run",
            "Close open cards",
            "--project",
            "femtobot",
        ],
    )

    assert result.exit_code == 0
    assert captured["codex_command"] == "npm exec --yes @zed-industries/codex-acp --"
    assert captured["codex_approval_policy"] == "never"


def test_run_agent_flag_replaces_profile_default_agents(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _seed_project_profile(tmp_path)
    monkeypatch.setenv("OPERATOR_DATA_DIR", str(tmp_path))

    captured: dict[str, object] = {}

    class FakeService:
        async def run(
            self,
            goal,
            options,
            *,
            operation_id=None,
            attached_sessions=None,
            policy=None,
            budget=None,
            runtime_hints=None,
        ):
            captured["policy"] = policy
            return OperationOutcome(
                operation_id="op-project-run",
                status=OperationStatus.RUNNING,
                summary="Started from project profile.",
            )

    monkeypatch.setattr(
        "agent_operator.cli.main.build_service",
        lambda settings, event_sink=None: FakeService(),
    )

    result = runner.invoke(
        app,
        [
            "run",
            "Close open cards",
            "--project",
            "femtobot",
            "--agent",
            "claude_acp",
        ],
    )

    assert result.exit_code == 0
    assert captured["policy"].allowed_agents == ["claude_acp"]


def test_run_streams_live_events_in_human_mode(tmp_path: Path, monkeypatch) -> None:
    project_dir = tmp_path / "project"
    project_dir.mkdir(parents=True)
    (project_dir / "operator-profile.yaml").write_text(
        "\n".join(
            [
                "name: project",
                "default_objective: Close open cards",
                "cwd: .",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(project_dir)
    monkeypatch.delenv("OPERATOR_DATA_DIR", raising=False)

    class FakeService:
        def __init__(self, event_sink) -> None:
            self._event_sink = event_sink

        async def run(
            self,
            goal,
            options,
            *,
            operation_id=None,
            attached_sessions=None,
            policy=None,
            budget=None,
            runtime_hints=None,
        ):
            assert self._event_sink is not None
            await self._event_sink.emit(
                RunEvent(
                    event_type="operation.started",
                    operation_id=operation_id or "op-live-run",
                    iteration=0,
                    payload={"objective": goal.objective_text},
                    category="trace",
                )
            )
            await self._event_sink.emit(
                RunEvent(
                    event_type="brain.decision.made",
                    operation_id=operation_id or "op-live-run",
                    iteration=1,
                    payload={
                        "action_type": "start_agent",
                        "target_agent": "codex_acp",
                        "rationale": "Need a repo-aware coding agent.",
                    },
                    category="trace",
                )
            )
            await self._event_sink.emit(
                RunEvent(
                    event_type="agent.invocation.started",
                    operation_id=operation_id or "op-live-run",
                    iteration=1,
                    session_id="session-live-1",
                    payload={
                        "adapter_key": "codex_acp",
                        "session_id": "session-live-1",
                        "session_name": "repo-audit",
                    },
                    category="trace",
                )
            )
            return OperationOutcome(
                operation_id=operation_id or "op-live-run",
                status=OperationStatus.COMPLETED,
                summary="Live run finished.",
            )

    monkeypatch.setattr(
        "agent_operator.cli.main.build_service",
        lambda settings, event_sink=None: FakeService(event_sink),
    )

    result = runner.invoke(app, ["run", "Close open cards"])

    assert result.exit_code == 0
    assert "starting: Close open cards" in result.stdout
    assert "[iter 1] decision: start_agent -> codex_acp" in result.stdout
    assert "[iter 1] agent started: codex_acp session=session-live-1 name=repo-audit" in (
        result.stdout
    )
    assert "completed: Live run finished." in result.stdout


def test_run_json_streams_event_objects_and_outcome(tmp_path: Path, monkeypatch) -> None:
    project_dir = tmp_path / "project"
    project_dir.mkdir(parents=True)
    (project_dir / "operator-profile.yaml").write_text(
        "\n".join(
            [
                "name: project",
                "default_objective: Close open cards",
                "cwd: .",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(project_dir)
    monkeypatch.delenv("OPERATOR_DATA_DIR", raising=False)

    class FakeService:
        def __init__(self, event_sink) -> None:
            self._event_sink = event_sink

        async def run(
            self,
            goal,
            options,
            *,
            operation_id=None,
            attached_sessions=None,
            policy=None,
            budget=None,
            runtime_hints=None,
        ):
            assert self._event_sink is not None
            await self._event_sink.emit(
                RunEvent(
                    event_type="operation.started",
                    operation_id=operation_id or "op-live-json",
                    iteration=0,
                    payload={"objective": goal.objective_text},
                    category="trace",
                )
            )
            await self._event_sink.emit(
                RunEvent(
                    event_type="evaluation.completed",
                    operation_id=operation_id or "op-live-json",
                    iteration=1,
                    payload={
                        "should_continue": False,
                        "goal_satisfied": True,
                        "summary": "Goal satisfied.",
                    },
                    category="trace",
                )
            )
            return OperationOutcome(
                operation_id=operation_id or "op-live-json",
                status=OperationStatus.COMPLETED,
                summary="Structured live run finished.",
            )

    monkeypatch.setattr(
        "agent_operator.cli.main.build_service",
        lambda settings, event_sink=None: FakeService(event_sink),
    )

    result = runner.invoke(app, ["run", "Close open cards", "--json"])

    assert result.exit_code == 0
    lines = [json.loads(line) for line in result.stdout.splitlines() if line.strip()]
    assert lines[0]["type"] == "operation"
    assert lines[1]["type"] == "event"
    assert lines[1]["event"]["event_type"] == "operation.started"
    assert lines[2]["event"]["event_type"] == "evaluation.completed"
    assert lines[3]["type"] == "outcome"
    assert lines[3]["outcome"]["summary"] == "Structured live run finished."


def test_run_streams_blocking_attention_wait_and_resume_messages(
    tmp_path: Path, monkeypatch
) -> None:
    project_dir = tmp_path / "project"
    project_dir.mkdir(parents=True)
    (project_dir / "operator-profile.yaml").write_text(
        "\n".join(
            [
                "name: project",
                "default_objective: Close open cards",
                "cwd: .",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(project_dir)
    monkeypatch.delenv("OPERATOR_DATA_DIR", raising=False)

    class FakeService:
        def __init__(self, event_sink) -> None:
            self._event_sink = event_sink

        async def run(
            self,
            goal,
            options,
            *,
            operation_id=None,
            attached_sessions=None,
            policy=None,
            budget=None,
            runtime_hints=None,
        ):
            del goal, options, attached_sessions, policy, budget, runtime_hints
            assert self._event_sink is not None
            live_operation_id = operation_id or "op-live-attention"
            await self._event_sink.emit(
                RunEvent(
                    event_type="attention.request.created",
                    operation_id=live_operation_id,
                    iteration=1,
                    payload={
                        "operation_id": live_operation_id,
                        "attention_id": "attention-live-1",
                        "attention_type": "approval_request",
                        "title": "Agent requested approval",
                        "blocking": True,
                        "status": "open",
                    },
                    category="trace",
                )
            )
            await self._event_sink.emit(
                RunEvent(
                    event_type="command.applied",
                    operation_id=live_operation_id,
                    iteration=1,
                    payload={
                        "command_id": "cmd-live-1",
                        "command_type": "answer_attention_request",
                        "status": "applied",
                        "prior_status": "accepted",
                    },
                    category="trace",
                )
            )
            return OperationOutcome(
                operation_id=live_operation_id,
                status=OperationStatus.COMPLETED,
                summary="Structured live run finished.",
            )

    monkeypatch.setattr(
        "agent_operator.cli.main.build_service",
        lambda settings, event_sink=None: FakeService(event_sink),
    )

    result = runner.invoke(app, ["run", "Close open cards"])

    assert result.exit_code == 0
    assert "[iter 1] Attention needed: Agent requested approval." in result.stdout
    assert 'attention-live-1 --text "..."' in result.stdout
    assert "Run: operator answer " in result.stdout
    assert "[iter 1] Answer received. Resuming..." in result.stdout
    assert "completed: Structured live run finished." in result.stdout


def test_run_wait_brief_uses_semantic_exit_code_for_resumable_completion(
    tmp_path: Path, monkeypatch
) -> None:
    project_dir = tmp_path / "project"
    project_dir.mkdir(parents=True)
    (project_dir / "operator-profile.yaml").write_text(
        "name: project\ncwd: .\ndefault_objective: Close open cards\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(project_dir)
    monkeypatch.delenv("OPERATOR_DATA_DIR", raising=False)

    class FakeService:
        async def run(
            self,
            goal,
            options,
            *,
            operation_id=None,
            attached_sessions=None,
            policy=None,
            budget=None,
            runtime_hints=None,
        ):
            return OperationOutcome(
                operation_id=operation_id or "op-wait",
                status=OperationStatus.RUNNING,
                summary="Started in resumable mode.",
            )

    class FakeStatusService:
        def __init__(self) -> None:
            self.calls = 0

        async def build_status_payload(self, operation_id: str):
            self.calls += 1
            outcome = OperationOutcome(
                operation_id=operation_id,
                status=OperationStatus.COMPLETED,
                summary="Completed after waiting.",
            )
            return None, outcome, None, None

    monkeypatch.setattr(
        "agent_operator.cli.main.build_service",
        lambda settings, event_sink=None: FakeService(),
    )
    monkeypatch.setattr(
        "agent_operator.cli.workflows.control_runtime.build_status_query_service",
        lambda settings: FakeStatusService(),
    )
    monkeypatch.setattr(
        "agent_operator.cli.workflows.run_output.build_status_query_service",
        lambda settings: FakeStatusService(),
    )

    result = runner.invoke(
        app,
        ["run", "Close open cards", "--mode", "resumable", "--wait", "--brief"],
    )

    assert result.exit_code == 0
    assert "STATUS=completed" in result.stdout
    assert "OPERATION=" in result.stdout


def test_run_wait_uses_needs_human_exit_code(tmp_path: Path, monkeypatch) -> None:
    project_dir = tmp_path / "project"
    project_dir.mkdir(parents=True)
    (project_dir / "operator-profile.yaml").write_text(
        "name: project\ncwd: .\ndefault_objective: Close open cards\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(project_dir)
    monkeypatch.delenv("OPERATOR_DATA_DIR", raising=False)

    class FakeService:
        async def run(
            self,
            goal,
            options,
            *,
            operation_id=None,
            attached_sessions=None,
            policy=None,
            budget=None,
            runtime_hints=None,
        ):
            return OperationOutcome(
                operation_id=operation_id or "op-needs-human",
                status=OperationStatus.RUNNING,
                summary="Started in resumable mode.",
            )

    class FakeStatusService:
        async def build_status_payload(self, operation_id: str):
            outcome = OperationOutcome(
                operation_id=operation_id,
                status=OperationStatus.NEEDS_HUMAN,
                summary="Need an answer.",
            )
            return None, outcome, None, None

    monkeypatch.setattr(
        "agent_operator.cli.main.build_service",
        lambda settings, event_sink=None: FakeService(),
    )
    monkeypatch.setattr(
        "agent_operator.cli.workflows.control_runtime.build_status_query_service",
        lambda settings: FakeStatusService(),
    )

    result = runner.invoke(
        app,
        ["run", "Close open cards", "--mode", "resumable", "--wait", "--json"],
    )

    assert result.exit_code == 2
    payload = json.loads(result.stdout)
    assert payload["status"] == "needs_human"


def test_run_timeout_requires_resumable_mode(tmp_path: Path, monkeypatch) -> None:
    project_dir = tmp_path / "project"
    project_dir.mkdir(parents=True)
    (project_dir / "operator-profile.yaml").write_text(
        "name: project\ncwd: .\ndefault_objective: Close open cards\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(project_dir)
    monkeypatch.delenv("OPERATOR_DATA_DIR", raising=False)

    result = runner.invoke(app, ["run", "Close open cards", "--wait", "--timeout", "1"])

    assert result.exit_code != 0
    assert "--timeout is currently supported only with --mode resumable." in result.output


def test_resume_streams_live_events(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("OPERATOR_DATA_DIR", str(tmp_path))

    class FakeService:
        def __init__(self, event_sink) -> None:
            self._event_sink = event_sink

        async def resume(self, operation_id: str, *, options):
            assert self._event_sink is not None
            await self._event_sink.emit(
                RunEvent(
                    event_type="command.applied",
                    operation_id=operation_id,
                    iteration=2,
                    payload={
                        "command_type": "resume_operator",
                        "status": "applied",
                    },
                    category="trace",
                )
            )
            return OperationOutcome(
                operation_id=operation_id,
                status=OperationStatus.RUNNING,
                summary="Resume cycle finished.",
            )

    monkeypatch.setattr(
        "agent_operator.cli.helpers.services._current_build_service",
        lambda: (lambda settings, event_sink=None: FakeService(event_sink)),
    )

    result = runner.invoke(app, ["resume", "op-resume-live"])

    assert result.exit_code == 0
    assert "[iter 2] command applied: resume_operator" in result.stdout
    assert "running: Resume cycle finished." in result.stdout


def test_resume_streams_execution_profile_transparency_events(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("OPERATOR_DATA_DIR", str(tmp_path))

    class FakeService:
        def __init__(self, event_sink) -> None:
            self._event_sink = event_sink

        async def resume(self, operation_id: str, *, options):
            assert self._event_sink is not None
            await self._event_sink.emit(
                RunEvent(
                    event_type="command.applied",
                    operation_id=operation_id,
                    iteration=2,
                    payload={
                        "command_type": "set_execution_profile",
                        "adapter_key": "codex_acp",
                        "previous_model": "gpt-5.4",
                        "previous_effort_value": "low",
                        "current_model": "gpt-5.4-mini",
                        "current_effort_value": "medium",
                    },
                    category="trace",
                )
            )
            await self._event_sink.emit(
                RunEvent(
                    event_type="session.execution_profile.applied",
                    operation_id=operation_id,
                    iteration=2,
                    session_id="session-1",
                    payload={
                        "session_id": "session-1",
                        "adapter_key": "codex_acp",
                        "model": "gpt-5.4-mini",
                        "effort_value": "medium",
                        "applied_via": "reuse",
                    },
                    category="trace",
                )
            )
            return OperationOutcome(
                operation_id=operation_id,
                status=OperationStatus.RUNNING,
                summary="Resume cycle finished.",
            )

    monkeypatch.setattr(
        "agent_operator.cli.helpers.services._current_build_service",
        lambda: (lambda settings, event_sink=None: FakeService(event_sink)),
    )

    result = runner.invoke(app, ["resume", "op-resume-profile-live"])

    assert result.exit_code == 0
    assert (
        "[iter 2] execution profile updated for codex_acp: gpt-5.4 / low -> gpt-5.4-mini / medium"
        in result.stdout
    )
    assert (
        "[iter 2] session session-1 reused with codex_acp gpt-5.4-mini / medium"
        in result.stdout
    )


def test_resume_restores_effective_adapter_settings_from_operation_metadata(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("OPERATOR_DATA_DIR", str(tmp_path))
    store = FileOperationStore(tmp_path / "runs")
    operation_id = "op-resume-settings"

    async def _seed() -> None:
        state = OperationState(
            operation_id=operation_id,
            goal=OperationGoal(
                objective="Resume with restored settings",
                metadata={
                    "effective_adapter_settings": {
                        "codex_acp": {
                            "command": "npx @zed-industries/codex-acp --",
                            "model": "gpt-5.4",
                            "reasoning_effort": "high",
                        }
                    }
                },
            ),
            **state_settings(),
        )
        await store.save_operation(state)

    anyio.run(_seed)
    captured: dict[str, object] = {}

    class FakeService:
        async def resume(self, operation_id: str, *, options):
            return OperationOutcome(
                operation_id=operation_id,
                status=OperationStatus.RUNNING,
                summary="Resumed.",
            )

    def _build_service(settings, event_sink=None):
        captured["codex_command"] = settings.codex_acp.command
        captured["codex_model"] = settings.codex_acp.model
        captured["codex_effort"] = settings.codex_acp.reasoning_effort
        return FakeService()

    monkeypatch.setattr("agent_operator.cli.main.build_service", _build_service)

    result = runner.invoke(app, ["resume", operation_id])

    assert result.exit_code == 0
    assert captured["codex_command"] == "npx @zed-industries/codex-acp --"
    assert captured["codex_model"] == "gpt-5.4"
    assert captured["codex_effort"] == "high"


def test_resume_restores_effective_adapter_settings_from_event_sourced_metadata(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("OPERATOR_DATA_DIR", str(tmp_path))
    operation_id = "op-resume-es-settings"

    async def _seed() -> None:
        settings = OperatorSettings(data_dir=tmp_path)
        goal = OperationGoal(
            objective="Resume v2-only with restored settings",
            metadata={
                "effective_adapter_settings": {
                    "codex_acp": {
                        "command": "npx @zed-industries/codex-acp --",
                        "model": "gpt-5.4",
                        "reasoning_effort": "high",
                    }
                }
            },
        )
        service = build_replay_service(settings)
        birth = EventSourcedOperationBirthService(
            event_store=FileOperationEventStore(tmp_path / "operation_events"),
            checkpoint_store=FileOperationCheckpointStore(tmp_path / "operation_checkpoints"),
            projector=DefaultOperationProjector(),
        )
        state = OperationState(
            operation_id=operation_id,
            goal=goal,
            **state_settings(),
        )
        await birth.birth(state)
        await service.load(operation_id)

    anyio.run(_seed)
    captured: dict[str, object] = {}

    class FakeService:
        async def resume(self, operation_id: str, *, options):
            return OperationOutcome(
                operation_id=operation_id,
                status=OperationStatus.RUNNING,
                summary="Resumed.",
            )

    def _build_service(settings, event_sink=None):
        del event_sink
        captured["codex_command"] = settings.codex_acp.command
        captured["codex_model"] = settings.codex_acp.model
        captured["codex_effort"] = settings.codex_acp.reasoning_effort
        return FakeService()

    monkeypatch.setattr("agent_operator.cli.main.build_service", _build_service)

    result = runner.invoke(app, ["resume", operation_id])

    assert result.exit_code == 0
    assert captured["codex_command"] == "npx @zed-industries/codex-acp --"
    assert captured["codex_model"] == "gpt-5.4"
    assert captured["codex_effort"] == "high"


def test_tick_restores_effective_adapter_settings_from_event_sourced_metadata(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("OPERATOR_DATA_DIR", str(tmp_path))
    operation_id = "op-tick-es-settings"

    async def _seed() -> None:
        settings = OperatorSettings(data_dir=tmp_path)
        goal = OperationGoal(
            objective="Tick v2-only with restored settings",
            metadata={
                "effective_adapter_settings": {
                    "codex_acp": {
                        "command": "npx @zed-industries/codex-acp --",
                        "model": "gpt-5.4",
                        "reasoning_effort": "low",
                    }
                }
            },
        )
        service = build_replay_service(settings)
        birth = EventSourcedOperationBirthService(
            event_store=FileOperationEventStore(tmp_path / "operation_events"),
            checkpoint_store=FileOperationCheckpointStore(tmp_path / "operation_checkpoints"),
            projector=DefaultOperationProjector(),
        )
        state = OperationState(
            operation_id=operation_id,
            goal=goal,
            **state_settings(),
        )
        await birth.birth(state)
        await service.load(operation_id)

    anyio.run(_seed)
    captured: dict[str, object] = {}

    class FakeService:
        async def tick(self, operation_id: str) -> OperationOutcome:
            return OperationOutcome(
                operation_id=operation_id,
                status=OperationStatus.RUNNING,
                summary="Ticked.",
            )

    def _build_delivery(settings, *, operation_id: str, projector=None):
        del projector
        captured["operation_id"] = operation_id
        captured["codex_command"] = settings.codex_acp.command
        captured["codex_model"] = settings.codex_acp.model
        captured["codex_effort"] = settings.codex_acp.reasoning_effort
        return FakeService()

    monkeypatch.setattr(
        "agent_operator.cli.workflows.control_runtime.build_projecting_delivery_commands_service",
        _build_delivery,
    )

    result = runner.invoke(app, ["tick", operation_id])

    assert result.exit_code == 0
    assert captured["operation_id"] == operation_id
    assert captured["codex_command"] == "npx @zed-industries/codex-acp --"
    assert captured["codex_model"] == "gpt-5.4"
    assert captured["codex_effort"] == "low"


def test_resume_surfaces_connect_error_honestly(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("OPERATOR_DATA_DIR", str(tmp_path))
    operation_id = "op-resume-connect-error"
    store = FileOperationStore(tmp_path / "runs")

    async def _seed() -> None:
        state = OperationState(
            operation_id=operation_id,
            goal=OperationGoal(objective="Resume after answered attention."),
            **state_settings(),
            status=OperationStatus.RUNNING,
        )
        await store.save_operation(state)

    anyio.run(_seed)

    class FakeService:
        async def resume(self, operation_id: str, *, options):
            raise httpx.ConnectError(
                "[Errno 8] nodename nor servname provided, or not known",
                request=httpx.Request("POST", "https://api.openai.com/v1/responses"),
            )

    monkeypatch.setattr(
        "agent_operator.cli.main.build_service",
        lambda settings, event_sink=None: FakeService(),
    )

    result = runner.invoke(app, ["resume", operation_id])

    assert result.exit_code == 4
    rendered = result.stdout + result.stderr
    assert "ConnectError: [Errno 8] nodename nor servname provided, or not known" in rendered
    assert "Traceback" not in rendered


def test_watch_follows_live_attached_events_and_state(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("OPERATOR_DATA_DIR", str(tmp_path))
    operation_id = "op-watch-live"
    session = AgentSessionHandle(
        adapter_key="codex_acp",
        session_id="session-watch-1",
        session_name="repo-audit",
    )
    store = FileOperationStore(tmp_path / "runs")
    event_sink = JsonlEventSink(tmp_path, operation_id)

    async def _seed() -> None:
        state = OperationState(
            operation_id=operation_id,
            goal=OperationGoal(objective="Inspect the repo"),
            **state_settings(),
            status=OperationStatus.RUNNING,
            sessions=[
                SessionRecord(
                    handle=session,
                    status=SessionRecordStatus.RUNNING,
                    waiting_reason="Inspecting the repository layout.",
                )
            ],
            current_focus=FocusState.model_validate(
                {
                    "kind": "session",
                    "target_id": session.session_id,
                    "mode": "blocking",
                    "blocking_reason": "Inspecting the repository layout.",
                    "interrupt_policy": "terminal_only",
                    "resume_policy": "replan",
                }
            ),
        )
        await store.save_operation(state)
        await event_sink.emit(
            RunEvent(
                event_type="operation.started",
                operation_id=operation_id,
                iteration=0,
                payload={"objective": "Inspect the repo"},
                category="trace",
            )
        )
        await event_sink.emit(
            RunEvent(
                event_type="agent.invocation.started",
                operation_id=operation_id,
                iteration=1,
                session_id=session.session_id,
                payload={
                    "adapter_key": "codex_acp",
                    "session_name": "repo-audit",
                },
                category="trace",
            )
        )

    anyio.run(_seed)

    result_holder: dict[str, object] = {}

    def _watch() -> None:
        result_holder["result"] = runner.invoke(
            app,
            ["watch", operation_id, "--poll-interval", "0.05"],
        )

    thread = threading.Thread(target=_watch)
    thread.start()
    time.sleep(0.15)

    async def _finish() -> None:
        state = await store.load_operation(operation_id)
        assert state is not None
        state.status = OperationStatus.COMPLETED
        state.final_summary = "Live attached watch completed."
        state.sessions[0].status = SessionRecordStatus.COMPLETED
        state.sessions[0].waiting_reason = "Repo inspection finished."
        await store.save_operation(state)
        await event_sink.emit(
            RunEvent(
                event_type="agent.invocation.completed",
                operation_id=operation_id,
                iteration=1,
                session_id=session.session_id,
                payload={
                    "status": "success",
                    "output_text": "Repo inspection finished.",
                },
                category="trace",
            )
        )
        await store.save_outcome(
            OperationOutcome(
                operation_id=operation_id,
                status=OperationStatus.COMPLETED,
                summary="Live attached watch completed.",
            )
        )

    anyio.run(_finish)
    thread.join(timeout=2)

    assert not thread.is_alive()
    result = result_holder["result"]
    assert result.exit_code == 0
    assert "starting: Inspect the repo" in result.stdout
    assert "[iter 1] agent started: codex_acp session=session-watch-1 name=repo-audit" in (
        result.stdout
    )
    assert (
        "Operation op-watch-live [RUNNING]" in result.stdout
        or "Operation op-watch-live [COMPLETED]" in result.stdout
    )
    assert "Agent: codex_acp | session-watch-1" in result.stdout
    assert (
        "Wait: Inspecting the repository layout." in result.stdout
        or "Wait: Repo inspection finished." in result.stdout
    )
    assert "Attention: none" in result.stdout
    assert "[iter 1] agent completed: success | Repo inspection finished." in result.stdout
    assert "completed: Live attached watch completed." in result.stdout


def test_watch_once_emits_single_snapshot_and_exits(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("OPERATOR_DATA_DIR", str(tmp_path))
    operation_id = "op-watch-once"
    store = FileOperationStore(tmp_path / "runs")

    async def _seed() -> None:
        state = OperationState(
            operation_id=operation_id,
            goal=OperationGoal(objective="Inspect the repo"),
            **state_settings(),
            status=OperationStatus.RUNNING,
            final_summary="Working.",
        )
        await store.save_operation(state)

    anyio.run(_seed)

    result = runner.invoke(app, ["watch", operation_id, "--once", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["operation_id"] == operation_id
    assert payload["status"] == "running"


def test_watch_resolves_last_operation_reference(tmp_path: Path, monkeypatch) -> None:
    operation_id = "op-watch-last"
    runs_dir = tmp_path / "runs"
    store = FileOperationStore(runs_dir)
    event_sink = JsonlEventSink(tmp_path, operation_id)

    async def _seed() -> None:
        state = OperationState(
            operation_id=operation_id,
            goal=OperationGoal(objective="Inspect the repo"),
            **state_settings(),
            status=OperationStatus.COMPLETED,
            final_summary="Watch target completed.",
        )
        await store.save_operation(state)
        await event_sink.emit(
            RunEvent(
                event_type="operation.started",
                operation_id=operation_id,
                iteration=0,
                payload={"objective": "Inspect the repo"},
                category="trace",
            )
        )
        await store.save_outcome(
            OperationOutcome(
                operation_id=operation_id,
                status=OperationStatus.COMPLETED,
                summary="Watch target completed.",
            )
        )

    anyio.run(_seed)
    monkeypatch.setenv("OPERATOR_DATA_DIR", str(tmp_path))

    result = runner.invoke(app, ["watch", "last", "--poll-interval", "0.05"])

    assert result.exit_code == 0
    assert "Operation op-watch-last" in result.stdout
    assert "completed: Watch target completed." in result.stdout


def test_format_live_snapshot_surfaces_typed_attention_brief() -> None:
    snapshot = {
        "operation_id": "op-1",
        "status": "needs_human",
        "scheduler_state": "active",
        "open_attention_count": 1,
        "attention_brief": "[policy_gap] Testing policy is missing",
        "action_hint": "operator answer op-1 attention-1 --text '...'",
        "summary": "Blocked on attention request: Testing policy is missing.",
    }

    formatted = _format_live_snapshot(snapshot)

    assert "Operation op-1 [NEEDS_HUMAN]" in formatted
    assert "Attention: 1 open; [policy_gap] Testing policy is missing" in formatted
    assert "Action: operator answer op-1 attention-1 --text '...'" in formatted


def test_format_live_snapshot_surfaces_attention_absence_explicitly() -> None:
    snapshot = {
        "operation_id": "op-2",
        "status": "running",
        "scheduler_state": "active",
        "focus": "Inspecting repository boundaries.",
        "summary": "Inspecting repository boundaries.",
    }

    formatted = _format_live_snapshot(snapshot)

    assert "Operation op-2 [RUNNING]" in formatted
    assert "Attention: none" in formatted


def test_render_watch_snapshot_keeps_compact_live_summary() -> None:
    snapshot = {
        "operation_id": "op-watch-1",
        "status": "running",
        "focus": "Implement the operation watch live surface.",
        "session_id": "session-1",
        "adapter_key": "codex_acp",
        "latest_turn": {
            "agent_key": "codex_acp",
            "session_display_name": "repo-audit",
            "assignment_brief": "editing watch formatting and focused tests",
        },
        "waiting_reason": "Waiting for the current agent turn to finish.",
        "open_attention_count": 0,
        "summary": {
            "work_summary": "Updated the watch output contract and focused tests.",
        },
    }

    rendered = render_watch_snapshot(
        snapshot,
        latest_update="[iter 4] agent completed: success | Updated watch rendering.",
    )

    assert "Operation op-watch-1 [RUNNING]" in rendered
    assert "Agent: codex_acp | repo-audit" in rendered
    assert "Task: editing watch formatting and focused tests" in rendered
    assert "Attention: none" in rendered
    assert "Recent: [iter 4] agent completed: success | Updated watch rendering." in rendered
    assert "scheduler=" not in rendered


def test_render_watch_snapshot_omits_recent_line_without_update() -> None:
    snapshot = {
        "operation_id": "op-watch-2",
        "status": "needs_human",
        "attention_brief": "[approval_request] Approve deploy",
        "open_attention_count": 1,
        "action_hint": "operator answer op-watch-2 attention-1 --text 'Approved.'",
        "summary": "Blocked on approval request.",
    }

    rendered = render_watch_snapshot(snapshot, latest_update=None)

    assert "Attention: 1 open; [approval_request] Approve deploy" in rendered
    assert "Action: operator answer op-watch-2 attention-1 --text 'Approved.'" in rendered
    assert "Recent:" not in rendered


def test_unpause_resumes_paused_attached_operation(tmp_path: Path, monkeypatch) -> None:
    operation_id = _seed_paused_operation(tmp_path)
    monkeypatch.setenv("OPERATOR_DATA_DIR", str(tmp_path))

    class FakeService:
        async def resume(self, operation_id: str, *, options):
            assert options.run_mode.value == "attached"
            return OperationOutcome(
                operation_id=operation_id,
                status=OperationStatus.RUNNING,
                summary="Resumed attached operation.",
            )

    monkeypatch.setattr(
        "agent_operator.cli.main.build_service",
        lambda settings, event_sink=None: FakeService(),
    )

    result = runner.invoke(app, ["unpause", operation_id])

    assert result.exit_code == 0
    assert "enqueued: resume_operator" in result.stdout
    assert "running: Resumed attached operation." in result.stdout


def test_answer_resumes_blocked_attached_operation(tmp_path: Path, monkeypatch) -> None:
    operation_id, attention_id = _seed_blocked_attention_operation(tmp_path)
    monkeypatch.setenv("OPERATOR_DATA_DIR", str(tmp_path))

    class FakeService:
        async def resume(self, operation_id: str, *, options):
            assert options.run_mode.value == "attached"
            return OperationOutcome(
                operation_id=operation_id,
                status=OperationStatus.RUNNING,
                summary="Replanned after attention answer.",
            )

    monkeypatch.setattr(
        "agent_operator.cli.main.build_service",
        lambda settings, event_sink=None: FakeService(),
    )

    result = runner.invoke(
        app,
        ["answer", operation_id, attention_id, "--text", "Use staging."],
    )

    assert result.exit_code == 0
    assert "enqueued: answer_attention_request" in result.stdout
    assert "running: Replanned after attention answer." in result.stdout


def test_answer_without_attention_id_uses_oldest_blocking_attention(
    tmp_path: Path,
    monkeypatch,
) -> None:
    operation_id, _ = _seed_blocked_attention_operation(tmp_path)
    monkeypatch.setenv("OPERATOR_DATA_DIR", str(tmp_path))

    class FakeService:
        async def resume(self, operation_id: str, *, options):
            return OperationOutcome(
                operation_id=operation_id,
                status=OperationStatus.RUNNING,
                summary="Replanned after attention answer.",
            )

    monkeypatch.setattr(
        "agent_operator.cli.main.build_service",
        lambda settings, event_sink=None: FakeService(),
    )

    result = runner.invoke(
        app,
        ["answer", operation_id, "--text", "Use staging."],
    )

    assert result.exit_code == 0
    record = _read_control_intent(tmp_path)
    assert record.command is not None
    assert record.command.command_type is OperationCommandType.ANSWER_ATTENTION_REQUEST
    assert record.command.target_scope is CommandTargetScope.ATTENTION_REQUEST
    assert record.command.target_id is not None


def test_answer_accepts_last_operation_reference(tmp_path: Path, monkeypatch) -> None:
    older_id, older_attention_id = _seed_blocked_attention_operation(tmp_path)
    runs_dir = tmp_path / "runs"
    store = FileOperationStore(runs_dir)
    newer_id = "op-cli-attention-newer"
    newer_attention_id = "attention-newer"

    async def _seed_newer() -> None:
        newer_state = OperationState(
            operation_id=newer_id,
            goal=OperationGoal(objective="Second blocked operation"),
            **state_settings(),
            status=OperationStatus.NEEDS_HUMAN,
            attention_requests=[
                AttentionRequest(
                    attention_id=newer_attention_id,
                    operation_id=newer_id,
                    attention_type=AttentionType.APPROVAL_REQUEST,
                    title="Approve prod deploy",
                    question="Approve prod deploy?",
                    target_scope=CommandTargetScope.OPERATION,
                    target_id=newer_id,
                    blocking=True,
                    status=AttentionStatus.OPEN,
                )
            ],
        )
        newer_state.current_focus = FocusState.model_validate(
            {
                "kind": "attention_request",
                "target_id": newer_attention_id,
                "mode": "blocking",
                "blocking_reason": "Waiting for approval.",
                "interrupt_policy": "material_wakeup",
                "resume_policy": "replan",
            }
        )
        await store.save_operation(newer_state)

    anyio.run(_seed_newer)
    monkeypatch.setenv("OPERATOR_DATA_DIR", str(tmp_path))

    class FakeService:
        async def resume(self, operation_id: str, *, options):
            return OperationOutcome(
                operation_id=operation_id,
                status=OperationStatus.RUNNING,
                summary="Replanned after attention answer.",
            )

    monkeypatch.setattr(
        "agent_operator.cli.main.build_service",
        lambda settings, event_sink=None: FakeService(),
    )

    result = runner.invoke(app, ["answer", "last", "--text", "Approved."])

    assert result.exit_code == 0
    record = _read_control_intent(tmp_path)
    assert record.command is not None
    assert record.command.operation_id == newer_id
    assert record.command.target_id == newer_attention_id


def test_interrupt_accepts_short_operation_prefix(tmp_path: Path, monkeypatch) -> None:
    operation_id = "12345678-aaaa-bbbb-cccc-1234567890ab"
    runs_dir = tmp_path / "runs"
    store = FileOperationStore(runs_dir)

    async def _seed() -> None:
        state = OperationState(
            operation_id=operation_id,
            goal=OperationGoal(objective="Interrupt by prefix"),
            **state_settings(),
            status=OperationStatus.RUNNING,
            sessions=[
                SessionRecord(
                    handle=AgentSessionHandle(
                        adapter_key="codex_acp",
                        session_id="session-prefix",
                        session_name="repo-audit",
                    ),
                    status=SessionRecordStatus.RUNNING,
                )
            ],
            current_focus=FocusState.model_validate(
                {
                    "kind": "session",
                    "target_id": "session-prefix",
                    "mode": "blocking",
                    "blocking_reason": "Waiting for the active turn.",
                    "interrupt_policy": "terminal_only",
                    "resume_policy": "replan",
                }
            ),
        )
        await store.save_operation(state)

    anyio.run(_seed)
    monkeypatch.setenv("OPERATOR_DATA_DIR", str(tmp_path))

    result = runner.invoke(app, ["interrupt", "12345678"])

    assert result.exit_code == 0
    record = _read_control_intent(tmp_path)
    assert record.command is not None
    assert record.command.command_type is OperationCommandType.STOP_AGENT_TURN
    assert record.command.operation_id == operation_id


def test_interrupt_enqueues_session_targeted_command(tmp_path: Path, monkeypatch) -> None:
    operation_id = "op-cli-stop-turn"
    runs_dir = tmp_path / "runs"
    store = FileOperationStore(runs_dir)

    async def _seed() -> None:
        state = OperationState(
            operation_id=operation_id,
            goal=OperationGoal(objective="Stop the current turn"),
            **state_settings(),
            status=OperationStatus.RUNNING,
            sessions=[
                SessionRecord(
                    handle=AgentSessionHandle(
                        adapter_key="codex_acp",
                        session_id="session-stop-1",
                    ),
                    status=SessionRecordStatus.RUNNING,
                )
            ],
            current_focus=FocusState.model_validate(
                {
                    "kind": "session",
                    "target_id": "session-stop-1",
                    "mode": "blocking",
                    "blocking_reason": "Waiting for the active turn.",
                    "interrupt_policy": "terminal_only",
                    "resume_policy": "replan",
                }
            ),
        )
        await store.save_operation(state)

    anyio.run(_seed)
    monkeypatch.setenv("OPERATOR_DATA_DIR", str(tmp_path))

    result = runner.invoke(app, ["interrupt", operation_id])

    assert result.exit_code == 0
    assert "enqueued: stop_agent_turn" in result.stdout
    inbox = FileOperationCommandInbox(tmp_path / "commands")
    commands = anyio.run(inbox.list, operation_id)
    assert len(commands) == 1
    assert commands[0].command_type is OperationCommandType.STOP_AGENT_TURN
    assert commands[0].target_scope is CommandTargetScope.SESSION
    assert commands[0].target_id == "session-stop-1"


def test_interrupt_task_flag_resolves_bound_session(tmp_path: Path, monkeypatch) -> None:
    """--task routes stop_turn to the session bound to that task."""
    operation_id = "op-cli-stop-turn-task"
    runs_dir = tmp_path / "runs"
    store = FileOperationStore(runs_dir)

    task = TaskState(
        task_id="task-adr066",
        title="Task for stop_turn test",
        goal="Test --task flag",
        definition_of_done="Done.",
        status=TaskStatus.RUNNING,
    )

    async def _seed() -> None:
        state = OperationState(
            operation_id=operation_id,
            goal=OperationGoal(objective="Stop a specific task turn"),
            **state_settings(),
            status=OperationStatus.RUNNING,
            tasks=[task],
            sessions=[
                SessionRecord(
                    handle=AgentSessionHandle(
                        adapter_key="codex_acp",
                        session_id="session-task-bound",
                    ),
                    status=SessionRecordStatus.RUNNING,
                    bound_task_ids=["task-adr066"],
                )
            ],
        )
        await store.save_operation(state)

    anyio.run(_seed)
    monkeypatch.setenv("OPERATOR_DATA_DIR", str(tmp_path))

    # Use the task UUID
    result = runner.invoke(app, ["interrupt", operation_id, "--task", "task-adr066"])

    assert result.exit_code == 0, result.output
    assert "enqueued: stop_agent_turn" in result.stdout
    inbox = FileOperationCommandInbox(tmp_path / "commands")
    commands = anyio.run(inbox.list, operation_id)
    assert len(commands) == 1
    assert commands[0].target_id == "session-task-bound"


def test_interrupt_task_flag_short_id_resolves(tmp_path: Path, monkeypatch) -> None:
    """--task accepts the task-XXXX short display ID."""
    operation_id = "op-cli-stop-turn-short"
    runs_dir = tmp_path / "runs"
    store = FileOperationStore(runs_dir)

    task = TaskState(
        task_id="task-shortid-full",
        title="Task for short ID test",
        goal="Test short ID",
        definition_of_done="Done.",
        status=TaskStatus.RUNNING,
        task_short_id="aabbccdd",
    )

    async def _seed() -> None:
        state = OperationState(
            operation_id=operation_id,
            goal=OperationGoal(objective="Stop via short ID"),
            **state_settings(),
            status=OperationStatus.RUNNING,
            tasks=[task],
            sessions=[
                SessionRecord(
                    handle=AgentSessionHandle(
                        adapter_key="codex_acp",
                        session_id="session-short-bound",
                    ),
                    status=SessionRecordStatus.RUNNING,
                    bound_task_ids=["task-shortid-full"],
                )
            ],
        )
        await store.save_operation(state)

    anyio.run(_seed)
    monkeypatch.setenv("OPERATOR_DATA_DIR", str(tmp_path))

    # Use the short display ID with prefix
    result = runner.invoke(app, ["interrupt", operation_id, "--task", "task-aabbccdd"])

    assert result.exit_code == 0, result.output
    inbox = FileOperationCommandInbox(tmp_path / "commands")
    commands = anyio.run(inbox.list, operation_id)
    assert commands[0].target_id == "session-short-bound"


def test_interrupt_task_flag_invalid_state_rejected(tmp_path: Path, monkeypatch) -> None:
    """--task rejects with stop_turn_invalid_state when task is not RUNNING."""
    operation_id = "op-cli-stop-turn-invalid"
    runs_dir = tmp_path / "runs"
    store = FileOperationStore(runs_dir)

    task = TaskState(
        task_id="task-notrunning",
        title="Completed task",
        goal="Already done.",
        definition_of_done="Done.",
        status=TaskStatus.COMPLETED,
    )

    async def _seed() -> None:
        state = OperationState(
            operation_id=operation_id,
            goal=OperationGoal(objective="Test invalid state"),
            **state_settings(),
            status=OperationStatus.RUNNING,
            tasks=[task],
            sessions=[],
        )
        await store.save_operation(state)

    anyio.run(_seed)
    monkeypatch.setenv("OPERATOR_DATA_DIR", str(tmp_path))

    result = runner.invoke(app, ["interrupt", operation_id, "--task", "task-notrunning"])

    assert result.exit_code != 0
    assert "stop_turn_invalid_state" in result.output
