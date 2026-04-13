from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from agent_operator.acp.adapter_runtime import AcpAdapterRuntime
from agent_operator.acp.session_runtime import AcpAgentSessionRuntime
from agent_operator.adapters.claude_acp import ClaudeAcpAgentAdapter
from agent_operator.adapters.codex_acp import CodexAcpAgentAdapter
from agent_operator.adapters.opencode_acp import OpencodeAcpAgentAdapter
from agent_operator.config import OperatorSettings
from agent_operator.domain import (
    AgentCapability,
    AgentDescriptor,
    standard_coding_agent_capabilities,
)
from agent_operator.protocols import AdapterRuntime, AgentSessionRuntime, PermissionEvaluator


class AdapterRuntimeFactory(Protocol):
    """Build one adapter runtime for a concrete working directory and log path."""

    def __call__(self, *, working_directory: Path, log_path: Path) -> AdapterRuntime: ...


class AgentSessionRuntimeFactory(Protocol):
    """Build one session runtime for a concrete working directory and log path."""

    def __call__(self, *, working_directory: Path, log_path: Path) -> AgentSessionRuntime: ...


@dataclass(slots=True)
class AgentRuntimeBinding:
    """Composition-root binding between runtime descriptor and runtime factories.

    Attributes:
        agent_key: Stable agent identifier used across config and runtime selection.
        descriptor: Static agent descriptor exposed to planning and operator policy.
        build_adapter_runtime: Factory for the transport-scoped runtime contract.
        build_session_runtime: Factory for the one-live-session runtime contract.
    """

    agent_key: str
    descriptor: AgentDescriptor
    build_adapter_runtime: AdapterRuntimeFactory
    build_session_runtime: AgentSessionRuntimeFactory


def build_agent_runtime_bindings(
    settings: OperatorSettings,
    *,
    permission_evaluator: PermissionEvaluator | None = None,
) -> dict[str, AgentRuntimeBinding]:
    """Build runtime-oriented composition bindings for configured agents.

    Examples:
        >>> settings = OperatorSettings()
        >>> bindings = build_agent_runtime_bindings(settings)
        >>> sorted(bindings)
        ['claude_acp', 'codex_acp', 'opencode_acp']
    """

    claude_adapter = ClaudeAcpAgentAdapter(
        command=settings.claude_acp.command,
        model=settings.claude_acp.model,
        effort=settings.claude_acp.effort,
        permission_mode=settings.claude_acp.permission_mode,
        timeout_seconds=settings.claude_acp.timeout_seconds,
        mcp_servers=settings.claude_acp.mcp_servers,
        substrate_backend=settings.claude_acp.substrate_backend,
        stdio_limit_bytes=settings.claude_acp.stdio_limit_bytes,
        working_directory=settings.claude_acp.working_directory,
        permission_evaluator=permission_evaluator,
    )
    codex_adapter = CodexAcpAgentAdapter(
        command=settings.codex_acp.command,
        model=settings.codex_acp.model,
        reasoning_effort=settings.codex_acp.reasoning_effort,
        approval_policy=settings.codex_acp.approval_policy,
        sandbox_mode=settings.codex_acp.sandbox_mode,
        timeout_seconds=settings.codex_acp.timeout_seconds,
        mcp_servers=settings.codex_acp.mcp_servers,
        substrate_backend=settings.codex_acp.substrate_backend,
        stdio_limit_bytes=settings.codex_acp.stdio_limit_bytes,
        working_directory=settings.codex_acp.working_directory,
        permission_evaluator=permission_evaluator,
    )
    opencode_adapter = OpencodeAcpAgentAdapter(
        command=settings.opencode_acp.command,
        model=settings.opencode_acp.model,
        timeout_seconds=settings.opencode_acp.timeout_seconds,
        mcp_servers=settings.opencode_acp.mcp_servers,
        substrate_backend=settings.opencode_acp.substrate_backend,
        stdio_limit_bytes=settings.opencode_acp.stdio_limit_bytes,
        working_directory=settings.opencode_acp.working_directory,
        permission_evaluator=permission_evaluator,
    )
    return {
        "claude_acp": AgentRuntimeBinding(
            agent_key="claude_acp",
            descriptor=_claude_descriptor(),
            build_adapter_runtime=_build_adapter_runtime_factory(
                adapter_key="claude_acp",
                adapter=claude_adapter,
            ),
            build_session_runtime=_build_session_runtime_factory(
                adapter_key="claude_acp",
                adapter=claude_adapter,
            ),
        ),
        "codex_acp": AgentRuntimeBinding(
            agent_key="codex_acp",
            descriptor=_codex_descriptor(),
            build_adapter_runtime=_build_adapter_runtime_factory(
                adapter_key="codex_acp",
                adapter=codex_adapter,
            ),
            build_session_runtime=_build_session_runtime_factory(
                adapter_key="codex_acp",
                adapter=codex_adapter,
            ),
        ),
        "opencode_acp": AgentRuntimeBinding(
            agent_key="opencode_acp",
            descriptor=_opencode_descriptor(),
            build_adapter_runtime=_build_adapter_runtime_factory(
                adapter_key="opencode_acp",
                adapter=opencode_adapter,
            ),
            build_session_runtime=_build_session_runtime_factory(
                adapter_key="opencode_acp",
                adapter=opencode_adapter,
            ),
        ),
    }


