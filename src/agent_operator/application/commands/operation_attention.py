from __future__ import annotations

from agent_operator.domain import (
    AgentResult,
    AgentSessionHandle,
    AttentionRequest,
    AttentionStatus,
    AttentionType,
    BrainDecision,
    CommandTargetScope,
    InvolvementLevel,
    OperationState,
    PolicyCoverageStatus,
    TaskState,
)


class OperationAttentionCoordinator:
    """Own one-operation attention lookup and construction rules."""

    def event_payload(self, attention: AttentionRequest) -> dict[str, object]:
        """Return the canonical lifecycle event payload for one attention request.

        Args:
            attention: Attention request to serialize for domain events.

        Returns:
            Stable JSON-serializable payload for attention lifecycle events.
        """

        return {
            "attention_id": attention.attention_id,
            "operation_id": attention.operation_id,
            "attention_type": attention.attention_type.value,
            "title": attention.title,
            "question": attention.question,
            "context_brief": attention.context_brief,
            "target_scope": attention.target_scope.value,
            "target_id": attention.target_id,
            "blocking": attention.blocking,
            "suggested_options": list(attention.suggested_options),
            "status": attention.status.value,
            "answer_text": attention.answer_text,
            "answer_source_command_id": attention.answer_source_command_id,
            "created_at": attention.created_at.isoformat(),
            "answered_at": attention.answered_at.isoformat() if attention.answered_at else None,
            "resolved_at": attention.resolved_at.isoformat() if attention.resolved_at else None,
            "resolution_summary": attention.resolution_summary,
            "metadata": dict(attention.metadata),
        }

    def find_attention_request(
        self,
        state: OperationState,
        attention_id: str | None,
    ) -> AttentionRequest | None:
        if attention_id is None:
            return None
        return next(
            (item for item in state.attention_requests if item.attention_id == attention_id),
            None,
        )

    def open_attention_request(
        self,
        state: OperationState,
        *,
        attention_type: AttentionType,
        title: str,
        question: str,
        context_brief: str | None,
        target_scope: CommandTargetScope,
        target_id: str | None,
        blocking: bool,
        suggested_options: list[str] | None = None,
    ) -> AttentionRequest:
        normalized_question = question.strip()
        existing = next(
            (
                item
                for item in state.attention_requests
                if item.status is AttentionStatus.OPEN
                and item.attention_type is attention_type
                and item.target_scope is target_scope
                and item.target_id == target_id
                and item.question == normalized_question
            ),
            None,
        )
        if existing is not None:
            return existing
        attention = AttentionRequest(
            operation_id=state.operation_id,
            attention_type=attention_type,
            target_scope=target_scope,
            target_id=target_id,
            title=title,
            question=normalized_question,
            context_brief=context_brief,
            suggested_options=suggested_options or [],
            blocking=(blocking and self.attention_should_block(state, attention_type)),
        )
        state.attention_requests.append(attention)
        return attention

    def attention_should_block(
        self,
        state: OperationState,
        attention_type: AttentionType,
    ) -> bool:
        if state.involvement_level is InvolvementLevel.APPROVAL_HEAVY:
            return True
        if attention_type in {
            AttentionType.APPROVAL_REQUEST,
            AttentionType.BLOCKED_EXTERNAL_DEPENDENCY,
        }:
            return True
        return state.involvement_level is not InvolvementLevel.UNATTENDED

    def attention_from_incomplete_result(
        self,
        state: OperationState,
        session: AgentSessionHandle,
        task: TaskState | None,
        result: AgentResult,
    ) -> AttentionRequest | None:
        if result.error is None:
            return None
        if result.error.code == "agent_waiting_input":
            return self.open_attention_request(
                state,
                attention_type=AttentionType.APPROVAL_REQUEST,
                title="Agent is waiting for approval",
                question=result.error.message,
                context_brief=(
                    f"Session {session.session_id}"
                    + (f" for task {task.title}" if task is not None else "")
                ),
                target_scope=CommandTargetScope.SESSION,
                target_id=session.session_id,
                blocking=True,
            )
        if result.error.code == "agent_requested_escalation":
            return self.open_attention_request(
                state,
                attention_type=AttentionType.APPROVAL_REQUEST,
                title="Agent requested escalation",
                question=result.error.message,
                context_brief=(
                    f"Session {session.session_id}"
                    + (f" for task {task.title}" if task is not None else "")
                ),
                target_scope=CommandTargetScope.SESSION,
                target_id=session.session_id,
                blocking=True,
            )
        return None

    def decision_requires_policy_gap(
        self,
        state: OperationState,
        decision: BrainDecision,
    ) -> bool:
        if state.policy_coverage.project_scope is None:
            return False
        if state.policy_coverage.status not in {
            PolicyCoverageStatus.NO_POLICY,
            PolicyCoverageStatus.UNCOVERED,
        }:
            return False
        return self.metadata_flag(decision.metadata.get("requires_policy_decision"))

    def open_policy_gap_attention(
        self,
        state: OperationState,
        decision: BrainDecision,
        task: TaskState | None,
    ) -> AttentionRequest:
        return self.open_attention_request(
            state,
            attention_type=AttentionType.POLICY_GAP,
            title=self.attention_title_from_decision(decision, AttentionType.POLICY_GAP),
            question=self.policy_gap_question_from_decision(decision),
            context_brief=self.attention_context_from_decision(decision, task),
            target_scope=CommandTargetScope.OPERATION,
            target_id=state.operation_id,
            blocking=True,
            suggested_options=self.attention_options_from_decision(decision),
        )

    def policy_gap_question_from_decision(self, decision: BrainDecision) -> str:
        raw_question = decision.metadata.get("policy_question")
        if isinstance(raw_question, str) and raw_question.strip():
            return raw_question.strip()
        return decision.rationale

    def decision_requires_novel_strategic_fork(self, decision: BrainDecision) -> bool:
        return self.metadata_flag(decision.metadata.get("requires_strategy_decision"))

    def open_novel_strategic_fork_attention(
        self,
        state: OperationState,
        decision: BrainDecision,
        task: TaskState | None,
    ) -> AttentionRequest:
        return self.open_attention_request(
            state,
            attention_type=AttentionType.NOVEL_STRATEGIC_FORK,
            title=self.attention_title_from_decision(decision, AttentionType.NOVEL_STRATEGIC_FORK),
            question=self.strategic_fork_question_from_decision(decision),
            context_brief=self.attention_context_from_decision(decision, task),
            target_scope=CommandTargetScope.OPERATION,
            target_id=state.operation_id,
            blocking=True,
            suggested_options=self.attention_options_from_decision(decision),
        )

    def strategic_fork_question_from_decision(self, decision: BrainDecision) -> str:
        raw_question = decision.metadata.get("strategy_question")
        if isinstance(raw_question, str) and raw_question.strip():
            return raw_question.strip()
        return decision.rationale

    def attention_question_from_decision(
        self,
        decision: BrainDecision,
        attention_type: AttentionType,
    ) -> str:
        if attention_type is AttentionType.POLICY_GAP:
            return self.policy_gap_question_from_decision(decision)
        if attention_type is AttentionType.NOVEL_STRATEGIC_FORK:
            return self.strategic_fork_question_from_decision(decision)
        return decision.rationale

    def metadata_flag(self, raw_value: object) -> bool:
        if isinstance(raw_value, bool):
            return raw_value
        if isinstance(raw_value, str):
            return raw_value.strip().lower() in {"1", "true", "yes"}
        return False

    def attention_type_from_decision(self, decision: BrainDecision) -> AttentionType:
        raw_value = decision.metadata.get("attention_type")
        if isinstance(raw_value, str):
            normalized = raw_value.strip()
            if normalized:
                try:
                    return AttentionType(normalized)
                except ValueError:
                    pass
        return AttentionType.QUESTION

    def attention_title_from_decision(
        self,
        decision: BrainDecision,
        attention_type: AttentionType,
    ) -> str:
        raw_title = decision.metadata.get("attention_title")
        if isinstance(raw_title, str) and raw_title.strip():
            return raw_title.strip()
        return {
            AttentionType.QUESTION: "Clarification required",
            AttentionType.POLICY_GAP: "Policy decision required",
            AttentionType.NOVEL_STRATEGIC_FORK: "Strategic decision required",
            AttentionType.BLOCKED_EXTERNAL_DEPENDENCY: "External dependency is blocking",
            AttentionType.APPROVAL_REQUEST: "Approval required",
        }[attention_type]

    def attention_context_from_decision(
        self,
        decision: BrainDecision,
        task: TaskState | None,
    ) -> str:
        raw_context = decision.metadata.get("attention_context")
        if isinstance(raw_context, str) and raw_context.strip():
            return raw_context.strip()
        if task is not None:
            return f"Task: {task.title}"
        return "The operator requested user input."

    def attention_options_from_decision(self, decision: BrainDecision) -> list[str]:
        raw_options = decision.metadata.get("attention_options")
        if not isinstance(raw_options, list):
            return []
        return [item.strip() for item in raw_options if isinstance(item, str) and item.strip()]
