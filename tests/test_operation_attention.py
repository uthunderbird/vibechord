from __future__ import annotations

from agent_operator.application.commands.operation_attention import OperationAttentionCoordinator
from agent_operator.domain import (
    AgentError,
    AgentResult,
    AgentResultStatus,
    AgentSessionHandle,
    AttentionType,
    CommandTargetScope,
    OperationGoal,
    OperationState,
    TaskState,
)


def test_attention_from_incomplete_result_preserves_permission_escalation_metadata() -> None:
    coordinator = OperationAttentionCoordinator()
    state = OperationState(goal=OperationGoal(objective="continue work"))
    task = TaskState(
        task_id="task-1",
        title="Continue theorem work",
        goal="Continue theorem work",
        definition_of_done="Permission boundary is resolved.",
    )
    session = AgentSessionHandle(adapter_key="codex_acp", session_id="sess-1")
    result = AgentResult(
        session_id=session.session_id,
        status=AgentResultStatus.INCOMPLETE,
        error=AgentError(
            code="agent_waiting_input",
            message="Codex ACP turn is waiting for approval.",
            retryable=False,
            raw={
                "kind": "permission_escalation",
                "signature": {
                    "adapter_key": "codex_acp",
                    "method": "session/request_permission",
                    "interaction": "approval",
                    "title": "Edit file",
                    "tool_kind": "edit",
                    "command": ["git", "status"],
                },
                "policy_title": "Codex edit approval",
                "policy_rule_text": "Decision: approve. Exact-match permission signature replay.",
            },
        ),
    )

    attention = coordinator.attention_from_incomplete_result(
        state,
        session,
        task,
        result,
    )

    assert attention is not None
    assert attention.attention_type is AttentionType.APPROVAL_REQUEST
    assert attention.target_scope is CommandTargetScope.SESSION
    assert attention.target_id == session.session_id
    assert attention.metadata["signature"]["adapter_key"] == "codex_acp"
    assert attention.metadata["policy_title"] == "Codex edit approval"
    assert (
        attention.metadata["policy_rule_text"]
        == "Decision: approve. Exact-match permission signature replay."
    )
