from __future__ import annotations

from typing import Protocol

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
from agent_operator.dtos import ConverseTurnDTO


class OperatorBrain(Protocol):
    async def converse(self, prompt: str) -> ConverseTurnDTO: ...

    async def answer_question(self, state: OperationState, question: str) -> str: ...

    async def decide_next_action(self, state: OperationState) -> BrainDecision: ...

    async def evaluate_result(self, state: OperationState) -> Evaluation: ...

    async def summarize_agent_turn(
        self,
        state: OperationState,
        *,
        operator_instruction: str,
        result: AgentResult,
    ) -> AgentTurnSummary: ...

    async def normalize_artifact(
        self,
        goal: OperationGoal,
        result: AgentResult,
    ) -> AgentResult: ...

    async def distill_memory(
        self,
        state: OperationState,
        *,
        scope: str,
        scope_id: str,
        source_refs: list[dict[str, str]],
        instruction: str,
    ) -> MemoryEntryDraft: ...

    async def summarize_progress(self, state: OperationState) -> ProgressSummary: ...
