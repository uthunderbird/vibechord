from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

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
from agent_operator.acp.session_runner import AcpSessionState
from agent_operator.protocols import PermissionEvaluator

JsonObject = dict[str, Any]


async def handle_permission_server_request(
    *,
    adapter_key: str,
    session: AcpSessionState,
    payload: JsonObject,
    auto_approve: bool,
    permission_evaluator: PermissionEvaluator | None,
    close_session_connection: Callable[[AcpSessionState], Awaitable[None]],
) -> bool:
    """Handle a shared ACP permission or input request for an adapter session.

    Args:
        adapter_key: Adapter identity used for normalization and rendered messaging.
        session: Mutable ACP session state to update.
        payload: Raw server request payload from ACP.
        auto_approve: Whether the adapter-specific local heuristic approves immediately.
        permission_evaluator: Optional operator policy evaluator for escalated requests.
        close_session_connection: Callback that closes the live ACP connection when needed.

    Returns:
        `True` when the payload was recognized as a shared permission/input request.
        `False` when the payload should be ignored by this helper.
    """

    request = normalize_permission_request(
        adapter_key=adapter_key,
        working_directory=session.working_directory,
        payload=payload,
    )
    if request is None:
        return False
    decision = evaluate_permission_request(request, auto_approve=auto_approve)
    evaluation = PermissionEvaluationResult(decision=decision)
    if (
        decision is AcpPermissionDecision.ESCALATE
        and permission_evaluator is not None
        and isinstance(session.handle.metadata.get("operation_id"), str)
    ):
        evaluation = await permission_evaluator.evaluate(
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
    elif decision is AcpPermissionDecision.WAIT_INPUT:
        session.pending_input_message = waiting_message_for_request(request)
        session.pending_input_raw = {
            "kind": "user_input_request",
            "request": serialize_permission_request(request),
            "raw_payload": payload,
        }
    else:
        session.pending_input_message = None
        session.pending_input_raw = None
        session.last_error = (
            evaluation.rationale
            or "Permission request rejected by operator policy."
        )
        await replace_active_prompt_with_error(session, session.last_error)
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
        await close_session_connection(session)
    return True


async def replace_active_prompt_with_error(session: AcpSessionState, message: str) -> None:
    """Replace the active prompt task with a terminal runtime error."""

    if session.active_prompt is not None and not session.active_prompt.done():
        session.active_prompt.cancel()
    session.active_prompt = asyncio.create_task(_raise_runtime_error(message))


async def _raise_runtime_error(message: str) -> JsonObject:
    raise RuntimeError(message)
