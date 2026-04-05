from pathlib import Path

from pydantic import BaseModel, Field


class AgentRunRequest(BaseModel):
    goal: str
    instruction: str
    session_name: str | None = None
    one_shot: bool = False
    working_directory: Path = Field(default_factory=Path.cwd)
    metadata: dict[str, str] = Field(default_factory=dict)
