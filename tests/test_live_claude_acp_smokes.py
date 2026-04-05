from __future__ import annotations

import os
import shutil

import pytest

from agent_operator.bootstrap import build_store
from agent_operator.config import OperatorSettings
from agent_operator.smoke import (
    extract_final_plan,
    run_alignment_post_research_plan_smoke,
    run_mixed_agent_selection_smoke,
    run_mixed_code_agent_selection_smoke,
)


def _has_codex_oauth() -> bool:
    try:
        from oauth_cli_kit import get_token

        token = get_token()
    except Exception:
        return False
    return bool(getattr(token, "account_id", None)) and bool(getattr(token, "access", None))


pytestmark = pytest.mark.skipif(
    os.environ.get("OPERATOR_RUN_CLAUDE_ACP_SMOKES") != "1"
    or shutil.which("npx") is None
    or not _has_codex_oauth(),
    reason="requires OPERATOR_RUN_CLAUDE_ACP_SMOKES=1, npx, and Codex OAuth",
)


@pytest.mark.anyio
async def test_alignment_post_research_plan_smoke_over_claude_acp() -> None:
    settings = OperatorSettings()
    assert settings.brain_provider == "openai_codex"

    outcome = await run_alignment_post_research_plan_smoke("claude_acp")
    final_plan = extract_final_plan(outcome)

    assert outcome.status.value == "completed"
    assert len(final_plan.splitlines()) >= 4
    assert len(final_plan) >= 120


@pytest.mark.anyio
async def test_mixed_agent_selection_smoke_over_claude_acp() -> None:
    settings = OperatorSettings()
    outcome = await run_mixed_agent_selection_smoke("claude_acp")

    store = build_store(settings)
    operation = await store.load_operation(outcome.operation_id)

    assert outcome.status.value == "completed"
    assert outcome.final_result is not None
    assert "alignment" in outcome.final_result.output_text.lower()
    assert operation is not None

    chosen_agents = [
        iteration.decision.target_agent
        for iteration in operation.iterations
        if iteration.decision is not None and iteration.decision.target_agent is not None
    ]
    assert chosen_agents
    assert chosen_agents[0] in {"claude_acp", "codex_acp"}


@pytest.mark.anyio
async def test_mixed_code_agent_selection_smoke_over_claude_acp() -> None:
    settings = OperatorSettings()
    outcome = await run_mixed_code_agent_selection_smoke("claude_acp")

    store = build_store(settings)
    operation = await store.load_operation(outcome.operation_id)

    assert outcome.status.value == "completed"
    assert outcome.final_result is not None
    assert "src/agent_operator/" in outcome.final_result.output_text
    assert operation is not None

    chosen_agents = [
        iteration.decision.target_agent
        for iteration in operation.iterations
        if iteration.decision is not None and iteration.decision.target_agent is not None
    ]
    assert chosen_agents
    assert chosen_agents[0] == "codex_acp"
