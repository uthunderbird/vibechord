from __future__ import annotations

import anyio

from agent_operator.domain import OperationGoal, OperationState, OperationStatus
from agent_operator.providers import ProviderBackedBrain


class _QuestionProvider:
    def __init__(self) -> None:
        self.calls: list[tuple[OperationState, str]] = []

    async def answer_question(self, state: OperationState, question: str) -> str:
        self.calls.append((state, question))
        return f"status={state.status.value}; question={question}"


def test_provider_backed_brain_delegates_answer_question() -> None:
    provider = _QuestionProvider()
    brain = ProviderBackedBrain(provider)  # type: ignore[arg-type]
    state = OperationState(
        goal=OperationGoal(objective="Ship the feature"),
        status=OperationStatus.RUNNING,
    )

    answer = anyio.run(brain.answer_question, state, "What is happening?")

    assert answer == "status=running; question=What is happening?"
    assert provider.calls == [(state, "What is happening?")]
