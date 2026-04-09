from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

type TerminalSettings = (
    list[int | list[bytes | int]] | list[int | list[bytes]] | list[int | list[int]]
)


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
            brief=payload.get("brief") if isinstance(payload.get("brief"), dict) else None,
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


@dataclass(slots=True)
class FleetWorkbenchState:
    all_items: list[FleetItem] = field(default_factory=list)
    items: list[FleetItem] = field(default_factory=list)
    selected_index: int = 0
    selected_operation_payload: dict[str, object] | None = None
    selected_fleet_brief: dict[str, object] | None = None
    project: str | None = None
    total_operations: int = 0
    last_message: str | None = None
    pending_confirmation: str | None = None
    pending_answer_operation_id: str | None = None
    pending_answer_attention_id: str | None = None
    pending_answer_task_id: str | None = None
    pending_answer_blocking: bool = True
    pending_answer_text: str = ""
    pending_answer_prompt: str = "Answer text: "
    attention_picker_active: bool = False
    attention_picker_operation_id: str | None = None
    attention_picker_task_id: str | None = None
    attention_picker_index: int = 0
    help_overlay_active: bool = False
    view_level: str = "fleet"
    selected_task_index: int = 0
    operation_panel_mode: str = "detail"
    task_filter_query: str = ""
    pending_task_filter_text: str | None = None
    pending_task_filter_restore_query: str = ""
    selected_timeline_index: int = 0
    session_panel_mode: str = "timeline"
    session_filter_query: str = ""
    pending_session_filter_text: str | None = None
    pending_session_filter_restore_query: str = ""
    forensic_filter_query: str = ""
    pending_forensic_filter_text: str | None = None
    pending_forensic_filter_restore_query: str = ""
    filter_query: str = ""
    pending_filter_text: str | None = None
    pending_filter_restore_query: str = ""

    @property
    def selected_item(self) -> FleetItem | None:
        if not self.items or self.selected_index < 0 or self.selected_index >= len(self.items):
            return None
        return self.items[self.selected_index]

    @property
    def selected_task(self) -> OperationTaskItem | None:
        tasks = filtered_dashboard_tasks(self.selected_operation_payload, self.task_filter_query)
        if not tasks or self.selected_task_index < 0 or self.selected_task_index >= len(tasks):
            return None
        return tasks[self.selected_task_index]

    @property
    def selected_timeline_event(self) -> TimelineEventItem | None:
        events = filtered_session_timeline_events(
            self.selected_operation_payload,
            self.selected_task,
            self.session_filter_query,
        )
        if (
            not events
            or self.selected_timeline_index < 0
            or self.selected_timeline_index >= len(events)
        ):
            return None
        return events[self.selected_timeline_index]


def payload_items(payload: dict[str, object]) -> list[FleetItem]:
    items: list[FleetItem] = []
    rows = payload.get("rows")
    if isinstance(rows, list):
        for raw_item in rows:
            if isinstance(raw_item, dict):
                items.append(FleetItem.from_payload(raw_item))
        return items
    for bucket in ("needs_attention", "active", "recent"):
        raw_items = payload.get(bucket)
        if not isinstance(raw_items, list):
            continue
        for entry in raw_items:
            if isinstance(entry, dict):
                item = FleetItem.from_payload(entry)
                if item.bucket != bucket:
                    item = FleetItem(
                        operation_id=item.operation_id,
                        attention_badge=item.attention_badge,
                        display_name=item.display_name,
                        state_label=item.state_label,
                        agent_cue=item.agent_cue,
                        recency_brief=item.recency_brief,
                        row_hint=item.row_hint,
                        status=item.status,
                        scheduler_state=item.scheduler_state,
                        objective_brief=item.objective_brief,
                        focus_brief=item.focus_brief,
                        latest_outcome_brief=item.latest_outcome_brief,
                        blocker_brief=item.blocker_brief,
                        runtime_alert=item.runtime_alert,
                        open_attention_count=item.open_attention_count,
                        open_blocking_attention_count=item.open_blocking_attention_count,
                        open_nonblocking_attention_count=item.open_nonblocking_attention_count,
                        attention_briefs=item.attention_briefs,
                        project_profile_name=item.project_profile_name,
                        brief=item.brief,
                        bucket=bucket,
                    )
                items.append(item)
    return items


