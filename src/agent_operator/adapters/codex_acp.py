from __future__ import annotations

import shlex
from collections.abc import Callable
from pathlib import Path
from typing import Any

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


class CodexAcpAgentAdapter:
    def __init__(
        self,
        command: str = "codex-acp",
        model: str | None = None,
        reasoning_effort: str | None = None,
        approval_policy: str | None = None,
        sandbox_mode: str | None = None,
        timeout_seconds: float | None = None,
        mcp_servers: list[dict[str, object]] | None = None,
        substrate_backend: str = "bespoke",
        stdio_limit_bytes: int = 1_048_576,
        working_directory: Path | None = None,
        connection_factory: Callable[[Path, Path], AcpConnection] | None = None,
        permission_evaluator: PermissionEvaluator | None = None,
    ) -> None:
        self._command = _build_codex_acp_command(
            command,
            approval_policy=approval_policy,
            sandbox_mode=sandbox_mode,
        )
        self._approval_policy = approval_policy
        self._model = model
        self._reasoning_effort = reasoning_effort
        self._timeout_seconds = timeout_seconds
        self._mcp_servers = list(mcp_servers or [])
        self._substrate_backend = substrate_backend
        self._stdio_limit_bytes = stdio_limit_bytes
        self._working_directory = working_directory or Path.cwd()
        self._connection_factory = connection_factory or self._default_connection_factory
        self._permission_evaluator = permission_evaluator
        self._runner = AcpSessionRunner(
            adapter_key="codex_acp",
            working_directory=self._working_directory,
            mcp_servers=self._mcp_servers,
            connection_factory=self._connection_factory,
            hooks=_CodexAcpHooks(self),
        )
        self._sessions = self._runner.sessions

    async def describe(self) -> AgentDescriptor:
        return AgentDescriptor(
            key="codex_acp",
            display_name="Codex via ACP",
            capabilities=[
                AgentCapability(name="acp", description="ACP session over stdio"),
                AgentCapability(name="follow_up", description="Can resume prior Codex sessions"),
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
                env_var_hint="OPERATOR_CODEX_ACP__COMMAND",
                stdio_limit_bytes=self._stdio_limit_bytes,
            )
        return AcpSubprocessConnection(
            command=self._command,
            cwd=cwd,
            log_path=log_path,
            env_var_hint="OPERATOR_CODEX_ACP__COMMAND",
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
        if self._reasoning_effort:
            await connection.request(
                "session/set_config_option",
                {
                    "sessionId": session_id,
                    "configId": "reasoning_effort",
                    "value": self._reasoning_effort,
                },
            )


class _CodexAcpHooks:
    adapter_key = "codex_acp"
    running_message = "Codex ACP turn is running."
    completed_message = "Codex ACP turn completed."
    follow_up_running_error = "Cannot send a follow-up while a Codex ACP turn is still running."

    def __init__(self, owner: CodexAcpAgentAdapter) -> None:
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
            auto_approve=self._should_auto_approve_permission(session, payload),
            permission_evaluator=self._owner._permission_evaluator,
            close_session_connection=self._owner._close_session_connection,
        )

    def classify_collect_exception(
        self,
        exc: Exception,
        stderr: str,
    ) -> AcpCollectErrorClassification:
        status, error_code, retryable, error_raw = _classify_codex_acp_error(str(exc), stderr)
        error_message = _codex_error_message(str(exc), stderr, error_raw)
        return AcpCollectErrorClassification(
            status=status,
            error=AgentError(
                code=error_code,
                message=error_message,
                retryable=retryable,
                raw=error_raw,
            ),
        )

    def should_reuse_live_connection(self, session: AcpSessionState) -> bool:
        return False

    def should_keep_connection_after_collect(self, handle: AgentSessionHandle) -> bool:
        return False

    def unknown_session_error(self, session_id: str) -> str:
        return f"Unknown Codex ACP session: {session_id}"

    def _should_auto_approve_permission(
        self,
        session: AcpSessionState,
        payload: JsonObject,
    ) -> bool:
        if self._owner._approval_policy == "never":
            return True
        params = payload.get("params")
        if not isinstance(params, dict):
            return False
        tool_call = params.get("toolCall")
        if not isinstance(tool_call, dict):
            return False
        raw_input = tool_call.get("rawInput")
        if not isinstance(raw_input, dict):
            return False
        amendment = raw_input.get("proposed_execpolicy_amendment")
        argv = amendment if isinstance(amendment, list) else raw_input.get("command")
        if not isinstance(argv, list) or not all(isinstance(item, str) for item in argv):
            return False
        return _is_safe_git_add_command(session.working_directory, argv)


def _is_safe_git_add_command(working_directory: Path, argv: list[str]) -> bool:
    if len(argv) < 5:
        return False
    if argv[0] != "git" or argv[1] != "-C" or argv[3] != "add":
        return False
    try:
        repo_root = Path(argv[2]).resolve()
        working_root = working_directory.resolve()
    except OSError:
        return False
    if repo_root != working_root:
        return False
    raw_paths = argv[4:]
    if not raw_paths:
        return False
    for raw_path in raw_paths:
        if raw_path == "--":
            continue
        if raw_path.startswith("-"):
            return False
        candidate = Path(raw_path)
        resolved = (
            (repo_root / candidate).resolve()
            if not candidate.is_absolute()
            else candidate.resolve()
        )
        try:
            resolved.relative_to(repo_root)
        except ValueError:
            return False
    return True


def _build_codex_acp_command(
    command: str,
    *,
    approval_policy: str | None = None,
    sandbox_mode: str | None = None,
) -> str:
    argv = shlex.split(command)
    if not argv:
        raise ValueError("ACP command must not be empty.")
    # Insert -c flags before any trailing "--" end-of-options marker so that
    # commands like "npx @zed-industries/codex-acp --" don't treat -c as a
    # positional argument after the "--" separator.
    insert_at = len(argv)
    if argv and argv[-1] == "--":
        insert_at = len(argv) - 1
    extra: list[str] = []
    if approval_policy:
        extra.extend(["-c", f'approval_policy="{approval_policy}"'])
    if sandbox_mode:
        extra.extend(["-c", f'sandbox_mode="{sandbox_mode}"'])
    argv[insert_at:insert_at] = extra
    return shlex.join(argv)


def _classify_codex_acp_error(
    message: str,
    stderr: str,
) -> tuple[AgentResultStatus, str, bool, JsonObject | None]:
    haystack = f"{message}\n{stderr}".lower()
    if _looks_like_provider_capacity(haystack):
        return (
            AgentResultStatus.FAILED,
            "codex_acp_provider_overloaded",
            True,
            {
                "failure_kind": "provider_capacity",
                "recovery_mode": "new_session",
                "codex_error_info": "server_overloaded",
            },
        )
    if _looks_like_recoverable_disconnect(haystack):
        return (
            AgentResultStatus.DISCONNECTED,
            "codex_acp_disconnected",
            True,
            {"recovery_mode": "same_session"},
        )
    if _looks_like_protocol_mismatch(haystack):
        return (
            AgentResultStatus.FAILED,
            "codex_acp_protocol_mismatch",
            True,
            {"recovery_mode": "new_session"},
        )
    return (AgentResultStatus.FAILED, "codex_acp_failed", False, None)


def _looks_like_recoverable_disconnect(haystack: str) -> bool:
    markers = (
        "acp subprocess closed before completing all pending requests",
        "acp subprocess closed before completing pending requests",
        "subprocess closed before completing all pending requests",
        "separator is found, but chunk is longer than limit",
    )
    return any(marker in haystack for marker in markers)


def _looks_like_protocol_mismatch(haystack: str) -> bool:
    """Detect ACP protocol parameter errors (e.g. missing required fields like mcpServers)."""
    markers = (
        "invalid params",
        "missing field",
        "missing required",
        "unknown field",
        "invalid request",
    )
    return any(marker in haystack for marker in markers)


def _looks_like_provider_capacity(haystack: str) -> bool:
    markers = (
        "selected model is at capacity",
        "server_overloaded",
        "model is at capacity",
    )
    return any(marker in haystack for marker in markers)


def _codex_error_message(message: str, stderr: str, raw: JsonObject | None) -> str:
    if raw and raw.get("failure_kind") == "provider_capacity":
        for line in stderr.splitlines():
            if "Selected model is at capacity." in line:
                return "Selected model is at capacity. Please try a different model."
        return "Codex provider is overloaded. Please retry with a different model or later."
    return message
