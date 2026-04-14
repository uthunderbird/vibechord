from __future__ import annotations

from agent_operator.domain import (
    CanonicalPersistenceMode,
    ExecutionBudget,
    OperationCheckpoint,
    OperationGoal,
    OperationPolicy,
    OperationState,
    RuntimeHints,
)


class OperationStateViewService:
    """Build ephemeral `OperationState` views from canonical checkpoints.

    These views are runtime-facing read models for prompting, reporting, and orchestration. They
    are not canonical persistence authority.

    Examples:
        >>> service = OperationStateViewService()
        >>> state = service.from_checkpoint(OperationCheckpoint.initial("op-1"))
        >>> state.operation_id
        'op-1'
    """

    def from_checkpoint(self, checkpoint: OperationCheckpoint) -> OperationState:
        """Project one canonical checkpoint into an in-memory operation-state view."""
        objective_payload = (
            checkpoint.objective.model_dump(mode="json")
            if checkpoint.objective is not None
            else {}
        )
        goal = OperationGoal(
            objective=objective_payload.get("objective", ""),
            harness_instructions=objective_payload.get("harness_instructions"),
            success_criteria=list(objective_payload.get("success_criteria", [])),
            metadata=dict(objective_payload.get("metadata", {})),
            external_ticket=(
                checkpoint.external_ticket.model_copy(deep=True)
                if checkpoint.external_ticket is not None
                else None
            ),
        )
        return OperationState(
            operation_id=checkpoint.operation_id,
            canonical_persistence_mode=CanonicalPersistenceMode.EVENT_SOURCED,
            goal=goal,
            policy=OperationPolicy(
                allowed_agents=list(checkpoint.allowed_agents),
                involvement_level=checkpoint.involvement_level,
            ),
            execution_budget=ExecutionBudget(),
            runtime_hints=RuntimeHints(),
            objective=(
                checkpoint.objective.model_copy(deep=True)
                if checkpoint.objective is not None
                else None
            ),
            status=checkpoint.status,
            tasks=[task.model_copy(deep=True) for task in checkpoint.tasks],
            sessions=[session.model_copy(deep=True) for session in checkpoint.sessions],
            executions=[execution.model_copy(deep=True) for execution in checkpoint.executions],
            attention_requests=[
                request.model_copy(deep=True)
                for request in checkpoint.attention_requests
            ],
            active_policies=[policy.model_copy(deep=True) for policy in checkpoint.active_policies],
            policy_coverage=checkpoint.policy_coverage.model_copy(deep=True),
            involvement_level=checkpoint.involvement_level,
            processed_command_ids=list(checkpoint.processed_command_ids),
            scheduler_state=checkpoint.scheduler_state,
            operator_messages=[
                message.model_copy(deep=True)
                for message in checkpoint.operator_messages
            ],
            current_focus=(
                checkpoint.current_focus.model_copy(deep=True)
                if checkpoint.current_focus is not None
                else None
            ),
            final_summary=checkpoint.final_summary,
            created_at=checkpoint.created_at,
            updated_at=checkpoint.updated_at,
        )
