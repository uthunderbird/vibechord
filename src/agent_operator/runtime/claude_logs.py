from __future__ import annotations

import json
import time
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class ClaudeLogEvent:
    timestamp: str
    category: str
    summary: str
    details: dict[str, Any]


def load_claude_log_events(path: Path) -> list[ClaudeLogEvent]:
    events: list[ClaudeLogEvent] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            raw = line.strip()
            if not raw:
                continue
            parsed = _parse_claude_log_line(raw)
            if parsed is not None:
                events.append(parsed)
    return events


def iter_claude_log_events(
    path: Path,
    *,
    follow: bool = False,
    poll_interval_seconds: float = 1.0,
) -> Iterator[ClaudeLogEvent]:
    with path.open(encoding="utf-8") as handle:
        while True:
            position = handle.tell()
            line = handle.readline()
            if line:
                parsed = _parse_claude_log_line(line.strip())
                if parsed is not None:
                    yield parsed
                continue
            if not follow:
                break
            handle.seek(position)
            time.sleep(poll_interval_seconds)


def format_claude_log_event(event: ClaudeLogEvent) -> str:
    return f"{event.timestamp} [{event.category}] {event.summary}"


def _parse_claude_log_line(raw: str) -> ClaudeLogEvent | None:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None

    timestamp = str(payload.get("timestamp", "-"))
    event_type = payload.get("type")

    if event_type == "system":
        return _parse_system_event(timestamp, payload)
    if event_type == "assistant":
        return _parse_assistant_event(timestamp, payload)
    if event_type == "user":
        return _parse_user_event(timestamp, payload)
    if event_type == "tool_use":
        return _parse_tool_use_event(timestamp, payload)
    if event_type == "result":
        return _parse_result_event(timestamp, payload)
    return None


def _parse_system_event(timestamp: str, payload: dict[str, Any]) -> ClaudeLogEvent | None:
    subtype = payload.get("subtype")
    if subtype != "init":
        return None
    cwd = payload.get("cwd")
    model = payload.get("model")
    tools = payload.get("tools")
    summary = f"Session started in {cwd}" if isinstance(cwd, str) and cwd else "Session started"
    if isinstance(model, str) and model:
        summary += f" | model={model}"
    if isinstance(tools, list) and tools:
        summary += f" | tools={len(tools)}"
    return ClaudeLogEvent(
        timestamp=timestamp,
        category="session",
        summary=summary,
        details=payload,
    )


def _parse_assistant_event(timestamp: str, payload: dict[str, Any]) -> ClaudeLogEvent | None:
    text = _extract_text_parts(payload.get("message"))
    if not text:
        return None
    return ClaudeLogEvent(
        timestamp=timestamp,
        category="assistant",
        summary=_truncate(text),
        details=payload,
    )


def _parse_user_event(timestamp: str, payload: dict[str, Any]) -> ClaudeLogEvent | None:
    text = _extract_text_parts(payload.get("message"))
    if not text:
        return None
    return ClaudeLogEvent(
        timestamp=timestamp,
        category="user",
        summary=_truncate(text),
        details=payload,
    )


def _parse_tool_use_event(timestamp: str, payload: dict[str, Any]) -> ClaudeLogEvent | None:
    tool_name = payload.get("name")
    if not isinstance(tool_name, str) or not tool_name:
        return None
    tool_input = payload.get("input")
    summary = f"{tool_name} called"
    category = "tool"
    if tool_name == "Bash" and isinstance(tool_input, dict):
        command = tool_input.get("command")
        if isinstance(command, str) and command:
            summary = f"Bash: {_truncate(command, 140)}"
    elif isinstance(tool_input, dict) and tool_input:
        summary = f"{tool_name}: {_truncate(json.dumps(tool_input, ensure_ascii=False), 160)}"

    if _is_escalation_request(tool_input):
        category = "escalation"
        summary = "Escalation requested"
        justification = _extract_escalation_justification(tool_input)
        if justification:
            summary += f": {_truncate(justification, 160)}"

    return ClaudeLogEvent(
        timestamp=timestamp,
        category=category,
        summary=summary,
        details=payload,
    )


def _parse_result_event(timestamp: str, payload: dict[str, Any]) -> ClaudeLogEvent | None:
    subtype = payload.get("subtype")
    if subtype == "success":
        result = payload.get("result")
        summary = "Task completed"
        if isinstance(result, str) and result:
            summary += f": {_truncate(result)}"
        return ClaudeLogEvent(
            timestamp=timestamp,
            category="task",
            summary=summary,
            details=payload,
        )
    if subtype == "error":
        message = payload.get("error")
        if not isinstance(message, str) or not message:
            message = "unknown error"
        return ClaudeLogEvent(
            timestamp=timestamp,
            category="task-error",
            summary=f"Task failed: {_truncate(message)}",
            details=payload,
        )
    return None


def _extract_text_parts(message: Any) -> str:
    if not isinstance(message, dict):
        return ""
    content = message.get("content")
    if not isinstance(content, list):
        return ""
    parts: list[str] = []
    for item in content:
        if not isinstance(item, dict):
            continue
        if item.get("type") != "text":
            continue
        text = item.get("text")
        if isinstance(text, str) and text:
            parts.append(text)
    return "".join(parts).strip()


def _is_escalation_request(tool_input: Any) -> bool:
    if not isinstance(tool_input, dict):
        return False
    return tool_input.get("with_escalated_permissions") is True


def _extract_escalation_justification(tool_input: Any) -> str | None:
    if not isinstance(tool_input, dict):
        return None
    justification = tool_input.get("justification")
    if isinstance(justification, str) and justification.strip():
        return justification.strip()
    command = tool_input.get("command")
    if isinstance(command, str) and command.strip():
        return command.strip()
    return None


def _truncate(text: str, limit: int = 120) -> str:
    compact = " ".join(text.split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 3].rstrip() + "..."
