from __future__ import annotations

import shlex
from collections.abc import Callable
from pathlib import Path
from typing import Any, Literal

from agent_operator.acp import (
    AcpConnection,
    AcpSdkConnection,
    AcpSubprocessConnection,
)
from agent_operator.acp.runtime_permissions import handle_permission_server_request
from agent_operator.acp.session_runner import (
    AcpCollectErrorClassification,
    AcpSessionRunner,
    AcpSessionState,
)
from agent_operator.domain import (
    AgentCapability,
    AgentDescriptor,
    AgentError,
    AgentProgress,
    AgentResult,
    AgentResultStatus,
    AgentSessionHandle,
    standard_coding_agent_capabilities,
)
from agent_operator.dtos.requests import AgentRunRequest
from agent_operator.protocols import PermissionEvaluator

JsonObject = dict[str, Any]


class OpencodeAcpAgentAdapter:
    def __init__(
        self,
        command: str = "opencode acp",
        model: str | None = None,
        timeout_seconds: float | None = None,
        mcp_servers: list[dict[str, object]] | None = None,
        substrate_backend: Literal["bespoke", "sdk"] = "bespoke",
        stdio_limit_bytes: int = 1_048_576,
        working_directory: Path | None = None,
        connection_factory: Callable[[Path, Path], AcpConnection] | None = None,
        permission_evaluator: PermissionEvaluator | None = None,
    ) -> None:
        self._command = _build_opencode_acp_command(command)
        self._model = model
        self._timeout_seconds = timeout_seconds
        self._mcp_servers = list(mcp_servers or [])
        self._substrate_backend = substrate_backend
        self._stdio_limit_bytes = stdio_limit_bytes
        self._working_directory = working_directory or Path.cwd()
        self._connection_factory = connection_factory or self._default_connection_factory
        self._permission_evaluator = permission_evaluator
        self._runner = AcpSessionRunner(
            adapter_key="opencode_acp",
            working_directory=self._working_directory,
            mcp_servers=self._mcp_servers,
            connection_factory=self._connection_factory,
            hooks=_OpencodeAcpHooks(self),
        )
        self._sessions = self._runner.sessions

    async def describe(self) -> AgentDescriptor:
        return AgentDescriptor(
            key="opencode_acp",
            display_name="OpenCode via ACP",
            capabilities=[
                AgentCapability(name="acp", description="ACP session over stdio"),
                AgentCapability(name="follow_up", description="Can resume prior OpenCode sessions"),
                *standard_coding_agent_capabilities(),
            ],
            supports_follow_up=True,
        )

    async def start(self, request: AgentRunRequest) -> AgentSessionHandle:
        return await self._runner.start(request)

    async def send(self, handle: AgentSessionHandle, message: str) -> None:
        await self._runner.send(handle, message)

    async def poll(self, handle: AgentSessionHandle) -> AgentProgress:
        return await self._runner.poll(handle)

    async def collect(self, handle: AgentSessionHandle) -> AgentResult:
        return await self._runner.collect(handle)

    async def cancel(self, handle: AgentSessionHandle) -> None:
        await self._runner.cancel(handle)

    async def close(self, handle: AgentSessionHandle) -> None:
        await self._runner.close(handle)

    async def _close_session_connection(self, session: AcpSessionState) -> None:
        await self._runner.close_session_connection(session)

    def _default_connection_factory(self, cwd: Path, log_path: Path) -> AcpConnection:
        if self._substrate_backend == "sdk":
            return AcpSdkConnection(
                command=self._command,
                cwd=cwd,
                log_path=log_path,
                env_var_hint="OPERATOR_OPENCODE_ACP__COMMAND",
                stdio_limit_bytes=self._stdio_limit_bytes,
            )
        return AcpSubprocessConnection(
            command=self._command,
            cwd=cwd,
            log_path=log_path,
            env_var_hint="OPERATOR_OPENCODE_ACP__COMMAND",
        )

    async def _configure_session(self, connection: AcpConnection, session_id: str) -> None:
        if self._model:
            await connection.request(
                "session/set_config_option",
                {
                    "sessionId": session_id,
                    "configId": "model",
                    "value": self._model,
                },
            )


class _OpencodeAcpHooks:
    adapter_key = "opencode_acp"
    running_message = "OpenCode ACP turn is running."
    completed_message = "OpenCode ACP turn completed."
    follow_up_running_error = "Cannot send a follow-up while an OpenCode ACP turn is still running."

    def __init__(self, owner: OpencodeAcpAgentAdapter) -> None:
        self._owner = owner

    async def configure_new_session(self, connection: AcpConnection, session_id: str) -> None:
        await self._owner._configure_session(connection, session_id)

    async def configure_loaded_session(self, connection: AcpConnection, session_id: str) -> None:
        await self._owner._configure_session(connection, session_id)

    async def handle_server_request(self, session: AcpSessionState, payload: JsonObject) -> None:
        await handle_permission_server_request(
            adapter_key=self.adapter_key,
            session=session,
            payload=payload,
            auto_approve=False,
            permission_evaluator=self._owner._permission_evaluator,
            close_session_connection=self._owner._close_session_connection,
        )

    def classify_collect_exception(
        self,
        exc: Exception,
        stderr: str,
    ) -> AcpCollectErrorClassification:
        status, error_code, retryable, error_raw = _classify_opencode_acp_error(str(exc), stderr)
        return AcpCollectErrorClassification(
            status=status,
            error=AgentError(
                code=error_code,
                message=str(exc),
                retryable=retryable,
                raw=error_raw,
            ),
        )

    def should_reuse_live_connection(self, session: AcpSessionState) -> bool:
        return False

    def should_keep_connection_after_collect(self, handle: AgentSessionHandle) -> bool:
        return False

    def unknown_session_error(self, session_id: str) -> str:
        return f"Unknown OpenCode ACP session: {session_id}"


def _build_opencode_acp_command(command: str) -> str:
    argv = shlex.split(command)
    if not argv:
        raise ValueError("ACP command must not be empty.")
    return shlex.join(argv)


def _classify_opencode_acp_error(
    message: str,
    stderr: str,
) -> tuple[AgentResultStatus, str, bool, JsonObject | None]:
    haystack = f"{message}\n{stderr}".lower()
    if _looks_like_recoverable_disconnect(haystack):
        return (
            AgentResultStatus.DISCONNECTED,
            "opencode_acp_disconnected",
            True,
            {"recovery_mode": "same_session"},
        )
    if _looks_like_protocol_mismatch(haystack):
        return (
            AgentResultStatus.FAILED,
            "opencode_acp_protocol_mismatch",
            True,
            {"recovery_mode": "new_session"},
        )
    return (AgentResultStatus.FAILED, "opencode_acp_failed", False, None)


def _looks_like_recoverable_disconnect(haystack: str) -> bool:
    markers = (
        "acp subprocess closed before completing all pending requests",
        "acp subprocess closed before completing pending requests",
        "subprocess closed before completing all pending requests",
        "separator is found, but chunk is longer than limit",
    )
    return any(marker in haystack for marker in markers)


def _looks_like_protocol_mismatch(haystack: str) -> bool:
    markers = (
        "invalid params",
        "missing field",
        "missing required",
        "unknown field",
        "invalid request",
    )
    return any(marker in haystack for marker in markers)
