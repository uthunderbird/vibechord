from __future__ import annotations

from agent_operator.bootstrap import build_service
from agent_operator.config import OperatorSettings
from agent_operator.domain import ExecutionBudget, OperationGoal, OperationOutcome, OperationPolicy


def _claude_agent_label(agent_key: str) -> str:
    return "Claude ACP"


def build_alignment_post_research_plan_goal(claude_agent_key: str = "claude_acp") -> OperationGoal:
    claude_label = _claude_agent_label(claude_agent_key)
    return OperationGoal(
        objective=(
            f"Use {claude_label} as the only external agent to produce a preliminary research plan "
            "for a concrete post idea for an AI Alignment channel."
        ),
        success_criteria=[
            f"{claude_label} first runs /swarm to brainstorm multiple candidate "
            "post ideas for an AI Alignment channel.",
            "The brainstorming swarm is taken to a final recommendation or clear winner.",
            "The operator selects the most promising concrete topic.",
            f"{claude_label} then runs a new /swarm focused on drafting a "
            "preliminary research plan for that topic.",
            "The final artifact is only the research plan for the selected "
            "concrete topic, not brainstorming notes.",
        ],
        metadata={
            "requires_separate_agent_runs": True,
            "prefer_one_shot_agent_runs": True,
            "prefer_one_shot_for_swarm": True,
            "phase_contract": (
                f"Phase 1 and phase 2 must be executed as two separate {claude_label} runs. "
                "Phase 1 is brainstorming and topic selection only. "
                "Phase 2 is research-plan drafting only. "
                "It is invalid to combine both phases into one agent run."
            ),
            "required_process": [
                f"Ask {claude_label} to run /swarm for idea brainstorming.",
                "Drive the brainstorming swarm to a final chosen idea.",
                "Select the idea the operator judges most promising.",
                f"Ask {claude_label} to run a new /swarm for a preliminary research plan.",
            ],
            "output_contract": (
                "Final deliverable must be a research plan for one specific post topic. "
                "Do not finish on idea lists or meta commentary."
            ),
            "result_normalization_instruction": (
                "Extract or rewrite the agent response into only the final standalone "
                "research plan. Remove swarm/process scaffolding, expert discussion, "
                "and meta commentary. Keep the substantive plan content."
            ),
            "claude_constraints": {
                "model": "claude-sonnet-4-6",
                "effort": "low",
                "skills_source": "~/.claude/",
            },
            "operator_constraints": {
                "brain_provider": "openai_codex",
                "model": "gpt-5.4",
                "effort": "low",
            },
            "candidate_agents": [claude_agent_key],
            "claude_agent_key": claude_agent_key,
        },
    )


async def run_alignment_post_research_plan_smoke(
    claude_agent_key: str = "claude_acp",
) -> OperationOutcome:
    settings = OperatorSettings()
    service = build_service(settings)
    return await service.run(
        build_alignment_post_research_plan_goal(claude_agent_key=claude_agent_key),
        policy=OperationPolicy(
            allowed_agents=[claude_agent_key],
        ),
        budget=ExecutionBudget(
            max_iterations=5,
        ),
    )


def build_mixed_agent_selection_goal(claude_agent_key: str = "claude_acp") -> OperationGoal:
    claude_label = _claude_agent_label(claude_agent_key)
    return OperationGoal(
        objective=(
            f"Choose the more suitable external agent between {claude_label} and Codex ACP, "
            "then use exactly one of them to produce a concise note for an AI Alignment "
            "channel on why evaluations must distinguish capability from alignment."
        ),
        success_criteria=[
            f"The operator chooses between {claude_label} and Codex ACP rather than "
            "assuming one in advance.",
            "The operator uses exactly one external agent run for the final deliverable.",
            "The final artifact is a concise standalone note, not process commentary.",
            "The note explains why capability evaluations and alignment evaluations "
            "should not be conflated.",
        ],
        metadata={
            "requires_agent_selection": True,
            "prefer_one_shot_agent_runs": True,
            "agent_selection_contract": (
                f"You must choose between {claude_agent_key} and codex_acp "
                "based on suitability for "
                "this task. Do not assume one agent in advance unless prior evidence in the run "
                "justifies it."
            ),
            "preferred_shape": "3 short bullets and a one-sentence conclusion",
            "output_contract": (
                "Return only the final note. No meta commentary about agent choice, no operator "
                "reasoning, and no process transcript."
            ),
            "result_normalization_instruction": (
                "Rewrite the raw agent response into only the final standalone note. Keep the "
                "substance, but remove tool chatter, process commentary, and wrappers."
            ),
            "operator_constraints": {
                "brain_provider": "openai_codex",
                "model": "gpt-5.4",
                "effort": "low",
            },
            "candidate_agents": [claude_agent_key, "codex_acp"],
        },
    )


async def run_mixed_agent_selection_smoke(
    claude_agent_key: str = "claude_acp",
) -> OperationOutcome:
    settings = OperatorSettings()
    service = build_service(settings)
    return await service.run(
        build_mixed_agent_selection_goal(claude_agent_key=claude_agent_key),
        policy=OperationPolicy(
            allowed_agents=[claude_agent_key, "codex_acp"],
        ),
        budget=ExecutionBudget(
            max_iterations=4,
        ),
    )


