from __future__ import annotations

from agent_operator.domain import (
    AgentResult,
    AgentResultStatus,
    AgentTurnSummary,
    BrainActionType,
    BrainDecision,
    FocusKind,
    FocusMode,
    FocusState,
    IterationState,
    OperationGoal,
    OperationState,
    OperationStatus,
    OperatorMessage,
    PolicyApplicability,
    PolicyCategory,
    PolicyEntry,
)
from agent_operator.providers.prompting import (
    build_converse_fleet_prompt,
    build_converse_operation_prompt,
    build_decision_prompt,
    build_evaluation_prompt,
    build_question_answer_prompt,
    build_turn_summary_prompt,
)
from agent_operator.testing.operator_service_support import state_settings


def test_build_decision_prompt_surfaces_active_project_policy() -> None:
    state = OperationState(
        goal=OperationGoal(objective="Ship the feature"),
        **state_settings(),
        active_policies=[
            PolicyEntry(
                policy_id="policy-1",
                project_scope="profile:femtobot",
                title="Manual testing debt",
                category=PolicyCategory.TESTING,
                rule_text="Document manual-only verification in MANUAL_TESTING_REQUIRED.md.",
                applicability=PolicyApplicability(objective_keywords=["manual testing"]),
            )
        ],
    )

    prompt = build_decision_prompt(state)

    assert "Active project policy:" in prompt
    assert "MANUAL_TESTING_REQUIRED.md" in prompt
    assert '"objective_keywords": ["manual testing"]' in prompt


def test_build_decision_prompt_excludes_dropped_operator_messages() -> None:
    state = OperationState(
        goal=OperationGoal(objective="Ship the feature"),
        **state_settings(),
        operator_messages=[
            OperatorMessage(message_id="msg-active", text="Keep the release notes concise."),
            OperatorMessage(
                message_id="msg-dropped",
                text="Old message that should not reach planning.",
                dropped_from_context=True,
                planning_cycles_active=2,
            ),
        ],
    )

    prompt = build_decision_prompt(state)

    assert "Keep the release notes concise." in prompt
    assert "Old message that should not reach planning." not in prompt


def test_build_question_answer_prompt_enforces_read_only_grounded_answering() -> None:
    state = OperationState(
        goal=OperationGoal(objective="Ship the feature"),
        **state_settings(),
    )

    prompt = build_question_answer_prompt(state, "What is the current status?")

    assert "read-only question answering surface" in prompt
    assert "strictly read-only" in prompt
    assert "User question:\nWhat is the current status?" in prompt
    assert "Tasks:" in prompt
    assert "Recent iteration history:" in prompt


def test_build_decision_prompt_requires_typed_clarification_metadata() -> None:
    prompt = build_decision_prompt(
        OperationState(
            goal=OperationGoal(objective="Ship the feature"),
            **state_settings(),
        )
    )

    assert "attention_type=policy_gap" in prompt
    assert "attention_type=novel_strategic_fork" in prompt
    assert "attention_options" in prompt
    assert "metadata.requires_policy_decision=true" in prompt


def test_decision_prompt_requires_instruction_to_be_only_final_agent_message() -> None:
    state = OperationState(
        goal=OperationGoal(
            objective="close all open cards",
            harness_instructions="Most of the time tell the agent to continue.",
        ),
        **state_settings(
            allowed_agents=["codex_acp"],
            metadata={
                "run_mode": "attached",
                "background_runtime_mode": "attached_live",
            },
        ),
    )

    prompt = build_decision_prompt(state)

    assert "The instruction field is the exact message that will be sent to the agent." in prompt
    assert "Do not paste the whole operator prompt" in prompt
    assert "For reusable sessions, prefer short follow-ups like 'Continue.'" in prompt
    assert "require the agent to commit and push after each completed feature-sized slice" in prompt
    assert "create a private repository and use gh" in prompt
    assert "run swarm mode grounded in the relevant VISION or product vision" in prompt
    assert "Harness Instructions:" in prompt
    assert "Involvement Level:" in prompt
    assert "Open Attention Requests:" in prompt
    assert "Answered Attention Pending Replan:" in prompt
    assert "WAIT_FOR_AGENT is valid only when there is a real in-flight dependency" in prompt
    assert "do not use WAIT_FOR_AGENT to monopolize the run on one agent" in prompt
    assert "Use FAIL when the objective should end as failed" in prompt


def test_build_decision_prompt_requires_workfront_key_for_delegated_fronts() -> None:
    state = OperationState(
        goal=OperationGoal(objective="Close the next ADR gap"),
        **state_settings(
            allowed_agents=["codex_acp"],
            metadata={
                "run_mode": "attached",
                "background_runtime_mode": "attached_live",
            },
        ),
    )

    prompt = build_decision_prompt(state)

    assert "set workfront_key to a short stable identifier" in prompt
    assert "bounded delegated front" in prompt
    assert "change it when replanning to a different slice" in prompt