def filter_fleet_items(items: list[FleetItem], query: str) -> list[FleetItem]:
    normalized = query.strip().lower()
    if not normalized:
        return list(items)
    terms = [term for term in normalized.split() if term]
    if not terms:
        return list(items)
    return [item for item in items if _fleet_item_matches_filter(item, terms)]


def _fleet_item_matches_filter(item: FleetItem, terms: list[str]) -> bool:
    haystack = " ".join(
        value.lower()
        for value in (
            item.operation_id,
            item.display_name,
            item.state_label,
            item.status,
            item.scheduler_state,
            item.agent_cue,
            item.objective_brief,
            item.focus_brief or "",
            item.latest_outcome_brief or "",
            item.blocker_brief or "",
            item.runtime_alert or "",
            item.project_profile_name or "",
            " ".join(item.attention_briefs),
        )
        if value
    )
    return all(term in haystack for term in terms)


def dashboard_tasks(payload: dict[str, object] | None) -> list[OperationTaskItem]:
    if not isinstance(payload, dict):
        return []
    raw_tasks = payload.get("tasks")
    if not isinstance(raw_tasks, list):
        return []
    return [OperationTaskItem.from_payload(item) for item in raw_tasks if isinstance(item, dict)]


def filtered_dashboard_tasks(
    payload: dict[str, object] | None,
    query: str,
) -> list[OperationTaskItem]:
    tasks = dashboard_tasks(payload)
    normalized = query.strip().lower()
    if not normalized:
        return tasks
    terms = [term for term in normalized.split() if term]
    if not terms:
        return tasks
    return [task for task in tasks if _task_matches_filter(task, terms)]


def _task_matches_filter(task: OperationTaskItem, terms: list[str]) -> bool:
    haystack = " ".join(
        value.lower()
        for value in (
            task.task_id,
            task.task_short_id,
            task.title,
            task.goal,
            task.definition_of_done,
            task.status,
            task.assigned_agent or "",
            " ".join(task.notes),
        )
        if value
    )
    return all(term in haystack for term in terms)


def session_timeline_events(
    payload: dict[str, object] | None, task: OperationTaskItem | None
) -> list[TimelineEventItem]:
    session_view = selected_session_view(payload, task)
    if session_view is not None:
        raw_events = session_view.get("timeline")
        if isinstance(raw_events, list):
            return [
                TimelineEventItem.from_payload(item)
                for item in raw_events
                if isinstance(item, dict)
            ]
    if not isinstance(payload, dict):
        return []
    raw_events = payload.get("timeline_events")
    if not isinstance(raw_events, list):
        return []
    session_id = task.linked_session_id if task is not None else None
    task_id = task.task_id if task is not None else None
    events = [TimelineEventItem.from_payload(item) for item in raw_events if isinstance(item, dict)]
    if session_id is None and task_id is None:
        return events
    filtered = [item for item in events if item.session_id == session_id or item.task_id == task_id]
    return filtered or events


def filtered_session_timeline_events(
    payload: dict[str, object] | None,
    task: OperationTaskItem | None,
    query: str,
) -> list[TimelineEventItem]:
    events = session_timeline_events(payload, task)
    normalized = query.strip().lower()
    if not normalized:
        return events
    terms = [term for term in normalized.split() if term]
    if not terms:
        return events
    return [event for event in events if _timeline_event_matches_filter(event, terms)]


def _timeline_event_matches_filter(event: TimelineEventItem, terms: list[str]) -> bool:
    haystack = " ".join(
        value.lower()
        for value in (
            event.event_type,
            event.summary,
            event.task_id or "",
            event.session_id or "",
            str(event.iteration),
        )
        if value
    )
    return all(term in haystack for term in terms)


def session_brief(
    payload: dict[str, object] | None, task: OperationTaskItem | None
) -> dict[str, str]:
    session_view = selected_session_view(payload, task)
    if session_view is not None:
        brief = session_view.get("session_brief")
        if isinstance(brief, dict):
            return {
                "now": optional_text(brief.get("now")) or "-",
                "wait": optional_text(brief.get("wait")) or "-",
                "attention": optional_text(brief.get("attention")) or "-",
                "latest_output": optional_text(brief.get("latest_output")) or "-",
            }
    if not isinstance(payload, dict):
        return {"now": "-", "wait": "-", "attention": "-", "latest_output": "-"}
    session = selected_session(payload, task)
    attention_titles = task_attention_titles(payload, task) if task is not None else []
    wait = optional_text(session.get("waiting_reason")) if session is not None else None
    status = optional_text(session.get("status")) if session is not None else None
    now = _session_now_text(status, wait)
    latest_output = _session_latest_output(payload, task)
    return {
        "now": now,
        "wait": wait or (status or "-"),
        "attention": "; ".join(attention_titles[:2]) if attention_titles else "-",
        "latest_output": latest_output,
    }


