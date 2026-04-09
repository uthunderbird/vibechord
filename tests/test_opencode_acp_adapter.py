from __future__ import annotations

from agent_operator.adapters.opencode_acp import (
    _build_opencode_acp_command,
    _classify_opencode_acp_error,
)
from agent_operator.domain import AgentResultStatus


def test_build_opencode_acp_command_normalizes_whitespace() -> None:
    assert _build_opencode_acp_command("  opencode   acp  ") == "opencode acp"


def test_classify_opencode_acp_error_detects_recoverable_disconnect() -> None:
    status, code, retryable, raw = _classify_opencode_acp_error(
        "ACP subprocess closed before completing all pending requests.",
        "",
    )
    assert status == AgentResultStatus.DISCONNECTED
    assert code == "opencode_acp_disconnected"
    assert retryable is True
    assert raw == {"recovery_mode": "same_session"}


def test_classify_opencode_acp_error_detects_protocol_mismatch() -> None:
    status, code, retryable, raw = _classify_opencode_acp_error(
        "invalid request: missing field value",
        "",
    )
    assert status == AgentResultStatus.FAILED
    assert code == "opencode_acp_protocol_mismatch"
    assert retryable is True
    assert raw == {"recovery_mode": "new_session"}


def test_classify_opencode_acp_error_falls_back_to_failed_unknown() -> None:
    status, code, retryable, raw = _classify_opencode_acp_error(
        "tool execution failed",
        "",
    )
    assert status == AgentResultStatus.FAILED
    assert code == "opencode_acp_failed"
    assert retryable is False
    assert raw is None
