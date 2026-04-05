from __future__ import annotations

import os
import shutil

import pytest

from agent_operator.config import OperatorSettings
from agent_operator.smoke import extract_final_plan, run_alignment_post_research_plan_smoke


def _has_codex_oauth() -> bool:
    try:
        from oauth_cli_kit import get_token

        token = get_token()
    except Exception:
        return False
    return bool(getattr(token, "account_id", None)) and bool(getattr(token, "access", None))


pytestmark = pytest.mark.skipif(
    os.environ.get("OPERATOR_RUN_ALIGNMENT_SMOKE") != "1"
    or shutil.which("claude") is None
    or not _has_codex_oauth(),
    reason="requires OPERATOR_RUN_ALIGNMENT_SMOKE=1, local Claude CLI, and Codex OAuth",
)


@pytest.mark.anyio
async def test_alignment_post_research_plan_smoke() -> None:
    settings = OperatorSettings()
    assert settings.brain_provider == "openai_codex"

    outcome = await run_alignment_post_research_plan_smoke()
    final_plan = extract_final_plan(outcome)

    assert outcome.status.value == "completed"
    assert len(final_plan.splitlines()) >= 4
    assert len(final_plan) >= 120
