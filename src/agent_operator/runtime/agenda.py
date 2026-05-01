from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field

from agent_operator.domain import (
    AttentionStatus,
    InvolvementLevel,
    OperationBrief,
    OperationState,
    OperationStatus,
    OperationSummary,
    SchedulerState,
)


class AgendaBucket(StrEnum):
    NEEDS_ATTENTION = "needs_attention"
    ACTIVE = "active"
    RECENT = "recent"


class AgendaItem(BaseModel):
    operation_id: str
    bucket: AgendaBucket
    status: OperationStatus
    objective_brief: str
    project_profile_name: str | None = None
    policy_scope: str | None = None
    scheduler_state: SchedulerState = SchedulerState.ACTIVE
    involvement_level: InvolvementLevel = InvolvementLevel.AUTO
    focus_brief: str | None = None
    latest_outcome_brief: str | None = None
    blocker_brief: str | None = None
    runtime_alert: str | None = None
    sync_health: dict[str, object] | None = None
    open_attention_count: int = 0
    open_blocking_attention_count: int = 0
    open_nonblocking_attention_count: int = 0
    attention_titles: list[str] = Field(default_factory=list)
    attention_briefs: list[str] = Field(default_factory=list)
    blocking_attention_titles: list[str] = Field(default_factory=list)
    nonblocking_attention_titles: list[str] = Field(default_factory=list)
    runnable_task_count: int = 0
    reusable_session_count: int = 0
    updated_at: datetime


class AgendaSnapshot(BaseModel):
    total_operations: int
    needs_attention: list[AgendaItem] = Field(default_factory=list)
    active: list[AgendaItem] = Field(default_factory=list)
    recent: list[AgendaItem] = Field(default_factory=list)


def build_agenda_item(
    operation: OperationState,
    summary: OperationSummary,
    *,
    brief: OperationBrief | None = None,
    runtime_alert: str | None = None,
    sync_health: dict[str, object] | None = None,
) -> AgendaItem:
    metadata = operation.goal.metadata
    open_attention = [
        item for item in operation.attention_requests if item.status is AttentionStatus.OPEN
    ]
    blocking_open_attention = [item for item in open_attention if item.blocking]
    nonblocking_open_attention = [item for item in open_attention if not item.blocking]
    latest_outcome = None
    if brief is not None:
        latest_outcome = brief.latest_outcome_brief or brief.blocker_brief
    latest_outcome = latest_outcome or summary.final_summary
    blocker = brief.blocker_brief if brief is not None else None
    item = AgendaItem(
        operation_id=operation.operation_id,
        bucket=AgendaBucket.RECENT,
        status=operation.status,
        objective_brief=brief.objective_brief if brief is not None else summary.objective_prompt,
        project_profile_name=_read_str(metadata, "project_profile_name"),
        policy_scope=_read_str(metadata, "policy_scope"),
        scheduler_state=operation.scheduler_state,
        involvement_level=operation.involvement_level,
        focus_brief=brief.focus_brief if brief is not None else summary.focus,
        latest_outcome_brief=latest_outcome,
        blocker_brief=blocker,
        runtime_alert=runtime_alert,
        sync_health=sync_health,
        open_attention_count=len(open_attention),
        open_blocking_attention_count=len(blocking_open_attention),
        open_nonblocking_attention_count=len(nonblocking_open_attention),
        attention_titles=[item.title for item in open_attention[:3]],
        attention_briefs=[
            f"[{item.attention_type.value}] {item.title}" for item in open_attention[:3]
        ],
        blocking_attention_titles=[item.title for item in blocking_open_attention[:3]],
        nonblocking_attention_titles=[item.title for item in nonblocking_open_attention[:3]],
        runnable_task_count=summary.runnable_task_count,
        reusable_session_count=summary.reusable_session_count,
        updated_at=summary.updated_at,
    )
    item.bucket = _bucket_for(item)
    return item


def build_agenda_snapshot(
    items: list[AgendaItem],
    *,
    include_recent: bool,
) -> AgendaSnapshot:
    filtered = sorted(items, key=_agenda_sort_key)
    needs_attention = [item for item in filtered if item.bucket is AgendaBucket.NEEDS_ATTENTION]
    active = [item for item in filtered if item.bucket is AgendaBucket.ACTIVE]
    recent = [item for item in filtered if item.bucket is AgendaBucket.RECENT]
    if not include_recent and (needs_attention or active):
        recent = []
    return AgendaSnapshot(
        total_operations=len(filtered),
        needs_attention=needs_attention,
        active=active,
        recent=recent,
    )


def agenda_matches_project(item: AgendaItem, project_name: str | None) -> bool:
    if project_name is None:
        return True
    if item.project_profile_name == project_name:
        return True
    return item.policy_scope == f"profile:{project_name}"


def _bucket_for(item: AgendaItem) -> AgendaBucket:
    if item.runtime_alert is not None:
        return AgendaBucket.NEEDS_ATTENTION
    if item.open_attention_count > 0:
        return AgendaBucket.NEEDS_ATTENTION
    if item.status is OperationStatus.NEEDS_HUMAN:
        return AgendaBucket.NEEDS_ATTENTION
    if item.scheduler_state in {SchedulerState.PAUSED, SchedulerState.PAUSE_REQUESTED}:
        return AgendaBucket.NEEDS_ATTENTION
    if item.status is OperationStatus.RUNNING:
        return AgendaBucket.ACTIVE
    return AgendaBucket.RECENT


def _agenda_sort_key(item: AgendaItem) -> tuple[int, int, float, str]:
    return (
        _bucket_rank(item),
        _attention_rank(item),
        -item.updated_at.timestamp(),
        item.operation_id,
    )


def _bucket_rank(item: AgendaItem) -> int:
    return {
        AgendaBucket.NEEDS_ATTENTION: 0,
        AgendaBucket.ACTIVE: 1,
        AgendaBucket.RECENT: 2,
    }[item.bucket]


def _attention_rank(item: AgendaItem) -> int:
    if item.bucket is not AgendaBucket.NEEDS_ATTENTION:
        return 9
    if item.runtime_alert is not None:
        return 0
    if item.open_attention_count > 0 or item.status is OperationStatus.NEEDS_HUMAN:
        return 1
    if item.scheduler_state in {SchedulerState.PAUSED, SchedulerState.PAUSE_REQUESTED}:
        return 2
    return 3


def _read_str(metadata: dict[str, object], key: str) -> str | None:
    value = metadata.get(key)
    return value if isinstance(value, str) and value else None
