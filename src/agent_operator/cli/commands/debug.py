from __future__ import annotations

import anyio
import typer

from agent_operator.bootstrap import build_background_run_inspection_store

from ..app import app, debug_app
from ..options import JSON_OPTION, WATCH_POLL_INTERVAL_OPTION
from ..workflows import daemon_async, recover_async, resume_async, tick_async
from ..workflows.forensics import (
    context_async,
    event_append_async,
    inspect_async,
    sessions_async,
    trace_async,
    wakeups_async,
)

debug_event_app = typer.Typer(no_args_is_help=True)
debug_app.add_typer(debug_event_app, name="event")


@app.command(hidden=True)
def resume(
    operation_id: str,
    max_cycles: int = typer.Option(8, help="Maximum scheduler cycles for this resume."),
    json_mode: bool = JSON_OPTION,
) -> None:
    anyio.run(resume_async, operation_id, max_cycles, json_mode)


@debug_app.command("resume")
def debug_resume(
    operation_id: str,
    max_cycles: int = typer.Option(8, help="Maximum scheduler cycles for this resume."),
    json_mode: bool = JSON_OPTION,
) -> None:
    resume(operation_id, max_cycles, json_mode)


@app.command(hidden=True)
def tick(operation_id: str) -> None:
    anyio.run(tick_async, operation_id)


@debug_app.command("tick")
def debug_tick(operation_id: str) -> None:
    tick(operation_id)


@app.command(hidden=True)
def daemon(
    once: bool = typer.Option(
        False, "--once", help="Run a single sweep for ready wakeups and exit."
    ),
    poll_interval: float = WATCH_POLL_INTERVAL_OPTION,
    max_cycles_per_operation: int = typer.Option(
        1,
        "--max-cycles-per-operation",
        min=1,
        help="Maximum scheduler cycles to run per resumed operation.",
    ),
    json_mode: bool = JSON_OPTION,
) -> None:
    anyio.run(daemon_async, once, poll_interval, max_cycles_per_operation, json_mode)


@debug_app.command("daemon")
def debug_daemon(
    once: bool = typer.Option(
        False, "--once", help="Run a single sweep for ready wakeups and exit."
    ),
    poll_interval: float = WATCH_POLL_INTERVAL_OPTION,
    max_cycles_per_operation: int = typer.Option(
        1,
        "--max-cycles-per-operation",
        min=1,
        help="Maximum scheduler cycles to run per resumed operation.",
    ),
    json_mode: bool = JSON_OPTION,
) -> None:
    daemon(once, poll_interval, max_cycles_per_operation, json_mode)


@app.command(hidden=True)
def recover(
    operation_id: str,
    session_id: str | None = typer.Option(
        None,
        "--session",
        help=(
            "Force recovery for a specific session instead of auto-selecting the active stuck one."
        ),
    ),
    max_cycles: int = typer.Option(1, help="Maximum scheduler cycles after forced recovery."),
    json_mode: bool = JSON_OPTION,
) -> None:
    anyio.run(recover_async, operation_id, session_id, max_cycles, json_mode)


@debug_app.command("recover")
def debug_recover(
    operation_id: str,
    session_id: str | None = typer.Option(
        None,
        "--session",
        help=(
            "Force recovery for a specific session instead of auto-selecting the active stuck one."
        ),
    ),
    max_cycles: int = typer.Option(1, help="Maximum scheduler cycles after forced recovery."),
    json_mode: bool = JSON_OPTION,
) -> None:
    recover(operation_id, session_id, max_cycles, json_mode)


@app.command(hidden=True)
def wakeups(
    operation_id: str, json_mode: bool = typer.Option(False, "--json", help="Emit JSON payload.")
) -> None:
    anyio.run(wakeups_async, operation_id, json_mode)


@debug_app.command("wakeups")
def debug_wakeups(
    operation_id: str, json_mode: bool = typer.Option(False, "--json", help="Emit JSON payload.")
) -> None:
    wakeups(operation_id, json_mode)


@app.command(hidden=True)
def sessions(
    operation_id: str, json_mode: bool = typer.Option(False, "--json", help="Emit JSON payload.")
) -> None:
    anyio.run(
        sessions_async,
        operation_id,
        json_mode,
        build_background_run_inspection_store,
    )


@debug_app.command("sessions")
def debug_sessions(
    operation_id: str, json_mode: bool = typer.Option(False, "--json", help="Emit JSON payload.")
) -> None:
    sessions(operation_id, json_mode)


@app.command(hidden=True)
def inspect(
    operation_id: str,
    full: bool = typer.Option(False, "--full", help="Show full forensic trace output."),
    json_mode: bool = typer.Option(
        False, "--json", help="Emit a single JSON object instead of human-readable output."
    ),
) -> None:
    anyio.run(inspect_async, operation_id, full, json_mode)


@debug_app.command("inspect")
def debug_inspect(
    operation_id: str,
    full: bool = typer.Option(
        False,
        "--full",
        help="Include the full stored state, trace, events, wakeups, and background runs.",
    ),
    json_mode: bool = typer.Option(
        False, "--json", help="Emit a machine-readable forensic payload."
    ),
) -> None:
    inspect(operation_id, full, json_mode)


@app.command(hidden=True)
def context(
    operation_id: str,
    json_mode: bool = typer.Option(
        False, "--json", help="Emit a machine-readable effective control-plane context payload."
    ),
) -> None:
    anyio.run(context_async, operation_id, json_mode)


@debug_app.command("context")
def debug_context(
    operation_id: str,
    json_mode: bool = typer.Option(
        False, "--json", help="Emit a machine-readable effective control-plane context payload."
    ),
) -> None:
    context(operation_id, json_mode)


@app.command(hidden=True)
def trace(
    operation_id: str,
    json_mode: bool = typer.Option(
        False, "--json", help="Emit a machine-readable forensic trace payload."
    ),
) -> None:
    anyio.run(trace_async, operation_id, json_mode)


@debug_app.command("trace")
def debug_trace(
    operation_id: str,
    json_mode: bool = typer.Option(
        False, "--json", help="Emit a machine-readable forensic trace payload."
    ),
) -> None:
    trace(operation_id, json_mode)


@debug_event_app.command("append")
def debug_event_append(
    operation_ref: str,
    event_type: str = typer.Option(..., "--event-type", help="Allowlisted repair event type."),
    payload_json: str = typer.Option(..., "--payload-json", help="JSON object payload."),
    reason: str | None = typer.Option(
        None,
        "--reason",
        help="Required for non-dry-run append; stored in event metadata.",
    ),
    expected_last_sequence: int | None = typer.Option(
        None,
        "--expected-last-sequence",
        min=0,
        help="Optional optimistic sequence guard for non-dry-run append.",
    ),
    yes: bool = typer.Option(
        False,
        "--yes",
        help="Apply the append. Without this flag the command performs a dry-run preview.",
    ),
    json_mode: bool = typer.Option(False, "--json", help="Emit machine-readable output."),
) -> None:
    anyio.run(
        event_append_async,
        operation_ref,
        event_type,
        payload_json,
        reason,
        expected_last_sequence,
        yes,
        json_mode,
    )
