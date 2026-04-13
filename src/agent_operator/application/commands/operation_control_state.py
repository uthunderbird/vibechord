from __future__ import annotations

from datetime import UTC, datetime

from agent_operator.application.queries.operation_state_views import OperationStateViewService
from agent_operator.application.queries.operation_traceability import OperationTraceabilityService
from agent_operator.domain import OperationCheckpoint, OperationState
from agent_operator.protocols import OperationStore


class OperationControlStateCoordinator:
    """Keep in-memory operation state aligned with durable control/checkpoint truth."""

    def __init__(
        self,
        *,
        store: OperationStore,
        traceability_service: OperationTraceabilityService,
        operation_state_view_service: OperationStateViewService | None = None,
    ) -> None:
        self._store = store
        self._traceability_service = traceability_service
        self._operation_state_view_service = (
            operation_state_view_service or OperationStateViewService()
        )

    async def persist_command_effect_state(
        self,
        state: OperationState,
        *,
        save_snapshot: bool = True,
    ) -> None:
        state.updated_at = datetime.now(UTC)
        await self._traceability_service.sync_traceability_artifacts(state)
        if save_snapshot:
            await self._store.save_operation(state)

    def remember_processed_command(self, state: OperationState, command_id: str) -> None:
        if command_id not in state.processed_command_ids:
            state.processed_command_ids.append(command_id)

    def refresh_state_from_checkpoint(
        self,
        state: OperationState,
        checkpoint: OperationCheckpoint,
    ) -> None:
        refreshed = self._operation_state_view_service.from_checkpoint(checkpoint)
        refreshed.policy = state.policy.model_copy(deep=True)
        refreshed.policy.involvement_level = refreshed.involvement_level
        refreshed.policy.allowed_agents = list(checkpoint.allowed_agents)
        refreshed.execution_budget = state.execution_budget.model_copy(deep=True)
        refreshed.runtime_hints = state.runtime_hints.model_copy(deep=True)
        refreshed.goal = state.goal.model_copy(deep=True)
        refreshed.run_started_at = state.run_started_at
        refreshed.iterations = [item.model_copy(deep=True) for item in state.iterations]
        refreshed.features = [item.model_copy(deep=True) for item in state.features]
        refreshed.memory_entries = [item.model_copy(deep=True) for item in state.memory_entries]
        refreshed.artifacts = [item.model_copy(deep=True) for item in state.artifacts]
        refreshed.operation_brief = (
            state.operation_brief.model_copy(deep=True)
            if state.operation_brief is not None
            else None
        )
        refreshed.pending_replan_command_ids = list(state.pending_replan_command_ids)
        if hasattr(state, "iteration_briefs"):
            refreshed.iteration_briefs = [
                item.model_copy(deep=True) for item in state.iteration_briefs
            ]
        if hasattr(state, "agent_turn_briefs"):
            refreshed.agent_turn_briefs = [
                item.model_copy(deep=True) for item in state.agent_turn_briefs
            ]
        if hasattr(state, "pending_wakeups"):
            refreshed.pending_wakeups = [
                item.model_copy(deep=True) for item in state.pending_wakeups
            ]
        if hasattr(state, "pending_attention_resolution_ids"):
            refreshed.pending_attention_resolution_ids = list(
                state.pending_attention_resolution_ids
            )
        if hasattr(state, "current_focus"):
            current_focus = state.current_focus
            refreshed.current_focus = (
                current_focus.model_copy(deep=True) if current_focus is not None else None
            )
        if hasattr(state, "active_session"):
            active_session = state.active_session
            refreshed.active_session = (
                active_session.model_copy(deep=True) if active_session is not None else None
            )

        for field_name in OperationState.model_fields:
            setattr(state, field_name, getattr(refreshed, field_name))
