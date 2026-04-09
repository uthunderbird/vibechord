from __future__ import annotations

import anyio
import typer

from .app import app
from .options import WATCH_POLL_INTERVAL_OPTION
from .workflows import agenda_async, fleet_async, history_async, list_async


@app.command("list")
def list_operations(
    json_mode: bool = typer.Option(
        False,
        "--json",
        help="Emit one JSON object per operation instead of human-readable output.",
    ),
) -> None:
    anyio.run(list_async, json_mode)


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


@app.command()
def fleet(
    project: str | None = typer.Option(None, "--project", help="Project profile name."),
    include_all: bool = typer.Option(
        False,
        "--all",
        help="Include recent terminal operations even when actionable work exists.",
    ),
    once: bool = typer.Option(False, "--once", help="Render a single fleet snapshot and exit."),
    json_mode: bool = typer.Option(False, "--json", help="Emit a machine-readable fleet snapshot."),
    poll_interval: float = WATCH_POLL_INTERVAL_OPTION,
) -> None:
    anyio.run(fleet_async, project, include_all, once, json_mode, poll_interval)
