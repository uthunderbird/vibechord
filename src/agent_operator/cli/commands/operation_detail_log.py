from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

import anyio
import typer

from agent_operator.runtime import (
    find_codex_session_log,
    format_claude_log_event,
    format_codex_log_event,
    iter_claude_log_events,
    iter_codex_log_events,
    load_claude_log_events,
    load_codex_log_events,
)

from ..app import app
from ..helpers.logs import (
    format_opencode_log_event,
    iter_opencode_log_events,
    load_opencode_log_events,
    resolve_claude_log_path_for_session,
    resolve_jsonl_log_path_for_session,
    resolve_log_target,
)
from ..helpers.resolution import (
    load_required_canonical_operation_state_async,
    resolve_operation_id,
)
from ..helpers.services import load_settings
from ..options import CODEX_HOME_OPTION


@app.command()
def log(
    operation_ref: str,
    limit: int = typer.Option(40, "--limit", min=1, help="Maximum events to print."),
    follow: bool = typer.Option(False, "--follow", help="Follow the agent transcript."),
    agent: str = typer.Option("auto", "--agent", help="auto, codex, claude, or opencode."),
    json_mode: bool = typer.Option(False, "--json", help="Emit machine-readable JSON."),
    codex_home: Path = CODEX_HOME_OPTION,
) -> None:
    resolved_operation_id = resolve_operation_id(operation_ref)
    settings = load_settings()

    async def _log() -> None:
        operation = await load_required_canonical_operation_state_async(
            settings, resolved_operation_id
        )
        log_kind, session = resolve_log_target(operation, agent=agent)
        if log_kind == "codex":
            path = find_codex_session_log(codex_home, session.session_id)
            if path is None:
                raise typer.BadParameter(
                    "Codex transcript for session "
                    f"{session.session_id!r} was not found under {str(codex_home)!r}."
                )
            if follow:
                typer.echo(f"# Codex log for operation {resolved_operation_id}")
                typer.echo(f"# session={session.session_id}")
                typer.echo(f"# file={path}")
                for event in iter_codex_log_events(path, follow=True):
                    typer.echo(
                        json.dumps(asdict(event), ensure_ascii=False)
                        if json_mode
                        else format_codex_log_event(event)
                    )
                return
            events = load_codex_log_events(path)[-limit:]
            if json_mode:
                typer.echo(
                    json.dumps(
                        {
                            "operation_id": resolved_operation_id,
                            "session_id": session.session_id,
                            "path": str(path),
                            "agent": "codex",
                            "events": [asdict(event) for event in events],
                        },
                        indent=2,
                        ensure_ascii=False,
                    )
                )
                return
            typer.echo(f"# Codex log for operation {resolved_operation_id}")
            typer.echo(f"# session={session.session_id}")
            typer.echo(f"# file={path}")
            for event in events:
                typer.echo(format_codex_log_event(event))
            return
        if log_kind == "claude":
            path = resolve_claude_log_path_for_session(session)
            if follow:
                typer.echo(f"# Claude log for operation {resolved_operation_id}")
                typer.echo(f"# session={session.session_id}")
                typer.echo(f"# file={path}")
                for event in iter_claude_log_events(path, follow=True):
                    typer.echo(
                        json.dumps(asdict(event), ensure_ascii=False)
                        if json_mode
                        else format_claude_log_event(event)
                    )
                return
            events = load_claude_log_events(path)[-limit:]
            if json_mode:
                typer.echo(
                    json.dumps(
                        {
                            "operation_id": resolved_operation_id,
                            "session_id": session.session_id,
                            "path": str(path),
                            "agent": "claude",
                            "events": [asdict(event) for event in events],
                        },
                        indent=2,
                        ensure_ascii=False,
                    )
                )
                return
            typer.echo(f"# Claude log for operation {resolved_operation_id}")
            typer.echo(f"# session={session.session_id}")
            typer.echo(f"# file={path}")
            for event in events:
                typer.echo(format_claude_log_event(event))
            return
        path = resolve_jsonl_log_path_for_session(session, provider="OpenCode")
        if follow:
            typer.echo(f"# OpenCode log for operation {resolved_operation_id}")
            typer.echo(f"# session={session.session_id}")
            typer.echo(f"# file={path}")
            for event in iter_opencode_log_events(path, follow=True):
                typer.echo(
                    json.dumps(asdict(event), ensure_ascii=False)
                    if json_mode
                    else format_opencode_log_event(event)
                )
            return
        events = load_opencode_log_events(path)[-limit:]
        if json_mode:
            typer.echo(
                json.dumps(
                    {
                        "operation_id": resolved_operation_id,
                        "session_id": session.session_id,
                        "path": str(path),
                        "agent": "opencode",
                        "events": [asdict(event) for event in events],
                    },
                    indent=2,
                    ensure_ascii=False,
                )
            )
            return
        typer.echo(f"# OpenCode log for operation {resolved_operation_id}")
        typer.echo(f"# session={session.session_id}")
        typer.echo(f"# file={path}")
        for event in events:
            typer.echo(format_opencode_log_event(event))

    anyio.run(_log)
