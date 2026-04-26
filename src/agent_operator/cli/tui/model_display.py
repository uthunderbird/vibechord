from __future__ import annotations

from .model_types import OperationTaskItem, TimelineEventItem, optional_int, optional_text


def filtered_decisions(
    payload: dict[str, object] | None,
    task: OperationTaskItem | None,
) -> list[str]:
    raw_decisions = payload.get("decision_memos") if isinstance(payload, dict) else None
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
    payload: dict[str, object] | None,
    task: OperationTaskItem | None,
) -> list[str]:
    raw_entries = payload.get("memory_entries") if isinstance(payload, dict) else None
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
    if key == "N":
        return "N"
    return key.lower()


def session_event_label(event: TimelineEventItem) -> str:
    event_type = event.event_type
    if event_type.startswith("warning."):
        return "warning"
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
    if event_type.startswith("warning.") or "attention" in event_type:
        return "!"
    if event_type.startswith("agent.") or "session" in event_type:
        return ">"
    if event_type.startswith("brain."):
        return "*"
    if "task" in event_type:
        return "+"
    return "-"


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
