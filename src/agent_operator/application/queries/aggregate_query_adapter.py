"""Layer 3a bridge: OperationAggregate → OperationState + aggregate-accepting query facade.

Removed in full Layer 3 rewrite when OperationProjectionService is updated to accept
OperationAggregate directly.
"""
from __future__ import annotations

from typing import Protocol

from agent_operator.domain.aggregate import OperationAggregate
from agent_operator.domain.enums import AttentionStatus, SchedulerState
from agent_operator.domain.operation import OperationOutcome, OperationState
from agent_operator.domain.policy import PolicyCoverage


class ProjectionService(Protocol):
    """Temporary v1 projection surface consumed by the aggregate query bridge."""

    def build_live_snapshot(
        self,
        state: OperationState,
        outcome: OperationOutcome | None,
        *,
        runtime_alert: str | None = None,
    ) -> dict[str, object]: ...

    def build_durable_truth_payload(
        self,
        state: OperationState,
        *,
        include_inactive_memory: bool = False,
    ) -> dict[str, object]: ...


def aggregate_to_state(agg: OperationAggregate) -> OperationState:
    """Convert OperationAggregate to OperationState for the v1 projection layer.

    Layer 3a bridge — removed when OperationProjectionService is rewritten in full Layer 3.
    Only fields that OperationProjectionService actually reads are populated.
    """
    return OperationState(
        goal=agg.goal,
        operation_id=agg.operation_id,
        policy=agg.policy,
        execution_budget=agg.execution_budget,
        runtime_hints=agg.runtime_hints,
        execution_profile_overrides=dict(agg.execution_profile_overrides),
        status=agg.status,
        objective=agg.objective,
        tasks=list(agg.tasks),
        features=list(agg.features),
        sessions=list(agg.sessions),
        executions=list(agg.executions),
        artifacts=list(agg.artifacts),
        memory_entries=list(agg.memory_entries),
        current_focus=agg.current_focus,
        attention_requests=list(agg.attention_requests),
        active_policies=[],
        policy_coverage=PolicyCoverage(),
        involvement_level=agg.policy.involvement_level,
        scheduler_state=agg.scheduler_state,
        operator_messages=list(agg.operator_messages),
        final_summary=agg.final_summary,
    )


class AggregateQueryAdapter:
    """Aggregate-accepting facade over OperationProjectionService.

    Layer 3a bridge — accepts OperationAggregate, converts to OperationState,
    delegates to the existing projection service. Removed in full Layer 3 rewrite.
    """

    def __init__(self, projection_service: ProjectionService) -> None:
        self._projection_service = projection_service

    def build_live_snapshot(
        self,
        agg: OperationAggregate,
        outcome: OperationOutcome | None,
        *,
        runtime_alert: str | None = None,
    ) -> dict[str, object]:
        state = aggregate_to_state(agg)
        return self._projection_service.build_live_snapshot(
            state, outcome, runtime_alert=runtime_alert
        )

    def build_durable_truth_payload(
        self,
        agg: OperationAggregate,
        *,
        include_inactive_memory: bool = False,
    ) -> dict[str, object]:
        state = aggregate_to_state(agg)
        return self._projection_service.build_durable_truth_payload(
            state, include_inactive_memory=include_inactive_memory
        )

    def build_status_action_hint(self, agg: OperationAggregate) -> str | None:
        state = aggregate_to_state(agg)
        open_attention = [
            a for a in state.attention_requests if a.status is AttentionStatus.OPEN
        ]
        if open_attention:
            return (
                f"operator answer {state.operation_id} "
                f"{open_attention[0].attention_id} --text '...'"
            )
        if (
            state.active_session_record is not None
            and state.scheduler_state is not SchedulerState.DRAINING
        ):
            return f"operator interrupt {state.operation_id}"
        if state.scheduler_state in {SchedulerState.PAUSED, SchedulerState.PAUSE_REQUESTED}:
            return f"operator unpause {state.operation_id}"
        return None
