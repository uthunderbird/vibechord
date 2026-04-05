from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING

from agent_operator.domain import PolicyApplicability, PolicyEntry, PolicyStatus

if TYPE_CHECKING:
    from agent_operator.domain import OperationState


class FilePolicyStore:
    def __init__(self, root: Path) -> None:
        self._root = root
        self._root.mkdir(parents=True, exist_ok=True)

    async def save(self, entry: PolicyEntry) -> None:
        path = self._path(entry.project_scope, entry.policy_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(entry.model_dump_json(indent=2), encoding="utf-8")

    async def load(self, policy_id: str) -> PolicyEntry | None:
        for path in self._candidate_paths(policy_id):
            if path.exists():
                return PolicyEntry.model_validate_json(path.read_text(encoding="utf-8"))
        return None

    async def list(
        self,
        *,
        project_scope: str | None = None,
        status: PolicyStatus | None = None,
    ) -> list[PolicyEntry]:
        entries = [
            PolicyEntry.model_validate_json(path.read_text(encoding="utf-8"))
            for path in sorted(self._root.rglob("*.json"))
        ]
        if project_scope is not None:
            entries = [entry for entry in entries if entry.project_scope == project_scope]
        if status is not None:
            entries = [entry for entry in entries if entry.status is status]
        entries.sort(key=lambda item: (item.created_at, item.policy_id))
        return entries

    def _path(self, project_scope: str, policy_id: str) -> Path:
        if re.fullmatch(r"[A-Za-z0-9._-]+", project_scope):
            return self._root / project_scope / f"{policy_id}.json"
        return self._root / f"{policy_id}.json"

    def _candidate_paths(self, policy_id: str) -> list[Path]:
        paths = [self._root / f"{policy_id}.json"]
        paths.extend(sorted(self._root.glob(f"*/{policy_id}.json")))
        return paths


def policy_match_reasons(
    policy: PolicyEntry,
    *,
    project_scope: str | None,
    operation: OperationState | None = None,
) -> list[str]:
    reasons: list[str] = []
    if project_scope is None:
        return ["operation has no policy scope"]
    if policy.project_scope != project_scope:
        return [f"scope mismatch: policy={policy.project_scope} operation={project_scope}"]
    applicability = policy.applicability
    if applicability.is_global:
        return ["global policy"]
    reasons.append(f"scope match: {project_scope}")
    if operation is None:
        return reasons

    objective_haystack = _normalize_text(
        [
            operation.objective_state.objective,
            operation.objective_state.harness_instructions,
            *operation.objective_state.success_criteria,
        ]
    )
    task_haystack = _normalize_text(
        [task.title for task in operation.tasks]
        + [task.goal for task in operation.tasks]
        + [note for task in operation.tasks for note in task.notes]
    )
    allowed_agents = set(operation.policy.allowed_agents)
    run_mode = str(operation.runtime_hints.metadata.get("run_mode", "attached")).strip()

    if applicability.objective_keywords:
        reasons.append(
            (
                "objective keyword match"
                if _matches_keywords(objective_haystack, applicability.objective_keywords)
                else "objective keyword mismatch"
            )
            + f": {', '.join(applicability.objective_keywords)}"
        )
    if applicability.task_keywords:
        reasons.append(
            (
                "task keyword match"
                if _matches_keywords(task_haystack, applicability.task_keywords)
                else "task keyword mismatch"
            )
            + f": {', '.join(applicability.task_keywords)}"
        )
    if applicability.agent_keys:
        matched_agents = [key for key in applicability.agent_keys if key in allowed_agents]
        if matched_agents:
            reasons.append("agent match: " + ", ".join(matched_agents))
        else:
            reasons.append("agent mismatch: " + ", ".join(applicability.agent_keys))
    if applicability.run_modes:
        if run_mode in {item.value for item in applicability.run_modes}:
            reasons.append("run mode match: " + run_mode)
        else:
            reasons.append(
                "run mode mismatch: "
                + ", ".join(item.value for item in applicability.run_modes)
            )
    if applicability.involvement_levels:
        if operation.involvement_level in set(applicability.involvement_levels):
            reasons.append(f"involvement match: {operation.involvement_level.value}")
        else:
            reasons.append(
                "involvement mismatch: "
                + ", ".join(item.value for item in applicability.involvement_levels)
            )
    return reasons


def policy_applies_to_operation(policy: PolicyEntry, operation: OperationState) -> bool:
    raw_scope = operation.goal.metadata.get("policy_scope")
    project_scope = raw_scope.strip() if isinstance(raw_scope, str) and raw_scope.strip() else None
    if policy.project_scope != project_scope:
        return False
    applicability = policy.applicability
    if applicability.is_global:
        return True

    objective_haystack = _normalize_text(
        [
            operation.objective_state.objective,
            operation.objective_state.harness_instructions,
            *operation.objective_state.success_criteria,
        ]
    )
    if applicability.objective_keywords and not _matches_keywords(
        objective_haystack,
        applicability.objective_keywords,
    ):
        return False

    task_haystack = _normalize_text(
        [task.title for task in operation.tasks]
        + [task.goal for task in operation.tasks]
        + [note for task in operation.tasks for note in task.notes]
    )
    if applicability.task_keywords and not _matches_keywords(
        task_haystack,
        applicability.task_keywords,
    ):
        return False

    if applicability.agent_keys:
        allowed_agents = set(operation.policy.allowed_agents)
        if not any(agent_key in allowed_agents for agent_key in applicability.agent_keys):
            return False

    if applicability.run_modes:
        run_mode = str(operation.runtime_hints.metadata.get("run_mode", "attached")).strip()
        if run_mode not in {item.value for item in applicability.run_modes}:
            return False

    return not (
        applicability.involvement_levels
        and operation.involvement_level not in set(applicability.involvement_levels)
    )


def describe_policy_applicability(policy: PolicyEntry, operation: OperationState) -> str:
    if policy.applicability.is_global:
        return "all operations in this project scope"
    return "; ".join(
        policy_match_reasons(
            policy,
            project_scope=(
                raw_scope.strip()
                if isinstance((raw_scope := operation.goal.metadata.get("policy_scope")), str)
                and raw_scope.strip()
                else None
            ),
            operation=operation,
        )
    )


def format_policy_applicability(applicability: PolicyApplicability) -> str:
    if applicability.is_global:
        return "all operations in this project scope"
    parts: list[str] = []
    if applicability.objective_keywords:
        parts.append("objective=" + ", ".join(applicability.objective_keywords))
    if applicability.task_keywords:
        parts.append("task=" + ", ".join(applicability.task_keywords))
    if applicability.agent_keys:
        parts.append("agent=" + ", ".join(applicability.agent_keys))
    if applicability.run_modes:
        parts.append("mode=" + ", ".join(item.value for item in applicability.run_modes))
    if applicability.involvement_levels:
        parts.append(
            "involvement=" + ", ".join(item.value for item in applicability.involvement_levels)
        )
    return " | ".join(parts)


def _normalize_text(chunks: list[object | None]) -> str:
    rendered = " ".join(str(chunk).strip().lower() for chunk in chunks if str(chunk or "").strip())
    return re.sub(r"\s+", " ", rendered).strip()


def _matches_keywords(haystack: str, keywords: list[str]) -> bool:
    if not haystack:
        return False
    return any(keyword.strip().lower() in haystack for keyword in keywords if keyword.strip())
