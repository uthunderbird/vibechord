"""Unit tests for LifecycleGate — pure predicate service (ADR 0195)."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from agent_operator.application.drive.lifecycle_gate import LifecycleGate
from agent_operator.application.drive.process_manager_context import (
    ProcessManagerContext,
    RuntimeSessionContext,
    build_pm_context,
)
from agent_operator.domain.agent import AgentDescriptor
from agent_operator.domain.aggregate import OperationAggregate
from agent_operator.domain.enums import (
    FocusKind,
    FocusMode,
    OperationStatus,
    PolicyCoverageStatus,
    PolicyStatus,
    SchedulerState,
)
from agent_operator.domain.operation import (
    ExecutionBudget,
    FocusState,
    ObjectiveState,
    OperationGoal,
)
from agent_operator.domain.policy import PolicyApplicability, PolicyCategory, PolicyEntry

# ── Helpers ────────────────────────────────────────────────────────────────────


def _agg(**kwargs: object) -> OperationAggregate:
    agg = OperationAggregate.create(OperationGoal(objective="test"))
    if kwargs:
        import dataclasses
        agg = dataclasses.replace(agg, **kwargs)
    return agg


def _ctx(**kwargs: object) -> ProcessManagerContext:
    return ProcessManagerContext(**kwargs)  # type: ignore[arg-type]


class StubAdapterRegistry:
    def __init__(self) -> None:
        self._descriptors = {
            "codex_acp": AgentDescriptor(key="codex_acp", display_name="Codex ACP"),
        }

    def has(self, adapter_key: str) -> bool:
        return adapter_key in self._descriptors

    async def describe(self, adapter_key: str) -> AgentDescriptor:
        return self._descriptors[adapter_key]


class InvalidAdapterRegistry:
    pass


class StubPolicyStore:
    def __init__(self, entries: list[PolicyEntry]) -> None:
        self._entries = list(entries)

    async def list(
        self,
        *,
        project_scope: str | None = None,
        status: PolicyStatus | None = None,
    ) -> list[PolicyEntry]:
        entries = list(self._entries)
        if project_scope is not None:
            entries = [entry for entry in entries if entry.project_scope == project_scope]
        if status is not None:
            entries = [entry for entry in entries if entry.status is status]
        return entries


gate = LifecycleGate()


# ── should_continue ────────────────────────────────────────────────────────────


def test_should_continue_true_when_running() -> None:
    assert gate.should_continue(_agg(), ctx=_ctx(), cycles_executed=0, cycle_budget=100) is True


def test_should_continue_false_when_completed() -> None:
    import dataclasses
    agg = dataclasses.replace(_agg(), status=OperationStatus.COMPLETED)
    assert gate.should_continue(agg, ctx=_ctx(), cycles_executed=0, cycle_budget=100) is False


def test_should_continue_false_when_failed() -> None:
    import dataclasses
    agg = dataclasses.replace(_agg(), status=OperationStatus.FAILED)
    assert gate.should_continue(agg, ctx=_ctx(), cycles_executed=0, cycle_budget=100) is False


def test_should_continue_false_when_cancelled() -> None:
    import dataclasses
    agg = dataclasses.replace(_agg(), status=OperationStatus.CANCELLED)
    assert gate.should_continue(agg, ctx=_ctx(), cycles_executed=0, cycle_budget=100) is False


def test_should_continue_false_when_scheduler_paused() -> None:
    import dataclasses
    agg = dataclasses.replace(_agg(), scheduler_state=SchedulerState.PAUSED)
    assert gate.should_continue(agg, ctx=_ctx(), cycles_executed=0, cycle_budget=100) is False


def test_should_continue_false_when_budget_exceeded() -> None:
    assert gate.should_continue(_agg(), ctx=_ctx(), cycles_executed=10, cycle_budget=10) is False


def test_should_continue_false_when_context_is_draining() -> None:
    ctx = _ctx(draining=True)
    assert gate.should_continue(_agg(), ctx=ctx, cycles_executed=0, cycle_budget=100) is False


def test_should_continue_false_when_needs_human_no_pending() -> None:
    import dataclasses
    agg = dataclasses.replace(_agg(), status=OperationStatus.NEEDS_HUMAN)
    assert gate.should_continue(agg, ctx=_ctx(), cycles_executed=0, cycle_budget=100) is False


def test_should_continue_true_when_needs_human_with_pending_attention() -> None:
    import dataclasses
    agg = dataclasses.replace(
        _agg(),
        status=OperationStatus.NEEDS_HUMAN,
        pending_attention_resolution_ids=["req-1"],
    )
    assert gate.should_continue(agg, ctx=_ctx(), cycles_executed=0, cycle_budget=100) is True


# ── check_timeout ──────────────────────────────────────────────────────────────


def test_check_timeout_false_when_no_timeout_configured() -> None:
    agg = _agg()
    assert gate.check_timeout(agg) is False


def test_check_timeout_true_when_elapsed() -> None:
    import dataclasses
    old_time = datetime.now(UTC) - timedelta(seconds=200)
    budget = ExecutionBudget(timeout_seconds=100)
    agg = dataclasses.replace(_agg(), execution_budget=budget, created_at=old_time)
    assert gate.check_timeout(agg) is True


def test_check_timeout_false_when_within_budget() -> None:
    import dataclasses
    budget = ExecutionBudget(timeout_seconds=3600)
    agg = dataclasses.replace(_agg(), execution_budget=budget)
    assert gate.check_timeout(agg) is False


# ── check_budget ───────────────────────────────────────────────────────────────


def test_check_budget_false_below_limit() -> None:
    assert gate.check_budget(_agg(), cycles_executed=5, cycle_budget=10) is False


def test_check_budget_true_at_limit() -> None:
    assert gate.check_budget(_agg(), cycles_executed=10, cycle_budget=10) is True


def test_check_budget_true_above_limit() -> None:
    assert gate.check_budget(_agg(), cycles_executed=11, cycle_budget=10) is True


# ── is_scheduler_paused ────────────────────────────────────────────────────────


def test_is_scheduler_paused_false_when_active() -> None:
    assert gate.is_scheduler_paused(_agg()) is False


def test_is_scheduler_paused_true_when_paused() -> None:
    import dataclasses
    agg = dataclasses.replace(_agg(), scheduler_state=SchedulerState.PAUSED)
    assert gate.is_scheduler_paused(agg) is True


def test_is_scheduler_paused_false_when_pause_requested() -> None:
    import dataclasses
    agg = dataclasses.replace(_agg(), scheduler_state=SchedulerState.PAUSE_REQUESTED)
    assert gate.is_scheduler_paused(agg) is False


# ── should_break_for_status ────────────────────────────────────────────────────


def test_should_break_for_running_is_false() -> None:
    assert gate.should_break_for_status(_agg()) is False


def test_should_break_for_needs_human_is_true() -> None:
    import dataclasses
    agg = dataclasses.replace(_agg(), status=OperationStatus.NEEDS_HUMAN)
    assert gate.should_break_for_status(agg) is True


# ── is_blocked_on_background_wait ─────────────────────────────────────────────


def test_is_blocked_on_background_wait_false_when_no_focus() -> None:
    assert gate.is_blocked_on_background_wait(_agg(), _ctx()) is False


def test_is_blocked_on_background_wait_false_when_advisory_focus() -> None:
    import dataclasses
    focus = FocusState(kind=FocusKind.TASK, target_id="task-1", mode=FocusMode.ADVISORY)
    agg = dataclasses.replace(_agg(), current_focus=focus)
    assert gate.is_blocked_on_background_wait(agg, _ctx()) is False


def test_is_blocked_on_background_wait_true_when_session_running() -> None:
    import dataclasses
    focus = FocusState(kind=FocusKind.SESSION, target_id="sess-1", mode=FocusMode.BLOCKING)
    agg = dataclasses.replace(_agg(), current_focus=focus)
    ctx = _ctx(
        session_contexts={
            "sess-1": RuntimeSessionContext("sess-1", is_background_running=True),
        }
    )
    assert gate.is_blocked_on_background_wait(agg, ctx) is True


def test_is_blocked_on_background_wait_false_when_session_not_running() -> None:
    import dataclasses
    focus = FocusState(kind=FocusKind.SESSION, target_id="sess-1", mode=FocusMode.BLOCKING)
    agg = dataclasses.replace(_agg(), current_focus=focus)
    ctx = _ctx(
        session_contexts={
            "sess-1": RuntimeSessionContext("sess-1", is_background_running=False),
        }
    )
    assert gate.is_blocked_on_background_wait(agg, ctx) is False


@pytest.mark.anyio
async def test_build_pm_context_uses_duck_typed_adapter_registry() -> None:
    agg = _agg(allowed_agents=["codex_acp"])
    ctx = await build_pm_context(
        agg,
        policy_store=object(),
        adapter_registry=StubAdapterRegistry(),
    )

    assert [descriptor.key for descriptor in ctx.available_agents] == ["codex_acp"]


@pytest.mark.anyio
async def test_build_pm_context_rebuilds_policy_coverage_from_policy_store() -> None:
    agg = _agg(
        goal=OperationGoal(
            objective="Ship the release checklist",
            metadata={"policy_scope": "profile:test"},
        ),
        objective=ObjectiveState(objective="Ship the release checklist"),
        allowed_agents=["codex_acp"],
    )
    policy_store = StubPolicyStore(
        [
            PolicyEntry(
                policy_id="policy-1",
                project_scope="profile:test",
                title="Release policy",
                category=PolicyCategory.RELEASE,
                rule_text="Require review for release work.",
                applicability=PolicyApplicability(objective_keywords=["release"]),
            )
        ]
    )

    ctx = await build_pm_context(
        agg,
        policy_store=policy_store,
        adapter_registry=StubAdapterRegistry(),
    )

    assert ctx.policy_context is not None
    assert ctx.policy_context.status is PolicyCoverageStatus.COVERED
    assert ctx.policy_context.project_scope == "profile:test"
    assert ctx.policy_context.active_policy_count == 1


@pytest.mark.anyio
async def test_build_pm_context_rejects_registry_without_required_methods() -> None:
    agg = _agg(allowed_agents=["codex_acp"])

    with pytest.raises(
        TypeError,
        match="adapter_registry must provide has\\(\\) and describe\\(\\)",
    ):
        await build_pm_context(
            agg,
            policy_store=object(),
            adapter_registry=InvalidAdapterRegistry(),
        )
