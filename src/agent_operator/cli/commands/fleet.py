from __future__ import annotations

import anyio
import typer

from ..app import app, fleet_app
from ..options import WATCH_POLL_INTERVAL_OPTION
from ..workflows import agenda_async, fleet_async, history_async, list_async


@app.command("list")
def list_operations(
    json_mode: bool = typer.Option(
        False,
        "--json",
        help="Emit one JSON object per operation instead of human-readable output.",
    ),
) -> None:
    anyio.run(list_async, json_mode)


@fleet_app.command("list")
def fleet_list(
    json_mode: bool = typer.Option(
        False,
        "--json",
        help="Emit one JSON object per operation instead of human-readable output.",
    ),
) -> None:
    list_operations(json_mode)


@app.command("history")
def history(
    operation_ref: str | None = typer.Argument(
        None,
        metavar="[OP]",
        help="Optional operation reference (full id, short prefix, or 'last').",
    ),
    json_mode: bool = typer.Option(False, "--json", help="Emit machine-readable JSON."),
) -> None:
    anyio.run(history_async, operation_ref, json_mode)


@fleet_app.command("history")
def fleet_history(
    operation_ref: str | None = typer.Argument(
        None,
        metavar="[OP]",
        help="Optional operation reference (full id, short prefix, or 'last').",
    ),
    json_mode: bool = typer.Option(False, "--json", help="Emit machine-readable JSON."),
) -> None:
    history(operation_ref, json_mode)


@app.command()
def agenda(
    project: str | None = typer.Option(None, "--project", help="Project profile name."),
    include_all: bool = typer.Option(
        False,
        "--all",
        help="Include recent terminal operations even when actionable work exists.",
    ),
    json_mode: bool = typer.Option(False, "--json", help="Emit machine-readable JSON."),
) -> None:
    anyio.run(agenda_async, project, include_all, json_mode)


@fleet_app.command("agenda")
def fleet_agenda(
    project: str | None = typer.Option(None, "--project", help="Project profile name."),
    include_all: bool = typer.Option(
        False,
        "--all",
        help="Include recent terminal operations even when actionable work exists.",
    ),
    json_mode: bool = typer.Option(False, "--json", help="Emit machine-readable JSON."),
) -> None:
    agenda(project, include_all, json_mode)


@fleet_app.callback(invoke_without_command=True)
def fleet(
    ctx: typer.Context,
    project: str | None = typer.Option(None, "--project", help="Project profile name."),
    include_all: bool = typer.Option(
        False,
        "--all",
        help="Include recent terminal operations even when actionable work exists.",
    ),
    once: bool = typer.Option(False, "--once", help="Render a single fleet snapshot and exit."),
    discover: bool = typer.Option(
        False,
        "--discover",
        help="Scan configured roots for projects instead of rendering the fleet view.",
    ),
    depth: int | None = typer.Option(
        None,
        "--depth",
        min=0,
        help="Discovery scan depth. Defaults to 4 for configured roots, 3 for first-run home scan.",
    ),
    add: bool = typer.Option(
        False,
        "--add",
        help="Persist discovered project parent roots into global config.",
    ),
    json_mode: bool = typer.Option(False, "--json", help="Emit a machine-readable fleet snapshot."),
    poll_interval: float = WATCH_POLL_INTERVAL_OPTION,
) -> None:
    if ctx.invoked_subcommand is not None:
        return
    anyio.run(
        fleet_async,
        project,
        include_all,
        once,
        json_mode,
        poll_interval,
        discover,
        depth,
        add,
    )
