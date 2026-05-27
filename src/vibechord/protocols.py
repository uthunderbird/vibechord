"""Protocol contracts for replaceable vibechord boundaries."""

from __future__ import annotations

from typing import Protocol

from vibechord.domain import AgentResult, BrainDecision, OperationSnapshot, RunEvent


class Clock(Protocol):
    """Clock provider used to make tests deterministic."""

    def now(self) -> str:
        """Return an ISO-8601 timestamp."""


class EventStore(Protocol):
    """Append/replay contract for canonical operation events."""

    def append(
        self,
        operation_id: str,
        kind: str,
        payload: dict[str, str | int | bool],
        command_id: str | None = None,
    ) -> RunEvent:
        """Append one event or return the existing command event idempotently."""

    def replay(self, operation_id: str) -> tuple[RunEvent, ...]:
        """Replay events for one operation."""

    def all_events(self) -> tuple[RunEvent, ...]:
        """Return all events ordered by operation and sequence."""


class OperatorBrain(Protocol):
    """Decision maker used by OperationDriver."""

    def decide(self, snapshot: OperationSnapshot) -> BrainDecision:
        """Return the next action for an operation snapshot."""


class AgentAdapter(Protocol):
    """External agent adapter contract."""

    def invoke(self, agent_name: str, agent_input: str) -> AgentResult:
        """Invoke an external agent and return a domain-level result."""
