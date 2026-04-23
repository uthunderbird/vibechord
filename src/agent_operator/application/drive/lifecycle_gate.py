"""LifecycleGate — pure predicate functions for drive loop continuation (ADR 0195).

No I/O, no async, no mutations. All methods are stateless predicates over
OperationAggregate + ProcessManagerContext. Independently testable without mocks.
"""
from __future__ import annotations

from datetime import UTC, datetime

from agent_operator.application.drive.process_manager_context import ProcessManagerContext
from agent_operator.domain.aggregate import OperationAggregate
from agent_operator.domain.enums import FocusKind, FocusMode, OperationStatus, SchedulerState


class LifecycleGate:
    """Pure predicate service for drive loop gating decisions."""

    def should_continue(
        self,
        agg: OperationAggregate,
        *,
        ctx: ProcessManagerContext,
        cycles_executed: int,
        cycle_budget: int,
    ) -> bool:
        """Return True if the while loop should run another iteration."""
        if ctx.draining:
            return False
        if agg.status in {
            OperationStatus.COMPLETED,
            OperationStatus.FAILED,
            OperationStatus.CANCELLED,
        }:
            return False
        if self.is_scheduler_paused(agg):
            return False
        if self.check_budget(agg, cycles_executed=cycles_executed, cycle_budget=cycle_budget):
            return False
        if agg.status is OperationStatus.NEEDS_HUMAN:
            # Only continue if there are pending attention resolutions or replan triggers
            return bool(agg.pending_attention_resolution_ids or agg.pending_replan_command_ids)
        return True

    def check_timeout(self, agg: OperationAggregate) -> bool:
        """Return True if the operation has exceeded its timeout."""
        timeout = agg.execution_budget.timeout_seconds
        if timeout is None:
            return False
        created = agg.created_at
        elapsed = (datetime.now(UTC) - created).total_seconds()
        return elapsed >= float(timeout)

    def check_budget(
        self,
        agg: OperationAggregate,
        *,
        cycles_executed: int,
        cycle_budget: int,
    ) -> bool:
        """Return True if max iterations or cycle budget is exhausted."""
        return cycles_executed >= cycle_budget

    def is_scheduler_paused(self, agg: OperationAggregate) -> bool:
        """Return True if the scheduler has been paused."""
        return agg.scheduler_state is SchedulerState.PAUSED

    def should_pause_materialize(self, agg: OperationAggregate) -> bool:
        """Return True if PAUSE_REQUESTED state can be materialized to PAUSED.

        Materialization is safe when no turn is actively running.
        The drive loop calls this before checking is_scheduler_paused().
        """
        return agg.scheduler_state is SchedulerState.PAUSE_REQUESTED

    def should_break_for_status(self, agg: OperationAggregate) -> bool:
        """Return True when status requires breaking out of the while loop."""
        return agg.status in {
            OperationStatus.COMPLETED,
            OperationStatus.FAILED,
            OperationStatus.CANCELLED,
            OperationStatus.NEEDS_HUMAN,
        }

    def is_blocked_on_background_wait(
        self,
        agg: OperationAggregate,
        ctx: ProcessManagerContext,
    ) -> bool:
        """Return True when the operation is blocked waiting for a background session result."""
        focus = agg.current_focus
        if focus is None or focus.mode is not FocusMode.BLOCKING:
            return False
        if focus.kind is not FocusKind.SESSION:
            return False
        session_ctx = ctx.session_contexts.get(focus.target_id)
        if session_ctx is None:
            return False
        return session_ctx.is_background_running
