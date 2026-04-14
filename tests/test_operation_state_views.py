from __future__ import annotations

import pytest

from agent_operator.application.queries.operation_state_views import (
    OperationStateViewService,
)
from agent_operator.domain import (
    InvolvementLevel,
    ObjectiveState,
    OperationCheckpoint,
)


def test_from_checkpoint_uses_explicit_objective_derivation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    checkpoint = OperationCheckpoint(
        operation_id="op-derived-view",
        allowed_agents=["codex_acp"],
        involvement_level=InvolvementLevel.COLLABORATIVE,
        objective=ObjectiveState(
            objective="Inspect the repository",
            harness_instructions="Stay on the state-view path.",
            success_criteria=["Use explicit serialization."],
            metadata={"source": "checkpoint"},
        ),
    )

    def _fail_model_dump(self, *args, **kwargs):
        raise AssertionError(
            "state-view projection should not serialize ObjectiveState directly"
        )

    monkeypatch.setattr(ObjectiveState, "model_dump", _fail_model_dump)

    state = OperationStateViewService().from_checkpoint(checkpoint)

    assert state.goal.objective == "Inspect the repository"
    assert state.goal.harness_instructions == "Stay on the state-view path."
    assert state.goal.success_criteria == ["Use explicit serialization."]
    assert state.goal.metadata == {"source": "checkpoint"}
    assert state.objective is not None
    assert state.objective.objective == "Inspect the repository"
