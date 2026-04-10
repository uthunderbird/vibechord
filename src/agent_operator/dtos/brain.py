from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from agent_operator.domain.enums import (
    AttentionType,
    BrainActionType,
    FeatureStatus,
    FocusKind,
    InterruptPolicy,
    ResumePolicy,
    SessionPolicy,
    TaskStatus,
)


class FeatureDraftDTO(BaseModel):
    title: str
    acceptance_criteria: str
    notes: list[str] = Field(default_factory=list)


class FeaturePatchDTO(BaseModel):
    feature_id: str
    title: str | None = None
    acceptance_criteria: str | None = None
    status: FeatureStatus | None = None
    append_notes: list[str] = Field(default_factory=list)


class TaskDraftDTO(BaseModel):
    title: str
    goal: str
    definition_of_done: str
    brain_priority: int = 50
    feature_id: str | None = None
    assigned_agent: str | None = None
    session_policy: SessionPolicy = SessionPolicy.PREFER_REUSE
    dependencies: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class TaskPatchDTO(BaseModel):
    task_id: str
    title: str | None = None
    goal: str | None = None
    definition_of_done: str | None = None
    status: TaskStatus | None = None
    brain_priority: int | None = None
    assigned_agent: str | None = None
    linked_session_id: str | None = None
    session_policy: SessionPolicy | None = None
    append_notes: list[str] = Field(default_factory=list)
    add_memory_refs: list[str] = Field(default_factory=list)
    add_artifact_refs: list[str] = Field(default_factory=list)
    add_dependencies: list[str] = Field(default_factory=list)
    remove_dependencies: list[str] = Field(default_factory=list)
    dependency_removal_reason: str | None = None


class BlockingFocusDTO(BaseModel):
    kind: FocusKind
    target_id: str
    blocking_reason: str
    interrupt_policy: InterruptPolicy = InterruptPolicy.MATERIAL_WAKEUP
    resume_policy: ResumePolicy = ResumePolicy.REPLAN


class StructuredDecisionDTO(BaseModel):
    action_type: BrainActionType
    target_agent: str | None = None
    session_id: str | None = None
    session_name: str | None = None
    one_shot: bool = False
    workfront_key: str | None = None
    instruction: str | None = None
    rationale: str
    confidence: float | None = None
    assumptions: list[str]
    expected_outcome: str | None = None
    focus_task_id: str | None = None
    new_features: list[FeatureDraftDTO] = Field(default_factory=list)
    feature_updates: list[FeaturePatchDTO] = Field(default_factory=list)
    new_tasks: list[TaskDraftDTO] = Field(default_factory=list)
    task_updates: list[TaskPatchDTO] = Field(default_factory=list)
    blocking_focus: BlockingFocusDTO | None = None
    attention_type: AttentionType | None = None
    attention_title: str | None = None
    attention_context: str | None = None
    attention_options: list[str] = Field(default_factory=list)


class EvaluationDTO(BaseModel):
    goal_satisfied: bool
    should_continue: bool
    summary: str
    blocker: str | None = None


class AgentTurnSummaryDTO(BaseModel):
    declared_goal: str
    actual_work_done: str
    route_or_target_chosen: str | None = None
    repo_changes: list[str] = Field(default_factory=list)
    progress_class: Literal["material_delta", "inspection_only", "no_verified_delta"] | None = None
    blocker_keys: list[str] = Field(default_factory=list)
    state_delta: str
    verification_status: str
    remaining_blockers: list[str] = Field(default_factory=list)
    recommended_next_step: str
    rationale: str | None = None


class ArtifactNormalizationDTO(BaseModel):
    normalized_output: str
    rationale: str | None = None


class MemorySourceRefDTO(BaseModel):
    kind: str
    ref_id: str


class MemoryEntryDraftDTO(BaseModel):
    scope: str
    scope_id: str
    summary: str
    source_refs: list[MemorySourceRefDTO] = Field(default_factory=list)
    rationale: str | None = None


class PermissionDecisionDTO(BaseModel):
    decision: str
    rationale: str
    suggested_options: list[str] = Field(default_factory=list)
    policy_title: str | None = None
    policy_rule_text: str | None = None


# --- File context tool-use loop types ---

class FileToolCallStep:
    """Provider is requesting a file tool call before making a decision."""

    kind: Literal["tool_call"] = "tool_call"

    def __init__(self, tool_name: str, arguments: dict[str, Any]) -> None:
        self.tool_name = tool_name
        self.arguments = arguments


class DecisionStep:
    """Provider has produced a final structured decision."""

    kind: Literal["decision"] = "decision"

    def __init__(self, dto: StructuredDecisionDTO) -> None:
        self.dto = dto


FileContextStep = FileToolCallStep | DecisionStep

# Tool names the brain may call
FILE_TOOL_READ_FILE = "read_file"
FILE_TOOL_LIST_DIR = "list_dir"
FILE_TOOL_SEARCH_TEXT = "search_text"
FILE_TOOL_NAMES = frozenset({FILE_TOOL_READ_FILE, FILE_TOOL_LIST_DIR, FILE_TOOL_SEARCH_TEXT})
