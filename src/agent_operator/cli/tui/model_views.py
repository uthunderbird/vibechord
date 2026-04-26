from __future__ import annotations

from dataclasses import replace

from .model_attention import task_attention_titles
from .model_display import raw_transcript_lines
from .model_types import (
    FleetItem,
    OperationTaskItem,
    TimelineEventItem,
    optional_int,
    optional_text,
    sort_dashboard_tasks,
)


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
            if not isinstance(entry, dict):
                continue
            item = FleetItem.from_payload(entry)
            items.append(replace(item, bucket=bucket) if item.bucket != bucket else item)
    return items


def filter_fleet_items(items: list[FleetItem], query: str) -> list[FleetItem]:
    normalized = query.strip().lower()
    if not normalized:
        return list(items)
    terms = [term for term in normalized.split() if term]
    if not terms:
        return list(items)
    return [item for item in items if _fleet_item_matches_filter(item, terms)]


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
        return sort_dashboard_tasks(tasks)
    terms = [term for term in normalized.split() if term]
    if not terms:
        return sort_dashboard_tasks(tasks)
    return sort_dashboard_tasks([task for task in tasks if _task_matches_filter(task, terms)])


def session_timeline_events(
    payload: dict[str, object] | None,
    task: OperationTaskItem | None,
) -> list[TimelineEventItem]:
    session_view = selected_session_view(payload, task)
    live_feed_events = _live_feed_timeline_events(payload, task)
    permission_events = _permission_timeline_events(payload, task)
    if session_view is not None:
        raw_events = session_view.get("timeline")
        if isinstance(raw_events, list):
            events = live_feed_events or [
                TimelineEventItem.from_payload(item)
                for item in raw_events
                if isinstance(item, dict)
            ]
            events.extend(permission_events)
            return sort_session_timeline_events(_dedupe_timeline_events(events))
    if not isinstance(payload, dict):
        return []
    raw_events = payload.get("timeline_events")
    if not isinstance(raw_events, list):
        raw_events = []
    session_id = task.linked_session_id if task is not None else None
    task_id = task.task_id if task is not None else None
    events = live_feed_events or [
        TimelineEventItem.from_payload(item) for item in raw_events if isinstance(item, dict)
    ]
    events.extend(permission_events)
    if session_id is None and task_id is None:
        return sort_session_timeline_events(_dedupe_timeline_events(events))
    filtered = [item for item in events if item.session_id == session_id or item.task_id == task_id]
    return sort_session_timeline_events(_dedupe_timeline_events(filtered or events))


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


