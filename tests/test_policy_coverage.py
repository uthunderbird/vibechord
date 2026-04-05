from __future__ import annotations

from datetime import UTC, datetime

import pytest

from agent_operator.domain import (
    AgentDescriptor,
    AgentProgress,
    AgentProgressState,
    AgentResult,
    AgentResultStatus,
    AgentSessionHandle,
    BrainActionType,
    BrainDecision,
    Evaluation,
    OperationGoal,
    OperationPolicy,
    OperationState,
    PolicyApplicability,
    PolicyCategory,
    PolicyCoverageStatus,
    PolicyEntry,
)
from agent_operator.providers.prompting import build_decision_prompt
from agent_operator.testing.operator_service_support import make_service
from agent_operator.testing.runtime_bindings import build_test_runtime_bindings


class MemoryStore:
    def __init__(self) -> None:
        self.operations: dict[str, OperationState] = {}
        self.outcomes: dict[str, object] = {}

    async def save_operation(self, state: OperationState) -> None:
        self.operations[state.operation_id] = state.model_copy(deep=True)

    async def save_outcome(self, outcome: object) -> None:
        self.outcomes[outcome.operation_id] = outcome

    async def load_operation(self, operation_id: str) -> OperationState | None:
        return self.operations.get(operation_id)

    async def load_outcome(self, operation_id: str) -> object | None:
        return self.outcomes.get(operation_id)

    async def list_operation_ids(self) -> list[str]:
        return list(self.operations)

    async def list_operations(self) -> list[object]:
        return []


class MemoryTraceStore:
    async def save_operation_brief(self, brief: object) -> None:
        return None

    async def append_iteration_brief(self, operation_id: str, brief: object) -> None:
        return None

    async def append_agent_turn_brief(self, operation_id: str, brief: object) -> None:
        return None

    async def append_command_brief(self, operation_id: str, brief: object) -> None:
        return None

    async def append_evaluation_brief(self, operation_id: str, brief: object) -> None:
        return None

    async def save_decision_memo(self, operation_id: str, memo: object) -> None:
        return None

    async def append_trace_record(self, operation_id: str, record: object) -> None:
        return None

    async def write_report(self, operation_id: str, report: str) -> None:
        return None


class MemoryEventSink:
    async def emit(self, event: object) -> None:
        return None


class MemoryPolicyStore:
    def __init__(self) -> None:
        self.entries: dict[str, PolicyEntry] = {}

    async def save(self, entry: PolicyEntry) -> None:
        self.entries[entry.policy_id] = entry.model_copy(deep=True)

    async def load(self, policy_id: str) -> PolicyEntry | None:
        return self.entries.get(policy_id)

    async def list(
        self,
        *,
        project_scope: str | None = None,
        status: object | None = None,
    ) -> list[PolicyEntry]:
        entries = [entry.model_copy(deep=True) for entry in self.entries.values()]
        if project_scope is not None:
            entries = [entry for entry in entries if entry.project_scope == project_scope]
        if status is not None:
            entries = [entry for entry in entries if entry.status is status]
        entries.sort(key=lambda item: (item.created_at, item.policy_id))
        return entries


class NoOpBrain:
    async def decide_next_action(self, state: OperationState) -> BrainDecision:
        return BrainDecision(
            action_type=BrainActionType.STOP,
            rationale="done",
        )

    async def evaluate_result(self, state: OperationState) -> Evaluation:
        return Evaluation(goal_satisfied=True, should_continue=False, summary="done")

    async def distill_memory(
        self,
        state: OperationState,
        *,
        scope: str,
        scope_id: str,
        source_refs: list[dict[str, str]],
        instruction: str,
    ) -> object:
        raise AssertionError("distill_memory should not be called in this test")


class FakeAgent:
    async def describe(self) -> AgentDescriptor:
        return AgentDescriptor(
            key="claude_acp",
            display_name="Claude Code",
            supports_follow_up=True,
        )

    async def start(self, request: object) -> AgentSessionHandle:
        return AgentSessionHandle(
            adapter_key="claude_acp",
            session_id="session-1",
            one_shot=request.one_shot,
        )

    async def send(self, handle: AgentSessionHandle, message: str) -> None:
        return None

    async def poll(self, handle: AgentSessionHandle) -> AgentProgress:
        return AgentProgress(
            session_id=handle.session_id,
            state=AgentProgressState.COMPLETED,
            message="done",
            updated_at=datetime.now(UTC),
        )

    async def collect(self, handle: AgentSessionHandle) -> AgentResult:
        return AgentResult(
            session_id=handle.session_id,
            status=AgentResultStatus.SUCCESS,
            output_text="done",
            completed_at=datetime.now(UTC),
        )

    async def cancel(self, handle: AgentSessionHandle) -> None:
        return None

    async def close(self, handle: AgentSessionHandle) -> None:
        return None


@pytest.mark.anyio
async def test_service_marks_policy_coverage_as_uncovered_when_scope_has_only_non_matching_policy(
) -> None:
    store = MemoryStore()
    policy_store = MemoryPolicyStore()
    await policy_store.save(
        PolicyEntry(
            policy_id="policy-release",
            project_scope="profile:femtobot",
            title="Release approvals",
            category=PolicyCategory.RELEASE,
            rule_text="Require explicit release approval.",
            applicability=PolicyApplicability(objective_keywords=["release"]),
        )
    )
    service = make_service(
        operator_policy=NoOpBrain(),
        store=store,
        trace_store=MemoryTraceStore(),
        event_sink=MemoryEventSink(),
        agent_runtime_bindings=build_test_runtime_bindings(
            {"claude_acp": FakeAgent()}
        ),
        policy_store=policy_store,
    )

    outcome = await service.run(
        OperationGoal(
            objective="Document the manual testing workflow",
            metadata={"policy_scope": "profile:femtobot"},
        ),
        policy=OperationPolicy(allowed_agents=["claude_acp"]),
    )
    operation = await store.load_operation(outcome.operation_id)

    assert operation is not None
    assert operation.active_policies == []
    assert operation.policy_coverage.status is PolicyCoverageStatus.UNCOVERED
    assert operation.policy_coverage.project_scope == "profile:femtobot"
    assert operation.policy_coverage.scoped_policy_count == 1
    assert operation.policy_coverage.active_policy_count == 0


def test_build_decision_prompt_surfaces_policy_coverage_summary() -> None:
    state = OperationState(
        goal=OperationGoal(
            objective="Document the manual testing workflow",
            metadata={"policy_scope": "profile:femtobot"},
        ),
        policy=OperationPolicy(),
    )
    state.policy_coverage.status = PolicyCoverageStatus.UNCOVERED
    state.policy_coverage.project_scope = "profile:femtobot"
    state.policy_coverage.scoped_policy_count = 2
    state.policy_coverage.summary = (
        "This scope has project policy, but none of it currently applies."
    )

    prompt = build_decision_prompt(state)

    assert "Policy coverage:" in prompt
    assert '"status": "uncovered"' in prompt
    assert '"scoped_policy_count": 2' in prompt
    assert "prefer attention_type=policy_gap" in prompt
    assert "metadata.requires_policy_decision=true" in prompt
