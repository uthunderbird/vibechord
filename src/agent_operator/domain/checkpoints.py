from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, Field

from agent_operator.domain.attention import AttentionRequest
from agent_operator.domain.control import OperatorMessage
from agent_operator.domain.enums import InvolvementLevel, OperationStatus, SchedulerState
from agent_operator.domain.operation import (
    ExecutionState,
    FocusState,
    ObjectiveState,
    SessionState,
    TaskState,
)
from agent_operator.domain.policy import PolicyCoverage, PolicyEntry


class OperationCheckpoint(BaseModel):
    """Canonical replay target folded from operation domain events.

    Attributes:
        operation_id: Owning operation identifier.
        objective: Canonical objective state for the operation.
        status: Canonical operation lifecycle status.
        tasks: Canonical task graph state.
        sessions: Canonical session state.
        executions: Canonical execution state.
        attention_requests: Canonical attention lifecycle state.
        scheduler_state: Canonical scheduler lifecycle state.
        operator_messages: Optional operation-owned context substate.
        active_policies: Optional operation-owned policy substate.
        policy_coverage: Optional policy applicability substate.
        involvement_level: Canonical involvement level.
        final_summary: Optional terminal summary.
        created_at: Checkpoint creation timestamp.
        updated_at: Last fold timestamp.

    Examples:
        >>> checkpoint = OperationCheckpoint.initial("op-1")
        >>> checkpoint.operation_id
        'op-1'
    """

    operation_id: str
    objective: ObjectiveState | None = None
    status: OperationStatus = OperationStatus.RUNNING
    tasks: list[TaskState] = Field(default_factory=list)
    sessions: list[SessionState] = Field(default_factory=list)
    executions: list[ExecutionState] = Field(default_factory=list)
    attention_requests: list[AttentionRequest] = Field(default_factory=list)
    scheduler_state: SchedulerState = SchedulerState.ACTIVE
    operator_messages: list[OperatorMessage] = Field(default_factory=list)
    active_policies: list[PolicyEntry] = Field(default_factory=list)
    policy_coverage: PolicyCoverage = Field(default_factory=PolicyCoverage)
    allowed_agents: list[str] = Field(default_factory=list)
    involvement_level: InvolvementLevel = InvolvementLevel.AUTO
    processed_command_ids: list[str] = Field(default_factory=list)
    current_focus: FocusState | None = None
    final_summary: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @classmethod
    def initial(
        cls,
        operation_id: str,
        *,
        created_at: datetime | None = None,
    ) -> OperationCheckpoint:
        """Build an empty initial checkpoint for one operation.

        Args:
            operation_id: Owning operation identifier.
            created_at: Optional checkpoint creation time override.

        Returns:
            Empty canonical checkpoint.
        """

        timestamp = created_at or datetime.now(UTC)
        return cls(
            operation_id=operation_id,
            created_at=timestamp,
            updated_at=timestamp,
        )
