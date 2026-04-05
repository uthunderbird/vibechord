from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field, model_validator

from agent_operator.domain.enums import RunEventKind


class RunEvent(BaseModel):
    event_id: str = Field(default_factory=lambda: str(uuid4()))
    event_type: str
    kind: RunEventKind = RunEventKind.TRACE
    category: Literal["domain", "trace"] | None = None
    operation_id: str
    iteration: int
    task_id: str | None = None
    session_id: str | None = None
    dedupe_key: str | None = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    not_before: datetime | None = None
    payload: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_category(self) -> RunEvent:
        if self.kind is RunEventKind.TRACE and self.category is None:
            raise ValueError(
                f"RunEvent with kind=TRACE must have a category set "
                f"(event_type={self.event_type!r}). "
                "Wakeup events are exempt; use kind=RunEventKind.WAKEUP for those."
            )
        return self
