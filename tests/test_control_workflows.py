from __future__ import annotations

import ast
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from agent_operator.cli.workflows.control_runtime import (
    _build_run_goal_metadata,
    _restore_operation_scoped_runtime_settings,
)
from agent_operator.cli.workflows.run_support import (
    finalize_startup_failure,
    run_with_startup_failure_handling,
)
from agent_operator.config import OperatorSettings
from agent_operator.domain import (
    ExecutionBudget,
    InvolvementLevel,
    OperationGoal,
    OperationOutcome,
    OperationPolicy,
    OperationState,
    OperationStatus,
    ProjectProfile,
    ProjectProfileAdapterSettings,
    ResolvedProjectRunConfig,
    RunMode,
    RunOptions,
    RuntimeHints,
    TaskStatus,
)


def _state_settings() -> dict[str, object]:
    return {
        "policy": OperationPolicy(involvement_level=InvolvementLevel.AUTO),
        "execution_budget": ExecutionBudget(max_iterations=4),
        "runtime_hints": RuntimeHints(metadata={"run_mode": "attached"}),
    }


class _MemoryStore:
    def __init__(self) -> None:
        self.operations: dict[str, OperationState] = {}
        self.outcomes: dict[str, OperationOutcome] = {}

    async def load_operation(self, operation_id: str) -> OperationState | None:
        return self.operations.get(operation_id)

    async def save_operation(self, state: OperationState) -> None:
        self.operations[state.operation_id] = state

    async def save_outcome(self, outcome: OperationOutcome) -> None:
        self.outcomes[outcome.operation_id] = outcome


class _LifecycleCoordinator:
    def __init__(self, store: _MemoryStore) -> None:
        self._store = store
        self.calls: list[str] = []

    def mark_failed(self, state: OperationState, *, summary: str) -> None:
        self.calls.append("mark_failed")
        state.status = OperationStatus.FAILED
        state.final_summary = summary
        state.objective_state.summary = summary

    async def finalize_outcome(self, state: OperationState) -> OperationOutcome:
        self.calls.append("finalize_outcome")
        await self._store.save_operation(state)
        outcome = OperationOutcome(
            operation_id=state.operation_id,
            status=state.status,
            summary=state.final_summary or "",
            ended_at=state.updated_at,
        )
        await self._store.save_outcome(outcome)
        return outcome


class _Service:
    def __init__(self, store: _MemoryStore, coordinator: _LifecycleCoordinator) -> None:
        self._store = store
        self._operation_lifecycle_coordinator = coordinator

    async def run(self, *args, **kwargs) -> OperationOutcome:
        raise RuntimeError("Operation failed during startup.")


CONTROL_WORKFLOW_FILE = (
    Path(__file__).resolve().parents[1]
    / "src"
    / "agent_operator"
    / "cli"
    / "workflows"
    / "control.py"
)
RUN_SUPPORT_FILE = (
    Path(__file__).resolve().parents[1]
    / "src"
    / "agent_operator"
    / "cli"
    / "workflows"
    / "run_support.py"
)


