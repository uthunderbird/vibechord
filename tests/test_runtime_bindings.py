from __future__ import annotations

from pathlib import Path

import agent_operator.protocols as protocols
from agent_operator.acp import AcpSdkConnection, AcpSubprocessConnection
from agent_operator.acp.adapter_runtime import AcpAdapterRuntime
from agent_operator.acp.session_runtime import AcpAgentSessionRuntime
from agent_operator.adapters import build_agent_runtime_bindings
from agent_operator.adapters.runtime_bindings import _supports_session_fork
from agent_operator.config import (
    ClaudeAcpAdapterSettings,
    CodexAcpAdapterSettings,
    OpencodeAcpAdapterSettings,
    OperatorSettings,
)
from agent_operator.testing.operator_service_support import FakeAgent
from agent_operator.testing.runtime_bindings import build_test_runtime_bindings


def test_build_agent_runtime_bindings_exposes_runtime_factories_and_descriptors() -> None:
    settings = OperatorSettings(
        claude_acp=ClaudeAcpAdapterSettings(substrate_backend="sdk", stdio_limit_bytes=123456),
        codex_acp=CodexAcpAdapterSettings(substrate_backend="bespoke", stdio_limit_bytes=654321),
        opencode_acp=OpencodeAcpAdapterSettings(substrate_backend="sdk", stdio_limit_bytes=222222),
    )

    bindings = build_agent_runtime_bindings(settings)

    assert sorted(bindings) == ["claude_acp", "codex_acp", "opencode_acp"]
    claude_binding = bindings["claude_acp"]
    codex_binding = bindings["codex_acp"]
    opencode_binding = bindings["opencode_acp"]
    assert claude_binding.agent_key == "claude_acp"
    assert codex_binding.agent_key == "codex_acp"
    assert opencode_binding.agent_key == "opencode_acp"
    assert claude_binding.descriptor.key == "claude_acp"
    assert codex_binding.descriptor.key == "codex_acp"
    assert opencode_binding.descriptor.key == "opencode_acp"
    assert opencode_binding.descriptor.display_name == "OpenCode via ACP"
    assert claude_binding.descriptor.supports_follow_up is True
    assert codex_binding.descriptor.supports_follow_up is True
    assert opencode_binding.descriptor.supports_follow_up is True
    assert claude_binding.descriptor.supports_fork is True
    assert codex_binding.descriptor.supports_fork is True
    assert opencode_binding.descriptor.supports_fork is True
    assert "fork" in [item.name for item in claude_binding.descriptor.capabilities]
    assert "fork" in [item.name for item in codex_binding.descriptor.capabilities]
    assert "fork" in [item.name for item in opencode_binding.descriptor.capabilities]

    claude_adapter_runtime = claude_binding.build_adapter_runtime(
        working_directory=Path("/tmp/claude"),
        log_path=Path("/tmp/claude.jsonl"),
    )
    codex_adapter_runtime = codex_binding.build_adapter_runtime(
        working_directory=Path("/tmp/codex"),
        log_path=Path("/tmp/codex.jsonl"),
    )
    opencode_adapter_runtime = opencode_binding.build_adapter_runtime(
        working_directory=Path("/tmp/opencode"),
        log_path=Path("/tmp/opencode.jsonl"),
    )

    assert isinstance(claude_adapter_runtime, AcpAdapterRuntime)
    assert isinstance(codex_adapter_runtime, AcpAdapterRuntime)
    assert isinstance(opencode_adapter_runtime, AcpAdapterRuntime)
    assert isinstance(claude_adapter_runtime._connection, AcpSdkConnection)  # type: ignore[attr-defined]
    assert isinstance(codex_adapter_runtime._connection, AcpSubprocessConnection)  # type: ignore[attr-defined]
    assert isinstance(opencode_adapter_runtime._connection, AcpSdkConnection)  # type: ignore[attr-defined]
    assert claude_adapter_runtime._connection._stdio_limit_bytes == 123456  # type: ignore[attr-defined]
    assert opencode_adapter_runtime._connection._stdio_limit_bytes == 222222  # type: ignore[attr-defined]

    session_runtime = claude_binding.build_session_runtime(
        working_directory=Path("/tmp/claude"),
        log_path=Path("/tmp/claude-session.jsonl"),
    )
    assert isinstance(session_runtime, AcpAgentSessionRuntime)
    assert session_runtime._configure_new_session is not None  # type: ignore[attr-defined]
    assert session_runtime._configure_loaded_session is not None  # type: ignore[attr-defined]
    assert session_runtime._handle_server_request is not None  # type: ignore[attr-defined]


def test_protocols_package_exposes_runtime_contracts_not_agentadapter() -> None:
    """`agent_operator.protocols` should stop exporting `AgentAdapter` as public truth."""
    assert hasattr(protocols, "AdapterRuntime")
    assert hasattr(protocols, "AgentSessionRuntime")
    assert hasattr(protocols, "OperationRuntime")
    assert not hasattr(protocols, "AgentAdapter")


def test_supports_session_fork_requires_loaded_session_configuration_hook() -> None:
    class _Hooks:
        configure_loaded_session = None

    class _Runner:
        _hooks = _Hooks()

    class _Adapter:
        _runner = _Runner()

    assert _supports_session_fork(_Adapter()) is False


def test_build_test_runtime_bindings_only_advertises_fork_when_agent_implements_it() -> None:
    fake_agent = FakeAgent()
    fake_agent.supports_fork = True  # type: ignore[attr-defined]

    bindings = build_test_runtime_bindings({"claude_acp": fake_agent})

    assert bindings["claude_acp"].descriptor.supports_fork is False
