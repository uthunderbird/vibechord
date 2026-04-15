from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from agent_operator.domain.enums import InvolvementLevel, RunMode, SessionReusePolicy


class ProjectProfileMcpServer(BaseModel):
    name: str
    command: str | None = None
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)
    url: str | None = None
    cwd: Path | None = None


class ProjectProfileAllowedModel(BaseModel):
    model: str
    effort: str | None = None
    reasoning_effort: str | None = None


class ProjectProfileAdapterSettings(BaseModel):
    model_config = ConfigDict(extra="allow")

    timeout_seconds: float | None = Field(default=None, ge=0)
    mcp_servers: list[ProjectProfileMcpServer] = Field(default_factory=list)
    allowed_models: list[ProjectProfileAllowedModel] = Field(default_factory=list)


class TicketReportingConfig(BaseModel):
    on_success: Literal["comment_and_close", "comment_only", "silent"] = "silent"
    on_failure: Literal["comment_only", "silent"] = "silent"
    on_cancelled: Literal["comment_only", "silent"] = "silent"
    webhook_url: str | None = None
    intake_hook: Path | None = None


class ProjectProfile(BaseModel):
    name: str
    cwd: Path | None = None
    paths: list[Path] = Field(default_factory=list)
    history_ledger: bool = True
    default_objective: str | None = None
    default_agents: list[str] = Field(default_factory=list)
    default_harness_instructions: str | None = None
    default_success_criteria: list[str] = Field(default_factory=list)
    default_max_iterations: int | None = Field(default=None, ge=1)
    default_run_mode: RunMode | None = None
    default_involvement_level: InvolvementLevel | None = None
    adapter_settings: dict[str, ProjectProfileAdapterSettings] = Field(default_factory=dict)
    dashboard_prefs: dict[str, object] = Field(default_factory=dict)
    session_reuse_policy: SessionReusePolicy | None = None
    default_message_window: int | None = Field(default=None, ge=0)
    ticket_reporting: TicketReportingConfig = Field(default_factory=TicketReportingConfig)


class ResolvedProjectRunConfig(BaseModel):
    profile_name: str | None = None
    cwd: Path | None = None
    history_ledger: bool = True
    objective_text: str | None = None
    default_agents: list[str] = Field(default_factory=list)
    harness_instructions: str | None = None
    success_criteria: list[str] = Field(default_factory=list)
    max_iterations: int
    run_mode: RunMode
    involvement_level: InvolvementLevel
    session_reuse_policy: SessionReusePolicy = SessionReusePolicy.ALWAYS_NEW
    message_window: int = 3
    overrides: list[str] = Field(default_factory=list)
