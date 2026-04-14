from __future__ import annotations

import ast
from datetime import UTC, datetime
from pathlib import Path

import pytest

from agent_operator.cli.workflows.run_support import (
    finalize_startup_failure,
    run_with_startup_failure_handling,
)
from agent_operator.domain import (
    ExecutionBudget,
    InvolvementLevel,
    OperationGoal,
    OperationOutcome,
    OperationPolicy,
    OperationState,
    OperationStatus,
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
