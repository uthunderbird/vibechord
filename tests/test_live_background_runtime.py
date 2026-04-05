from __future__ import annotations

import os
import shutil
from pathlib import Path

import anyio
import pytest

from agent_operator.adapters import build_agent_runtime_bindings
from agent_operator.config import OperatorSettings
from agent_operator.domain import AgentSessionHandle
from agent_operator.dtos import AgentRunRequest
from agent_operator.runtime import FileWakeupInbox, InProcessAgentRunSupervisor


def _has_codex_oauth() -> bool:
    try:
        from oauth_cli_kit import get_token

        token = get_token()
    except Exception:
        return False
    return bool(getattr(token, "account_id", None)) and bool(getattr(token, "access", None))


async def _wait_for_wakeup(
    inbox: FileWakeupInbox,
    operation_id: str,
    *,
    timeout_seconds: float = 90.0,
) -> None:
    with anyio.fail_after(timeout_seconds):
        while True:
            pending = await inbox.list_pending(operation_id)
            if pending:
                return
            await anyio.sleep(0.25)


pytestmark = pytest.mark.skipif(
    os.environ.get("OPERATOR_RUN_BACKGROUND_LIVE") != "1",
    reason="requires OPERATOR_RUN_BACKGROUND_LIVE=1",
)


@pytest.mark.anyio
async def test_background_claude_acp_roundtrip_live(tmp_path: Path, monkeypatch) -> None:
    command = os.environ.get(
        "OPERATOR_CLAUDE_ACP_LIVE_COMMAND",
        "npx @agentclientprotocol/claude-agent-acp",
    )
    substrate_backend = os.environ.get("OPERATOR_CLAUDE_ACP_LIVE_SUBSTRATE_BACKEND", "sdk")
    executable = command.split()[0]
    if shutil.which(executable) is None:
        pytest.skip(f"missing executable for live claude-acp command: {executable}")

    monkeypatch.setenv("OPERATOR_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("OPERATOR_CLAUDE_ACP__COMMAND", command)
    monkeypatch.setenv("OPERATOR_CLAUDE_ACP__PERMISSION_MODE", "bypassPermissions")
    monkeypatch.setenv("OPERATOR_CLAUDE_ACP__SUBSTRATE_BACKEND", substrate_backend)

    inbox = FileWakeupInbox(tmp_path / "wakeups")
    supervisor = InProcessAgentRunSupervisor(
        tmp_path / "background",
        tmp_path,
        runtime_bindings=build_agent_runtime_bindings(OperatorSettings()),
        wakeup_inbox=inbox,
    )

    run = await supervisor.start_background_turn(
        "bg-op-claude",
        1,
        "claude_acp",
        AgentRunRequest(
            goal="background live smoke",
            instruction="Reply with exactly BG_CLAUDE_OK and nothing else.",
        ),
    )
    assert run.session_id is not None

    await _wait_for_wakeup(inbox, "bg-op-claude")
    claimed = await inbox.claim("bg-op-claude")
    await inbox.ack([event.event_id for event in claimed])
    result = await supervisor.collect_background_turn(run.run_id)

    assert result is not None
    assert result.status.value == "success"
    assert result.output_text.strip() == "BG_CLAUDE_OK"


@pytest.mark.anyio
async def test_background_codex_acp_continuation_live(tmp_path: Path, monkeypatch) -> None:
    command = os.environ.get("OPERATOR_CODEX_ACP_LIVE_COMMAND", "npx @zed-industries/codex-acp")
    substrate_backend = os.environ.get("OPERATOR_CODEX_ACP_LIVE_SUBSTRATE_BACKEND", "bespoke")
    executable = command.split()[0]
    if shutil.which(executable) is None:
        pytest.skip(f"missing executable for live codex-acp command: {executable}")
    if not _has_codex_oauth():
        pytest.skip("missing Codex OAuth")

    monkeypatch.setenv("OPERATOR_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("OPERATOR_CODEX_ACP__COMMAND", command)
    monkeypatch.setenv("OPERATOR_CODEX_ACP__WORKING_DIRECTORY", str(Path.cwd()))
    monkeypatch.setenv("OPERATOR_CODEX_ACP__SUBSTRATE_BACKEND", substrate_backend)

    inbox = FileWakeupInbox(tmp_path / "wakeups")
    supervisor = InProcessAgentRunSupervisor(
        tmp_path / "background",
        tmp_path,
        runtime_bindings=build_agent_runtime_bindings(OperatorSettings()),
        wakeup_inbox=inbox,
    )

    first = await supervisor.start_background_turn(
        "bg-op-codex",
        1,
        "codex_acp",
        AgentRunRequest(
            goal="background codex smoke",
            instruction="Reply with exactly BG_CODEX_FIRST and nothing else.",
        ),
    )
    assert first.session_id is not None
    await _wait_for_wakeup(inbox, "bg-op-codex")
    claimed = await inbox.claim("bg-op-codex")
    await inbox.ack([event.event_id for event in claimed])
    first_result = await supervisor.collect_background_turn(first.run_id)
    assert first_result is not None
    assert first_result.status.value == "success"
    assert first_result.output_text.strip() == "BG_CODEX_FIRST"

    second = await supervisor.start_background_turn(
        "bg-op-codex",
        2,
        "codex_acp",
        AgentRunRequest(
            goal="background codex smoke",
            instruction="Reply with exactly BG_CODEX_SECOND and nothing else.",
        ),
        existing_session=AgentSessionHandle(
            adapter_key="codex_acp",
            session_id=first.session_id,
            metadata={"working_directory": str(Path.cwd())},
        ),
    )
    await _wait_for_wakeup(inbox, "bg-op-codex")
    claimed = await inbox.claim("bg-op-codex")
    await inbox.ack([event.event_id for event in claimed])
    second_result = await supervisor.collect_background_turn(second.run_id)
    assert second_result is not None
    assert second_result.status.value == "success"
    assert second_result.output_text.strip() == "BG_CODEX_SECOND"
