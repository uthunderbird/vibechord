from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field, model_validator

from agent_operator.domain.enums import AttentionStatus, AttentionType, CommandTargetScope


class AttentionRequest(BaseModel):
    attention_id: str = Field(default_factory=lambda: str(uuid4()))
    operation_id: str
    attention_type: AttentionType
    target_scope: CommandTargetScope = CommandTargetScope.OPERATION
    target_id: str | None = None
    title: str
    question: str
    context_brief: str | None = None
    suggested_options: list[str] = Field(default_factory=list)
    blocking: bool = True
    status: AttentionStatus = AttentionStatus.OPEN
    answer_text: str | None = None
    answer_source_command_id: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    answered_at: datetime | None = None
    resolved_at: datetime | None = None
    resolution_summary: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _normalize(self) -> AttentionRequest:
        self.title = self.title.strip()
        self.question = self.question.strip()
        self.context_brief = self.context_brief.strip() if self.context_brief else None
        self.suggested_options = [item.strip() for item in self.suggested_options if item.strip()]
        if not self.title:
            raise ValueError("AttentionRequest.title must not be empty.")
        if not self.question:
            raise ValueError("AttentionRequest.question must not be empty.")
        return self
