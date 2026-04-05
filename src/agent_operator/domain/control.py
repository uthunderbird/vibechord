from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field, model_validator

from agent_operator.domain.enums import CommandStatus, CommandTargetScope, OperationCommandType


class OperationCommand(BaseModel):
    command_id: str = Field(default_factory=lambda: str(uuid4()))
    operation_id: str
    command_type: OperationCommandType
    target_scope: CommandTargetScope
    target_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    submitted_by: str = "user"
    submitted_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    status: CommandStatus = CommandStatus.PENDING
    rejection_reason: str | None = None
    applied_at: datetime | None = None


class OperatorMessage(BaseModel):
    message_id: str = Field(default_factory=lambda: str(uuid4()))
    submitted_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    text: str
    source_command_id: str | None = None
    applied_at: datetime | None = None
    dropped_from_context: bool = False
    planning_cycles_active: int = 0

    @model_validator(mode="after")
    def _validate_text(self) -> OperatorMessage:
        self.text = self.text.strip()
        if not self.text:
            raise ValueError("OperatorMessage.text must not be empty.")
        return self
