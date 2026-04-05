from __future__ import annotations

import os
import shutil

import pytest

from agent_operator.adapters.claude_acp import ClaudeAcpAgentAdapter
from agent_operator.dtos import AgentRunRequest


def _claude_acp_command() -> str:
    return os.environ.get(
        "OPERATOR_CLAUDE_ACP_LIVE_COMMAND",
        "npx @agentclientprotocol/claude-agent-acp",
    )


def _claude_acp_substrate_backend() -> str:
    return os.environ.get("OPERATOR_CLAUDE_ACP_LIVE_SUBSTRATE_BACKEND", "bespoke")


pytestmark = pytest.mark.skipif(
    os.environ.get("OPERATOR_RUN_CLAUDE_ACP_LIVE") != "1",
    reason="requires OPERATOR_RUN_CLAUDE_ACP_LIVE=1",
)


@pytest.mark.anyio
async def test_claude_acp_live_roundtrip() -> None:
    command = _claude_acp_command()
    executable = command.split()[0]
    if shutil.which(executable) is None:
        pytest.skip(f"missing executable for live claude-acp command: {executable}")

    adapter = ClaudeAcpAgentAdapter(
        command=command,
        model=os.environ.get("OPERATOR_CLAUDE_ACP_MODEL"),
        effort=os.environ.get("OPERATOR_CLAUDE_ACP_EFFORT"),
        permission_mode=os.environ.get("OPERATOR_CLAUDE_ACP_PERMISSION_MODE"),
        substrate_backend=_claude_acp_substrate_backend(),
    )
    handle = await adapter.start(
        AgentRunRequest(
            goal="live claude acp smoke",
            instruction="Reply with exactly CLAUDE_ACP_OK and nothing else.",
        )
    )
    result = await adapter.collect(handle)

    assert result.status.value == "success"
    assert result.output_text.strip() == "CLAUDE_ACP_OK"

    await adapter.send(handle, "Reply with exactly CLAUDE_ACP_SECOND and nothing else.")
    second = await adapter.collect(handle)

    assert second.status.value == "success"
    assert second.output_text.strip() == "CLAUDE_ACP_SECOND"