def selected_session(
    payload: dict[str, object] | None,
    task: OperationTaskItem | None,
) -> dict[str, object] | None:
    session_view = selected_session_view(payload, task)
    if session_view is not None:
        session = session_view.get("session")
        if isinstance(session, dict):
            return session
    if not isinstance(payload, dict) or task is None or task.linked_session_id is None:
        return None
    raw_sessions = payload.get("sessions")
    if not isinstance(raw_sessions, list):
        return None
    for item in raw_sessions:
        if not isinstance(item, dict):
            continue
        if optional_text(item.get("session_id")) == task.linked_session_id:
            return item
    return None


def selected_session_view(
    payload: dict[str, object] | None,
    task: OperationTaskItem | None,
) -> dict[str, object] | None:
    if not isinstance(payload, dict) or task is None:
        return None
    raw_views = payload.get("session_views")
    if not isinstance(raw_views, list):
        return None
    for item in raw_views:
        if not isinstance(item, dict):
            continue
        if optional_text(item.get("task_id")) == task.task_id:
            return item
    return None


def session_identity_text(payload: dict[str, object] | None, task: OperationTaskItem | None) -> str:
    session = selected_session(payload, task)
    if session is None:
        return "Session: -"
    adapter = optional_text(session.get("adapter_key")) or "-"
    session_id = optional_text(session.get("session_id")) or "-"
    status = optional_text(session.get("status")) or "-"
    wait = optional_text(session.get("waiting_reason"))
    summary = f"Session: {adapter} · {session_id} · {status}"
    if wait is not None:
        summary += f" · {wait}"
    return summary


def session_event_label(event: TimelineEventItem) -> str:
    event_type = event.event_type
    if event_type == "agent.invocation.started":
        return "agent started"
    if event_type == "agent.invocation.completed":
        return "agent completed"
    if event_type.startswith("agent."):
        return "agent event"
    if event_type.startswith("brain."):
        return "brain decision"
    if "attention" in event_type:
        return "attention"
    if "session" in event_type:
        return "session event"
    if "task" in event_type:
        return "task event"
    return event_type.replace(".", " ")


def session_event_glyph(event: TimelineEventItem) -> str:
    event_type = event.event_type
    if event_type.startswith("agent."):
        return ">"
    if event_type.startswith("brain."):
        return "*"
    if "attention" in event_type:
        return "!"
    if "session" in event_type:
        return ">"
    if "task" in event_type:
        return "+"
    return "-"


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


def status_text(item: FleetItem) -> str:
    return item.state_label


def signal_text(item: FleetItem) -> str:
    if item.attention_badge == "-" or item.attention_badge == "":
        return "-"
    if item.attention_badge.startswith("B"):
        return f"[!!{item.attention_badge.removeprefix('B')}]"
    if item.attention_badge.startswith("Q"):
        return f"[!{item.attention_badge.removeprefix('Q')}]"
    if item.attention_badge.startswith("A"):
        return f"[~{item.attention_badge.removeprefix('A')}]"
    if item.attention_badge == "!!":
        return "[!! alert]"
    return "-"


def task_lane(task: OperationTaskItem) -> str:
    if task.status == "running":
        return "RUNNING"
    if task.status == "completed":
        return "COMPLETED"
    if task.status == "failed":
        return "FAILED"
    if task.status == "cancelled":
        return "CANCELLED"
    if task.dependencies:
        return "BLOCKED"
    return "READY"


def task_session_summary(payload: dict[str, object], task: OperationTaskItem) -> str | None:
    raw_sessions = payload.get("sessions")
    if not isinstance(raw_sessions, list):
        return None
    for session in raw_sessions:
        if not isinstance(session, dict):
            continue
        if optional_text(session.get("session_id")) != task.linked_session_id:
            continue
        adapter = optional_text(session.get("adapter_key")) or "-"
        status = optional_text(session.get("status")) or "-"
        waiting = optional_text(session.get("waiting_reason"))
        summary = f"{adapter} [{status}]"
        if waiting is not None:
            summary += f" waiting={waiting}"
        return summary
    return None


