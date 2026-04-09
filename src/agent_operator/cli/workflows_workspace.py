from __future__ import annotations

from pathlib import Path

import typer

from agent_operator.runtime import (
    clear_project_operator_state,
    discover_workspace_root,
)

from .helpers_services import load_settings


async def clear_async(yes: bool) -> None:
    settings = load_settings()
    workspace_root = discover_workspace_root()
    if not yes:
        confirmed = typer.confirm(
            "Clear operator runtime state for this workspace? "
            "This deletes runs, events, background artifacts, and history."
        )
        if not confirmed:
            typer.echo("cancelled")
            raise typer.Exit()
    try:
        result = clear_project_operator_state(
            workspace_root=workspace_root,
            data_dir=Path(settings.data_dir),
        )
    except RuntimeError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc

    typer.echo(f"Cleared operator state for {workspace_root}")
    typer.echo("Deleted:")
    if result.deleted:
        for path in result.deleted:
            typer.echo(f"- {path}")
    else:
        typer.echo("- nothing")
    typer.echo("Preserved:")
    if result.preserved:
        for path in result.preserved:
            typer.echo(f"- {path}")
    else:
        typer.echo("- nothing")
