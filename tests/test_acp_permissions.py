from __future__ import annotations

from pathlib import Path

from agent_operator.acp.permissions import (
    AcpPermissionDecision,
    AcpPermissionInteraction,
    evaluate_permission_request,
    normalize_permission_request,
    render_permission_decision,
    waiting_message_for_request,
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
