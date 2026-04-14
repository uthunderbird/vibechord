from __future__ import annotations

import sys
from datetime import UTC, datetime
from typing import Protocol

from agent_operator.domain import OperationStatus, TaskStatus


class OperationStore(Protocol):
    async def load_operation(self, operation_id: str): ...


class LifecycleCoordinator(Protocol):
    def mark_failed(self, state, *, summary: str) -> None: ...

    async def finalize_outcome(self, state): ...


class OperatorServiceWithLifecycle(Protocol):
    _store: OperationStore
    _operation_lifecycle_coordinator: LifecycleCoordinator

    async def run(
        self,
        goal,
        *,
        policy,
        budget,
        runtime_hints,
        options,
        operation_id: str,
        attached_sessions=None,
    ): ...


async def finalize_startup_failure(
    *,
    service: OperatorServiceWithLifecycle,
    operation_id: str,
    summary: str,
) -> None:
    state = await service._store.load_operation(operation_id)
    if state is None:
        return
    operation_terminal = state.status in {
        OperationStatus.COMPLETED,
        OperationStatus.FAILED,
        OperationStatus.CANCELLED,
    }
    root_task_terminal = bool(state.tasks) and state.tasks[0].status in {
        TaskStatus.COMPLETED,
        TaskStatus.FAILED,
        TaskStatus.CANCELLED,
    }
    if operation_terminal or root_task_terminal:
        return
    state.updated_at = datetime.now(UTC)
    if state.tasks:
        root_task = state.tasks[0]
        if root_task.status not in {
            TaskStatus.COMPLETED,
            TaskStatus.FAILED,
            TaskStatus.CANCELLED,
        }:
            root_task.status = TaskStatus.FAILED
            root_task.updated_at = state.updated_at
    service._operation_lifecycle_coordinator.mark_failed(state, summary=summary)
    await service._operation_lifecycle_coordinator.finalize_outcome(state)


async def run_with_startup_failure_handling(
    *,
    service: OperatorServiceWithLifecycle,
    goal,
    policy,
    budget,
    runtime_hints,
    options,
    operation_id: str,
    attached_sessions,
):
    try:
        return await service.run(
            goal,
            policy=policy,
            budget=budget,
            runtime_hints=runtime_hints,
            options=options,
            operation_id=operation_id,
            attached_sessions=attached_sessions,
        )
    except Exception:
        summary = "Operation failed during startup."
        _exc_type, exc, _tb = sys.exc_info()
        if exc is not None:
            summary = str(exc) or summary
        await finalize_startup_failure(
            service=service,
            operation_id=operation_id,
            summary=summary,
        )
        raise
