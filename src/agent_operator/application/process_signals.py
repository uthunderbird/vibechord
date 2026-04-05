from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field, model_validator


class ProcessManagerSignal(BaseModel):
    """Internal bridge signal observed by process managers.

    Instances carry only control-plane-safe facts and do not contain user-visible
    orchestration decisions.

    Attributes:
        signal_id: Stable signal identifier for traceability.
        operation_id: Owning operation identifier.
        signal_type: Canonical control-plane event type.
        source_command_id: Optional command identifier that triggered the signal.
        task_id: Optional linked task identifier.
        session_id: Optional linked session identifier.
        execution_id: Optional linked execution identifier.
        metadata: Control-plane metadata attached by the emitter.
        observed_at: Creation timestamp.

    Examples:
        >>> signal = ProcessManagerSignal(
        ...     operation_id="op-1",
        ...     signal_type="planning_context_changed",
        ...     source_command_id="cmd-1",
        ... )
        >>> signal.signal_id != ""
        True
    """

    signal_id: str = Field(default_factory=lambda: str(uuid4()))
    operation_id: str
    signal_type: str
    source_command_id: str | None = None
    task_id: str | None = None
    session_id: str | None = None
    execution_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    observed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @model_validator(mode="after")
    def _validate_signal_type(self) -> ProcessManagerSignal:
        self.signal_type = self.signal_type.strip()
        if not self.signal_type:
            raise ValueError("ProcessManagerSignal.signal_type must not be empty.")
        return self
