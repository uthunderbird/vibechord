from __future__ import annotations

import json
from pathlib import Path

import typer
import yaml

from agent_operator.config import (
    add_global_project_root,
    global_config_path,
    load_global_config,
    open_global_config_in_editor,
    redacted_global_config_payload,
)

from ..app import config_app

CONFIG_SET_ROOT_ARGUMENT = typer.Argument(
    ...,
    exists=True,
    file_okay=False,
    dir_okay=True,
    resolve_path=True,
)


@config_app.command("show")
def config_show(
    json_mode: bool = typer.Option(False, "--json", help="Emit machine-readable JSON."),
) -> None:
    config = load_global_config()
    payload = redacted_global_config_payload(config)
    if json_mode:
        typer.echo(json.dumps(payload, indent=2, ensure_ascii=False))
        return
    typer.echo(yaml.safe_dump(payload, sort_keys=False, allow_unicode=True).rstrip())


@config_app.command("edit")
def config_edit() -> None:
    try:
        path = open_global_config_in_editor()
    except RuntimeError as exc:
        raise typer.BadParameter(str(exc)) from exc
    typer.echo(f"Opened global config: {path}")


@config_app.command("set-root")
def config_set_root(
    path: Path = CONFIG_SET_ROOT_ARGUMENT,
    json_mode: bool = typer.Option(False, "--json", help="Emit machine-readable JSON."),
) -> None:
    try:
        config, added = add_global_project_root(path)
    except RuntimeError as exc:
        raise typer.BadParameter(str(exc)) from exc
    payload = {
        "config_path": str(global_config_path()),
        "added": added,
        "project_root": str(path.expanduser().resolve()),
        "project_roots": [str(item) for item in config.project_roots],
    }
    if json_mode:
        typer.echo(json.dumps(payload, indent=2, ensure_ascii=False))
        return
    status = "Added" if added else "Already present"
    typer.echo(f"{status} project root: {payload['project_root']}")
