from __future__ import annotations

import json
import time
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import typer

from agent_operator.domain import AgentSessionHandle, OperationState
from agent_operator.runtime import (
    find_codex_session_log,
    format_claude_log_event,
    format_codex_log_event,
    iter_claude_log_events,
    iter_codex_log_events,
    load_claude_log_events,
    load_codex_log_events,
)

from .helpers_rendering import shorten_live_text


def resolve_claude_log_path_for_session(session: AgentSessionHandle) -> Path:
    return resolve_jsonl_log_path_for_session(session, provider="Claude")


def resolve_jsonl_log_path_for_session(session: AgentSessionHandle, *, provider: str) -> Path:
    raw_path = session.metadata.get("log_path")
    if not isinstance(raw_path, str) or not raw_path.strip():
        raise typer.BadParameter(f"{provider} log path for session {session.session_id!r} is not available.")
    path = Path(raw_path)
    if not path.exists():
        raise typer.BadParameter(
            f"{provider} log for session {session.session_id!r} was not found at {str(path)!r}."
        )
    return path


def first_non_empty_str(*items: object) -> str | None:
    for item in items:
        if isinstance(item, str) and item.strip():
            return item.strip()
    return None


@dataclass(slots=True)
class OpencodeLogEvent:
    timestamp: str
    category: str
    summary: str
    details: dict[str, Any]


def parse_opencode_log_line(raw: str) -> OpencodeLogEvent | None:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return OpencodeLogEvent(
            timestamp="-",
            category="raw",
            summary=shorten_live_text(raw, limit=120) or "",
            details={"raw": raw},
        )
    if not isinstance(payload, dict):
        return OpencodeLogEvent(
            timestamp="-",
            category="raw",
            summary=shorten_live_text(str(payload), limit=120) or "",
            details={"raw": payload},
        )
    timestamp = str(payload.get("timestamp", "-"))
    category = (
        first_non_empty_str(
            payload.get("type"),
            payload.get("category"),
            payload.get("event"),
            payload.get("kind"),
            payload.get("subtype"),
        )
        or "event"
    )
    summary = (
        first_non_empty_str(
            payload.get("summary"),
            payload.get("message"),
            payload.get("result"),
            payload.get("text"),
            payload.get("content"),
        )
        or shorten_live_text(json.dumps(payload, ensure_ascii=False), limit=120)
        or "-"
    )
    return OpencodeLogEvent(timestamp=timestamp, category=category, summary=summary, details=payload)


def load_opencode_log_events(path: Path) -> list[OpencodeLogEvent]:
    events: list[OpencodeLogEvent] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            raw = line.strip()
            if not raw:
                continue
            parsed = parse_opencode_log_line(raw)
            if parsed is not None:
                events.append(parsed)
    return events


def iter_opencode_log_events(
    path: Path,
    *,
    follow: bool = False,
    poll_interval_seconds: float = 1.0,
) -> Iterator[OpencodeLogEvent]:
    with path.open(encoding="utf-8") as handle:
        while True:
            position = handle.tell()
            line = handle.readline()
            if line:
                parsed = parse_opencode_log_line(line.strip())
                if parsed is not None:
                    yield parsed
                continue
            if not follow:
                break
            handle.seek(position)
            time.sleep(poll_interval_seconds)


def format_opencode_log_event(event: OpencodeLogEvent) -> str:
    return f"{event.timestamp} [{event.category}] {event.summary}"


def resolve_log_target(operation: OperationState, *, agent: str) -> tuple[str, AgentSessionHandle]:
    normalized = agent.strip().lower()
    if normalized not in {"auto", "codex", "claude", "opencode"}:
        raise typer.BadParameter("--agent must be one of: auto, codex, claude, or opencode")
    session_handles = [item.handle for item in operation.sessions]
    if normalized == "claude":
        session = next((item for item in session_handles if item.adapter_key == "claude_acp"), None)
        if session is None:
            raise typer.BadParameter(f"Operation {operation.operation_id!r} does not have a claude_acp session.")
        return "claude", session
    if normalized == "opencode":
        session = next((item for item in session_handles if item.adapter_key in {"opencode", "opencode_acp"}), None)
        if session is None:
            raise typer.BadParameter(f"Operation {operation.operation_id!r} does not have an opencode session.")
        return "opencode", session
    if normalized == "codex":
        session = next((item for item in session_handles if item.adapter_key == "codex_acp"), None)
        if session is None:
            raise typer.BadParameter(f"Operation {operation.operation_id!r} does not have a codex_acp session.")
        return "codex", session
    codex = next((item for item in session_handles if item.adapter_key == "codex_acp"), None)
    if codex is not None:
        return "codex", codex
    claude = next((item for item in session_handles if item.adapter_key == "claude_acp"), None)
    if claude is not None:
        return "claude", claude
    opencode = next((item for item in session_handles if item.adapter_key in {"opencode", "opencode_acp"}), None)
    if opencode is not None:
        return "opencode", opencode
    raise typer.BadParameter(f"Operation {operation.operation_id!r} does not have a transcript-capable session.")


def build_dashboard_upstream_transcript(operation: OperationState, *, codex_home: Path) -> dict[str, object] | None:
    if not operation.sessions:
        return None
    try:
        log_kind, session = resolve_log_target(operation, agent="auto")
    except typer.BadParameter:
        return None
    if log_kind == "codex":
        path = find_codex_session_log(codex_home, session.session_id)
        if path is None:
            return None
        return {
            "title": "Codex Log",
            "events": [format_codex_log_event(event) for event in load_codex_log_events(path)[-30:]],
        }
    if log_kind == "claude":
        path = resolve_claude_log_path_for_session(session)
        return {
            "title": "Claude Log",
            "events": [format_claude_log_event(event) for event in load_claude_log_events(path)[-30:]],
        }
    path = resolve_jsonl_log_path_for_session(session, provider="OpenCode")
    return {
        "title": "OpenCode Log",
        "events": [format_opencode_log_event(event) for event in load_opencode_log_events(path)[-30:]],
    }