def test_build_decision_prompt_surfaces_available_agent_descriptors() -> None:
    state = OperationState(
        goal=OperationGoal(objective="Ship the feature"),
        **state_settings(
            allowed_agents=["codex_acp"],
            metadata={
                "available_agent_descriptors": [
                    {
                        "key": "codex_acp",
                        "display_name": "Codex via ACP",
                        "capabilities": [
                            {"name": "read_files", "description": "Can read repository files."},
                            {"name": "grep_search", "description": "Can search repository text."},
                        ],
                        "supports_follow_up": True,
                        "supports_cancellation": True,
                        "metadata": {},
                    }
                ]
            },
        ),
    )

    prompt = build_decision_prompt(state)

    assert "Available Agent Descriptors:" in prompt
    assert '"key": "codex_acp"' in prompt
    assert '"name": "read_files"' in prompt
    assert '"name": "grep_search"' in prompt


def test_build_decision_prompt_preserves_tail_of_long_result_excerpt() -> None:
    long_output = (
        "HEAD-MARKER "
        + ("A" * 2600)
        + " IMPORTANT-MIDDLE "
        + ("B" * 2600)
        + " TAIL-MARKER"
    )
    state = OperationState(
        goal=OperationGoal(objective="Ship the feature"),
        **state_settings(),
        iterations=[
            IterationState(
                index=1,
                decision=BrainDecision(
                    action_type=BrainActionType.CONTINUE_AGENT,
                    rationale="Continue the current line of work.",
                ),
                result=AgentResult(
                    session_id="session-1",
                    status=AgentResultStatus.SUCCESS,
                    output_text=long_output,
                ),
            ),
            IterationState(
                index=2,
                decision=BrainDecision(
                    action_type=BrainActionType.CONTINUE_AGENT,
                    rationale="Continue the current line of work.",
                ),
                result=AgentResult(
                    session_id="session-1",
                    status=AgentResultStatus.SUCCESS,
                    output_text="short latest result",
                ),
            ),
        ],
    )

    prompt = build_decision_prompt(state)

    assert "HEAD-MARKER" in prompt
    assert "TAIL-MARKER" in prompt
    assert "[operator excerpt omitted middle content]" in prompt


def test_build_decision_prompt_uses_turn_summary_for_older_iterations_and_full_latest_result(
) -> None:
    old_full_result = "OLDER-HEAD " + ("middle " * 2000) + " OLDER-TAIL"
    latest_full_result = "LATEST-HEAD " + ("body " * 2500) + " LATEST-TAIL"
    state = OperationState(
        goal=OperationGoal(objective="Solve it"),
        **state_settings(allowed_agents=["claude_acp"]),
    )
    state.iterations.extend(
        [
            IterationState(
                index=1,
                decision=BrainDecision(
                    action_type=BrainActionType.START_AGENT,
                    target_agent="claude_acp",
                    instruction="old turn",
                    rationale="start",
                ),
                result=AgentResult(
                    session_id="session-1",
                    status=AgentResultStatus.SUCCESS,
                    output_text=old_full_result,
                ),
                turn_summary=AgentTurnSummary(
                    declared_goal="Old goal",
                    actual_work_done="Closed old route.",
                    state_delta="Old state delta.",
                    verification_status="Verified old turn.",
                    recommended_next_step="Move on.",
                ),
            ),
            IterationState(
                index=2,
                decision=BrainDecision(
                    action_type=BrainActionType.CONTINUE_AGENT,
                    target_agent="claude_acp",
                    session_id="session-1",
                    instruction="latest turn",
                    rationale="continue",
                ),
                result=AgentResult(
                    session_id="session-1",
                    status=AgentResultStatus.SUCCESS,
                    output_text=latest_full_result,
                ),
                turn_summary=AgentTurnSummary(
                    declared_goal="Latest goal",
                    actual_work_done="Did latest work.",
                    state_delta="Latest state delta.",
                    verification_status="Latest verification.",
                    recommended_next_step="Latest next step.",
                ),
            ),
        ]
    )

    prompt = build_decision_prompt(state)

    assert "Closed old route." in prompt
    assert "Old state delta." in prompt
    assert "OLDER-TAIL" not in prompt
    assert '"full_result": "LATEST-HEAD ' in prompt
    assert "LATEST-TAIL" in prompt


def test_build_evaluation_prompt_falls_back_to_excerpt_when_summary_missing() -> None:
    old_full_result = "EXCERPT-HEAD " + ("middle " * 1500) + " EXCERPT-TAIL"
    latest_full_result = "LATEST-FULL " + ("body " * 1000) + " LATEST-END"
    state = OperationState(
        goal=OperationGoal(objective="Solve it"),
        **state_settings(allowed_agents=["claude_acp"]),
    )
    state.iterations.extend(
        [
            IterationState(
                index=1,
                decision=BrainDecision(
                    action_type=BrainActionType.START_AGENT,
                    target_agent="claude_acp",
                    instruction="turn",
                    rationale="start",
                ),
                result=AgentResult(
                    session_id="session-1",
                    status=AgentResultStatus.SUCCESS,
                    output_text=old_full_result,
                ),
            ),
            IterationState(
                index=2,
                decision=BrainDecision(
                    action_type=BrainActionType.CONTINUE_AGENT,
                    target_agent="claude_acp",
                    session_id="session-1",
                    instruction="turn 2",
                    rationale="continue",
                ),
                result=AgentResult(
                    session_id="session-1",
                    status=AgentResultStatus.SUCCESS,
                    output_text=latest_full_result,
                ),
            ),
        ]
    )

    prompt = build_evaluation_prompt(state)

    assert "EXCERPT-HEAD" in prompt
    assert "EXCERPT-TAIL" in prompt
    assert '"result_excerpt":' in prompt
    assert '"full_result": "LATEST-FULL ' in prompt


