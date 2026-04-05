from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from pydantic import BaseModel, Field

from agent_operator.domain.enums import (
    InvolvementLevel,
    PolicyCategory,
    PolicyCoverageStatus,
    PolicyStatus,
    RunMode,
)


class PolicySourceRef(BaseModel):
    kind: str
    ref_id: str


class PermissionRequestSignature(BaseModel):
    adapter_key: str
    method: str
    interaction: str
    title: str | None = None
    tool_kind: str | None = None
    skill_name: str | None = None
    command: list[str] = Field(default_factory=list)


class PolicyApplicability(BaseModel):
    objective_keywords: list[str] = Field(default_factory=list)
    task_keywords: list[str] = Field(default_factory=list)
    agent_keys: list[str] = Field(default_factory=list)
    run_modes: list[RunMode] = Field(default_factory=list)
    involvement_levels: list[InvolvementLevel] = Field(default_factory=list)
    permission_signatures: list[PermissionRequestSignature] = Field(default_factory=list)

    @property
    def is_global(self) -> bool:
        return not (
            self.objective_keywords
            or self.task_keywords
            or self.agent_keys
            or self.run_modes
            or self.involvement_levels
            or self.permission_signatures
        )


class PolicyEntry(BaseModel):
    policy_id: str = Field(default_factory=lambda: str(uuid4()))
    project_scope: str
    title: str
    category: PolicyCategory = PolicyCategory.GENERAL
    rule_text: str
    applicability: PolicyApplicability = Field(default_factory=PolicyApplicability)
    rationale: str | None = None
    source_refs: list[PolicySourceRef] = Field(default_factory=list)
    status: PolicyStatus = PolicyStatus.ACTIVE
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    revoked_at: datetime | None = None
    revoked_reason: str | None = None
    superseded_by: str | None = None


class PolicyCoverage(BaseModel):
    status: PolicyCoverageStatus = PolicyCoverageStatus.NO_SCOPE
    project_scope: str | None = None
    scoped_policy_count: int = 0
    active_policy_count: int = 0
    summary: str = "This operation has no project policy scope."
