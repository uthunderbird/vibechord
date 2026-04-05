from agent_operator.domain import (
    AgentTurnSummary,
    BlockingFocus,
    BrainDecision,
    Evaluation,
    FeatureDraft,
    FeaturePatch,
    MemoryEntryDraft,
    MemorySourceRef,
    TaskDraft,
    TaskPatch,
)
from agent_operator.dtos import (
    AgentTurnSummaryDTO,
    BlockingFocusDTO,
    EvaluationDTO,
    FeatureDraftDTO,
    FeaturePatchDTO,
    MemoryEntryDraftDTO,
    StructuredDecisionDTO,
    TaskDraftDTO,
    TaskPatchDTO,
)


def _map_feature_draft(dto: FeatureDraftDTO) -> FeatureDraft:
    return FeatureDraft(
        title=dto.title,
        acceptance_criteria=dto.acceptance_criteria,
        notes=list(dto.notes),
    )


def _map_feature_patch(dto: FeaturePatchDTO) -> FeaturePatch:
    return FeaturePatch(
        feature_id=dto.feature_id,
        title=dto.title,
        acceptance_criteria=dto.acceptance_criteria,
        status=dto.status,
        append_notes=list(dto.append_notes),
    )


def _map_task_draft(dto: TaskDraftDTO) -> TaskDraft:
    return TaskDraft(
        title=dto.title,
        goal=dto.goal,
        definition_of_done=dto.definition_of_done,
        brain_priority=dto.brain_priority,
        feature_id=dto.feature_id,
        assigned_agent=dto.assigned_agent,
        session_policy=dto.session_policy,
        dependencies=list(dto.dependencies),
        notes=list(dto.notes),
    )


def _map_task_patch(dto: TaskPatchDTO) -> TaskPatch:
    return TaskPatch(
        task_id=dto.task_id,
        title=dto.title,
        goal=dto.goal,
        definition_of_done=dto.definition_of_done,
        status=dto.status,
        brain_priority=dto.brain_priority,
        assigned_agent=dto.assigned_agent,
        linked_session_id=dto.linked_session_id,
        session_policy=dto.session_policy,
        append_notes=list(dto.append_notes),
        add_memory_refs=list(dto.add_memory_refs),
        add_artifact_refs=list(dto.add_artifact_refs),
        add_dependencies=list(dto.add_dependencies),
        remove_dependencies=list(dto.remove_dependencies),
        dependency_removal_reason=dto.dependency_removal_reason,
    )


def _map_blocking_focus(dto: BlockingFocusDTO | None) -> BlockingFocus | None:
    if dto is None:
        return None
    return BlockingFocus(
        kind=dto.kind,
        target_id=dto.target_id,
        blocking_reason=dto.blocking_reason,
        interrupt_policy=dto.interrupt_policy,
        resume_policy=dto.resume_policy,
    )


def map_decision_dto(dto: StructuredDecisionDTO) -> BrainDecision:
    metadata: dict[str, object] = {}
    if dto.attention_type is not None:
        metadata["attention_type"] = dto.attention_type.value
    if dto.attention_title is not None:
        metadata["attention_title"] = dto.attention_title
    if dto.attention_context is not None:
        metadata["attention_context"] = dto.attention_context
    if dto.attention_options:
        metadata["attention_options"] = list(dto.attention_options)
    return BrainDecision(
        action_type=dto.action_type,
        target_agent=dto.target_agent,
        session_id=dto.session_id,
        session_name=dto.session_name,
        one_shot=dto.one_shot,
        instruction=dto.instruction,
        rationale=dto.rationale,
        confidence=dto.confidence,
        assumptions=dto.assumptions,
        expected_outcome=dto.expected_outcome,
        focus_task_id=dto.focus_task_id,
        new_features=[_map_feature_draft(item) for item in dto.new_features],
        feature_updates=[_map_feature_patch(item) for item in dto.feature_updates],
        new_tasks=[_map_task_draft(item) for item in dto.new_tasks],
        task_updates=[_map_task_patch(item) for item in dto.task_updates],
        blocking_focus=_map_blocking_focus(dto.blocking_focus),
        metadata=metadata,
    )


def map_evaluation_dto(dto: EvaluationDTO) -> Evaluation:
    return Evaluation(
        goal_satisfied=dto.goal_satisfied,
        should_continue=dto.should_continue,
        summary=dto.summary,
        blocker=dto.blocker,
        metadata={},
    )


def map_agent_turn_summary_dto(dto: AgentTurnSummaryDTO) -> AgentTurnSummary:
    return AgentTurnSummary(
        declared_goal=dto.declared_goal,
        actual_work_done=dto.actual_work_done,
        route_or_target_chosen=dto.route_or_target_chosen,
        repo_changes=list(dto.repo_changes),
        state_delta=dto.state_delta,
        verification_status=dto.verification_status,
        remaining_blockers=list(dto.remaining_blockers),
        recommended_next_step=dto.recommended_next_step,
        rationale=dto.rationale,
    )


def map_memory_entry_draft_dto(dto: MemoryEntryDraftDTO) -> MemoryEntryDraft:
    return MemoryEntryDraft(
        scope=dto.scope,
        scope_id=dto.scope_id,
        summary=dto.summary,
        source_refs=[MemorySourceRef(kind=ref.kind, ref_id=ref.ref_id) for ref in dto.source_refs],
        rationale=dto.rationale,
    )
