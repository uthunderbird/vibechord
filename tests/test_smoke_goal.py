from agent_operator.smoke import (
    build_alignment_post_research_plan_goal,
    build_codex_continuation_goal,
    build_mixed_agent_selection_goal,
    build_mixed_code_agent_selection_goal,
)


def test_alignment_post_smoke_goal_requires_two_swarm_phases() -> None:
    goal = build_alignment_post_research_plan_goal()

    assert "/swarm" in " ".join(goal.success_criteria)
    assert goal.metadata["requires_separate_agent_runs"] is True
    assert goal.metadata["prefer_one_shot_agent_runs"] is True
    assert goal.metadata["prefer_one_shot_for_swarm"] is True
    assert "two separate Claude ACP runs" in goal.metadata["phase_contract"]
    assert "research plan" in goal.metadata["output_contract"]
    assert "result_normalization_instruction" in goal.metadata
    assert goal.metadata["operator_constraints"]["brain_provider"] == "openai_codex"
    assert goal.metadata["claude_constraints"]["model"] == "claude-sonnet-4-6"
    assert goal.metadata["candidate_agents"] == ["claude_acp"]


def test_mixed_agent_selection_goal_requires_real_choice() -> None:
    goal = build_mixed_agent_selection_goal()

    assert goal.metadata["requires_agent_selection"] is True
    assert goal.metadata["prefer_one_shot_agent_runs"] is True
    assert "claude_acp and codex_acp" in goal.metadata["agent_selection_contract"]
    assert goal.metadata["candidate_agents"] == ["claude_acp", "codex_acp"]
    assert "final standalone note" in goal.metadata["result_normalization_instruction"]


def test_mixed_code_agent_selection_goal_is_repo_aware() -> None:
    goal = build_mixed_code_agent_selection_goal()

    assert goal.metadata["requires_agent_selection"] is True
    assert goal.metadata["prefer_one_shot_agent_runs"] is True
    assert "repo-aware and code-inspection oriented" in goal.metadata["agent_selection_contract"]
    assert "concrete file paths" in goal.metadata["output_contract"]
    assert goal.metadata["candidate_agents"] == ["claude_acp", "codex_acp"]


def test_codex_continuation_goal_requires_same_session() -> None:
    goal = build_codex_continuation_goal()

    assert goal.metadata["requires_same_agent_session"] is True
    assert "same Codex ACP session" in goal.metadata["phase_contract"]
    assert goal.metadata["candidate_agents"] == ["codex_acp"]
    assert "two next tasks" in goal.metadata["output_contract"]
