from __future__ import annotations

import os

import pytest

from agent_operator.bootstrap import build_store
from agent_operator.config import OperatorSettings
from agent_operator.smoke import run_codex_continuation_smoke

pytestmark = pytest.mark.skipif(
    os.environ.get("OPERATOR_RUN_CODEX_CONTINUATION_SMOKE") != "1",
    reason="requires OPERATOR_RUN_CODEX_CONTINUATION_SMOKE=1",
)


@pytest.mark.anyio
async def test_codex_continuation_smoke_uses_continue_agent() -> None:
    settings = OperatorSettings()
    outcome = await run_codex_continuation_smoke()

    store = build_store(settings)
    operation = await store.load_operation(outcome.operation_id)

    assert outcome.status.value == "completed"
    assert outcome.final_result is not None
    assert operation is not None

    actions = [
        (iteration.decision.action_type.value, iteration.decision.target_agent)
        for iteration in operation.iterations
        if iteration.decision is not None and iteration.decision.target_agent is not None
    ]
    assert actions
    assert actions[0] == ("start_agent", "codex_acp")
    assert len(actions) >= 2
    assert actions[1] == ("continue_agent", "codex_acp")
