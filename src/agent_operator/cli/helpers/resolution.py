from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import anyio
import typer

from agent_operator.application.queries.operation_resolution import OperationResolutionService
from agent_operator.application.queries.operation_state_views import OperationStateViewService
from agent_operator.bootstrap import build_replay_service, build_store
from agent_operator.config import OperatorSettings
from agent_operator.domain import OperationState, ProjectProfile
from agent_operator.runtime import (
    discover_local_project_profile,
    load_project_profile,
    prepare_operator_settings,
    profile_path,
)

if TYPE_CHECKING:
    from agent_operator.application.queries.operation_resolution import ReplayServiceLike


def _load_settings() -> OperatorSettings:
    return prepare_operator_settings(OperatorSettings())


async def resolve_operation_id_async(operation_ref: str) -> str:
    settings = _load_settings()
    try:
        return await _build_resolution_service(settings).resolve_operation_id(operation_ref)
    except RuntimeError as exc:
        raise typer.BadParameter(str(exc)) from exc


def resolve_operation_id(operation_ref: str) -> str:
    return anyio.run(resolve_operation_id_async, operation_ref)


async def list_canonical_operation_states_async(
    settings: OperatorSettings,
) -> list[OperationState]:
    return await _build_resolution_service(settings).list_canonical_operation_states()


def _event_sourced_operation_path(settings: OperatorSettings, operation_id: str) -> Path:
    return settings.data_dir / "operation_events" / f"{operation_id}.jsonl"


def _list_event_sourced_operation_ids(settings: OperatorSettings) -> list[str]:
    return _build_resolution_service(settings).list_event_sourced_operation_ids()


async def _load_event_sourced_operation_state(
    operation_id: str,
    *,
    replay_service: ReplayServiceLike,
    state_view_service: OperationStateViewService,
) -> OperationState | None:
    service = OperationResolutionService(
        store=build_store(_load_settings()),
        replay_service=replay_service,
        event_root=_load_settings().data_dir / "operation_events",
        state_view_service=state_view_service,
    )
    return await service.load_canonical_operation_state(operation_id)


def _build_resolution_service(settings: OperatorSettings) -> OperationResolutionService:
    return OperationResolutionService(
        store=build_store(settings),
        replay_service=build_replay_service(settings),
        event_root=settings.data_dir / "operation_events",
        state_view_service=OperationStateViewService(),
    )


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