def build_mixed_code_agent_selection_goal(
    claude_agent_key: str = "claude_acp",
) -> OperationGoal:
    claude_label = _claude_agent_label(claude_agent_key)
    return OperationGoal(
        objective=(
            f"Choose the more suitable external agent between {claude_label} and Codex ACP, "
            "then use exactly one of them to inspect this repository and identify the two "
            "best existing integration surfaces for future ACP client evolution."
        ),
        success_criteria=[
            f"The operator chooses between {claude_label} and Codex ACP rather than assuming one "
            " "
            "in advance.",
            "The chosen agent performs a repo-aware inspection of the current codebase.",
            "The final artifact names exactly two integration surfaces in the existing repo "
            "with concrete file paths.",
            "The final artifact explains why each surface is a strong extension point for "
            "future ACP client work.",
            "The final artifact is only the concise inspection note, not process commentary.",
        ],
        metadata={
            "requires_agent_selection": True,
            "prefer_one_shot_agent_runs": True,
            "agent_selection_contract": (
                f"You must choose between {claude_agent_key} and codex_acp "
                "based on suitability for "
                "this task. This task is explicitly repo-aware and code-inspection oriented, "
                "not a pure writing task."
            ),
            "preferred_shape": "2 bullets with file paths and a one-sentence recommendation",
            "output_contract": (
                "Return only the final concise inspection note. Include concrete file paths. "
                "No meta commentary about agent choice, no operator reasoning, and no process "
                "transcript."
            ),
            "result_normalization_instruction": (
                "Rewrite the raw agent response into only the final concise inspection note. "
                "Keep the substance and file paths, but remove tool chatter, process "
                "commentary, and wrappers."
            ),
            "operator_constraints": {
                "brain_provider": "openai_codex",
                "model": "gpt-5.4",
                "effort": "low",
            },
            "candidate_agents": [claude_agent_key, "codex_acp"],
        },
    )


async def run_mixed_code_agent_selection_smoke(
    claude_agent_key: str = "claude_acp",
) -> OperationOutcome:
    settings = OperatorSettings()
    service = build_service(settings)
    return await service.run(
        build_mixed_code_agent_selection_goal(claude_agent_key=claude_agent_key),
        policy=OperationPolicy(
            allowed_agents=[claude_agent_key, "codex_acp"],
        ),
        budget=ExecutionBudget(
            max_iterations=4,
        ),
    )


def build_codex_continuation_goal() -> OperationGoal:
    return OperationGoal(
        objective=(
            "Use Codex ACP to inspect this repository in two linked phases within the same "
            "agent session. First identify one strong ACP integration surface. Then continue "
            "the same session and expand it into two concrete next implementation tasks."
        ),
        success_criteria=[
            "The operator starts exactly one Codex ACP session for phase 1.",
            "The operator continues the same Codex ACP session for phase 2 rather than "
            "starting a fresh session.",
            "The final artifact names one integration surface with a concrete file path.",
            "The final artifact gives exactly two concrete next implementation tasks tied "
            "to that same surface.",
            "The final artifact is only the concise final note, not process commentary.",
        ],
        metadata={
            "requires_same_agent_session": True,
            "phase_contract": (
                "Phase 1 and phase 2 should happen in the same Codex ACP session. "
                "Phase 1 identifies one promising ACP integration surface. "
                "Phase 2 expands that same surface into two concrete next implementation tasks. "
                "Do not start a fresh session for phase 2 unless continuation is impossible. "
                "It is also invalid to combine both phases into one single agent turn."
            ),
            "required_process": [
                "Start Codex ACP for the initial repo inspection only.",
                "Evaluate the phase 1 result.",
                "Continue the same Codex ACP session for the phase 2 expansion only.",
            ],
            "output_contract": (
                "Return only the final concise note. Include one concrete file path and "
                "exactly two next tasks. No meta commentary or process transcript."
            ),
            "result_normalization_instruction": (
                "Rewrite the raw agent response into only the final concise note. Keep the "
                "selected file path and the two next tasks, but remove process commentary "
                "and intermediate repo-inspection chatter."
            ),
            "operator_constraints": {
                "brain_provider": "openai_codex",
                "model": "gpt-5.4",
                "effort": "low",
            },
            "candidate_agents": ["codex_acp"],
        },
    )


async def run_codex_continuation_smoke() -> OperationOutcome:
    settings = OperatorSettings()
    service = build_service(settings)
    return await service.run(
        build_codex_continuation_goal(),
        policy=OperationPolicy(
            allowed_agents=["codex_acp"],
        ),
        budget=ExecutionBudget(
            max_iterations=4,
        ),
    )


def extract_final_plan(outcome: OperationOutcome) -> str:
    if outcome.final_result is None or not outcome.final_result.output_text.strip():
        raise RuntimeError("Smoke run did not produce a final research plan artifact.")
    return outcome.final_result.output_text.strip()
