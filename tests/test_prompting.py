from __future__ import annotations

from agent_operator.domain import (
    AgentResult,
    AgentResultStatus,
    AgentTurnSummary,
    BrainActionType,
    BrainDecision,
    IterationState,
    OperationGoal,
    OperationState,
    PolicyApplicability,
    PolicyCategory,
    PolicyEntry,
)
from agent_operator.providers.prompting import build_decision_prompt, build_evaluation_prompt
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
