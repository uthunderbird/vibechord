from __future__ import annotations

from typing import Final

from agent_operator.application.process_signals import ProcessManagerSignal
from agent_operator.domain import (
    OperationState,
    PlanningTrigger,
)
from agent_operator.protocols import ProcessManager, ProcessManagerPolicy

_PLANNING_CONTEXT_DEDUPE_KEY: Final[str] = "planning_context_changed"
_POLICY_CONTEXT_DEDUPE_KEY: Final[str] = "policy_context_changed"


class PolicyDrivenProcessManager:
    """Process manager assembled from bounded policy units."""

    def __init__(self, policies: list[ProcessManagerPolicy]) -> None:
        self._policies = policies

    async def react(
        self,
        signal: ProcessManagerSignal,
        state: OperationState,
    ) -> list[PlanningTrigger]:
        triggers: list[PlanningTrigger] = []
        for policy in self._policies:
            trigger = await policy.evaluate(signal, state)
            if trigger is not None:
                triggers.append(trigger)
        return triggers


class PlanningContextChangedPolicy:
    """Emit one planning trigger for generic planning-context changes."""

    async def evaluate(
        self,
        signal: ProcessManagerSignal,
        state: OperationState,
    ) -> PlanningTrigger | None:
        if signal.signal_type != "planning_context_changed":
            return None
        return PlanningTrigger(
            operation_id=state.operation_id,
            reason=str(signal.metadata.get("reason", "planning_context_changed")),
            source_kind="signal",
            source_id=signal.signal_id,
            source_event_type=signal.signal_type,
            task_id=signal.task_id,
            session_id=signal.session_id,
            execution_id=signal.execution_id,
            dedupe_key=f"{state.operation_id}:{_PLANNING_CONTEXT_DEDUPE_KEY}",
        )


class AttentionAnsweredPolicy:
    """Emit one trigger when human attention input requires replanning."""

    async def evaluate(
        self,
        signal: ProcessManagerSignal,
        state: OperationState,
    ) -> PlanningTrigger | None:
        if signal.signal_type != "attention_answer_recorded":
            return None
        attention_id = str(signal.metadata["attention_id"])
        return PlanningTrigger(
            operation_id=state.operation_id,
            reason="attention_answer_recorded",
            source_kind="signal",
            source_id=signal.signal_id,
            source_event_type=signal.signal_type,
            task_id=signal.task_id,
            session_id=signal.session_id,
            execution_id=signal.execution_id,
            dedupe_key=f"{state.operation_id}:attention:{attention_id}",
        )


class PolicyContextChangedPolicy:
    """Emit one trigger when policy context affecting planning changes."""

    async def evaluate(
        self,
        signal: ProcessManagerSignal,
        state: OperationState,
    ) -> PlanningTrigger | None:
        if signal.signal_type != "policy_context_changed":
            return None
        return PlanningTrigger(
            operation_id=state.operation_id,
            reason="policy_context_changed",
            source_kind="signal",
            source_id=signal.signal_id,
            source_event_type=signal.signal_type,
            dedupe_key=f"{state.operation_id}:{_POLICY_CONTEXT_DEDUPE_KEY}",
        )


class AttachedTurnStoppedPolicy:
    """Emit one trigger when a draining attached turn has actually yielded."""

    async def evaluate(
        self,
        signal: ProcessManagerSignal,
        state: OperationState,
    ) -> PlanningTrigger | None:
        if signal.signal_type != "attached_turn_stopped":
            return None
        session_id = signal.session_id or str(signal.metadata.get("session_id", ""))
        if not session_id:
            return None
        return PlanningTrigger(
            operation_id=state.operation_id,
            reason="attached_turn_stopped",
            source_kind="signal",
            source_id=signal.signal_id,
            source_event_type=signal.signal_type,
            session_id=session_id,
            dedupe_key=f"{state.operation_id}:attached_turn_stopped:{session_id}",
        )


class ExecutionLostPolicy:
    """Emit one trigger when runtime reconciliation marks execution or session as lost."""

    async def evaluate(
        self,
        signal: ProcessManagerSignal,
        state: OperationState,
    ) -> PlanningTrigger | None:
        if signal.signal_type != "execution_lost":
            return None
        execution_id = signal.execution_id or str(signal.metadata.get("execution_id", ""))
        session_id = signal.session_id or str(signal.metadata.get("session_id", ""))
        dedupe_suffix = execution_id or session_id
        if not dedupe_suffix:
            return None
        return PlanningTrigger(
            operation_id=state.operation_id,
            reason="execution_lost",
            source_kind="signal",
            source_id=signal.signal_id,
            source_event_type=signal.signal_type,
            session_id=session_id or None,
            execution_id=execution_id or None,
            dedupe_key=f"{state.operation_id}:execution_lost:{dedupe_suffix}",
        )


class CodeProcessManagerBuilder:
    """Build code-defined process managers for the current bridge runtime."""

    def build(self) -> list[ProcessManager]:
        return [
            PolicyDrivenProcessManager([PlanningContextChangedPolicy()]),
            PolicyDrivenProcessManager([AttentionAnsweredPolicy()]),
            PolicyDrivenProcessManager([PolicyContextChangedPolicy()]),
            PolicyDrivenProcessManager([AttachedTurnStoppedPolicy(), ExecutionLostPolicy()]),
        ]
