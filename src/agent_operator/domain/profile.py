from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field

from agent_operator.domain.enums import InvolvementLevel, RunMode


class ProjectProfile(BaseModel):
    name: str
    cwd: Path | None = None
    paths: list[Path] = Field(default_factory=list)
    history_ledger: bool = True
    default_objective: str | None = None
    default_agents: list[str] = Field(default_factory=list)
    default_harness_instructions: str | None = None
    default_success_criteria: list[str] = Field(default_factory=list)
    default_max_iterations: int | None = None
    default_run_mode: RunMode | None = None
    default_involvement_level: InvolvementLevel | None = None
    adapter_settings: dict[str, dict[str, object]] = Field(default_factory=dict)
    dashboard_prefs: dict[str, object] = Field(default_factory=dict)
    session_reuse_policy: str | None = None
    default_message_window: int | None = None


class ResolvedProjectRunConfig(BaseModel):
    profile_name: str | None = None
    cwd: Path | None = None
    objective_text: str | None = None
    default_agents: list[str] = Field(default_factory=list)
    harness_instructions: str | None = None
    success_criteria: list[str] = Field(default_factory=list)
    max_iterations: int
    run_mode: RunMode
    involvement_level: InvolvementLevel
    message_window: int = 3
    overrides: list[str] = Field(default_factory=list)