@dataclass(frozen=True, slots=True)
class AttentionSummary:
    attention_id: str
    attention_type: str
    blocking: bool
    target_scope: str | None
    target_id: str | None
    title: str
    question: str | None
    created_at: datetime | None


def task_signal_text(payload: dict[str, object], task: OperationTaskItem) -> str:
    attentions = _task_attention(payload, task.task_id)
    blocking = sum(1 for item in attentions if item.blocking)
    if blocking:
        return f"[!!{blocking}]"
    if attentions:
        return f"[!{len(attentions)}]"
    return "-"


def oldest_task_blocking_attention(
    payload: dict[str, object],
    task_id: str | None,
) -> AttentionSummary | None:
    attentions = [
        item
        for item in _operation_attentions(payload)
        if item.target_id == task_id and item.blocking
    ]
    if not attentions:
        return None
    return sorted(attentions, key=_attention_sort_key)[0]


def oldest_task_nonblocking_attention(
    payload: dict[str, object],
    task_id: str | None,
) -> AttentionSummary | None:
    attentions = [
        item
        for item in _operation_attentions(payload)
        if item.target_id == task_id and not item.blocking
    ]
    if not attentions:
        return None
    return sorted(attentions, key=_attention_sort_key)[0]


def oldest_blocking_attention(payload: dict[str, object]) -> AttentionSummary | None:
    attentions = [item for item in _operation_attentions(payload) if item.blocking]
    if not attentions:
        return None
    return sorted(attentions, key=_attention_sort_key)[0]


def oldest_nonblocking_attention(payload: dict[str, object]) -> AttentionSummary | None:
    attentions = [item for item in _operation_attentions(payload) if not item.blocking]
    if not attentions:
        return None
    return sorted(attentions, key=_attention_sort_key)[0]


def oldest_operation_blocking_attention(
    payload: dict[str, object],
    *,
    operation_id: str,
) -> AttentionSummary | None:
    attentions = [
        item
        for item in _operation_attentions(payload)
        if item.blocking
        and (item.target_scope == "operation" or item.target_id in {None, operation_id})
    ]
    if not attentions:
        return None
    return sorted(attentions, key=_attention_sort_key)[0]


def task_scope_attentions(
    payload: dict[str, object],
    *,
    task_id: str | None,
) -> list[AttentionSummary]:
    attentions = [item for item in _operation_attentions(payload) if item.target_id == task_id]
    return sorted(attentions, key=_attention_sort_key)


def operation_scope_attentions(
    payload: dict[str, object],
    *,
    operation_id: str,
) -> list[AttentionSummary]:
    _ = operation_id
    attentions = list(_operation_attentions(payload))
    return sorted(attentions, key=_attention_sort_key)


def tasks_with_blocking_attention(
    payload: dict[str, object],
    tasks: list[OperationTaskItem],
) -> set[str]:
    result: set[str] = set()
    for task in tasks:
        for item in _task_attention(payload, task.task_id):
            if item.blocking:
                result.add(task.task_id)
                break
    return result


def task_attention_titles(payload: dict[str, object], task: OperationTaskItem) -> list[str]:
    return [item.title for item in _task_attention(payload, task.task_id) if item.title is not None]


def _operation_attentions(payload: dict[str, object]) -> tuple[AttentionSummary, ...]:
    if not isinstance(payload, dict):
        return ()
    raw_attention = payload.get("attention")
    if not isinstance(raw_attention, list):
        return ()
    items: list[AttentionSummary] = []
    for raw_item in raw_attention:
        if not isinstance(raw_item, dict):
            continue
        attention_id = optional_text(raw_item.get("attention_id"))
        if attention_id is None:
            continue
        attention_type = optional_text(raw_item.get("attention_type"))
        if attention_type is None:
            continue
        items.append(
            AttentionSummary(
                attention_id=attention_id,
                attention_type=attention_type,
                blocking=bool(raw_item.get("blocking")),
                target_scope=optional_text(raw_item.get("target_scope")),
                target_id=optional_text(raw_item.get("target_id")),
                title=optional_text(raw_item.get("title")) or "",
                question=optional_text(raw_item.get("question")),
                created_at=_parse_datetime(raw_item.get("created_at")),
            )
        )
    return tuple(items)


def _task_attention(payload: dict[str, object], task_id: str) -> tuple[AttentionSummary, ...]:
    return tuple(item for item in _operation_attentions(payload) if item.target_id == task_id)


