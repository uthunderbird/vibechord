from __future__ import annotations

from pathlib import Path

import anyio
import typer

from agent_operator.bootstrap import build_store
from agent_operator.config import OperatorSettings
from agent_operator.domain import OperationState, ProjectProfile
from agent_operator.runtime import (
    discover_local_project_profile,
    load_project_profile,
    prepare_operator_settings,
    profile_path,
)


def _load_settings() -> OperatorSettings:
    return prepare_operator_settings(OperatorSettings())


async def resolve_operation_id_async(operation_ref: str) -> str:
    settings = _load_settings()
    store = build_store(settings)
    summaries = await store.list_operations()
    event_sourced_ids = _list_event_sourced_operation_ids(settings)
    if operation_ref == "last":
        if not summaries and not event_sourced_ids:
            raise typer.BadParameter("No persisted operations were found.")
        states: list[OperationState] = []
        for summary in summaries:
            operation = await store.load_operation(summary.operation_id)
            if operation is not None:
                states.append(operation)
        if not states and event_sourced_ids:
            return event_sourced_ids[-1]
        if not states:
            raise typer.BadParameter("No persisted operations were found.")
        latest = max(states, key=lambda item: item.created_at)
        if event_sourced_ids:
            latest_event_sourced = _event_sourced_operation_path(settings, event_sourced_ids[-1])
            latest_mtime = latest_event_sourced.stat().st_mtime
            legacy_path = settings.data_dir / "runs" / f"{latest.operation_id}.json"
            if legacy_path.exists() and latest_mtime > legacy_path.stat().st_mtime:
                return event_sourced_ids[-1]
        return latest.operation_id
    exact = next(
        (item.operation_id for item in summaries if item.operation_id == operation_ref), None
    )
    if exact is not None:
        return exact
    if operation_ref in event_sourced_ids:
        return operation_ref
    matches = [
        item.operation_id for item in summaries if item.operation_id.startswith(operation_ref)
    ]
    matches.extend(item for item in event_sourced_ids if item.startswith(operation_ref))
    matches = sorted(set(matches))
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        rendered_matches = ", ".join(sorted(matches))
        message = (
            f"Operation reference {operation_ref!r} is ambiguous. "
            f"Matches: {rendered_matches}"
        )
        raise typer.BadParameter(
            message
        )
    raise typer.BadParameter(f"Operation {operation_ref!r} was not found.")


def resolve_operation_id(operation_ref: str) -> str:
    return anyio.run(resolve_operation_id_async, operation_ref)


def _event_sourced_operation_path(settings: OperatorSettings, operation_id: str) -> Path:
    return settings.data_dir / "operation_events" / f"{operation_id}.jsonl"


def _list_event_sourced_operation_ids(settings: OperatorSettings) -> list[str]:
    event_dir = settings.data_dir / "operation_events"
    if not event_dir.exists():
        return []
    paths = [path for path in event_dir.glob("*.jsonl") if path.is_file()]
    paths.sort(key=lambda path: (path.stat().st_mtime, path.name))
    return [path.stem for path in paths]


def resolve_history_entry(
    operation_ref: str, entries: list[dict[str, object]]
) -> dict[str, object]:
    if not entries:
        raise typer.BadParameter("No committed history entries were found.")
    if operation_ref == "last":
        return entries[-1]
    exact_matches = [item for item in entries if item.get("op_id") == operation_ref]
    if exact_matches:
        return exact_matches[-1]
    prefix_matches = []
    for item in entries:
        op_id = item.get("op_id")
        if isinstance(op_id, str) and op_id.startswith(operation_ref):
            prefix_matches.append(item)
    unique_ids = sorted({str(item["op_id"]) for item in prefix_matches})
    if len(unique_ids) == 1:
        for item in reversed(entries):
            if item.get("op_id") == unique_ids[0]:
                return item
    if len(unique_ids) > 1:
        raise typer.BadParameter(
            f"Operation reference {operation_ref!r} is ambiguous in committed history: "
            + ", ".join(unique_ids[:5])
            + ("..." if len(unique_ids) > 5 else "")
        )
    raise typer.BadParameter(
        f"Operation reference {operation_ref!r} was not found in committed history."
    )


def resolve_project_profile_selection(
    settings: OperatorSettings,
    *,
    name: str | None,
) -> tuple[ProjectProfile | None, Path | None, str | None]:
    if name is not None:
        return load_project_profile(settings, name), profile_path(settings, name), "explicit_cli"
    selection = discover_local_project_profile(settings)
    return selection.profile, selection.path, selection.source
