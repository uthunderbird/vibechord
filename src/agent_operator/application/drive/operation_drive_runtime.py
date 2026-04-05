from __future__ import annotations

from collections.abc import Awaitable, Callable

from agent_operator.application.operation_runtime_context import OperationRuntimeContext
from agent_operator.application.operation_runtime_reconciliation import (
    OperationRuntimeReconciliationService,
)
from agent_operator.domain import OperationState, RunOptions


class OperationDriveRuntimeService:
    """Own runtime reconciliation and gating used by the drive loop."""

    def __init__(
        self,
        *,
        runtime_context: OperationRuntimeContext,
        runtime_reconciliation_service: OperationRuntimeReconciliationService,
        refresh_policy_context: Callable[[OperationState], Awaitable[None]],
    ) -> None:
        self._runtime_context = runtime_context
        self._runtime_reconciliation_service = runtime_reconciliation_service
        self._refresh_policy_context_impl = refresh_policy_context

    async def _refresh_policy_context(self, state: OperationState) -> None:
        await self._refresh_policy_context_impl(state)

    async def _refresh_available_agent_descriptors(self, state: OperationState) -> None:
        await self._runtime_context.refresh_available_agent_descriptors(state)

    async def _cleanup_orphaned_background_runs(self, state: OperationState) -> None:
        await self._runtime_reconciliation_service.cleanup_orphaned_background_runs(state)

    async def _clear_expired_session_cooldowns(self, state: OperationState) -> None:
        await self._runtime_reconciliation_service.clear_expired_session_cooldowns(state)

    async def _migrate_legacy_rate_limit_failures(self, state: OperationState) -> None:
        await self._runtime_reconciliation_service.migrate_legacy_rate_limit_failures(state)

    def _should_use_background_runtime(self, options: RunOptions) -> bool:
        return self._runtime_context.should_use_background_runtime(options)

    async def _sync_terminal_background_runs(self, state: OperationState) -> None:
        await self._runtime_reconciliation_service.sync_terminal_background_runs(state)

    async def _reconcile_stale_background_runs(self, state: OperationState) -> None:
        await self._runtime_reconciliation_service.reconcile_stale_background_runs(state)

    async def _reconcile_background_wakeups(self, state: OperationState) -> None:
        await self._runtime_reconciliation_service.reconcile_background_wakeups(state)

    def _is_blocked_on_background_wait(self, state: OperationState) -> bool:
        return self._runtime_context.is_blocked_on_background_wait(state)

    def _materialize_pause_if_ready(self, state: OperationState) -> None:
        self._runtime_reconciliation_service.materialize_pause_if_ready(state)

    def _is_scheduler_paused(self, state: OperationState) -> bool:
        return self._runtime_reconciliation_service.is_scheduler_paused(state)

    def _should_retry_from_recoverable_block(self, state: OperationState) -> bool:
        return self._runtime_context.should_retry_from_recoverable_block(state)

    def _reconcile_state(self, state: OperationState) -> None:
        self._runtime_reconciliation_service.reconcile_state(state)
