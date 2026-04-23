from __future__ import annotations

import json
from pathlib import Path

import anyio
import typer

from agent_operator.domain import InvolvementLevel, ProjectProfile, RunMode
from agent_operator.runtime import committed_default_profile_path, committed_profile_dir

from ..app import app
from ..helpers.services import (
    normalize_agent_override,
    update_gitignore_with_operator_dir,
    write_default_project_profile,
)
from ..options import (
    ATTACH_AGENT_OPTION,
    ATTACH_NAME_OPTION,
    ATTACH_SESSION_OPTION,
    ATTACH_WORKING_DIR_OPTION,
    HARNESS_OPTION,
    INVOLVEMENT_OPTION,
    JSON_OPTION,
    MAX_ITERATIONS_OPTION,
    PROJECT_AGENT_OPTION,
    PROJECT_CWD_OPTION,
    PROJECT_FORCE_OPTION,
    PROJECT_HARNESS_OPTION,
    PROJECT_INVOLVEMENT_OPTION,
    PROJECT_MAX_ITERATIONS_OPTION,
    PROJECT_MESSAGE_WINDOW_OPTION,
    PROJECT_OBJECTIVE_OPTION,
    PROJECT_OPTION,
    PROJECT_PATH_OPTION,
    PROJECT_RUN_MODE_OPTION,
    PROJECT_SUCCESS_CRITERION_OPTION,
    RUN_AGENT_OPTION,
    RUN_MODE_OPTION,
    RUN_SUCCESS_CRITERION_OPTION,
)
from ..workflows import clear_async, run_async


@app.command(
    help="Start a new operation in the current workspace or from a named project profile."
)
def run(
    objective: str | None = typer.Argument(None, help="Objective for this run."),
    from_ticket: str | None = typer.Option(
        None,
        "--from",
        help="Populate the goal from a PM ticket ref such as github:owner/repo#123.",
    ),
    project: str | None = PROJECT_OPTION,
    harness: str | None = HARNESS_OPTION,
    success_criterion: list[str] | None = RUN_SUCCESS_CRITERION_OPTION,
    max_iterations: int | None = MAX_ITERATIONS_OPTION,
    agent: list[str] | None = RUN_AGENT_OPTION,
    mode: RunMode | None = RUN_MODE_OPTION,
    involvement: InvolvementLevel | None = INVOLVEMENT_OPTION,
    attach_session: str | None = ATTACH_SESSION_OPTION,
    attach_agent: str | None = ATTACH_AGENT_OPTION,
    attach_name: str | None = ATTACH_NAME_OPTION,
    attach_working_dir: Path | None = ATTACH_WORKING_DIR_OPTION,
    wait: bool = typer.Option(
        False,
        "--wait",
        help="Block until the operation reaches a terminal state or needs human input.",
    ),
    timeout: float | None = typer.Option(
        None,
        "--timeout",
        min=0.0,
        help="Maximum seconds to wait when --wait is used.",
    ),
    brief: bool = typer.Option(
        False,
        "--brief",
        help="Emit a single-line completion summary when --wait is used.",
    ),
    json_mode: bool = JSON_OPTION,
    v2: bool = typer.Option(
        False,
        "--v2",
        help="Use the v2 event-sourced drive stack (ADR 0194). Experimental.",
    ),
) -> None:
    if brief and not wait:
        raise typer.BadParameter("--brief requires --wait.")
    if timeout is not None and not wait:
        raise typer.BadParameter("--timeout requires --wait.")
    normalized_agents = normalize_agent_override(agent=agent)
    anyio.run(
        run_async,
        objective,
        from_ticket,
        project,
        harness,
        success_criterion,
        max_iterations,
        normalized_agents,
        mode,
        involvement,
        attach_session,
        attach_agent,
        attach_name,
        attach_working_dir,
        wait,
        timeout,
        brief,
        json_mode,
        v2,
    )


@app.command(
    help="Prepare this workspace for operator by writing the default committed project profile."
)
def init(
    cwd: Path | None = PROJECT_CWD_OPTION,
    path: list[Path] | None = PROJECT_PATH_OPTION,
    agent: list[str] | None = PROJECT_AGENT_OPTION,
    objective: str | None = PROJECT_OBJECTIVE_OPTION,
    harness: str | None = PROJECT_HARNESS_OPTION,
    success_criterion: list[str] | None = PROJECT_SUCCESS_CRITERION_OPTION,
    max_iterations: int | None = PROJECT_MAX_ITERATIONS_OPTION,
    run_mode: RunMode | None = PROJECT_RUN_MODE_OPTION,
    involvement: InvolvementLevel | None = PROJECT_INVOLVEMENT_OPTION,
    message_window: int | None = PROJECT_MESSAGE_WINDOW_OPTION,
    force: bool = PROJECT_FORCE_OPTION,
    json_mode: bool = typer.Option(False, "--json"),
) -> None:
    root = committed_default_profile_path().parent
    profile = ProjectProfile(
        name=root.name,
        cwd=cwd or Path("."),
        paths=list(path or []),
        default_objective=objective,
        default_agents=list(agent or []),
        default_harness_instructions=harness,
        default_success_criteria=list(success_criterion or []),
        default_max_iterations=max_iterations,
        default_run_mode=run_mode,
        default_involvement_level=involvement,
        default_message_window=message_window,
    )
    try:
        profile_path = write_default_project_profile(root=root, profile=profile, force=force)
    except RuntimeError as exc:
        raise typer.BadParameter(str(exc)) from exc
    committed_dir = committed_profile_dir(cwd=root)
    committed_dir.mkdir(parents=True, exist_ok=True)
    gitignore_updated = update_gitignore_with_operator_dir(root)
    payload = {
        "project_root": str(root),
        "profile_path": str(profile_path),
        "profiles_dir": str(committed_dir),
        "gitignore_updated": gitignore_updated,
        "profile": profile.model_dump(mode="json"),
    }
    if json_mode:
        typer.echo(json.dumps(payload, indent=2, ensure_ascii=False))
        return
    typer.echo(f"Initialized project profile: {profile_path}")


@app.command(
    help="Reset project-local operator runtime state without removing committed workspace profiles."
)
def clear(
    yes: bool = typer.Option(False, "--yes", help="Skip confirmation prompt."),
    force: bool = typer.Option(
        False,
        "--force",
        help="Discard live or recoverable operator state before clearing workspace runtime data.",
    ),
) -> None:
    anyio.run(clear_async, yes, force)
