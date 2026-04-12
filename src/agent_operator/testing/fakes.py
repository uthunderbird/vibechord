
from agent_operator.domain.agent import AgentResult
from agent_operator.domain.enums import BrainActionType
from agent_operator.domain.operation import OperationGoal, OperationState
from agent_operator.dtos import (
    AgentTurnSummaryDTO,
    ArtifactNormalizationDTO,
    EvaluationDTO,
    MemoryEntryDraftDTO,
    MemorySourceRefDTO,
    PermissionDecisionDTO,
    StructuredDecisionDTO,
)


class FakeStructuredOutputProvider:
    """Minimal provider for scaffolding the application loop."""

    async def answer_question(self, state: OperationState, question: str) -> str:
        return (
            f"Question: {question}\n"
            f"Status: {state.status.value}\n"
            f"Objective: {state.objective_state.objective}"
        )

    async def decide_next_action(self, state: OperationState) -> StructuredDecisionDTO:
        if not state.iterations:
            return StructuredDecisionDTO(
                action_type=BrainActionType.APPLY_POLICY,
                rationale="Scaffold provider requests a no-op policy step before stopping.",
                assumptions=[],
            )
        return StructuredDecisionDTO(
            action_type=BrainActionType.STOP,
            rationale="Scaffold provider stops after one placeholder iteration.",
            assumptions=[],
        )

    async def evaluate_result(self, state: OperationState) -> EvaluationDTO:
        return EvaluationDTO(
            goal_satisfied=False,
            should_continue=len(state.iterations) < 2,
            summary="Scaffold runtime reached its placeholder stopping condition.",
        )

    async def normalize_artifact(
        self,
        goal: OperationGoal,
        result: AgentResult,
    ) -> ArtifactNormalizationDTO:
        return ArtifactNormalizationDTO(
            normalized_output=result.output_text,
            rationale="No normalization needed in fake provider.",
        )

    async def summarize_agent_turn(
        self,
        state: OperationState,
        *,
        operator_instruction: str,
        result: AgentResult,
    ) -> AgentTurnSummaryDTO:
        return AgentTurnSummaryDTO(
            declared_goal=operator_instruction or state.objective_state.objective,
            actual_work_done="No-op scaffold provider turn summary.",
            state_delta="No meaningful state delta.",
            verification_status="Not verified.",
            recommended_next_step="Stop after the scaffold turn.",
        )

    async def distill_memory(
        self,
        state: OperationState,
        *,
        scope: str,
        scope_id: str,
        source_refs: list[dict[str, str]],
        instruction: str,
    ) -> MemoryEntryDraftDTO:
        return MemoryEntryDraftDTO(
            scope=scope,
            scope_id=scope_id,
            summary=f"Memory for {scope}:{scope_id}",
            source_refs=[
                MemorySourceRefDTO(kind=ref["kind"], ref_id=ref["ref_id"]) for ref in source_refs
            ],
            rationale=instruction,
        )

    async def evaluate_permission_request(
        self,
        state: OperationState,
        *,
        request_payload: dict[str, object],
        active_policy_payload: list[dict[str, object]],
    ) -> PermissionDecisionDTO:
        return PermissionDecisionDTO(
            decision="escalate",
            rationale="Fake provider escalates permission requests by default.",
            suggested_options=["Approve once", "Reject", "Record project rule"],
        )
