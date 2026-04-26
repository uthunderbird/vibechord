from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from .model_types import OperationTaskItem, optional_text


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
    return _oldest_matching_attention(
        payload,
        lambda item: item.target_id == task_id and item.blocking,
    )


def oldest_task_nonblocking_attention(
    payload: dict[str, object],
    task_id: str | None,
) -> AttentionSummary | None:
    return _oldest_matching_attention(
        payload,
        lambda item: item.target_id == task_id and not item.blocking,
    )


def oldest_blocking_attention(payload: dict[str, object]) -> AttentionSummary | None:
    return _oldest_matching_attention(payload, lambda item: item.blocking)


def oldest_nonblocking_attention(payload: dict[str, object]) -> AttentionSummary | None:
    return _oldest_matching_attention(payload, lambda item: not item.blocking)


def oldest_operation_blocking_attention(
    payload: dict[str, object],
    *,
    operation_id: str,
) -> AttentionSummary | None:
    return _oldest_matching_attention(
        payload,
        lambda item: item.blocking
        and (item.target_scope == "operation" or item.target_id in {None, operation_id}),
    )


def task_scope_attentions(
    payload: dict[str, object],
    *,
    task_id: str | None,
) -> list[AttentionSummary]:
    return sorted(
        [item for item in _operation_attentions(payload) if item.target_id == task_id],
        key=_attention_sort_key,
    )


def operation_scope_attentions(
    payload: dict[str, object],
    *,
    operation_id: str,
) -> list[AttentionSummary]:
    _ = operation_id
    return sorted(_operation_attentions(payload), key=_attention_sort_key)


def tasks_with_blocking_attention(
    payload: dict[str, object],
    tasks: list[OperationTaskItem],
) -> set[str]:
    result: set[str] = set()
    for task in tasks:
        if any(item.blocking for item in _task_attention(payload, task.task_id)):
            result.add(task.task_id)
    return result


def task_attention_titles(payload: dict[str, object], task: OperationTaskItem) -> list[str]:
    return [item.title for item in _task_attention(payload, task.task_id) if item.title is not None]


def _oldest_matching_attention(
    payload: dict[str, object],
    predicate: Callable[[AttentionSummary], bool],
) -> AttentionSummary | None:
    attentions = [item for item in _operation_attentions(payload) if predicate(item)]
    if not attentions:
        return None
    return sorted(attentions, key=_attention_sort_key)[0]


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
        attention_type = optional_text(raw_item.get("attention_type"))
        if attention_id is None or attention_type is None:
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
