from agent_operator.domain import (
    AgentResult,
    AgentTurnSummary,
    BrainDecision,
    Evaluation,
    MemoryEntryDraft,
    OperationGoal,
    OperationState,
    ProgressSummary,
)
from agent_operator.dtos import (
    AgentTurnSummaryDTO,
    ArtifactNormalizationDTO,
    EvaluationDTO,
    MemoryEntryDraftDTO,
    StructuredDecisionDTO,
)
from agent_operator.mappers import (
    map_agent_turn_summary_dto,
    map_decision_dto,
    map_evaluation_dto,
    map_memory_entry_draft_dto,
)
from agent_operator.protocols import StructuredOutputProvider


class ProviderBackedBrain:
    """Adapter from provider DTOs to the internal OperatorBrain contract."""

    def __init__(self, provider: StructuredOutputProvider) -> None:
        self._provider = provider

    @property
    def provider(self) -> StructuredOutputProvider:
        return self._provider

    async def decide_next_action(self, state: OperationState) -> BrainDecision:
        dto: StructuredDecisionDTO = await self._provider.decide_next_action(state)
        return map_decision_dto(dto)

    async def evaluate_result(self, state: OperationState) -> Evaluation:
        dto: EvaluationDTO = await self._provider.evaluate_result(state)
        return map_evaluation_dto(dto)

    async def summarize_agent_turn(
        self,
        state: OperationState,
        *,
        operator_instruction: str,
        result: AgentResult,
    ) -> AgentTurnSummary:
        dto: AgentTurnSummaryDTO = await self._provider.summarize_agent_turn(
            state,
            operator_instruction=operator_instruction,
            result=result,
        )
        return map_agent_turn_summary_dto(dto)

    async def normalize_artifact(
        self,
        goal: OperationGoal,
        result: AgentResult,
    ) -> AgentResult:
        dto: ArtifactNormalizationDTO = await self._provider.normalize_artifact(goal, result)
        normalized_output = dto.normalized_output.strip()
        if not normalized_output or normalized_output == result.output_text:
            return result
        raw = dict(result.raw or {})
        raw["normalized_by_operator_brain"] = True
        raw["normalization_rationale"] = dto.rationale
        raw["original_output_text"] = result.output_text
        return result.model_copy(update={"output_text": normalized_output, "raw": raw})

    async def distill_memory(
        self,
        state: OperationState,
        *,
        scope: str,
        scope_id: str,
        source_refs: list[dict[str, str]],
        instruction: str,
    ) -> MemoryEntryDraft:
        dto: MemoryEntryDraftDTO = await self._provider.distill_memory(
            state,
            scope=scope,
            scope_id=scope_id,
            source_refs=source_refs,
            instruction=instruction,
        )
        return map_memory_entry_draft_dto(dto)

    async def summarize_progress(self, state: OperationState) -> ProgressSummary:
        highlights = [
            f"iterations={len(state.iterations)}",
            f"status={state.status}",
        ]
        return ProgressSummary(
            summary=state.final_summary or state.goal.objective_text,
            highlights=highlights,
            next_focus="Await structured provider implementation.",
        )
