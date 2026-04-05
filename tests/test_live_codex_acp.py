from __future__ import annotations

import os
import shutil

import pytest

from agent_operator.adapters.codex_acp import CodexAcpAgentAdapter
from agent_operator.dtos import AgentRunRequest


def _codex_acp_command() -> str:
    return os.environ.get("OPERATOR_CODEX_ACP_LIVE_COMMAND", "npx @zed-industries/codex-acp")


def _codex_acp_substrate_backend() -> str:
    return os.environ.get("OPERATOR_CODEX_ACP_LIVE_SUBSTRATE_BACKEND", "bespoke")


pytestmark = pytest.mark.skipif(
    os.environ.get("OPERATOR_RUN_CODEX_ACP_LIVE") != "1",
    reason="requires OPERATOR_RUN_CODEX_ACP_LIVE=1",
)


@pytest.mark.anyio
async def test_codex_acp_live_roundtrip() -> None:
    command = _codex_acp_command()
    executable = command.split()[0]
    if shutil.which(executable) is None:
        pytest.skip(f"missing executable for live codex-acp command: {executable}")

    adapter = CodexAcpAgentAdapter(
        command=command,
        model=os.environ.get("OPERATOR_CODEX_ACP_MODEL"),
        reasoning_effort=os.environ.get("OPERATOR_CODEX_ACP_REASONING_EFFORT"),
        substrate_backend=_codex_acp_substrate_backend(),
    )
    handle = await adapter.start(
        AgentRunRequest(
            goal="live acp smoke",
            instruction="Reply with exactly ACP_OK and nothing else.",
        )
    )
    result = await adapter.collect(handle)

    assert result.status.value == "success"
    assert result.output_text.strip() == "ACP_OK"

    await adapter.send(handle, "Reply with exactly ACP_SECOND and nothing else.")
    second = await adapter.collect(handle)

    assert second.status.value == "success"
    assert second.output_text.strip() == "ACP_SECOND"
