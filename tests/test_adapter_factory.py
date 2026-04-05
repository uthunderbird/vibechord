from __future__ import annotations

from pathlib import Path

import agent_operator.adapters as adapters
from agent_operator.acp import AcpSdkConnection, AcpSubprocessConnection
from agent_operator.adapters import build_agent_runtime_bindings
from agent_operator.config import (
    ClaudeAcpAdapterSettings,
    CodexAcpAdapterSettings,
    OperatorSettings,
)


def test_build_agent_runtime_bindings_respects_per_adapter_substrate_backend() -> None:
    settings = OperatorSettings(
        claude_acp=ClaudeAcpAdapterSettings(substrate_backend="sdk", stdio_limit_bytes=123456),
        codex_acp=CodexAcpAdapterSettings(substrate_backend="bespoke", stdio_limit_bytes=654321),
    )

    bindings = build_agent_runtime_bindings(settings)
    claude_runtime = bindings["claude_acp"].build_adapter_runtime(
        working_directory=Path("/tmp/claude"),
        log_path=Path("/tmp/claude.jsonl"),
    )
    codex_runtime = bindings["codex_acp"].build_adapter_runtime(
        working_directory=Path("/tmp/codex"),
        log_path=Path("/tmp/codex.jsonl"),
    )

    assert isinstance(claude_runtime._connection, AcpSdkConnection)  # type: ignore[attr-defined]
    assert isinstance(codex_runtime._connection, AcpSubprocessConnection)  # type: ignore[attr-defined]
    assert claude_runtime._connection._stdio_limit_bytes == 123456  # type: ignore[attr-defined]


def test_adapters_package_exposes_runtime_bindings_not_build_agent_adapters() -> None:
    assert hasattr(adapters, "build_agent_runtime_bindings")
    assert not hasattr(adapters, "build_agent_adapters")
