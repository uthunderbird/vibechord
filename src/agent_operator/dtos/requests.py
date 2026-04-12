from pathlib import Path

from pydantic import BaseModel, Field

from agent_operator.domain.enums import SessionReusePolicy


class AgentRunRequest(BaseModel):
    goal: str
    instruction: str
    session_name: str | None = None
    one_shot: bool = False
    session_reuse_policy: SessionReusePolicy = SessionReusePolicy.ALWAYS_NEW
    working_directory: Path = Field(default_factory=Path.cwd)
    metadata: dict[str, str] = Field(default_factory=dict)
