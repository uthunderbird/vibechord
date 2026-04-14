from __future__ import annotations

from datetime import UTC, datetime

import pytest

from agent_operator.cli.workflows.run_support import finalize_startup_failure
from agent_operator.domain import (
    ExecutionBudget,
    InvolvementLevel,
    OperationGoal,
    OperationOutcome,
    OperationPolicy,
    OperationState,
    OperationStatus,
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
