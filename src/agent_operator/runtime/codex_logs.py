from __future__ import annotations

import json
import time
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class CodexLogEvent:
    timestamp: str
    category: str
    summary: str
    details: dict[str, Any]


def find_codex_session_log(codex_home: Path, session_id: str) -> Path | None:
    sessions_root = codex_home / "sessions"
    if not sessions_root.exists():
        return None
    matches = sorted(
        sessions_root.rglob(f"*{session_id}.jsonl"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    if matches:
        return matches[0]
    return None


def load_codex_log_events(path: Path) -> list[CodexLogEvent]:
    events: list[CodexLogEvent] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            raw = line.strip()
            if not raw:
                continue
            parsed = _parse_codex_log_line(raw)
            if parsed is not None:
                events.append(parsed)
    return events


def iter_codex_log_events(
    path: Path,
    *,
    follow: bool = False,
    poll_interval_seconds: float = 1.0,
) -> Iterator[CodexLogEvent]:
    with path.open(encoding="utf-8") as handle:
        while True:
            position = handle.tell()
            line = handle.readline()
            if line:
                parsed = _parse_codex_log_line(line.strip())
                if parsed is not None:
                    yield parsed
                continue
            if not follow:
                break
            handle.seek(position)
            time.sleep(poll_interval_seconds)


def format_codex_log_event(event: CodexLogEvent) -> str:
    return f"{event.timestamp} [{event.category}] {event.summary}"


def _parse_codex_log_line(raw: str) -> CodexLogEvent | None:
    try:
        item = json.loads(raw)
    except json.JSONDecodeError:
        return None
    timestamp = str(item.get("timestamp", "-"))
    item_type = item.get("type")
    payload = item.get("payload")
    if not isinstance(payload, dict):
        return None
    if item_type == "session_meta":
        session_id = payload.get("id")
        cwd = payload.get("cwd")
        model_provider = payload.get("model_provider")
        return CodexLogEvent(
            timestamp=timestamp,
            category="session",
            summary=(
                f"Session {session_id} started in {cwd}"
                + (f" via {model_provider}" if model_provider else "")
            ),
            details=payload,
        )
    if item_type == "turn_context":
        turn_id = payload.get("turn_id")
        cwd = payload.get("cwd")
        model = payload.get("model")
        approval_policy = payload.get("approval_policy")
        sandbox_policy = payload.get("sandbox_policy")
        sandbox_type = (
            sandbox_policy.get("type") if isinstance(sandbox_policy, dict) else sandbox_policy
        )
        return CodexLogEvent(
            timestamp=timestamp,
            category="turn",
            summary=(
                f"Turn {turn_id} in {cwd}"
                + (f" | model={model}" if model else "")
                + (f" | approval={approval_policy}" if approval_policy else "")
                + (f" | sandbox={sandbox_type}" if sandbox_type else "")
            ),
            details=payload,
        )
    if item_type == "event_msg":
        return _parse_event_msg(timestamp, payload)
    if item_type == "response_item":
        return _parse_response_item(timestamp, payload)
    return None


def _parse_event_msg(timestamp: str, payload: dict[str, Any]) -> CodexLogEvent | None:
    event_type = payload.get("type")
    if event_type == "task_started":
        return CodexLogEvent(
            timestamp=timestamp,
            category="task",
            summary=f"Task started for turn {payload.get('turn_id')}",
            details=payload,
        )
    if event_type == "task_complete":
        message = payload.get("last_agent_message")
        summary = "Task completed"
        if isinstance(message, str) and message:
            summary += f": {_truncate(message)}"
        return CodexLogEvent(
            timestamp=timestamp,
            category="task",
            summary=summary,
            details=payload,
        )
    if event_type == "turn_aborted":
        return CodexLogEvent(
            timestamp=timestamp,
            category="task",
            summary=f"Turn aborted: {payload.get('reason') or 'unknown reason'}",
            details=payload,
        )
    if event_type == "context_compacted":
        return CodexLogEvent(
            timestamp=timestamp,
            category="runtime",
            summary="Context compacted",
            details=payload,
        )
    if event_type == "user_message":
        message = payload.get("message")
        if isinstance(message, str) and message:
            return CodexLogEvent(
                timestamp=timestamp,
                category="user",
                summary=_truncate(message),
                details=payload,
            )
        return None
    if event_type == "agent_message":
        message = payload.get("message")
        phase = payload.get("phase")
        if isinstance(message, str) and message:
            label = f"agent/{phase}" if isinstance(phase, str) and phase else "agent"
            return CodexLogEvent(
                timestamp=timestamp,
                category=label,
                summary=_truncate(message),
                details=payload,
            )
        return None
    return None


def _parse_response_item(timestamp: str, payload: dict[str, Any]) -> CodexLogEvent | None:
    item_type = payload.get("type")
    if item_type == "message":
        role = payload.get("role")
        if role == "user":
            text = _extract_message_text(payload.get("content"))
            if text:
                return CodexLogEvent(
                    timestamp=timestamp,
                    category="user",
                    summary=_truncate(text),
                    details=payload,
                )
        return None
    if item_type in {"function_call", "custom_tool_call"}:
        name = payload.get("name")
        arguments = (
            payload.get("arguments") if item_type == "function_call" else payload.get("input")
        )
        return _parse_tool_call(timestamp, name, arguments, payload)
    if item_type in {"function_call_output", "custom_tool_call_output"}:
        output = payload.get("output")
        if isinstance(output, str):
            failure = _summarize_tool_failure(output)
            if failure is not None:
                return CodexLogEvent(
                    timestamp=timestamp,
                    category="tool-error",
                    summary=failure,
                    details=payload,
                )
        return None
    return None


def _parse_tool_call(
    timestamp: str,
    name: Any,
    arguments: Any,
    payload: dict[str, Any],
) -> CodexLogEvent | None:
    if not isinstance(name, str) or not name:
        return None
    parsed_arguments: dict[str, Any] | None = None
    if isinstance(arguments, str):
        try:
            candidate = json.loads(arguments)
        except json.JSONDecodeError:
            candidate = None
        if isinstance(candidate, dict):
            parsed_arguments = candidate
    elif isinstance(arguments, dict):
        parsed_arguments = arguments
    escalation = False
    summary = f"{name} called"
    if parsed_arguments:
        if name == "exec_command":
            command = parsed_arguments.get("cmd")
            if isinstance(command, str) and command:
                summary = f"exec_command: {_truncate(command, 140)}"
            sandbox_permissions = parsed_arguments.get("sandbox_permissions")
            justification = parsed_arguments.get("justification")
            if sandbox_permissions == "require_escalated":
                escalation = True
                summary = "Escalation requested"
                if isinstance(justification, str) and justification:
                    summary += f": {_truncate(justification, 160)}"
                elif isinstance(command, str) and command:
                    summary += f" via {_truncate(command, 120)}"
        elif name == "write_stdin":
            summary = "write_stdin"
        else:
            summary = f"{name}: {_truncate(json.dumps(parsed_arguments, ensure_ascii=False), 160)}"
    return CodexLogEvent(
        timestamp=timestamp,
        category="escalation" if escalation else "tool",
        summary=summary,
        details=payload,
    )


def _extract_message_text(content: Any) -> str | None:
    if not isinstance(content, list):
        return None
    parts: list[str] = []
    for item in content:
        if not isinstance(item, dict):
            continue
        text = item.get("text")
        if isinstance(text, str) and text:
            parts.append(text)
    if not parts:
        return None
    return "\n".join(parts)


def _summarize_tool_failure(output: str) -> str | None:
    if "Process exited with code 0" in output:
        return None
    first_meaningful: str | None = None
    for line in output.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("Command:"):
            continue
        if stripped.startswith("Chunk ID:"):
            continue
        if stripped.startswith("Wall time:"):
            continue
        if stripped.startswith("Original token count:"):
            continue
        first_meaningful = stripped
        break
    if "Process exited with code" in output:
        exit_line = next(
            (line.strip() for line in output.splitlines() if "Process exited with code" in line),
            "Process exited with non-zero code",
        )
        if first_meaningful is not None:
            return f"{exit_line}: {_truncate(first_meaningful, 160)}"
        return exit_line
    error_markers = ("error", "failed", "Operation not permitted", "No such file")
    if any(marker.lower() in output.lower() for marker in error_markers):
        return _truncate(first_meaningful or output, 180)
    return None


def _truncate(value: str, limit: int = 180) -> str:
    compact = " ".join(value.split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 1] + "…"