def _build_adapter_runtime_factory(
    *,
    adapter_key: str,
    adapter: object,
) -> AdapterRuntimeFactory:
    def factory(*, working_directory: Path, log_path: Path) -> AdapterRuntime:
        connection = adapter._default_connection_factory(working_directory, log_path)  # type: ignore[attr-defined]
        return AcpAdapterRuntime(
            adapter_key=adapter_key,
            working_directory=working_directory,
            connection=connection,
        )

    return factory


def _build_session_runtime_factory(
    *,
    adapter_key: str,
    adapter: object,
) -> AgentSessionRuntimeFactory:
    def factory(*, working_directory: Path, log_path: Path) -> AgentSessionRuntime:
        adapter_runtime = _build_adapter_runtime_factory(
            adapter_key=adapter_key,
            adapter=adapter,
        )(
            working_directory=working_directory,
            log_path=log_path,
        )
        hooks = adapter._runner._hooks  # type: ignore[attr-defined]
        return AcpAgentSessionRuntime(
            adapter_runtime=adapter_runtime,
            working_directory=working_directory,
            mcp_servers=list(getattr(adapter, "_mcp_servers", [])),
            configure_new_session=hooks.configure_new_session,
            configure_loaded_session=hooks.configure_loaded_session,
        )

    return factory


def _claude_descriptor() -> AgentDescriptor:
    return AgentDescriptor(
        key="claude_acp",
        display_name="Claude Code via ACP",
        capabilities=[
            AgentCapability(name="acp", description="ACP session over stdio"),
            AgentCapability(name="follow_up", description="Can resume Claude ACP sessions"),
            *standard_coding_agent_capabilities(),
        ],
        supports_follow_up=True,
        supports_cancellation=True,
    )


def _codex_descriptor() -> AgentDescriptor:
    return AgentDescriptor(
        key="codex_acp",
        display_name="Codex via ACP",
        capabilities=[
            AgentCapability(name="acp", description="ACP session over stdio"),
            AgentCapability(name="follow_up", description="Can resume prior Codex sessions"),
            *standard_coding_agent_capabilities(),
        ],
        supports_follow_up=True,
        supports_cancellation=True,
    )


def _opencode_descriptor() -> AgentDescriptor:
    return AgentDescriptor(
        key="opencode_acp",
        display_name="OpenCode via ACP",
        capabilities=[
            AgentCapability(name="acp", description="ACP session over stdio"),
            AgentCapability(name="follow_up", description="Can resume prior OpenCode sessions"),
            *standard_coding_agent_capabilities(),
        ],
        supports_follow_up=True,
        supports_cancellation=True,
    )


__all__ = [
    "AgentRuntimeBinding",
    "AgentSessionRuntimeFactory",
    "AdapterRuntimeFactory",
    "build_agent_runtime_bindings",
]
