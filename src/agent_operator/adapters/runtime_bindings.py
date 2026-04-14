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
    claude_supports_fork = _supports_session_fork(claude_adapter)
    codex_supports_fork = _supports_session_fork(codex_adapter)
    opencode_supports_fork = _supports_session_fork(opencode_adapter)
    return {
        "claude_acp": AgentRuntimeBinding(
            agent_key="claude_acp",
            descriptor=_claude_descriptor(supports_fork=claude_supports_fork),
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
            descriptor=_codex_descriptor(supports_fork=codex_supports_fork),
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
            descriptor=_opencode_descriptor(supports_fork=opencode_supports_fork),
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
            handle_server_request=hooks.handle_server_request,
        )

    return factory


def _supports_session_fork(adapter: object) -> bool:
    hooks = getattr(getattr(adapter, "_runner", None), "_hooks", None)
    return callable(getattr(hooks, "configure_loaded_session", None))


def _capabilities_for_acp_agent(
    *,
    follow_up_description: str,
    supports_fork: bool,
) -> list[AgentCapability]:
    capabilities = [
        AgentCapability(name="acp", description="ACP session over stdio"),
        AgentCapability(name="follow_up", description=follow_up_description),
    ]
    if supports_fork:
        capabilities.append(
            AgentCapability(name="fork", description="Can fork an existing ACP session")
        )
    capabilities.extend(standard_coding_agent_capabilities())
    return capabilities


def _claude_descriptor(*, supports_fork: bool) -> AgentDescriptor:
    return AgentDescriptor(
        key="claude_acp",
        display_name="Claude Code via ACP",
        capabilities=_capabilities_for_acp_agent(
            follow_up_description="Can resume Claude ACP sessions",
            supports_fork=supports_fork,
        ),
        supports_follow_up=True,
        supports_cancellation=True,
        supports_fork=supports_fork,
        metadata={"permission_resume_mode": "in_turn_continuation"},
    )


def _codex_descriptor(*, supports_fork: bool) -> AgentDescriptor:
    return AgentDescriptor(
        key="codex_acp",
        display_name="Codex via ACP",
        capabilities=_capabilities_for_acp_agent(
            follow_up_description="Can resume prior Codex sessions",
            supports_fork=supports_fork,
        ),
        supports_follow_up=True,
        supports_cancellation=True,
        supports_fork=supports_fork,
        metadata={"permission_resume_mode": "explicit_follow_up"},
    )


def _opencode_descriptor(*, supports_fork: bool) -> AgentDescriptor:
    return AgentDescriptor(
        key="opencode_acp",
        display_name="OpenCode via ACP",
        capabilities=_capabilities_for_acp_agent(
            follow_up_description="Can resume prior OpenCode sessions",
            supports_fork=supports_fork,
        ),
        supports_follow_up=True,
        supports_cancellation=True,
        supports_fork=supports_fork,
        metadata={"permission_resume_mode": "explicit_follow_up"},
    )


__all__ = [
    "AgentRuntimeBinding",
    "AgentSessionRuntimeFactory",
    "AdapterRuntimeFactory",
    "build_agent_runtime_bindings",
]
