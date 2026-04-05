from __future__ import annotations

import pytest

from agent_operator.application.process_managers import CodeProcessManagerBuilder
from agent_operator.application.process_signals import ProcessManagerSignal
from agent_operator.domain import (
    InvolvementLevel,
    OperationGoal,
    OperationPolicy,
    OperationState,
    PlanningTrigger,
)


def _build_state(operation_id: str = "op-1") -> OperationState:
    """Build a minimal operation state for process-manager tests."""

    return OperationState(
        operation_id=operation_id,
        goal=OperationGoal(objective="Continue execution."),
        policy=OperationPolicy(
            allowed_agents=["claude_acp"],
            involvement_level=InvolvementLevel.AUTO,
        ),
    )


async def _collect_triggers(signal: ProcessManagerSignal) -> list[PlanningTrigger]:
    """Run the code-defined process managers against one signal."""

    state = _build_state(signal.operation_id)
    triggers: list[PlanningTrigger] = []
    for manager in CodeProcessManagerBuilder().build():
        triggers.extend(await manager.react(signal, state))
    return triggers


def test_code_process_manager_builder_assembles_expected_managers() -> None:
    """Builder returns the bounded code-defined manager set."""

    managers = CodeProcessManagerBuilder().build()

    assert len(managers) == 4


@pytest.mark.anyio
async def test_planning_context_signal_emits_one_deterministic_trigger() -> None:
    """Planning-context changes emit one coalescible planning trigger."""

    signal = ProcessManagerSignal(
        operation_id="op-1",
        signal_type="planning_context_changed",
        source_command_id="cmd-1",
        metadata={"reason": "objective_updated"},
    )

    triggers = await _collect_triggers(signal)

    assert [item.reason for item in triggers] == ["objective_updated"]
    assert triggers[0].dedupe_key == "op-1:planning_context_changed"


@pytest.mark.anyio
async def test_attention_answer_signal_emits_attention_scoped_trigger() -> None:
    """Answered attention emits an attention-scoped planning trigger."""

    signal = ProcessManagerSignal(
        operation_id="op-1",
        signal_type="attention_answer_recorded",
        metadata={"attention_id": "att-1"},
    )

    triggers = await _collect_triggers(signal)

    assert [item.reason for item in triggers] == ["attention_answer_recorded"]
    assert triggers[0].dedupe_key == "op-1:attention:att-1"


@pytest.mark.anyio
async def test_execution_lost_signal_emits_execution_scoped_trigger() -> None:
    """Execution-loss signals emit recovery/planning triggers without route choice."""

    signal = ProcessManagerSignal(
        operation_id="op-1",
        signal_type="execution_lost",
        execution_id="exec-1",
        session_id="session-1",
    )

    triggers = await _collect_triggers(signal)

    assert [item.reason for item in triggers] == ["execution_lost"]
    assert triggers[0].dedupe_key == "op-1:execution_lost:exec-1"


@pytest.mark.anyio
async def test_unrelated_signal_emits_no_trigger() -> None:
    """Policies stay silent for unrelated signals."""

    signal = ProcessManagerSignal(
        operation_id="op-1",
        signal_type="noop",
    )

    triggers = await _collect_triggers(signal)

    assert triggers == []
