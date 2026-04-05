from __future__ import annotations

from pathlib import Path

import agent_operator.protocols as protocols
from agent_operator.acp import AcpSdkConnection, AcpSubprocessConnection
from agent_operator.acp.adapter_runtime import AcpAdapterRuntime
from agent_operator.acp.session_runtime import AcpAgentSessionRuntime
from agent_operator.adapters import build_agent_runtime_bindings
from agent_operator.config import (
    ClaudeAcpAdapterSettings,
    CodexAcpAdapterSettings,
    OperatorSettings,
)


def test_build_agent_runtime_bindings_exposes_runtime_factories_and_descriptors() -> None:
    settings = OperatorSettings(
        claude_acp=ClaudeAcpAdapterSettings(substrate_backend="sdk", stdio_limit_bytes=123456),
        codex_acp=CodexAcpAdapterSettings(substrate_backend="bespoke", stdio_limit_bytes=654321),
    )

    bindings = build_agent_runtime_bindings(settings)

    assert sorted(bindings) == ["claude_acp", "codex_acp"]
    claude_binding = bindings["claude_acp"]
    codex_binding = bindings["codex_acp"]
    assert claude_binding.agent_key == "claude_acp"
    assert codex_binding.agent_key == "codex_acp"
    assert claude_binding.descriptor.key == "claude_acp"
    assert codex_binding.descriptor.key == "codex_acp"
    assert claude_binding.descriptor.supports_follow_up is True
    assert codex_binding.descriptor.supports_follow_up is True

    claude_adapter_runtime = claude_binding.build_adapter_runtime(
        working_directory=Path("/tmp/claude"),
        log_path=Path("/tmp/claude.jsonl"),
    )
    codex_adapter_runtime = codex_binding.build_adapter_runtime(
        working_directory=Path("/tmp/codex"),
        log_path=Path("/tmp/codex.jsonl"),
    )

    assert isinstance(claude_adapter_runtime, AcpAdapterRuntime)
    assert isinstance(codex_adapter_runtime, AcpAdapterRuntime)
    assert isinstance(claude_adapter_runtime._connection, AcpSdkConnection)  # type: ignore[attr-defined]
    assert isinstance(codex_adapter_runtime._connection, AcpSubprocessConnection)  # type: ignore[attr-defined]
    assert claude_adapter_runtime._connection._stdio_limit_bytes == 123456  # type: ignore[attr-defined]

    session_runtime = claude_binding.build_session_runtime(
        working_directory=Path("/tmp/claude"),
        log_path=Path("/tmp/claude-session.jsonl"),
    )
    assert isinstance(session_runtime, AcpAgentSessionRuntime)


def test_protocols_package_exposes_runtime_contracts_not_agentadapter() -> None:
    """`agent_operator.protocols` should stop exporting `AgentAdapter` as public truth."""
    assert hasattr(protocols, "AdapterRuntime")
    assert hasattr(protocols, "AgentSessionRuntime")
    assert hasattr(protocols, "OperationRuntime")
    assert not hasattr(protocols, "AgentAdapter")
