from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, model_validator


class AgentSessionCommandType(str):
    """String-like session-runtime command discriminator."""

    START_SESSION = "start_session"
    SEND_MESSAGE = "send_message"
    REPLACE_SESSION = "replace_session"


class AgentSessionCommand(BaseModel):
    """Session-scoped command sent through `AgentSessionRuntime`.

    Attributes:
        command_type: Session command kind.
        instruction: Prompt/instruction for start/send/replace flows.
        session_id: Optional explicit target session identifier.
        metadata: Optional session command metadata.

    Examples:
        >>> command = AgentSessionCommand(
        ...     command_type=AgentSessionCommandType.START_SESSION,
        ...     instruction="Inspect the repository.",
        ... )
        >>> command.command_type
        'start_session'
    """

    command_type: str
    instruction: str | None = None
    session_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_shape(self) -> AgentSessionCommand:
        if self.command_type in {
            AgentSessionCommandType.START_SESSION,
            AgentSessionCommandType.SEND_MESSAGE,
            AgentSessionCommandType.REPLACE_SESSION,
        }:
            if not isinstance(self.instruction, str) or not self.instruction.strip():
                raise ValueError(
                    "Session start/send/replace commands require non-empty instruction."
                )
            return self
        raise ValueError(f"Unsupported agent session command type: {self.command_type}.")
