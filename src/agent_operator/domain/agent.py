from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from agent_operator.domain.enums import AgentProgressState, AgentResultStatus


class AgentCapability(BaseModel):
    name: str
    description: str = ""


class AgentDescriptor(BaseModel):
    key: str
    display_name: str
    capabilities: list[AgentCapability] = Field(default_factory=list)
    supports_follow_up: bool = True
    supports_cancellation: bool = True
    supports_fork: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)


class AgentSessionHandle(BaseModel):
    adapter_key: str
    session_id: str
    session_name: str | None = None
    display_name: str | None = None
    one_shot: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)


class AgentArtifact(BaseModel):
    name: str
    kind: str
    uri: str | None = None
    content: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class AgentUsage(BaseModel):
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    context_window_size: int | None = None
    context_tokens_used: int | None = None
    cost_amount: float | None = None
    cost_currency: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class AgentProgress(BaseModel):
    session_id: str
    state: AgentProgressState
    message: str
    updated_at: datetime
    progress_text: str | None = None
    partial_output: str | None = None
    usage: AgentUsage | None = None
    artifacts: list[AgentArtifact] = Field(default_factory=list)
    raw: dict[str, Any] | None = None


class AgentError(BaseModel):
    code: str
    message: str
    retryable: bool = False
    raw: dict[str, Any] | None = None


class AgentResult(BaseModel):
    session_id: str
    status: AgentResultStatus
    output_text: str = ""
    artifacts: list[AgentArtifact] = Field(default_factory=list)
    error: AgentError | None = None
    completed_at: datetime | None = None
    structured_output: dict[str, Any] | None = None
    usage: AgentUsage | None = None
    transcript: str | None = None
    raw: dict[str, Any] | None = None
