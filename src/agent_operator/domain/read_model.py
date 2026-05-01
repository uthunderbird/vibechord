"""OperationReadModel — derived projection, not persisted.

ADR 0193: Read model fields are reconstructible from the event log at any time.
They are not stored in OperationAggregate and not written to the checkpoint store.
DriveService appends to iteration_briefs and decision_records directly after each brain call.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from agent_operator.domain.traceability import AgentTurnBrief, IterationBrief, OperationBrief


@dataclass
class DecisionRecord:
    """Per-brain-call record — finer-grained than IterationBrief.

    Exists because more_actions sub-calls (ADR 0198) need to be visible to the brain
    via BrainContext.recent_decisions, whereas IterationBrief is one per while-loop cycle.
    """

    action_type: str
    more_actions: bool
    wake_cycle_id: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class OperationReadModel:
    """Derived read projection for one operation.

    Built by OperationReadModelProjector from the event stream, and appended to
    directly by DriveService for traceability data (iteration_briefs, decision_records).
    Not persisted to the checkpoint store — always reconstructible.
    """

    operation_id: str
    operation_brief: OperationBrief | None = None
    iteration_briefs: list[IterationBrief] = field(default_factory=list)
    decision_records: list[DecisionRecord] = field(default_factory=list)
    agent_turn_briefs: list[AgentTurnBrief] = field(default_factory=list)

    @classmethod
    def empty(cls, operation_id: str) -> OperationReadModel:
        return cls(operation_id=operation_id)


@dataclass
class PersistedReadModelProjection:
    """Stored read-model projection with explicit canonical event cursor.

    The projection payload is derived state. `source_event_sequence` names the
    canonical event stream sequence used to build it.
    """

    operation_id: str
    projection_type: str
    source_event_sequence: int
    projection_payload: dict[str, Any] = field(default_factory=dict)
    projected_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        if self.source_event_sequence < 0:
            raise ValueError("source_event_sequence must be non-negative.")
        if not self.operation_id:
            raise ValueError("operation_id must not be empty.")
        if not self.projection_type:
            raise ValueError("projection_type must not be empty.")
