from __future__ import annotations

import asyncio
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

from agent_operator.acp import (
    AcpConnection,
    AcpSdkConnection,
    AcpSubprocessConnection,
)
from agent_operator.acp.permissions import (
    AcpPermissionDecision,
    PermissionEvaluationResult,
    evaluate_permission_request,
    normalize_permission_request,
    permission_signature_for_request,
    render_permission_decision,
    serialize_permission_request,
    waiting_message_for_request,
)
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


class ClaudeAcpAgentAdapter:
    def __init__(
        self,
        command: str = (
            "npm exec --yes --package=@zed-industries/claude-code-acp -- "
            "claude-code-acp"
        ),
        model: str | None = None,
        effort: str | None = None,
        permission_mode: str | None = "bypassPermissions",
        timeout_seconds: float | None = None,
        mcp_servers: list[dict[str, object]] | None = None,
        substrate_backend: str = "bespoke",
        stdio_limit_bytes: int = 1_048_576,
        working_directory: Path | None = None,
        connection_factory: Callable[[Path, Path], AcpConnection] | None = None,
        permission_evaluator: PermissionEvaluator | None = None,
    ) -> None:
        self._command = command
        self._model = model
        self._effort = effort
        self._permission_mode = permission_mode
        self._timeout_seconds = timeout_seconds
        self._mcp_servers = list(mcp_servers or [])
        self._substrate_backend = substrate_backend
        self._stdio_limit_bytes = stdio_limit_bytes
        self._working_directory = working_directory or Path.cwd()
        self._connection_factory = connection_factory or self._default_connection_factory
        self._permission_evaluator = permission_evaluator
        self._runner = AcpSessionRunner(
            adapter_key="claude_acp",
            working_directory=self._working_directory,
            mcp_servers=self._mcp_servers,
            connection_factory=self._connection_factory,
            hooks=_ClaudeAcpHooks(self),
        )
        self._sessions = self._runner.sessions

    async def describe(self) -> AgentDescriptor:
        return AgentDescriptor(
            key="claude_acp",
            display_name="Claude Code via ACP",
            capabilities=[
                AgentCapability(name="acp", description="ACP session over stdio"),
                AgentCapability(name="follow_up", description="Can resume Claude ACP sessions"),
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
        env: dict[str, str] = {}
        if self._permission_mode:
            env["CLAUDE_PERMISSION_MODE"] = self._permission_mode
        max_thinking_tokens = _claude_acp_effort_to_max_thinking_tokens(self._effort)
        if max_thinking_tokens is not None:
            env["MAX_THINKING_TOKENS"] = str(max_thinking_tokens)
        if self._substrate_backend == "sdk":
            return AcpSdkConnection(
                command=self._command,
                cwd=cwd,
                log_path=log_path,
                env_var_hint="OPERATOR_CLAUDE_ACP__COMMAND",
                env=env,
                stdio_limit_bytes=self._stdio_limit_bytes,
            )
        return AcpSubprocessConnection(
            command=self._command,
            cwd=cwd,
            log_path=log_path,
            env_var_hint="OPERATOR_CLAUDE_ACP__COMMAND",
            env=env,
        )

    async def _apply_permission_mode(self, connection: AcpConnection, session_id: str) -> None:
        if not self._permission_mode:
            return
        await connection.request(
            "session/set_mode",
            {
                "sessionId": session_id,
                "modeId": self._permission_mode,
            },
        )

    async def _apply_model(self, connection: AcpConnection, session_id: str) -> None:
        if not self._model:
            return
        await connection.request(
            "session/set_model",
            {
                "sessionId": session_id,
                "modelId": self._model,
            },
        )

    def _should_auto_approve_permission(self, payload: JsonObject) -> bool:
        params = payload.get("params")
        if not isinstance(params, dict):
            return False
        tool_call = params.get("toolCall")
        if not isinstance(tool_call, dict):
            return False
        raw_input = tool_call.get("rawInput")
        if not isinstance(raw_input, dict):
            return False
        command = raw_input.get("command")
        if isinstance(command, list):
            command_text = " ".join(str(part) for part in command)
        elif isinstance(command, str):
            command_text = command
        else:
            return False
        normalized = command_text.strip()
        return normalized.startswith("lake build") or normalized.startswith("lake -Kenv=lean build")


class _ClaudeAcpHooks:
    adapter_key = "claude_acp"
    running_message = "Claude ACP turn is running."
    completed_message = "Claude ACP turn completed."
    follow_up_running_error = "Cannot send a follow-up while a Claude ACP turn is still running."

    def __init__(self, owner: ClaudeAcpAgentAdapter) -> None:
        self._owner = owner

    async def configure_new_session(self, connection: AcpConnection, session_id: str) -> None:
        await self._owner._apply_permission_mode(connection, session_id)
        await self._owner._apply_model(connection, session_id)

    async def configure_loaded_session(self, connection: AcpConnection, session_id: str) -> None:
        await self.configure_new_session(connection, session_id)

    async def handle_server_request(self, session: AcpSessionState, payload: JsonObject) -> None:
        request = normalize_permission_request(
            adapter_key=self.adapter_key,
            working_directory=session.working_directory,
            payload=payload,
        )
        if request is None:
            return
        decision = evaluate_permission_request(
            request,
            auto_approve=self._owner._should_auto_approve_permission(payload),
        )
        evaluation = PermissionEvaluationResult(decision=decision)
        if (
            decision is AcpPermissionDecision.ESCALATE
            and self._owner._permission_evaluator is not None
            and isinstance(session.handle.metadata.get("operation_id"), str)
        ):
            evaluation = await self._owner._permission_evaluator.evaluate(
                operation_id=str(session.handle.metadata["operation_id"]),
                working_directory=session.working_directory,
                request=request,
            )
            decision = evaluation.decision
        if decision is AcpPermissionDecision.APPROVE:
            session.pending_input_message = None
            session.pending_input_raw = None
        elif decision is AcpPermissionDecision.ESCALATE:
            session.pending_input_message = waiting_message_for_request(request)
            session.pending_input_raw = {
                "kind": "permission_escalation",
                "request": serialize_permission_request(request),
                "signature": permission_signature_for_request(request).model_dump(mode="json"),
                "rationale": evaluation.rationale,
                "suggested_options": list(evaluation.suggested_options),
                "policy_title": evaluation.policy_title,
                "policy_rule_text": evaluation.policy_rule_text,
                "raw_payload": payload,
            }
        else:
            session.pending_input_message = None
            session.pending_input_raw = None
            session.last_error = (
                evaluation.rationale
                or "Permission request rejected by operator policy."
            )
            await _replace_active_prompt_with_error(session, session.last_error)
        if session.connection is not None:
            await session.connection.respond(
                request.request_id,
                result=render_permission_decision(request=request, decision=decision),
            )
        if decision in {
            AcpPermissionDecision.REJECT,
            AcpPermissionDecision.WAIT_INPUT,
            AcpPermissionDecision.ESCALATE,
        }:
            await self._owner._close_session_connection(session)

    def classify_collect_exception(
        self,
        exc: Exception,
        stderr: str,
    ) -> AcpCollectErrorClassification:
        status, error_code, retryable, error_raw = _classify_claude_acp_error(str(exc), stderr)
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
        return session.connection is not None

    def should_keep_connection_after_collect(self, handle: AgentSessionHandle) -> bool:
        return not handle.one_shot

    def unknown_session_error(self, session_id: str) -> str:
        return f"Unknown Claude ACP session: {session_id}"


def _claude_acp_effort_to_max_thinking_tokens(effort: str | None) -> int | None:
    if effort is None:
        return None
    normalized = effort.strip().lower()
    if normalized == "none":
        return 0
    if normalized == "low":
        return 1024
    if normalized == "medium":
        return 4096
    if normalized == "high":
        return 16384
    if normalized == "max":
        return 32768
    raise ValueError(f"Unsupported Claude ACP effort level: {effort}")


def _classify_claude_acp_error(
    message: str,
    stderr: str,
) -> tuple[AgentResultStatus, str, bool, JsonObject | None]:
    haystack = f"{message}\n{stderr}".lower()
    if _looks_like_rate_limit(haystack):
        retry_after_seconds = _extract_retry_after_seconds(f"{message}\n{stderr}")
        raw: JsonObject = {"rate_limit_detected": True}
        if retry_after_seconds is not None:
            raw["retry_after_seconds"] = retry_after_seconds
        return (AgentResultStatus.FAILED, "claude_acp_rate_limited", True, raw)
    if _looks_like_recoverable_disconnect(haystack):
        return (
            AgentResultStatus.DISCONNECTED,
            "claude_acp_disconnected",
            True,
            {"recovery_mode": "same_session"},
        )
    if _looks_like_protocol_mismatch(haystack):
        return (
            AgentResultStatus.FAILED,
            "claude_acp_protocol_mismatch",
            True,
            {"recovery_mode": "new_session"},
        )
    return (AgentResultStatus.FAILED, "claude_acp_failed", False, None)


def _looks_like_rate_limit(haystack: str) -> bool:
    markers = (
        "rate limit",
        "rate_limit",
        "too many requests",
        "429",
        "usage limit",
        "quota exceeded",
        "credit balance is too low",
        "try again in",
        "you've hit your limit",
        "you hit your limit",
        "resets 1am",
    )
    return any(marker in haystack for marker in markers)


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


async def _raise_runtime_error(message: str) -> JsonObject:
    raise RuntimeError(message)


async def _replace_active_prompt_with_error(session: AcpSessionState, message: str) -> None:
    if session.active_prompt is not None and not session.active_prompt.done():
        session.active_prompt.cancel()
    session.active_prompt = asyncio.create_task(_raise_runtime_error(message))


def _extract_retry_after_seconds(text: str) -> int | None:
    patterns: tuple[tuple[str, int], ...] = (
        (r"try again in\s+(\d+)\s*hours?", 3600),
        (r"try again in\s+(\d+)\s*minutes?", 60),
        (r"try again in\s+(\d+)\s*seconds?", 1),
        (r"retry after\s+(\d+)\s*hours?", 3600),
        (r"retry after\s+(\d+)\s*minutes?", 60),
        (r"retry after\s+(\d+)\s*seconds?", 1),
    )
    lowered = text.lower()
    for pattern, multiplier in patterns:
        match = re.search(pattern, lowered)
        if match is None:
            continue
        return int(match.group(1)) * multiplier
    compound = re.search(
        r"try again in\s+(\d+)\s*h(?:ours?)?\s*(\d+)\s*m(?:in(?:ute)?s?)?",
        lowered,
    )
    if compound is not None:
        return int(compound.group(1)) * 3600 + int(compound.group(2)) * 60
    return None