def _attention_sort_key(item: AttentionSummary) -> tuple[datetime, str]:
    return (_stable_dt(item.created_at), item.attention_id)


def _parse_datetime(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _stable_dt(value: datetime | None) -> datetime:
    return value if value is not None else datetime.max


def filtered_decisions(
    payload: dict[str, object] | None, task: OperationTaskItem | None
) -> list[str]:
    if not isinstance(payload, dict):
        return []
    raw_decisions = payload.get("decision_memos")
    if not isinstance(raw_decisions, list):
        return []
    entries: list[str] = []
    for item in raw_decisions:
        if not isinstance(item, dict):
            continue
        task_id = optional_text(item.get("task_id"))
        if task is not None and task_id not in {None, task.task_id}:
            continue
        iteration = optional_int(item.get("iteration"))
        chosen_action = optional_text(item.get("chosen_action")) or "-"
        rationale = optional_text(item.get("rationale")) or "-"
        context = optional_text(item.get("decision_context_summary"))
        parts = [f"iter {iteration}: {chosen_action}"]
        if context is not None:
            parts.append(f"context: {context}")
        parts.append(f"why: {rationale}")
        entries.append("\n".join(parts))
    return entries


def filtered_memory_entries(
    payload: dict[str, object] | None, task: OperationTaskItem | None
) -> list[str]:
    if not isinstance(payload, dict):
        return []
    raw_entries = payload.get("memory_entries")
    if not isinstance(raw_entries, list):
        return []
    rendered: list[str] = []
    for item in raw_entries:
        if not isinstance(item, dict):
            continue
        scope_id = optional_text(item.get("scope_id"))
        memory_id = optional_text(item.get("memory_id")) or "-"
        freshness = optional_text(item.get("freshness")) or "-"
        scope = optional_text(item.get("scope")) or "-"
        summary = optional_text(item.get("summary")) or "-"
        if (
            task is not None
            and scope_id not in {None, task.task_id}
            and memory_id not in task.memory_refs
        ):
            continue
        rendered.append(f"{memory_id} [{scope}/{freshness}]\n{summary}")
    return rendered


def raw_transcript_lines(payload: dict[str, object] | None) -> list[str]:
    if not isinstance(payload, dict):
        return []
    transcript = payload.get("upstream_transcript")
    if isinstance(transcript, dict):
        events = transcript.get("events")
        if isinstance(events, list):
            return [str(item) for item in events if isinstance(item, str)]
    codex_log = payload.get("codex_log")
    if isinstance(codex_log, list):
        return [str(item) for item in codex_log if isinstance(item, str)]
    return []


def filtered_raw_transcript_lines(payload: dict[str, object] | None, query: str) -> list[str]:
    lines = raw_transcript_lines(payload)
    normalized = query.strip().lower()
    if not normalized:
        return lines
    terms = [term for term in normalized.split() if term]
    if not terms:
        return lines
    return [line for line in lines if all(term in line.lower() for term in terms)]


def event_detail_lines(event: TimelineEventItem | None) -> list[tuple[str, str]]:
    if event is None:
        return [("Selected Event", "No event selected.")]
    rows = [
        ("Selected Event", session_event_label(event)),
        ("Iteration", str(event.iteration)),
        ("Source", event.session_id or "-"),
        ("Summary", event.summary),
    ]
    if event.task_id is not None:
        rows.insert(2, ("Task", event.task_id))
    return rows


def _session_now_text(status: str | None, wait: str | None) -> str:
    if wait is not None:
        lowered = wait.lower()
        if "working" in lowered or "running" in lowered:
            return wait
    if status is None:
        return "-"
    if status == "running":
        return "Agent turn running"
    return status


def _session_latest_output(payload: dict[str, object], task: OperationTaskItem | None) -> str:
    events = session_timeline_events(payload, task)
    for event in reversed(events):
        if event.summary and event.summary != "-":
            return event.summary
    lines = raw_transcript_lines(payload)
    if lines:
        return lines[-1]
    return "-"


def normalize_key(key: str) -> str:
    if key == "\x1b[A":
        return "up"
    if key == "\x1b[B":
        return "down"
    if key == "\x1b":
        return "esc"
    if key == "\t":
        return "tab"
    if key == "\x03":
        return "ctrl+c"
    if key == "\r":
        return "enter"
    return key.lower()
