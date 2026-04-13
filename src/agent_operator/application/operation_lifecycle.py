from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from agent_operator.domain import (
    AgentResult,
    AgentSessionHandle,
    CanonicalPersistenceMode,
    FocusMode,
    IterationState,
    OperationDomainEventDraft,
    OperationOutcome,
    OperationState,
    OperationStatus,
    SessionState,
    SessionStatus,
    TaskState,
)
from agent_operator.protocols import OperationEventStore, OperationStore


class LifecycleReplayService(Protocol):
    async def load(self, operation_id: str): ...

    def advance(self, state, events): ...

    async def materialize(self, state): ...


class HistoryLedger(Protocol):
    async def append(self, state: OperationState, outcome: OperationOutcome) -> None: ...


class AgentResultHandler(Protocol):
    async def __call__(
        self,
        state: OperationState,
        iteration: IterationState,
        task: TaskState | None,
        session: AgentSessionHandle,
        result: AgentResult,
        *,
        wakeup_event_id: str | None = None,
    ) -> None: ...


class IterationBriefRecorder(Protocol):
    async def __call__(
        self,
        state: OperationState,
        iteration: IterationState,
        task: TaskState | None,
    ) -> None: ...


@dataclass(slots=True)
class OperationLifecycleCoordinator:
    """Own durable lifecycle closure sequencing for one operation."""

    store: OperationStore
    history_ledger: HistoryLedger | None = None
    event_store: OperationEventStore | None = None
    replay_service: LifecycleReplayService | None = None

    def mark_running(self, state: OperationState) -> None:
        state.status = OperationStatus.RUNNING
        state.final_summary = None
        state.objective_state.summary = None

    def mark_completed(self, state: OperationState, *, summary: str) -> None:
        state.status = OperationStatus.COMPLETED
        state.final_summary = summary
        state.objective_state.summary = summary

    def mark_failed(self, state: OperationState, *, summary: str) -> None:
        state.status = OperationStatus.FAILED
        state.final_summary = summary
        state.objective_state.summary = summary

    def mark_cancelled(self, state: OperationState, *, summary: str) -> None:
        state.status = OperationStatus.CANCELLED
        state.final_summary = summary
        state.objective_state.summary = summary

    def mark_needs_human(self, state: OperationState, *, summary: str) -> None:
        state.status = OperationStatus.NEEDS_HUMAN
        state.final_summary = summary
        state.objective_state.summary = summary

    async def finalize_outcome(
        self,
        state: OperationState,
        *,
        summary: str | None = None,
        final_result: AgentResult | None = None,
        history_statuses: frozenset[OperationStatus] = frozenset(
            {
                OperationStatus.COMPLETED,
                OperationStatus.FAILED,
                OperationStatus.CANCELLED,
            }
        ),
    ) -> OperationOutcome:
        if summary is not None:
            state.final_summary = summary
            state.objective_state.summary = summary
        outcome_summary = state.final_summary or ""
        outcome = OperationOutcome(
            operation_id=state.operation_id,
            status=state.status,
            summary=outcome_summary,
            ended_at=datetime.now(UTC),
            final_result=final_result,
        )
        await self._persist_terminal_status(state)
        await self.store.save_outcome(outcome)
        if self.history_ledger is not None and state.status in history_statuses:
            await self.history_ledger.append(state, outcome)
        return outcome

    async def cancel_operation(
        self,
        state: OperationState,
        *,
        final_result: AgentResult | None = None,
        summary: str = "Operation cancelled.",
    ) -> OperationOutcome:
        state.current_focus = None
        state.active_session = None
        for record in state.sessions:
            if record.status not in {
                SessionStatus.COMPLETED,
                SessionStatus.FAILED,
                SessionStatus.CANCELLED,
            }:
                record.status = SessionStatus.CANCELLED
                record.waiting_reason = "Cancelled by operator."
                record.updated_at = state.updated_at
        self.mark_cancelled(state, summary=summary)
        return await self.finalize_outcome(
            state,
            final_result=final_result,
        )

    async def cancel_scoped_execution(
        self,
        state: OperationState,
        *,
        record: SessionState | None,
        run_id: str | None,
        final_result: AgentResult | None = None,
        summary: str = "Cancellation requested.",
        emit_cancel_wakeup: Callable[[], Awaitable[None]] | None = None,
        emit_session_cancelled: Callable[[], Awaitable[None]] | None = None,
    ) -> OperationOutcome:
        if record is not None:
            record.status = SessionStatus.CANCELLED
            record.waiting_reason = "Cancelled by operator."
            record.updated_at = state.updated_at
        if run_id is not None and emit_cancel_wakeup is not None:
            await emit_cancel_wakeup()
        if record is not None and emit_session_cancelled is not None:
            await emit_session_cancelled()
        if record is not None:
            await self._persist_scoped_cancellation(record, state)
        return OperationOutcome(
            operation_id=state.operation_id,
            status=state.status,
            summary=summary,
            ended_at=datetime.now(UTC),
            final_result=final_result,
        )

    async def _persist_scoped_cancellation(
        self,
        record: SessionState,
        state: OperationState,
    ) -> None:
        await self._append_and_materialize(
            state,
            [
                OperationDomainEventDraft(
                    event_type="session.observed_state.changed",
                    payload={
                        "session_id": record.session_id,
                        "observed_state": record.observed_state.value,
                        "terminal_state": record.terminal_state.value,
                        "updated_at": record.updated_at.isoformat(),
                    },
                )
            ],
        )

    async def _persist_terminal_status(self, state: OperationState) -> None:
        await self._append_and_materialize(
            state,
            [
                OperationDomainEventDraft(
                    event_type="operation.status.changed",
                    payload={
                        "status": state.status.value,
                        "final_summary": state.final_summary,
                    },
                )
            ],
        )

    async def _append_and_materialize(
        self,
        state: OperationState,
        drafts: list[OperationDomainEventDraft],
    ) -> None:
        if (
            state.canonical_persistence_mode is not CanonicalPersistenceMode.EVENT_SOURCED
            or self.event_store is None
            or self.replay_service is None
        ):
            return
        replay_state = await self.replay_service.load(state.operation_id)
        stored_events = await self.event_store.append(
            state.operation_id,
            replay_state.last_applied_sequence,
            drafts,
        )
        await self.replay_service.materialize(
            self.replay_service.advance(replay_state, stored_events)
        )

    async def fold_reconciled_terminal_result(
        self,
        state: OperationState,
        *,
        iteration: IterationState,
        task: TaskState | None,
        session: AgentSessionHandle,
        result: AgentResult,
        handle_agent_result: AgentResultHandler,
        record_iteration_brief: IterationBriefRecorder,
        clear_blocking_focus: bool,
        wakeup_event_id: str | None = None,
    ) -> None:
        await handle_agent_result(
            state,
            iteration,
            task,
            session,
            result,
            wakeup_event_id=wakeup_event_id,
        )
        await record_iteration_brief(state, iteration, task)
        if (
            clear_blocking_focus
            and state.current_focus is not None
            and state.current_focus.mode is FocusMode.BLOCKING
            and state.current_focus.target_id == session.session_id
            and state.status is not OperationStatus.NEEDS_HUMAN
        ):
            state.current_focus = None
