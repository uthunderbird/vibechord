"""Canonical query-family package for application services."""

# ── v2 Layer 3a ───────────────────────────────────────────────────────────────
from agent_operator.application.queries.aggregate_query_adapter import (
    AggregateQueryAdapter,
    aggregate_to_state,
)
from agent_operator.application.queries.operation_read_model_projector import (
    OperationReadModelProjector,
)

__all__ = [
    "AggregateQueryAdapter",
    "aggregate_to_state",
    "OperationReadModelProjector",
]
