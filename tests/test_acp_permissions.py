from __future__ import annotations

import asyncio
from pathlib import Path
from typing import cast

import pytest

from agent_operator.acp import AcpConnection
from agent_operator.acp.permissions import (
    AcpPermissionDecision,
    AcpPermissionInteraction,
    PermissionEvaluationResult,
    evaluate_permission_request,
    normalize_permission_request,
    render_permission_decision,
    waiting_message_for_request,
)
from agent_operator.acp.runtime_permissions import handle_permission_server_request
from agent_operator.acp.session_runner import AcpSessionState
from agent_operator.domain import AgentSessionHandle


class _FakeConnection:
    def __init__(self) -> None:
        self.responses: list[tuple[int, dict[str, object] | None, dict[str, object] | None]] = []

    async def respond(
        self,
        request_id: int,
        *,
        result: dict[str, object] | None = None,
        error: dict[str, object] | None = None,
    ) -> None:
        self.responses.append((request_id, result, error))


class _FakePermissionEvaluator:
    async def evaluate(self, **_: object) -> PermissionEvaluationResult:
        return PermissionEvaluationResult(decision=AcpPermissionDecision.ESCALATE)


def test_normalize_and_render_claude_session_permission_request() -> None:
    request = normalize_permission_request(
        adapter_key="claude_acp",
        working_directory=Path("/tmp/repo"),
        payload={
            "jsonrpc": "2.0",
            "id": 7,
            "method": "session/request_permission",
            "params": {
                "sessionId": "sess-1",
                "toolCall": {
                    "title": "Run build",
                    "rawInput": {"command": "lake build Example"},
                },
                "options": [
                    {"optionId": "allow_always", "kind": "allow_always"},
                    {"optionId": "reject", "kind": "reject_once"},
                ],
            },
        },
    )
    assert request is not None
    assert request.interaction is AcpPermissionInteraction.APPROVAL
    assert waiting_message_for_request(request) == "Claude ACP turn is waiting for approval."
    assert evaluate_permission_request(request, auto_approve=True) is AcpPermissionDecision.APPROVE
    assert render_permission_decision(
        request=request,
        decision=AcpPermissionDecision.APPROVE,
    ) == {"outcome": {"outcome": "selected", "optionId": "allow_always"}}


def test_normalize_and_render_codex_user_input_request() -> None:
    request = normalize_permission_request(
        adapter_key="codex_acp",
        working_directory=Path("/tmp/repo"),
        payload={
            "jsonrpc": "2.0",
            "id": 11,
            "method": "item/tool/requestUserInput",
            "params": {
                "sessionId": "sess-1",
            },
        },
    )
    assert request is not None
    assert request.interaction is AcpPermissionInteraction.USER_INPUT
    assert (
        evaluate_permission_request(request, auto_approve=False)
        is AcpPermissionDecision.WAIT_INPUT
    )
    assert waiting_message_for_request(request) == "Codex ACP turn requested user input."
    assert render_permission_decision(
        request=request,
        decision=AcpPermissionDecision.WAIT_INPUT,
    ) == {"answers": {}}


def test_render_codex_reject_uses_abort_option() -> None:
    request = normalize_permission_request(
        adapter_key="codex_acp",
        working_directory=Path("/tmp/repo"),
        payload={
            "jsonrpc": "2.0",
            "id": 9,
            "method": "session/request_permission",
            "params": {
                "sessionId": "sess-1",
                "toolCall": {
                    "title": "Run git add",
                    "rawInput": {"command": ["git", "add", "x"]},
                },
                "options": [
                    {"optionId": "approved", "kind": "allow_once"},
                    {"optionId": "abort", "kind": "reject_once"},
                ],
            },
        },
    )
    assert request is not None
    assert render_permission_decision(
        request=request,
        decision=AcpPermissionDecision.REJECT,
    ) == {"outcome": {"outcome": "selected", "optionId": "abort"}}


def test_permission_decision_prompt_for_auto_forbids_escalation() -> None:
    from agent_operator.domain import OperationGoal, OperationState
    from agent_operator.providers.prompting import build_permission_decision_prompt

    state = OperationState(goal=OperationGoal(objective="continue"))
    prompt = build_permission_decision_prompt(
        state,
        request_payload={"kind": "permission"},
        active_policy_payload=[],
    )

    assert "Do not escalate this request to a human." in prompt


def test_permission_decision_prompt_for_approval_heavy_allows_escalation() -> None:
    from agent_operator.domain import InvolvementLevel, OperationGoal, OperationState
    from agent_operator.providers.prompting import build_permission_decision_prompt

    state = OperationState(
        goal=OperationGoal(objective="continue"),
        involvement_level=InvolvementLevel.APPROVAL_HEAVY,
    )
    prompt = build_permission_decision_prompt(
        state,
        request_payload={"kind": "permission"},
        active_policy_payload=[],
    )

    assert "Escalation to a blocking human attention request is allowed" in prompt


async def _close_connection(session: AcpSessionState) -> None:
    session.handle.metadata["closed"] = "yes"


def _session_state() -> AcpSessionState:
    return AcpSessionState(
        handle=AgentSessionHandle(adapter_key="codex_acp", session_id="sess-1", metadata={}),
        working_directory=Path("/tmp/repo"),
        acp_session_id="sess-1",
        connection=cast(AcpConnection, _FakeConnection()),
        active_prompt=asyncio.create_task(asyncio.sleep(60, result={})),
    )


@pytest.mark.anyio
async def test_shared_permission_helper_records_escalation_payload() -> None:
    session = _session_state()
    try:
        handled = await handle_permission_server_request(
            adapter_key="codex_acp",
            session=session,
            payload={
                "jsonrpc": "2.0",
                "id": 9,
                "method": "session/request_permission",
                "params": {
                    "sessionId": "sess-1",
                    "toolCall": {
                        "title": "Run git add",
                        "rawInput": {"command": ["git", "add", "x"]},
                    },
                    "options": [
                        {"optionId": "approved", "kind": "allow_once"},
                        {"optionId": "abort", "kind": "reject_once"},
                    ],
                },
            },
            auto_approve=False,
            permission_evaluator=_FakePermissionEvaluator(),
            close_session_connection=_close_connection,
        )

        assert handled is True
        assert session.pending_input_message == "Codex ACP turn is waiting for approval."
        assert isinstance(session.pending_input_raw, dict)
        assert session.pending_input_raw["kind"] == "permission_escalation"
        assert session.handle.metadata["closed"] == "yes"
    finally:
        assert session.active_prompt is not None
        session.active_prompt.cancel()


@pytest.mark.anyio
async def test_shared_permission_helper_records_user_input_wait() -> None:
    session = _session_state()
    try:
        handled = await handle_permission_server_request(
            adapter_key="codex_acp",
            session=session,
            payload={
                "jsonrpc": "2.0",
                "id": 11,
                "method": "item/tool/requestUserInput",
                "params": {"sessionId": "sess-1"},
            },
            auto_approve=False,
            permission_evaluator=None,
            close_session_connection=_close_connection,
        )

        assert handled is True
        assert session.pending_input_message == "Codex ACP turn requested user input."
        assert isinstance(session.pending_input_raw, dict)
        assert session.pending_input_raw["kind"] == "user_input_request"
        assert session.handle.metadata["closed"] == "yes"
    finally:
        assert session.active_prompt is not None
        session.active_prompt.cancel()
