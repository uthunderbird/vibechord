from __future__ import annotations

from typing import Protocol, runtime_checkable

from agent_operator.domain import AgentResult, OperationGoal, OperationState
from agent_operator.dtos import (
    AgentTurnSummaryDTO,
    ArtifactNormalizationDTO,
    EvaluationDTO,
    FileContextStep,
    MemoryEntryDraftDTO,
    PermissionDecisionDTO,
    StructuredDecisionDTO,
)


class StructuredOutputProvider(Protocol):
    async def decide_next_action(self, state: OperationState) -> StructuredDecisionDTO: ...

    async def evaluate_result(self, state: OperationState) -> EvaluationDTO: ...

    async def summarize_agent_turn(
        self,
        state: OperationState,
        *,
        operator_instruction: str,
        result: AgentResult,
    ) -> AgentTurnSummaryDTO: ...

    async def normalize_artifact(
        self,
        goal: OperationGoal,
        result: AgentResult,
    ) -> ArtifactNormalizationDTO: ...

    async def distill_memory(
        self,
        state: OperationState,
        *,
        scope: str,
        scope_id: str,
        source_refs: list[dict[str, str]],
        instruction: str,
    ) -> MemoryEntryDraftDTO: ...

    async def evaluate_permission_request(
        self,
        state: OperationState,
        *,
        request_payload: dict[str, object],
        active_policy_payload: list[dict[str, object]],
    ) -> PermissionDecisionDTO: ...


@runtime_checkable
class FileContextProvider(Protocol):
    """Optional extension: provider that can run a tool-use loop for file context.

    Providers that implement this protocol may call read_file / list_dir / search_text
    before committing to a structured decision. The service manages the loop, event
    emission, and MemoryEntry persistence — the provider handles one LLM round-trip
    per call and signals whether it wants a file tool or is ready to decide.
    """

    async def decide_with_file_context(self, state: OperationState) -> FileContextStep: ...
