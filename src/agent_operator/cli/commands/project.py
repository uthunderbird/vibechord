from __future__ import annotations

import json
from pathlib import Path

import anyio
import typer

from agent_operator.domain import InvolvementLevel, ProjectProfile
from agent_operator.runtime import (
    list_project_profiles,
    load_project_profile,
    profile_path,
    resolve_project_run_config,
    write_project_profile,
)

from ..app import project_app
from ..helpers.resolution import resolve_project_profile_selection
from ..helpers.services import load_settings, load_settings_with_data_dir
from ..options import (
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
from ..workflows import project_dashboard_async


def _emit_project_profile(profile: ProjectProfile, *, profile_path: Path | None = None) -> None:
    typer.echo(f"Profile: {profile.name}")
    if profile_path is not None:
        typer.echo(f"Path: {profile_path}")
    typer.echo(f"CWD: {profile.cwd or '-'}")
    typer.echo("Paths:")
    if profile.paths:
        for item in profile.paths:
            typer.echo(f"- {item}")
    else:
        typer.echo("- none")
    typer.echo("Default objective:")
    typer.echo(profile.default_objective or "-")
    typer.echo("Default agents:")
    if profile.default_agents:
        for agent_key in profile.default_agents:
            typer.echo(f"- {agent_key}")
    else:
        typer.echo("- none")
    typer.echo("Harness:")
    typer.echo(profile.default_harness_instructions or "-")
    typer.echo("Success criteria:")
    if profile.default_success_criteria:
        for criterion in profile.default_success_criteria:
            typer.echo(f"- {criterion}")
    else:
        typer.echo("- none")
    typer.echo(f"Max iterations: {profile.default_max_iterations or '-'}")
    typer.echo(f"Run mode: {profile.default_run_mode.value if profile.default_run_mode else '-'}")
    involvement = (
        profile.default_involvement_level.value
        if profile.default_involvement_level
        else "-"
    )
    typer.echo(f"Involvement: {involvement}")
    typer.echo("Adapter settings:")
    if profile.adapter_settings:
        for adapter_key, settings in sorted(profile.adapter_settings.items()):
            rendered = json.dumps(settings, ensure_ascii=False, sort_keys=True)
            typer.echo(f"- {adapter_key}: {rendered}")
    else:
        typer.echo("- none")
    typer.echo("Dashboard prefs:")
    if profile.dashboard_prefs:
        rendered = json.dumps(
            profile.dashboard_prefs,
            indent=2,
            ensure_ascii=False,
            sort_keys=True,
        )
        typer.echo(rendered)
    else:
        typer.echo("- none")
    typer.echo(f"History ledger: {'enabled' if profile.history_ledger else 'disabled'}")
    typer.echo(f"Session reuse policy: {profile.session_reuse_policy or '-'}")
    typer.echo(f"Message window: {profile.default_message_window or '-'}")


def _emit_resolved_project_config(payload: dict[str, object]) -> None:
    profile = payload["profile"]
    resolved = payload["resolved"]
    assert isinstance(profile, dict)
    assert isinstance(resolved, dict)
    typer.echo(f"Profile: {profile.get('name') or '-'}")
    typer.echo(f"Profile source: {payload.get('profile_source') or '-'}")
    typer.echo(f"Profile path: {payload.get('profile_path') or '-'}")
    typer.echo(f"Data dir: {payload.get('data_dir') or '-'}")
    typer.echo(f"Data dir source: {payload.get('data_dir_source') or '-'}")
    typer.echo("Resolved run defaults:")
    typer.echo(f"- CWD: {resolved.get('cwd') or '-'}")
    typer.echo(f"- Objective: {resolved.get('objective_text') or '-'}")
    typer.echo(
        f"- Agents: {', '.join(resolved.get('default_agents', [])) or '-'}"
    )
    typer.echo(f"- Harness: {resolved.get('harness_instructions') or '-'}")
    success_criteria = resolved.get("success_criteria", [])
    if isinstance(success_criteria, list) and success_criteria:
        typer.echo("- Success criteria:")
        for criterion in success_criteria:
            typer.echo(f"  - {criterion}")
    else:
        typer.echo("- Success criteria: none")
    typer.echo(f"- Max iterations: {resolved.get('max_iterations') or '-'}")
    typer.echo(f"- Run mode: {resolved.get('run_mode') or '-'}")
    typer.echo(f"- Involvement: {resolved.get('involvement_level') or '-'}")
    typer.echo(f"- Message window: {resolved.get('message_window') or '-'}")
    overrides = resolved.get("overrides", [])
    if isinstance(overrides, list) and overrides:
        typer.echo("- Overrides:")
        for item in overrides:
            typer.echo(f"  - {item}")
    else:
        typer.echo("- Overrides: none")


def _project_inventory_payload(settings) -> list[dict[str, object]]:
    payload: list[dict[str, object]] = []
    for name in list_project_profiles(settings):
        path = profile_path(settings, name)
        profile = load_project_profile(settings, name)
        payload.append(
            {
                "name": name,
                "path": str(path),
                "scope": "local" if path.parent == settings.data_dir / "profiles" else "committed",
                "cwd": str(profile.cwd) if profile.cwd is not None else None,
                "default_agents": list(profile.default_agents),
                "default_objective": profile.default_objective,
                "default_involvement_level": (
                    profile.default_involvement_level.value
                    if profile.default_involvement_level is not None
                    else None
                ),
            }
        )
    return payload


@project_app.command("list")
def project_list(json_mode: bool = typer.Option(False, "--json")) -> None:
    settings = load_settings()
    payload = _project_inventory_payload(settings)
    if json_mode:
        typer.echo(json.dumps({"project_profiles": payload}, indent=2, ensure_ascii=False))
        return
    typer.echo("Projects")
    if not payload:
        typer.echo("- none")
        return
    for item in payload:
        typer.echo(f"- {item['name']}")


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
    local: bool = typer.Option(
        False,
        "--local",
        help="Write the profile to .operator/profiles instead of operator-profiles.",
    ),
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
        profile, profile_path, _ = resolve_project_profile_selection(settings, name=name)
    except RuntimeError as exc:
        raise typer.BadParameter(str(exc)) from exc
    if profile is None:
        raise typer.BadParameter("No local operator-profile.yaml was found.")
    if json_mode:
        typer.echo(json.dumps(profile.model_dump(mode="json"), indent=2, ensure_ascii=False))
        return
    _emit_project_profile(profile, profile_path=profile_path)


@project_app.command("resolve")
def project_resolve(
    name: str | None = typer.Argument(None),
    json_mode: bool = typer.Option(False, "--json"),
) -> None:
    settings, data_dir_source = load_settings_with_data_dir()
    try:
        profile, selected_path, profile_source = resolve_project_profile_selection(
            settings, name=name
        )
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
    if json_mode:
        typer.echo(json.dumps(payload, indent=2, ensure_ascii=False))
        return
    _emit_resolved_project_config(payload)


@project_app.command("dashboard")
def project_dashboard(
    name: str | None = typer.Argument(None),
    once: bool = typer.Option(False, "--once", help="Render a single dashboard snapshot and exit."),
    json_mode: bool = typer.Option(
        False, "--json", help="Emit a machine-readable project dashboard snapshot."
    ),
    poll_interval: float = WATCH_POLL_INTERVAL_OPTION,
) -> None:
    anyio.run(project_dashboard_async, name, once, json_mode, poll_interval)
