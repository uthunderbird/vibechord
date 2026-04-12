from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from agent_operator.domain import OperationStatus


class McpParamsModel(BaseModel):
    """Base model for inbound MCP tool parameters.

    Examples:
        >>> class Example(McpParamsModel):
        ...     value: str
        >>> Example.model_validate({"value": "ok"}).value
        'ok'
    """

    model_config = ConfigDict(extra="forbid")


class ListOperationsParams(McpParamsModel):
    """Input schema for `list_operations`."""

    status_filter: OperationStatus | None = None


class RunOperationParams(McpParamsModel):
    """Input schema for `run_operation`."""

    goal: str
    agent: str | None = None
    wait: bool = False
    timeout_seconds: int | None = Field(default=None, ge=0)


class GetStatusParams(McpParamsModel):
    """Input schema for `get_status`."""

    operation_id: str


class AnswerAttentionParams(McpParamsModel):
    """Input schema for `answer_attention`."""

    operation_id: str
    attention_id: str | None = None
    answer: str


class CancelOperationParams(McpParamsModel):
    """Input schema for `cancel_operation`."""

    operation_id: str
    reason: str | None = None


class InterruptOperationParams(McpParamsModel):
    """Input schema for `interrupt_operation`."""

    operation_id: str