def test_build_turn_summary_prompt_requires_progress_class_and_blocker_keys() -> None:
    state = OperationState(
        goal=OperationGoal(objective="Close the next ADR gap"),
        **state_settings(),
    )

    prompt = build_turn_summary_prompt(
        state,
        operator_instruction="Continue with the next bounded slice.",
        result=AgentResult(
            session_id="session-1",
            status=AgentResultStatus.SUCCESS,
            output_text="No repository content changed in this turn.",
        ),
    )

    assert "Set progress_class to one of" in prompt
    assert "material_delta, inspection_only, no_verified_delta" in prompt
    assert "Use blocker_keys for short stable blocker-family tags" in prompt


def test_build_question_answer_prompt_enforces_read_only_boundary() -> None:
    state = OperationState(
        goal=OperationGoal(objective="Inspect the repository"),
        **state_settings(),
    )

    prompt = build_question_answer_prompt(state, "What is the operator likely to do next?")

    assert "read-only question answering surface" in prompt
    assert "do not claim to have modified operation state" in prompt
    assert "User question:" in prompt
    assert "What is the operator likely to do next?" in prompt


def test_build_converse_operation_prompt_distinguishes_brief_and_full_context() -> None:
    state = OperationState(
        operation_id="op-converse-1",
        goal=OperationGoal(objective="Inspect the repository"),
        **state_settings(),
    )

    brief_prompt = build_converse_operation_prompt(
        state,
        user_message="What is blocked?",
        conversation_history=[{"role": "user", "content": "What is blocked?"}],
        context_level="brief",
        recent_events=None,
    )
    full_prompt = build_converse_operation_prompt(
        state,
        user_message="What is blocked?",
        conversation_history=[{"role": "user", "content": "What is blocked?"}],
        context_level="full",
        recent_events=[{"event_id": "evt-1", "kind": "operation.started"}],
    )

    assert "Conversation mode: operation" in brief_prompt
    assert "Context level: brief" in brief_prompt
    assert "Recent event log:" not in brief_prompt
    assert "Tasks:" not in brief_prompt
    assert "Conversation mode: operation" in full_prompt
    assert "Context level: full" in full_prompt
    assert "Recent event log:" in full_prompt
    assert "Tasks:" in full_prompt
    assert "operator answer <operation-id> <attention-id> --text" in full_prompt


def test_build_converse_operation_prompt_uses_derived_focus_and_iteration_payloads(
    monkeypatch,
) -> None:
    state = OperationState(
        operation_id="op-converse-1",
        goal=OperationGoal(objective="Inspect the repository"),
        **state_settings(),
    )
    state.current_focus = FocusState(
        kind=FocusKind.SESSION,
        target_id="session-1",
        mode=FocusMode.ADVISORY,
    )
    state.iterations = [
        IterationState(
            index=1,
            task_id="task-1",
            notes=["Look at the current session state."],
        )
    ]

    def _fail_focus_model_dump(self, *args, **kwargs):
        raise AssertionError("converse prompt should not serialize FocusState directly")

    def _fail_iteration_model_dump(self, *args, **kwargs):
        raise AssertionError("converse prompt should not serialize IterationState directly")

    monkeypatch.setattr(FocusState, "model_dump", _fail_focus_model_dump)
    monkeypatch.setattr(IterationState, "model_dump", _fail_iteration_model_dump)

    prompt = build_converse_operation_prompt(
        state,
        user_message="What is blocked?",
        conversation_history=[],
        context_level="brief",
        recent_events=None,
    )

    assert '"target_id": "session-1"' in prompt
    assert '"index": 1' in prompt
    assert '"task_id": "task-1"' in prompt


def test_build_converse_fleet_prompt_surfaces_active_operation_context() -> None:
    operations = [
        OperationState(
            operation_id="op-fleet-1",
            goal=OperationGoal(objective="Ship alpha"),
            status=OperationStatus.RUNNING,
            **state_settings(),
        ),
        OperationState(
            operation_id="op-fleet-2",
            goal=OperationGoal(objective="Investigate failure"),
            status=OperationStatus.NEEDS_HUMAN,
            **state_settings(),
        ),
    ]

    prompt = build_converse_fleet_prompt(
        operations,
        user_message="Which operation is blocked?",
        conversation_history=[],
        context_level="brief",
    )

    assert "Conversation mode: fleet" in prompt
    assert "Context level: brief" in prompt
    assert '"operation_id": "op-fleet-1"' in prompt
    assert '"operation_id": "op-fleet-2"' in prompt
    assert '"objective": "Investigate failure"' in prompt
    assert "User message:\nWhich operation is blocked?" in prompt