def session_brief(
    payload: dict[str, object] | None,
    task: OperationTaskItem | None,
) -> dict[str, str]:
    session_view = selected_session_view(payload, task)
    if session_view is not None:
        brief = session_view.get("session_brief")
        if isinstance(brief, dict):
            return {
                "now": optional_text(brief.get("now")) or "-",
                "wait": optional_text(brief.get("wait")) or "-",
                "attention": optional_text(brief.get("attention")) or "-",
                "review": optional_text(brief.get("review")) or "-",
                "latest_output": optional_text(brief.get("latest_output")) or "-",
                "agent_activity": optional_text(brief.get("agent_activity")) or "-",
                "operator_state": optional_text(brief.get("operator_state")) or "-",
            }
    if not isinstance(payload, dict):
        return {
            "now": "-",
            "wait": "-",
            "attention": "-",
            "review": "-",
            "latest_output": "-",
            "agent_activity": "-",
            "operator_state": "-",
        }
    session = selected_session(payload, task)
    attention_titles = task_attention_titles(payload, task) if task is not None else []
    runtime_alert = optional_text(payload.get("runtime_alert"))
    wait = (
        None
        if runtime_alert is not None
        else optional_text(session.get("waiting_reason")) if session is not None else None
    )
    status = optional_text(session.get("status")) if session is not None else None
    return {
        "now": _session_now_text(status, wait),
        "wait": runtime_alert or wait or (status or "-"),
        "attention": "; ".join(attention_titles[:2]) if attention_titles else "-",
        "review": "-",
        "latest_output": _session_latest_output(payload, task),
        "agent_activity": (
            f"{optional_text(session.get('adapter_key')) or '-'} session"
            if session is not None
            else "-"
        ),
        "operator_state": "observing" if wait else ("following" if status == "running" else "-"),
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
        if (
            isinstance(item, dict)
            and optional_text(item.get("session_id")) == task.linked_session_id
        ):
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
        if isinstance(item, dict) and optional_text(item.get("task_id")) == task.task_id:
            return item
    return None


def session_identity_text(payload: dict[str, object] | None, task: OperationTaskItem | None) -> str:
    session = selected_session(payload, task)
    if session is None:
        return "Session: -"
    adapter = optional_text(session.get("adapter_key")) or "-"
    session_id = optional_text(session.get("session_id")) or "-"
    status = optional_text(session.get("status")) or "-"
    runtime_alert = (
        optional_text(payload.get("runtime_alert")) if isinstance(payload, dict) else None
    )
    wait = None if runtime_alert is not None else optional_text(session.get("waiting_reason"))
    summary = f"Session: {adapter} · {session_id} · {status}"
    if runtime_alert is not None:
        return summary + f" · {runtime_alert}"
    if wait is not None:
        return summary + f" · {wait}"
    return summary


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
        session_id = optional_text(session.get("session_id")) or task.linked_session_id or "-"
        status = optional_text(session.get("status")) or "-"
        runtime_alert = optional_text(payload.get("runtime_alert"))
        waiting = (
            None
            if runtime_alert is not None
            else optional_text(session.get("waiting_reason"))
        )
        summary = f"{adapter} · {session_id} · Status: {status}"
        if runtime_alert is not None:
            return summary + f" · {runtime_alert}"
        if waiting is not None:
            return summary + f" · {waiting}"
        return summary
    return None


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


def _live_feed_timeline_events(
    payload: dict[str, object] | None,
    task: OperationTaskItem | None,
) -> list[TimelineEventItem]:
    if not isinstance(payload, dict):
        return []
    raw_records = payload.get("live_feed")
    if not isinstance(raw_records, list):
        return []
    task_id = task.task_id if task is not None else None
    session_id = task.linked_session_id if task is not None else None
    events: list[TimelineEventItem] = []
    for raw_record in raw_records:
        if not isinstance(raw_record, dict):
            continue
        if raw_record.get("record_type") == "warning":
            warning_code = optional_text(raw_record.get("warning_code")) or "warning"
            summary = optional_text(raw_record.get("message")) or warning_code
            events.append(
                TimelineEventItem(
                    event_type=f"warning.{warning_code}",
                    iteration=optional_int(raw_record.get("sequence")),
                    task_id=task_id,
                    session_id=session_id,
                    summary=summary,
                )
            )
            continue
        if raw_record.get("record_type") != "event":
            continue
        raw_event = raw_record.get("event")
        if not isinstance(raw_event, dict):
            continue
        event_session_id = optional_text(raw_event.get("session_id"))
        event_task_id = optional_text(raw_event.get("task_id"))
        if session_id is not None and event_session_id not in {None, session_id}:
            continue
        if (
            task_id is not None
            and event_task_id not in {None, task_id}
            and event_session_id is None
        ):
            continue
        event_type = optional_text(raw_event.get("event_type")) or "event"
        events.append(
            TimelineEventItem(
                event_type=event_type,
                iteration=optional_int(raw_event.get("iteration")),
                task_id=event_task_id or task_id,
                session_id=event_session_id or session_id,
                summary=_live_feed_event_summary(event_type, raw_event),
            )
        )
    return events


def _live_feed_event_summary(event_type: str, raw_event: dict[str, object]) -> str:
    payload = raw_event.get("payload")
    payload_dict = payload if isinstance(payload, dict) else {}
    if event_type == "agent.invocation.started":
        adapter_key = optional_text(payload_dict.get("adapter_key")) or "agent"
        session_name = optional_text(payload_dict.get("session_name"))
        summary = f"agent started: {adapter_key}"
        return f"{summary} ({session_name})" if session_name is not None else summary
    if event_type == "agent.invocation.completed":
        status = optional_text(payload_dict.get("status")) or "unknown"
        output_text = optional_text(payload_dict.get("output_text"))
        summary = f"agent completed: {status}"
        return f"{summary} | {output_text}" if output_text is not None else summary
    if event_type == "attention.request.answered":
        attention_id = optional_text(payload_dict.get("attention_id")) or "unknown"
        return f"attention answered: {attention_id}"
    if event_type == "attention.request.created":
        title = optional_text(payload_dict.get("title")) or "attention request"
        return f"attention created: {title}"
    if event_type == "operation.status.changed":
        status = optional_text(payload_dict.get("status")) or "unknown"
        return f"operation status changed: {status}"
    return event_type.replace(".", " ")


def _permission_timeline_events(
    payload: dict[str, object] | None,
    task: OperationTaskItem | None,
) -> list[TimelineEventItem]:
    if not isinstance(payload, dict):
        return []
    raw_events = payload.get("permission_events")
    if not isinstance(raw_events, list):
        durable_truth = payload.get("durable_truth")
        raw_events = (
            durable_truth.get("permission_events") if isinstance(durable_truth, dict) else []
        )
    if not isinstance(raw_events, list):
        return []
    task_session_id = task.linked_session_id if task is not None else None
    events: list[TimelineEventItem] = []
    for index, raw_event in enumerate(raw_events):
        if not isinstance(raw_event, dict):
            continue
        payload_data = raw_event.get("payload")
        payload_dict = payload_data if isinstance(payload_data, dict) else {}
        session_id = optional_text(payload_dict.get("session_id"))
        if task_session_id is not None and session_id not in {None, task_session_id}:
            continue
        event_type = optional_text(raw_event.get("event_type")) or "permission.request"
        events.append(
            TimelineEventItem(
                event_type=event_type,
                iteration=optional_int(raw_event.get("sequence")),
                task_id=(
                    task.task_id
                    if task is not None
                    else optional_text(payload_dict.get("task_id"))
                ),
                session_id=session_id,
                summary=_permission_timeline_summary(
                    event_type,
                    payload_dict,
                    fallback_index=index,
                ),
            )
        )
    return events


def _permission_timeline_summary(
    event_type: str,
    payload: dict[object, object],
    *,
    fallback_index: int,
) -> str:
    adapter = optional_text(payload.get("adapter_key"))
    session = optional_text(payload.get("session_id"))
    prefix = "permission request"
    if adapter is not None:
        prefix += f" for {adapter}"
    if session is not None:
        prefix += f" session={session}"
    if event_type == "permission.request.decided":
        decision = optional_text(payload.get("decision")) or "decided"
        source = optional_text(payload.get("decision_source"))
        return f"{prefix} {decision}" + (f" via {source}" if source is not None else "")
    if event_type == "permission.request.escalated":
        rationale = optional_text(payload.get("rationale")) or optional_text(
            payload.get("escalation_rationale")
        )
        return f"{prefix} escalated" + (f": {rationale}" if rationale is not None else "")
    if event_type == "permission.request.followup_required":
        reason = optional_text(payload.get("required_followup_reason"))
        return f"{prefix} follow-up required" + (f": {reason}" if reason is not None else "")
    if event_type == "permission.request.observed":
        return f"{prefix} observed"
    return f"{prefix} event {fallback_index + 1}"


def _dedupe_timeline_events(events: list[TimelineEventItem]) -> list[TimelineEventItem]:
    seen: set[tuple[str, int, str | None, str | None, str]] = set()
    deduped: list[TimelineEventItem] = []
    for event in events:
        key = (event.event_type, event.iteration, event.task_id, event.session_id, event.summary)
        if key not in seen:
            seen.add(key)
            deduped.append(event)
    return deduped


def sort_session_timeline_events(events: list[TimelineEventItem]) -> list[TimelineEventItem]:
    indexed = list(enumerate(events))
    indexed.sort(key=lambda item: (-item[1].iteration, -item[0]))
    return [event for _, event in indexed]


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


def _session_now_text(status: str | None, wait: str | None) -> str:
    if wait is not None:
        lowered = wait.lower()
        if "working" in lowered or "running" in lowered:
            return wait
    if status is None:
        return "-"
    return "Agent turn running" if status == "running" else status


def _session_latest_output(payload: dict[str, object], task: OperationTaskItem | None) -> str:
    events = session_timeline_events(payload, task)
    for event in reversed(events):
        if event.summary and event.summary != "-":
            return event.summary
    lines = raw_transcript_lines(payload)
    return lines[-1] if lines else "-"