def test_build_run_goal_metadata_preserves_attach_and_profile_context() -> None:
    settings = OperatorSettings(data_dir=Path("/tmp/operator-data"))
    resolved = ResolvedProjectRunConfig(
        profile_name="demo",
        cwd=Path("/workspace/project"),
        default_agents=["codex_acp"],
        objective_text="Ship the change.",
        max_iterations=5,
        run_mode=RunMode.RESUMABLE,
        involvement_level=InvolvementLevel.AUTO,
    )
    profile = ProjectProfile(
        name="demo",
        adapter_settings={
            "codex_acp": ProjectProfileAdapterSettings(timeout_seconds=42),
        },
    )

    attached_sessions, metadata = _build_run_goal_metadata(
        settings=settings,
        resolved=resolved,
        data_dir_source="configured",
        profile=profile,
        selected_profile_path=Path("/workspace/project/operator-profile.yaml"),
        profile_source="local_profile_file",
        from_ticket="T-123",
        intake_result=SimpleNamespace(goal_text="Imported goal text."),
        objective="Ship the change.",
        attach_session="session-1",
        attach_agent="codex_acp",
        attach_name="existing",
        attach_working_dir=Path("/workspace/attached"),
    )

    assert [session.session_id for session in attached_sessions] == ["session-1"]
    assert attached_sessions[0].metadata == {"working_directory": "/workspace/attached"}
    assert metadata["working_directory"] == "/workspace/attached"
    assert metadata["attached_session_ids"] == ["session-1"]
    assert metadata["requires_same_agent_session"] is True
    assert metadata["external_ticket_ref"] == "T-123"
    assert metadata["external_ticket_context"] == "Imported goal text."
    assert metadata["project_profile_name"] == "demo"
    assert metadata["policy_scope"] == "profile:demo"
    assert metadata["project_profile_source"] == "local_profile_file"
    assert metadata["project_profile_path"] == "/workspace/project/operator-profile.yaml"
    assert metadata["data_dir_source"] == "configured"
    assert metadata["resolved_operator_launch"] == {
        "data_dir": "/tmp/operator-data",
        "data_dir_source": "configured",
        "profile_source": "local_profile_file",
        "profile_path": "/workspace/project/operator-profile.yaml",
    }
    assert metadata["effective_adapter_settings"] == {
        "codex_acp": settings.codex_acp.model_dump(mode="json")
    }


