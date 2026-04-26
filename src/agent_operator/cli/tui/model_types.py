from __future__ import annotations

from dataclasses import dataclass

type TerminalSettings = (
    list[int | list[bytes | int]] | list[int | list[bytes]] | list[int | list[int]]
)


def optional_text(value: object) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def optional_int(value: object) -> int:
    return value if isinstance(value, int) else 0


def text_tuple(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(str(item) for item in value if isinstance(item, str))


@dataclass(frozen=True, slots=True)
class FleetItem:
    operation_id: str
    attention_badge: str
    display_name: str
    state_label: str
    agent_cue: str
    recency_brief: str
    row_hint: str
    status: str
    scheduler_state: str
    objective_brief: str
    focus_brief: str | None
    latest_outcome_brief: str | None
    blocker_brief: str | None
    runtime_alert: str | None
    open_attention_count: int
    open_blocking_attention_count: int
    open_nonblocking_attention_count: int
    attention_briefs: tuple[str, ...]
    project_profile_name: str | None
    brief: dict[str, object] | None
    bucket: str

    @classmethod
    def from_payload(cls, payload: dict[str, object]) -> FleetItem:
        attention_briefs_raw = payload.get("attention_briefs")
        attention_briefs = (
            tuple(str(item) for item in attention_briefs_raw if isinstance(item, str))
            if isinstance(attention_briefs_raw, list)
            else ()
        )
        brief = payload.get("brief")
        objective_brief = optional_text(payload.get("objective_brief")) or "-"
        display_name = optional_text(payload.get("display_name")) or objective_brief
        return cls(
            operation_id=str(payload.get("operation_id") or "-"),
            attention_badge=str(
                payload.get("attention_badge") or cls._legacy_signal(payload=payload)
            ),
            display_name=display_name,
            state_label=str(payload.get("state_label") or cls._legacy_state(payload=payload)),
            agent_cue=str(
                payload.get("agent_cue")
                or payload.get("project_profile_name")
                or payload.get("policy_scope")
                or "-"
            ),
            recency_brief=optional_text(payload.get("recency_brief"))
            or optional_text(payload.get("focus_brief"))
            or optional_text(payload.get("latest_outcome_brief"))
            or "no recent activity",
            row_hint=str(payload.get("row_hint") or "-"),
            status=str(payload.get("status") or "-"),
            scheduler_state=str(payload.get("scheduler_state") or "-"),
            objective_brief=objective_brief,
            focus_brief=optional_text(payload.get("focus_brief")),
            latest_outcome_brief=optional_text(payload.get("latest_outcome_brief")),
            blocker_brief=optional_text(payload.get("blocker_brief")),
            runtime_alert=optional_text(payload.get("runtime_alert")),
            open_attention_count=optional_int(payload.get("open_attention_count")),
            open_blocking_attention_count=optional_int(
                payload.get("open_blocking_attention_count")
            ),
            open_nonblocking_attention_count=optional_int(
                payload.get("open_nonblocking_attention_count"),
            ),
            attention_briefs=attention_briefs,
            project_profile_name=optional_text(payload.get("project_profile_name")),
            brief=brief if isinstance(brief, dict) else None,
            bucket=str(payload.get("bucket") or payload.get("sort_bucket") or "recent"),
        )

    @staticmethod
    def _legacy_signal(payload: dict[str, object]) -> str:
        runtime_alert = optional_text(payload.get("runtime_alert"))
        if runtime_alert is not None:
            return "!!"
        if optional_int(payload.get("open_blocking_attention_count")) > 0:
            return f"B{optional_int(payload.get('open_blocking_attention_count'))}"
        if optional_int(payload.get("open_attention_count")) > 0:
            return f"A{optional_int(payload.get('open_attention_count'))}"
        if optional_int(payload.get("open_nonblocking_attention_count")) > 0:
            return f"Q{optional_int(payload.get('open_nonblocking_attention_count'))}"
        return "-"

    @staticmethod
    def _legacy_state(payload: dict[str, object]) -> str:
        status = optional_text(payload.get("status")) or "-"
        scheduler_state = optional_text(payload.get("scheduler_state"))
        if scheduler_state and scheduler_state != "active":
            return f"{status}/{scheduler_state}"
        return status

    @property
    def has_attention(self) -> bool:
        return self.runtime_alert is not None or self.open_attention_count > 0

    @property
    def has_blocking_attention(self) -> bool:
        return self.open_blocking_attention_count > 0


@dataclass(frozen=True, slots=True)
class OperationTaskItem:
    task_id: str
    task_short_id: str
    title: str
    goal: str
    definition_of_done: str
    status: str
    priority: int
    dependencies: tuple[str, ...]
    assigned_agent: str | None
    linked_session_id: str | None
    memory_refs: tuple[str, ...]
    artifact_refs: tuple[str, ...]
    notes: tuple[str, ...]

    @classmethod
    def from_payload(cls, payload: dict[str, object]) -> OperationTaskItem:
        return cls(
            task_id=str(payload.get("task_id") or "-"),
            task_short_id=str(payload.get("task_short_id") or "-"),
            title=str(payload.get("title") or "-"),
            goal=str(payload.get("goal") or "-"),
            definition_of_done=str(payload.get("definition_of_done") or "-"),
            status=str(payload.get("status") or "-"),
            priority=optional_int(payload.get("priority")),
            dependencies=text_tuple(payload.get("dependencies")),
            assigned_agent=optional_text(payload.get("assigned_agent")),
            linked_session_id=optional_text(payload.get("linked_session_id")),
            memory_refs=text_tuple(payload.get("memory_refs")),
            artifact_refs=text_tuple(payload.get("artifact_refs")),
            notes=text_tuple(payload.get("notes")),
        )


@dataclass(frozen=True, slots=True)
class TimelineEventItem:
    event_type: str
    iteration: int
    task_id: str | None
    session_id: str | None
    summary: str

    @classmethod
    def from_payload(cls, payload: dict[str, object]) -> TimelineEventItem:
        return cls(
            event_type=str(payload.get("event_type") or "-"),
            iteration=optional_int(payload.get("iteration")),
            task_id=optional_text(payload.get("task_id")),
            session_id=optional_text(payload.get("session_id")),
            summary=str(payload.get("summary") or "-"),
        )
