from __future__ import annotations

from pathlib import Path

import pytest

from agent_operator.application.operation_runtime import SupervisorBackedOperationRuntime
from agent_operator.domain import (
    AgentResult,
    AgentResultStatus,
    AgentSessionHandle,
    BackgroundRunStatus,
    ExecutionState,
)
from agent_operator.dtos import AgentRunRequest


class FakeSupervisor:
    """Minimal background supervisor double for operation-runtime tests."""

    def __init__(self) -> None:
        self.dispatched: list[tuple[str, int, str, str | None, str | None]] = []
        self.cancelled: list[str] = []
        self.finalized: list[tuple[str, BackgroundRunStatus, str | None]] = []
        self.polled: dict[str, ExecutionState] = {}
        self.collected: dict[str, AgentResult] = {}

    async def start_background_turn(
        self,
        operation_id: str,
        iteration: int,
        adapter_key: str,
        request: AgentRunRequest,
        *,
        existing_session: AgentSessionHandle | None = None,
        task_id: str | None = None,
        wakeup_delivery: str = "enqueue",
    ) -> ExecutionState:
        self.dispatched.append(
            (
                operation_id,
                iteration,
                adapter_key,
                existing_session.session_id if existing_session is not None else None,
                task_id,
            )
        )
        return ExecutionState(
            run_id="run-1",
            operation_id=operation_id,
            adapter_key=adapter_key,
            session_id=existing_session.session_id if existing_session is not None else "session-1",
            task_id=task_id,
            iteration=iteration,
            status=BackgroundRunStatus.RUNNING,
        )

    async def poll_background_turn(self, run_id: str) -> ExecutionState | None:
        return self.polled.get(run_id)

    async def collect_background_turn(self, run_id: str) -> AgentResult | None:
        return self.collected.get(run_id)

    async def cancel_background_turn(self, run_id: str) -> None:
        self.cancelled.append(run_id)

    async def finalize_background_turn(
        self,
        run_id: str,
        status: BackgroundRunStatus,
        *,
        error: str | None = None,
    ) -> None:
        self.finalized.append((run_id, status, error))

    async def list_runs(self, operation_id: str) -> list[ExecutionState]:
        return [item for item in self.polled.values() if item.operation_id == operation_id]


@pytest.mark.anyio
async def test_operation_runtime_dispatches_background_turn() -> None:
    supervisor = FakeSupervisor()
    runtime = SupervisorBackedOperationRuntime(supervisor=supervisor)
    request = AgentRunRequest(
        goal="Ship the feature",
        instruction="Inspect the repository",
        session_name="repo-audit",
        one_shot=False,
        working_directory=Path.cwd(),
        metadata={},
    )

    run = await runtime.dispatch_background_turn(
        operation_id="op-1",
        iteration=1,
        adapter_key="codex_acp",
        request=request,
        task_id="task-1",
    )

    assert run.run_id == "run-1"
    assert supervisor.dispatched == [("op-1", 1, "codex_acp", None, "task-1")]


@pytest.mark.anyio
async def test_operation_runtime_cancels_many_runs_for_one_operation() -> None:
    supervisor = FakeSupervisor()
    runtime = SupervisorBackedOperationRuntime(supervisor=supervisor)

    await runtime.cancel_operation_runs(["run-1", "run-2"])

    assert supervisor.cancelled == ["run-1", "run-2"]


@pytest.mark.anyio
async def test_operation_runtime_proxies_poll_collect_and_finalize() -> None:
    supervisor = FakeSupervisor()
    runtime = SupervisorBackedOperationRuntime(supervisor=supervisor)
    supervisor.polled["run-1"] = ExecutionState(
        run_id="run-1",
        operation_id="op-1",
        adapter_key="codex_acp",
        status=BackgroundRunStatus.COMPLETED,
    )
    supervisor.collected["run-1"] = AgentResult(
        session_id="session-1",
        status=AgentResultStatus.SUCCESS,
        output_text="done",
    )

    polled = await runtime.poll_background_turn("run-1")
    collected = await runtime.collect_background_turn("run-1")
    await runtime.finalize_background_turn("run-1", BackgroundRunStatus.COMPLETED, error=None)

    assert polled is not None
    assert polled.status is BackgroundRunStatus.COMPLETED
    assert collected is not None
    assert collected.output_text == "done"
    assert supervisor.finalized == [("run-1", BackgroundRunStatus.COMPLETED, None)]
