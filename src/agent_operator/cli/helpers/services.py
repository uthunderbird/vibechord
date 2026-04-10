from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

import typer

from agent_operator.application import (
    OperationAgendaQueryService,
    OperationDashboardQueryService,
    OperationDeliveryCommandService,
    OperationFleetWorkbenchQueryService,
    OperationProjectDashboardQueryService,
    OperationStatusQueryService,
)
from agent_operator.bootstrap import (
    build_background_run_inspection_store,
    build_command_inbox,
    build_event_sink,
    build_policy_store,
    build_store,
    build_trace_store,
    build_wakeup_inbox,
)
from agent_operator.bootstrap import (
    build_service as bootstrap_build_service,
)
from agent_operator.config import OperatorSettings
from agent_operator.domain import (
    ProjectProfile,
)
from agent_operator.runtime import (
    ProjectingEventSink,
    committed_default_profile_path,
    resolve_operator_data_dir,
)

from .logs import build_dashboard_upstream_transcript
from .rendering import (
    PROJECTIONS,
    build_runtime_alert,
    find_task_by_display_id,
    overlay_live_background_progress,
    render_inspect_summary,
    render_status_brief,
)

if TYPE_CHECKING:
    from collections.abc import Callable


def _current_build_service():
    try:
        import agent_operator.cli.main as cli_main

        return getattr(cli_main, "build_service", bootstrap_build_service)
    except Exception:
        return bootstrap_build_service


def load_settings() -> OperatorSettings:
    settings = OperatorSettings()
    settings.data_dir = resolve_operator_data_dir(settings).path
    return settings


def load_settings_with_data_dir() -> tuple[OperatorSettings, str]:
    settings = OperatorSettings()
    data_dir = resolve_operator_data_dir(settings)
    settings.data_dir = data_dir.path
    return settings, data_dir.source


def delivery_commands_service() -> OperationDeliveryCommandService:
    settings = load_settings()
    return build_delivery_commands_service(settings)


def build_agenda_query_service(settings: OperatorSettings) -> OperationAgendaQueryService:
    return OperationAgendaQueryService(
        store=build_store(settings),
        status_service=build_status_query_service(settings),
    )


def build_project_dashboard_query_service(
    settings: OperatorSettings,
) -> OperationProjectDashboardQueryService:
    return OperationProjectDashboardQueryService(
        agenda_queries=build_agenda_query_service(settings),
        projection_service=PROJECTIONS,
        policy_store=build_policy_store(settings),
    )


def build_fleet_workbench_query_service(
    settings: OperatorSettings,
) -> OperationFleetWorkbenchQueryService:
    return OperationFleetWorkbenchQueryService(
        agenda_queries=build_agenda_query_service(settings),
        projection_service=PROJECTIONS,
    )


def build_operation_dashboard_query_service(
    settings: OperatorSettings,
    *,
    operation_id: str,
    codex_home: Path,
) -> OperationDashboardQueryService:
    return OperationDashboardQueryService(
        status_service=build_status_query_service(settings),
        projection_service=PROJECTIONS,
        command_inbox=build_command_inbox(settings),
        event_reader=build_event_sink(settings, operation_id),
        trace_store=build_trace_store(settings),
        build_upstream_transcript=lambda operation: build_dashboard_upstream_transcript(
            operation,
            codex_home=codex_home,
        ),
    )


def build_delivery_commands_service(
    settings: OperatorSettings,
    *,
    service_factory: Callable[[], object] | None = None,
) -> OperationDeliveryCommandService:
    factory = service_factory or (lambda: _current_build_service()(settings))
    return OperationDeliveryCommandService(
        store=build_store(settings),
        command_inbox=build_command_inbox(settings),
        service_factory=factory,
        find_task_by_display_id=find_task_by_display_id,
    )


def build_status_query_service(settings: OperatorSettings) -> OperationStatusQueryService:
    return OperationStatusQueryService(
        store=build_store(settings),
        projection_service=PROJECTIONS,
        trace_store=build_trace_store(settings),
        background_inspection_store=build_background_run_inspection_store(settings),
        wakeup_inspection_store=build_wakeup_inbox(settings),
        overlay_live_background_progress=overlay_live_background_progress,
        build_runtime_alert=build_runtime_alert,
        render_status_brief=render_status_brief,
        render_inspect_summary=render_inspect_summary,
    )


def build_projecting_delivery_commands_service(
    settings: OperatorSettings,
    *,
    operation_id: str | None,
    projector,
) -> OperationDeliveryCommandService:
    return build_delivery_commands_service(
        settings,
        service_factory=lambda: _current_build_service()(
            settings,
            event_sink=ProjectingEventSink(
                build_event_sink(settings, operation_id),
                projector.handle_event,
            ),
        ),
    )


def build_projected_service(
    settings: OperatorSettings,
    *,
    operation_id: str | None,
    projector,
):
    return _current_build_service()(
        settings,
        event_sink=ProjectingEventSink(
            build_event_sink(settings, operation_id),
            projector.handle_event,
        ),
    )


def emit_free_mode_stub(*, cwd: Path, json_mode: bool) -> None:
    payload = {
        "mode": "free_stub",
        "cwd": str(cwd),
        "message": (
            "No local operator-profile.yaml was found. Project mode is available via "
            "operator-profile.yaml in the launch directory. Freeform live supervision mode "
            "is planned but not implemented yet."
        ),
    }
    if json_mode:
        typer.echo(json.dumps(payload, indent=2, ensure_ascii=False))
        return
    typer.echo(f"# free_mode_stub cwd={cwd}")
    typer.echo(payload["message"])


def normalize_agent_override(*, agent: list[str] | None) -> list[str] | None:
    if agent is None:
        return None
    normalized = [item.strip() for item in agent if item.strip()]
    return normalized or None


def update_gitignore_with_operator_dir(root: Path) -> bool:
    path = root / ".gitignore"
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    lines = existing.splitlines()
    if ".operator/" in lines:
        return False
    if existing and not existing.endswith("\n"):
        existing += "\n"
    existing += ".operator/\n"
    path.write_text(existing, encoding="utf-8")
    return True


def write_default_project_profile(
    *,
    root: Path,
    profile: ProjectProfile,
    force: bool = False,
) -> Path:
    path = committed_default_profile_path(cwd=root)
    if path.exists() and not force:
        raise RuntimeError("Project already configured (operator-profile.yaml found).")
    import yaml  # type: ignore[import-untyped]

    payload = profile.model_dump(mode="json")
    payload = {key: value for key, value in payload.items() if value not in (None, [], {})}
    path.write_text(
        yaml.dump(
            payload,
            sort_keys=False,
            allow_unicode=True,
            default_flow_style=False,
        ),
        encoding="utf-8",
    )
    return path
