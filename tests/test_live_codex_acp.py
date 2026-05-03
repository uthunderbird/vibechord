from __future__ import annotations

import os
import shlex
import shutil
import subprocess

import pytest

from agent_operator.adapters.codex_acp import CodexAcpAgentAdapter
from agent_operator.dtos import AgentRunRequest


def _codex_acp_command() -> str:
    return os.environ.get("OPERATOR_CODEX_ACP_LIVE_COMMAND", "npx @zed-industries/codex-acp")


def _codex_acp_substrate_backend() -> str:
    return os.environ.get("OPERATOR_CODEX_ACP_LIVE_SUBSTRATE_BACKEND", "bespoke")


def _codex_acp_readiness_command(command: str) -> list[str]:
    argv = shlex.split(command)
    if argv[:2] == ["npx", "@zed-industries/codex-acp"]:
        return ["npx", "@zed-industries/codex-acp", "--help"]
    return [*argv, "--help"]


def _skip_if_codex_acp_unavailable(command: str) -> None:
    readiness_command = _codex_acp_readiness_command(command)
    try:
        completed = subprocess.run(
            readiness_command,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
            timeout=15,
        )
    except subprocess.TimeoutExpired:
        pytest.skip(f"codex ACP readiness check timed out: {' '.join(readiness_command)}")
    if completed.returncode != 0:
        output = completed.stdout.strip().splitlines()
        detail = output[-1] if output else "no output"
        pytest.skip(f"codex ACP readiness check failed: {detail}")


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
    _skip_if_codex_acp_unavailable(command)

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
