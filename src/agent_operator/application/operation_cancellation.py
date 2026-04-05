from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from agent_operator.application.operation_lifecycle import OperationLifecycleCoordinator
from agent_operator.domain import (
    ExecutionState,
    OperationOutcome,
    OperationState,
    RunEventKind,
    SessionState,
)
from agent_operator.protocols import AgentRunSupervisor, EventSink, OperationStore


class BackgroundRunFinder(Protocol):
    """Callback used to find a background run inside one operation state."""

    def __call__(self, state: OperationState, run_id: str) -> ExecutionState | None: ...


class SessionRecordFinder(Protocol):
    """Callback used to find a session record inside one operation state."""

    def __call__(self, state: OperationState, session_id: str) -> SessionState | None: ...


class LatestResultFinder(Protocol):
    """Callback used to obtain the latest result for outcome construction."""

    def __call__(self, state: OperationState): ...


class WakeupEmitter(Protocol):
    """Callback used to emit cancellation wakeup events."""

    async def __call__(
        self,
        event_type: str,
        state: OperationState,
        iteration: int,
        payload: dict[str, object],
        *,
        task_id: str | None = None,
        session_id: str | None = None,
        kind: RunEventKind = RunEventKind.TRACE,
    ) -> None: ...


class HistoryLedger(Protocol):
    async def append(self, state: OperationState, outcome: OperationOutcome) -> None: ...


@dataclass(slots=True)
class OperationCancellationService:
    """Own cancellation-state mutation outside the public OperatorService facade.

    Examples:
        >>> service = OperationCancellationService(store=None, event_sink=None)  # doctest: +SKIP
    """

    store: OperationStore
    event_sink: EventSink
    supervisor: AgentRunSupervisor | None = None
    history_ledger: HistoryLedger | None = None
    lifecycle_coordinator: OperationLifecycleCoordinator | None = None

    async def cancel(
        self,
        *,
        operation_id: str,
        session_id: str | None,
        run_id: str | None,
        find_background_run: BackgroundRunFinder,
        find_session_record: SessionRecordFinder,
        find_latest_result: LatestResultFinder,
        emit: WakeupEmitter,
    ) -> OperationOutcome:
        """Apply cancellation semantics and persist updated state.

        Args:
            operation_id: Target operation identifier.
            session_id: Optional session cancellation target.
            run_id: Optional background run cancellation target.
            find_background_run: Background run lookup callback.
            find_session_record: Session lookup callback.
            find_latest_result: Latest result lookup callback.
            emit: Event emission callback owned by the facade.

        Returns:
            Operation outcome reflecting cancellation request handling.
        """
        state = await self.store.load_operation(operation_id)
        if state is None:
            raise RuntimeError(f"Operation {operation_id!r} was not found.")
        record = None
        if run_id is not None:
            run = find_background_run(state, run_id)
            if run is None:
                raise RuntimeError(f"Background run {run_id!r} was not found.")
            if self.supervisor is not None:
                await self.supervisor.cancel_background_turn(run_id)
            record = find_session_record(state, run.session_id)
        elif session_id is not None:
            record = find_session_record(state, session_id)
            if record is None:
                raise RuntimeError(f"Session {session_id!r} was not found.")
            if record.current_execution_id and self.supervisor is not None:
                await self.supervisor.cancel_background_turn(record.current_execution_id)
                run_id = record.current_execution_id
        else:
            coordinator = self.lifecycle_coordinator or OperationLifecycleCoordinator(
                store=self.store,
                history_ledger=self.history_ledger,
            )
            return await coordinator.cancel_operation(
                state,
                final_result=find_latest_result(state),
            )
        if record is not None:
            state.updated_at = datetime.now(UTC)
        coordinator = self.lifecycle_coordinator or OperationLifecycleCoordinator(
            store=self.store,
            history_ledger=self.history_ledger,
        )
        return await coordinator.cancel_scoped_execution(
            state,
            record=record,
            run_id=run_id,
            final_result=find_latest_result(state),
            emit_cancel_wakeup=(
                None
                if record is None or not run_id
                else lambda: emit(
                    "background_run.cancelled",
                    state,
                    record.latest_iteration or len(state.iterations),
                    {"run_id": run_id, "adapter_key": record.adapter_key},
                    task_id=record.bound_task_ids[-1] if record.bound_task_ids else None,
                    session_id=record.session_id,
                    kind=RunEventKind.WAKEUP,
                )
            ),
        )
