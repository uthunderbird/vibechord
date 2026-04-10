from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator

from agent_operator.domain.enums import (
    InvolvementLevel,
    OperationStatus,
    SchedulerState,
)


class TypedRefs(BaseModel):
    operation_id: str
    iteration: int | None = None
    task_id: str | None = None
    session_id: str | None = None
    artifact_id: str | None = None
    command_id: str | None = None

    def to_dict(self) -> dict[str, str]:
        result: dict[str, str] = {"operation_id": self.operation_id}
        if self.iteration is not None:
            result["iteration"] = str(self.iteration)
        if self.task_id is not None:
            result["task_id"] = self.task_id
        if self.session_id is not None:
            result["session_id"] = self.session_id
        if self.artifact_id is not None:
            result["artifact_id"] = self.artifact_id
        if self.command_id is not None:
            result["command_id"] = self.command_id
        return result


class OperationBrief(BaseModel):
    operation_id: str
    status: OperationStatus
    scheduler_state: SchedulerState = SchedulerState.ACTIVE
    involvement_level: InvolvementLevel = InvolvementLevel.AUTO
    objective_brief: str
    harness_brief: str | None = None
    focus_brief: str | None = None
    latest_outcome_brief: str | None = None
    blocker_brief: str | None = None
    runtime_alert_brief: str | None = None
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class IterationBrief(BaseModel):
    iteration: int
    task_id: str | None = None
    session_id: str | None = None
    operator_intent_brief: str
    assignment_brief: str | None = None
    result_brief: str | None = None
    status_brief: str
    refs: TypedRefs | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class AgentTurnSummary(BaseModel):
    declared_goal: str
    actual_work_done: str
    route_or_target_chosen: str | None = None
    repo_changes: list[str] = Field(default_factory=list)
    progress_class: str | None = None
    blocker_keys: list[str] = Field(default_factory=list)
    state_delta: str
    verification_status: str
    remaining_blockers: list[str] = Field(default_factory=list)
    recommended_next_step: str
    rationale: str | None = None


class AgentTurnBrief(BaseModel):
    operation_id: str
    iteration: int
    agent_key: str
    session_id: str
    background_run_id: str | None = None
    session_display_name: str | None = None
    assignment_brief: str
    expected_outcome: str | None = None
    result_brief: str | None = None
    turn_summary: AgentTurnSummary | None = None
    status: str
    artifact_refs: list[str] = Field(default_factory=list)
    raw_log_refs: list[str] = Field(default_factory=list)
    wakeup_refs: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class DecisionMemo(BaseModel):
    operation_id: str
    iteration: int
    task_id: str | None = None
    session_id: str | None = None
    decision_context_summary: str
    chosen_action: str
    rationale: str
    alternatives_considered: list[str] = Field(default_factory=list)
    why_not_chosen: list[str] = Field(default_factory=list)
    expected_outcome: str | None = None
    refs: TypedRefs | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class TraceRecord(BaseModel):
    operation_id: str
    iteration: int
    category: str
    title: str
    summary: str
    task_id: str | None = None
    session_id: str | None = None
    refs: dict[str, str] = Field(default_factory=dict)
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @field_validator("refs", mode="before")
    @classmethod
    def _coerce_refs(cls, value: Any) -> dict[str, str]:
        # Service code commonly produces TypedRefs for traceability. The timeline format
        # is a plain JSON dict, so we normalize here for backward-compatible persistence.
        if isinstance(value, TypedRefs):
            raw = value.model_dump(mode="json", exclude_none=True)
            return {k: str(v) for k, v in raw.items()}
        if isinstance(value, dict):
            out: dict[str, str] = {}
            for k, v in value.items():
                if v is None:
                    continue
                out[str(k)] = str(v)
            return out
        if value is None:
            return {}
        raise TypeError("TraceRecord.refs must be a dict or TypedRefs")


class CommandBrief(BaseModel):
    operation_id: str
    command_id: str
    command_type: str
    status: str
    iteration: int
    applied_at: datetime | None = None
    rejected_at: datetime | None = None
    rejection_reason: str | None = None


class EvaluationBrief(BaseModel):
    operation_id: str
    iteration: int
    goal_satisfied: bool
    should_continue: bool
    summary: str
    blocker: str | None = None


class TraceBriefBundle(BaseModel):
    operation_brief: OperationBrief | None = None
    iteration_briefs: list[IterationBrief] = Field(default_factory=list)
    agent_turn_briefs: list[AgentTurnBrief] = Field(default_factory=list)
    command_briefs: list[CommandBrief] = Field(default_factory=list)
    evaluation_briefs: list[EvaluationBrief] = Field(default_factory=list)
