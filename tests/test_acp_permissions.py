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
        return PermissionEvaluationResult(
            decision=AcpPermissionDecision.ESCALATE,
            rationale="Brain chose to escalate.",
            suggested_options=("Approve once", "Reject"),
            decision_source="brain",
        )


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


def test_permission_decision_prompt_for_collaborative_allows_escalation() -> None:
    from agent_operator.domain import InvolvementLevel, OperationGoal, OperationState
    from agent_operator.providers.prompting import build_permission_decision_prompt

    state = OperationState(
        goal=OperationGoal(objective="continue"),
        involvement_level=InvolvementLevel.COLLABORATIVE,
    )
    prompt = build_permission_decision_prompt(
        state,
        request_payload={"kind": "permission"},
        active_policy_payload=[],
    )

    assert "collaborative" in prompt
    assert "escalate" in prompt.lower()
    assert "Do not escalate" not in prompt


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
        handle=AgentSessionHandle(
            adapter_key="codex_acp",
            session_id="sess-1",
            metadata={"operation_id": "op-test"},
        ),
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
        assert session.pending_input_raw["decision"] == "escalate"
        assert session.pending_input_raw["decision_source"] == "brain"
        assert session.pending_input_raw["rationale"] == "Brain chose to escalate."
        assert session.pending_input_raw["suggested_options"] == ["Approve once", "Reject"]
        assert [item["event_type"] for item in session.permission_event_payloads] == [
            "permission.request.observed",
            "permission.request.escalated",
            "permission.request.followup_required",
        ]
        assert session.permission_event_payloads[1]["rationale"] == "Brain chose to escalate."
        assert session.handle.metadata["closed"] == "yes"
    finally:
        assert session.active_prompt is not None
        session.active_prompt.cancel()


@pytest.mark.anyio
async def test_shared_permission_helper_approve_leaves_session_open() -> None:
    session = _session_state()
    try:
        handled = await handle_permission_server_request(
            adapter_key="codex_acp",
            session=session,
            payload={
                "jsonrpc": "2.0",
                "id": 12,
                "method": "session/request_permission",
                "params": {
                    "sessionId": "sess-1",
                    "toolCall": {
                        "title": "Run tests",
                        "rawInput": {"command": ["pytest"]},
                    },
                    "options": [
                        {"optionId": "approved", "kind": "allow_once"},
                        {"optionId": "abort", "kind": "reject_once"},
                    ],
                },
            },
            auto_approve=True,
            permission_evaluator=None,
            close_session_connection=_close_connection,
        )

        assert handled is True
        assert session.pending_input_message is None
        assert session.pending_input_raw is None
        assert session.last_error is None
        assert [item["event_type"] for item in session.permission_event_payloads] == [
            "permission.request.observed",
            "permission.request.decided",
        ]
        assert session.permission_event_payloads[1]["decision"] == "approve"
        assert session.permission_event_payloads[1]["decision_source"] == "deterministic_rule"
        assert session.handle.metadata.get("closed") != "yes"
    finally:
        assert session.active_prompt is not None
        session.active_prompt.cancel()


@pytest.mark.anyio
async def test_shared_permission_helper_reject_sets_last_error_and_closes() -> None:
    class _RejectEvaluator:
        async def evaluate(
            self, *, operation_id: str, working_directory: object, request: object
        ) -> PermissionEvaluationResult:
            return PermissionEvaluationResult(
                decision=AcpPermissionDecision.REJECT,
                rationale="Rejected by policy.",
            )

    # operation_id must be in metadata for the evaluator to be called
    # (see runtime_permissions.py:59)
    session = AcpSessionState(
        handle=AgentSessionHandle(
            adapter_key="codex_acp",
            session_id="sess-1",
            metadata={"operation_id": "op-test"},
        ),
        working_directory=Path("/tmp/repo"),
        acp_session_id="sess-1",
        connection=cast(AcpConnection, _FakeConnection()),
        active_prompt=asyncio.create_task(asyncio.sleep(60, result={})),
    )
    try:
        handled = await handle_permission_server_request(
            adapter_key="codex_acp",
            session=session,
            payload={
                "jsonrpc": "2.0",
                "id": 13,
                "method": "session/request_permission",
                "params": {
                    "sessionId": "sess-1",
                    "toolCall": {
                        "title": "Run git push --force",
                        "rawInput": {"command": ["git", "push", "--force"]},
                    },
                    "options": [
                        {"optionId": "approved", "kind": "allow_once"},
                        {"optionId": "abort", "kind": "reject_once"},
                    ],
                },
            },
            auto_approve=False,
            permission_evaluator=_RejectEvaluator(),
            close_session_connection=_close_connection,
        )

        assert handled is True
        assert session.pending_input_message is None
        assert session.pending_input_raw is None
        assert session.last_error == "Rejected by policy."
        assert [item["event_type"] for item in session.permission_event_payloads] == [
            "permission.request.observed",
            "permission.request.decided",
            "permission.request.followup_required",
        ]
        assert session.permission_event_payloads[1]["decision"] == "reject"
        assert session.permission_event_payloads[1]["rationale"] == "Rejected by policy."
        assert session.handle.metadata["closed"] == "yes"
    finally:
        if session.active_prompt is not None and not session.active_prompt.done():
            session.active_prompt.cancel()


@pytest.mark.anyio
async def test_shared_permission_helper_claude_reject_does_not_require_followup() -> None:
    class _RejectEvaluator:
        async def evaluate(
            self, *, operation_id: str, working_directory: object, request: object
        ) -> PermissionEvaluationResult:
            return PermissionEvaluationResult(
                decision=AcpPermissionDecision.REJECT,
                rationale="Rejected by operator policy.",
            )

    session = AcpSessionState(
        handle=AgentSessionHandle(
            adapter_key="claude_acp",
            session_id="sess-1",
            metadata={"operation_id": "op-test"},
        ),
        working_directory=Path("/tmp/repo"),
        acp_session_id="sess-1",
        connection=cast(AcpConnection, _FakeConnection()),
        active_prompt=asyncio.create_task(asyncio.sleep(60, result={})),
    )
    try:
        handled = await handle_permission_server_request(
            adapter_key="claude_acp",
            session=session,
            payload={
                "jsonrpc": "2.0",
                "id": 14,
                "method": "session/request_permission",
                "params": {
                    "sessionId": "sess-1",
                    "toolCall": {
                        "title": "Run risky command",
                        "rawInput": {"command": ["git", "push", "--force"]},
                    },
                    "options": [
                        {"optionId": "allow_always", "kind": "allow_always"},
                        {"optionId": "reject", "kind": "reject_once"},
                    ],
                },
            },
            auto_approve=False,
            permission_evaluator=_RejectEvaluator(),
            close_session_connection=_close_connection,
        )

        assert handled is True
        assert [item["event_type"] for item in session.permission_event_payloads] == [
            "permission.request.observed",
            "permission.request.decided",
        ]
        assert session.permission_event_payloads[1]["decision"] == "reject"
    finally:
        if session.active_prompt is not None and not session.active_prompt.done():
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
        assert [item["event_type"] for item in session.permission_event_payloads] == [
            "permission.request.observed",
            "permission.request.escalated",
        ]
        assert session.handle.metadata["closed"] == "yes"
    finally:
        assert session.active_prompt is not None
        session.active_prompt.cancel()
