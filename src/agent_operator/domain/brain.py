from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from agent_operator.domain.enums import BrainActionType
from agent_operator.domain.operation import (
    BlockingFocus,
    FeatureDraft,
    FeaturePatch,
    MemorySourceRef,
    TaskDraft,
    TaskPatch,
)


class BrainDecision(BaseModel):
    action_type: BrainActionType
    target_agent: str | None = None
    session_id: str | None = None
    session_name: str | None = None
    one_shot: bool = False
    workfront_key: str | None = None
    instruction: str | None = None
    rationale: str
    confidence: float | None = None
    assumptions: list[str] = Field(default_factory=list)
    expected_outcome: str | None = None
    focus_task_id: str | None = None
    new_features: list[FeatureDraft] = Field(default_factory=list)
    feature_updates: list[FeaturePatch] = Field(default_factory=list)
    new_tasks: list[TaskDraft] = Field(default_factory=list)
    task_updates: list[TaskPatch] = Field(default_factory=list)
    blocking_focus: BlockingFocus | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class Evaluation(BaseModel):
    goal_satisfied: bool
    should_continue: bool
    summary: str
    blocker: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ProgressSummary(BaseModel):
    summary: str
    highlights: list[str] = Field(default_factory=list)
    next_focus: str | None = None


class MemoryEntryDraft(BaseModel):
    scope: str
    scope_id: str
    summary: str
    source_refs: list[MemorySourceRef] = Field(default_factory=list)
    rationale: str | None = None
