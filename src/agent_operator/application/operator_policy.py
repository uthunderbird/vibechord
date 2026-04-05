from __future__ import annotations

from agent_operator.protocols import OperatorBrain


class LlmFirstOperatorPolicy:
    """Adapter that exposes the current brain-first operator family as OperatorPolicy."""

    def __init__(self, brain: OperatorBrain) -> None:
        self._brain = brain

    @property
    def brain(self) -> OperatorBrain:
        return self._brain

    async def decide_next_action(self, state):
        return await self._brain.decide_next_action(state)

    async def evaluate_result(self, state):
        return await self._brain.evaluate_result(state)

    async def summarize_agent_turn(self, state, *, operator_instruction, result):
        return await self._brain.summarize_agent_turn(
            state,
            operator_instruction=operator_instruction,
            result=result,
        )

    async def normalize_artifact(self, goal, result):
        return await self._brain.normalize_artifact(goal, result)

    async def distill_memory(self, state, *, scope, scope_id, source_refs, instruction):
        return await self._brain.distill_memory(
            state,
            scope=scope,
            scope_id=scope_id,
            source_refs=source_refs,
            instruction=instruction,
        )

    async def summarize_progress(self, state):
        return await self._brain.summarize_progress(state)
