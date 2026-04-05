from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, model_validator


class AdapterCommandType(str):
    """String-like adapter command discriminator.

    Use the predefined class attributes instead of constructing ad hoc values in normal code.

    Examples:
        >>> AdapterCommandType.REQUEST
        'request'
    """

    REQUEST = "request"
    NOTIFY = "notify"
    RESPOND = "respond"


class AdapterCommand(BaseModel):
    """Transport-scoped command sent through `AdapterRuntime`.

    Attributes:
        command_type: Transport command kind.
        method: ACP/transport method for request/notify commands.
        params: Structured transport payload.
        request_id: Request identifier for response commands.
        result: JSON-RPC result payload for response commands.
        error: JSON-RPC error payload for response commands.

    Examples:
        >>> command = AdapterCommand(
        ...     command_type=AdapterCommandType.REQUEST,
        ...     method="session/new",
        ...     params={"cwd": "/tmp"},
        ... )
        >>> command.method
        'session/new'
    """

    command_type: str
    method: str | None = None
    params: dict[str, Any] = Field(default_factory=dict)
    request_id: int | None = None
    result: dict[str, Any] | None = None
    error: dict[str, Any] | None = None

    @model_validator(mode="after")
    def _validate_shape(self) -> AdapterCommand:
        command_type = self.command_type
        if command_type in {AdapterCommandType.REQUEST, AdapterCommandType.NOTIFY}:
            if not self.method:
                raise ValueError("Adapter request/notify commands require method.")
            return self
        if command_type == AdapterCommandType.RESPOND:
            if self.request_id is None:
                raise ValueError("Adapter respond commands require request_id.")
            return self
        raise ValueError(f"Unsupported adapter command type: {command_type}.")