@pytest.mark.anyio
async def test_restore_operation_scoped_runtime_settings_prefers_snapshot_over_profile(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = OperatorSettings()
    profile_path = tmp_path / "operator-profile.yaml"
    profile_path.write_text(
        "name: demo\nadapter_settings:\n  codex_acp:\n    timeout_seconds: 90\n",
        encoding="utf-8",
    )
    operation = OperationState(
        operation_id="op-restore",
        goal=OperationGoal(
            objective="Resume work.",
            metadata={
                "effective_adapter_settings": {
                    "codex_acp": {"timeout_seconds": 17.0},
                },
                "project_profile_path": str(profile_path),
            },
        ),
        status=OperationStatus.RUNNING,
        **_state_settings(),
    )

    async def _load_operation(
        passed_settings: OperatorSettings, operation_id: str
    ) -> OperationState | None:
        assert passed_settings is settings
        assert operation_id == "op-restore"
        return operation

    monkeypatch.setattr(
        "agent_operator.cli.workflows.control_runtime.load_canonical_operation_state_async",
        _load_operation,
    )

    settings.codex_acp.timeout_seconds = 1.0
    await _restore_operation_scoped_runtime_settings(settings, "op-restore")

    assert settings.codex_acp.timeout_seconds == 17.0


@pytest.mark.anyio
async def test_finalize_startup_failure_routes_terminalization_through_lifecycle_coordinator(
) -> None:
    store = _MemoryStore()
    coordinator = _LifecycleCoordinator(store)
    service = _Service(store, coordinator)
    state = OperationState(
        operation_id="op-startup-fail",
        goal=OperationGoal(objective="Investigate ADR closure."),
        status=OperationStatus.RUNNING,
        **_state_settings(),
    )
    await store.save_operation(state)

    await finalize_startup_failure(
        service=service,
        operation_id=state.operation_id,
        summary="Operation failed during startup.",
    )

    persisted = await store.load_operation(state.operation_id)
    assert persisted is not None
    assert persisted.status is OperationStatus.FAILED
    assert persisted.tasks[0].status is TaskStatus.FAILED
    assert coordinator.calls == ["mark_failed", "finalize_outcome"]
    assert store.outcomes[state.operation_id].status is OperationStatus.FAILED


@pytest.mark.anyio
async def test_finalize_startup_failure_does_not_overwrite_completed_operation() -> None:
    store = _MemoryStore()
    coordinator = _LifecycleCoordinator(store)
    service = _Service(store, coordinator)
    state = OperationState(
        operation_id="op-startup-done",
        goal=OperationGoal(objective="Already complete."),
        status=OperationStatus.COMPLETED,
        final_summary="Attached turn completed successfully.",
        **_state_settings(),
    )
    state.tasks[0].status = TaskStatus.COMPLETED
    state.tasks[0].updated_at = datetime.now(UTC)
    await store.save_operation(state)

    await finalize_startup_failure(
        service=service,
        operation_id=state.operation_id,
        summary="Operation failed during startup.",
    )

    persisted = await store.load_operation(state.operation_id)
    assert persisted is not None
    assert persisted.status is OperationStatus.COMPLETED
    assert persisted.final_summary == "Attached turn completed successfully."
    assert coordinator.calls == []
    assert store.outcomes == {}


@pytest.mark.anyio
async def test_run_startup_failure_wrapper_uses_lifecycle_coordinator_path() -> None:
    store = _MemoryStore()
    coordinator = _LifecycleCoordinator(store)
    service = _Service(store, coordinator)
    state = OperationState(
        operation_id="op-run-startup-fail",
        goal=OperationGoal(objective="Launch run."),
        status=OperationStatus.RUNNING,
        **_state_settings(),
    )
    await store.save_operation(state)

    with pytest.raises(RuntimeError, match="Operation failed during startup."):
        await run_with_startup_failure_handling(
            service=service,
            goal=state.goal,
            policy=state.policy,
            budget=state.execution_budget,
            runtime_hints=state.runtime_hints,
            options=RunOptions(),
            operation_id=state.operation_id,
            attached_sessions=None,
        )

    persisted = await store.load_operation(state.operation_id)
    assert persisted is not None
    assert persisted.status is OperationStatus.FAILED
    assert persisted.tasks[0].status is TaskStatus.FAILED
    assert coordinator.calls == ["mark_failed", "finalize_outcome"]
    assert store.outcomes[state.operation_id].summary == "Operation failed during startup."


def test_control_run_async_delegates_startup_failure_handling_without_direct_persistence() -> None:
    source = CONTROL_WORKFLOW_FILE.read_text(encoding="utf-8")
    tree = ast.parse(source)
    run_async = next(
        node
        for node in tree.body
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "run_async"
    )

    helper_calls = [
        child
        for child in ast.walk(run_async)
        if isinstance(child, ast.Call)
        and isinstance(child.func, ast.Name)
        and child.func.id == "run_with_startup_failure_handling"
    ]
    direct_persistence = [
        child.lineno
        for child in ast.walk(run_async)
        if isinstance(child, ast.Attribute)
        and child.attr in {"save_operation", "save_outcome"}
    ]

    assert len(helper_calls) == 1
    assert direct_persistence == []


def test_run_support_startup_failure_terminalization_avoids_direct_persistence() -> None:
    source = RUN_SUPPORT_FILE.read_text(encoding="utf-8")
    tree = ast.parse(source)
    target_functions = {
        node.name: node
        for node in tree.body
        if isinstance(node, ast.AsyncFunctionDef)
        and node.name in {"finalize_startup_failure", "run_with_startup_failure_handling"}
    }

    assert set(target_functions) == {
        "finalize_startup_failure",
        "run_with_startup_failure_handling",
    }

    direct_persistence = [
        child.lineno
        for node in target_functions.values()
        for child in ast.walk(node)
        if isinstance(child, ast.Attribute)
        and child.attr in {"save_operation", "save_outcome"}
    ]
    coordinator_terminalization = [
        child.lineno
        for child in ast.walk(target_functions["finalize_startup_failure"])
        if isinstance(child, ast.Attribute)
        and child.attr in {"mark_failed", "finalize_outcome"}
    ]

    assert direct_persistence == []
    assert coordinator_terminalization
