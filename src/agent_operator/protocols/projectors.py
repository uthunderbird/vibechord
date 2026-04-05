from __future__ import annotations

from typing import Protocol

from agent_operator.domain import OperationCheckpoint, StoredOperationDomainEvent


class OperationProjector(Protocol):
    """Pure projector for folding ordered domain events into one checkpoint.

    Examples:
        Implementations must be deterministic and depend only on the prior
        checkpoint plus the ordered domain event suffix.
    """

    def apply_event(
        self,
        checkpoint: OperationCheckpoint,
        event: StoredOperationDomainEvent,
    ) -> OperationCheckpoint: ...

    def project(
        self,
        checkpoint: OperationCheckpoint,
        events: list[StoredOperationDomainEvent],
    ) -> OperationCheckpoint: ...
