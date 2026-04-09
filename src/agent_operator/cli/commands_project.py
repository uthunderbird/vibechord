from __future__ import annotations

import json
from pathlib import Path

import anyio
import typer

from agent_operator.domain import InvolvementLevel, ProjectProfile
from agent_operator.runtime import list_project_profiles, resolve_project_run_config, write_project_profile

from .app import project_app
from .helpers_services import load_settings, load_settings_with_data_dir
from .helpers_resolution import resolve_project_profile_selection
from .options import (
    PROJECT_AGENT_OPTION,
    PROJECT_CWD_OPTION,
    PROJECT_FORCE_OPTION,
    PROJECT_HARNESS_OPTION,
    PROJECT_INVOLVEMENT_OPTION,
    PROJECT_MAX_ITERATIONS_OPTION,
    PROJECT_OBJECTIVE_OPTION,
    PROJECT_PATH_OPTION,
    PROJECT_SUCCESS_CRITERION_OPTION,
    WATCH_POLL_INTERVAL_OPTION,
)
from .workflows import project_dashboard_async


@project_app.command("list")
def project_list() -> None:
    settings = load_settings()
    for name in list_project_profiles(settings):
        typer.echo(name)


@project_app.command("create")
def project_create(
    name: str,
    cwd: Path | None = PROJECT_CWD_OPTION,
    path: list[Path] | None = PROJECT_PATH_OPTION,
    agent: list[str] | None = PROJECT_AGENT_OPTION,
    objective: str | None = PROJECT_OBJECTIVE_OPTION,
    harness: str | None = PROJECT_HARNESS_OPTION,
    success_criterion: list[str] | None = PROJECT_SUCCESS_CRITERION_OPTION,
    max_iterations: int | None = PROJECT_MAX_ITERATIONS_OPTION,
    involvement: InvolvementLevel | None = PROJECT_INVOLVEMENT_OPTION,
    local: bool = typer.Option(False, "--local", help="Write the profile to .operator/profiles instead of operator-profiles."),
    force: bool = PROJECT_FORCE_OPTION,
    json_mode: bool = typer.Option(False, "--json"),
) -> None:
    settings = load_settings()
    profile = ProjectProfile(
        name=name,
        cwd=cwd or Path.cwd(),
        paths=list(path or []),
        default_objective=objective,
        default_agents=list(agent or []),
        default_harness_instructions=harness,
        default_success_criteria=list(success_criterion or []),
        default_max_iterations=max_iterations,
        default_involvement_level=involvement,
    )
    try:
        profile_path = write_project_profile(settings, profile, force=force, local=local)
    except RuntimeError as exc:
        raise typer.BadParameter(str(exc)) from exc
    payload = {
        "profile_path": str(profile_path),
        "profile_scope": "local" if local else "committed",
        "profile": profile.model_dump(mode="json"),
    }
    if json_mode:
        typer.echo(json.dumps(payload, indent=2, ensure_ascii=False))
        return
    typer.echo(f"Wrote project profile: {profile_path}")


@project_app.command("inspect")
def project_inspect(
    name: str | None = typer.Argument(None),
    json_mode: bool = typer.Option(False, "--json"),
) -> None:
    settings, _ = load_settings_with_data_dir()
    try:
        profile, _, _ = resolve_project_profile_selection(settings, name=name)
    except RuntimeError as exc:
        raise typer.BadParameter(str(exc)) from exc
    if profile is None:
        raise typer.BadParameter("No local operator-profile.yaml was found.")
    typer.echo(json.dumps(profile.model_dump(mode="json"), indent=2, ensure_ascii=False))


@project_app.command("resolve")
def project_resolve(
    name: str | None = typer.Argument(None),
    json_mode: bool = typer.Option(False, "--json"),
) -> None:
    settings, data_dir_source = load_settings_with_data_dir()
    try:
        profile, selected_path, profile_source = resolve_project_profile_selection(settings, name=name)
    except RuntimeError as exc:
        raise typer.BadParameter(str(exc)) from exc
    if profile is None:
        raise typer.BadParameter("No local operator-profile.yaml was found.")
    resolved = resolve_project_run_config(
        settings,
        profile=profile,
        objective=None,
        harness=None,
        success_criteria=None,
        allowed_agents=None,
        max_iterations=None,
        run_mode=None,
        involvement_level=None,
    )
    payload = {
        "profile": profile.model_dump(mode="json"),
        "resolved": resolved.model_dump(mode="json"),
        "data_dir": str(settings.data_dir),
        "data_dir_source": data_dir_source,
        "profile_path": str(selected_path) if selected_path is not None else None,
        "profile_source": profile_source,
    }
    typer.echo(json.dumps(payload, indent=2, ensure_ascii=False))


@project_app.command("dashboard")
def project_dashboard(
    name: str | None = typer.Argument(None),
    once: bool = typer.Option(False, "--once", help="Render a single dashboard snapshot and exit."),
    json_mode: bool = typer.Option(False, "--json", help="Emit a machine-readable project dashboard snapshot."),
    poll_interval: float = WATCH_POLL_INTERVAL_OPTION,
) -> None:
    anyio.run(project_dashboard_async, name, once, json_mode, poll_interval)
