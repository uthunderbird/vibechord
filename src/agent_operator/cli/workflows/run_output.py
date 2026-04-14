from __future__ import annotations

import json

import typer

from agent_operator.domain import OperationOutcome, RunEvent, RunMode

from ..helpers.exit_codes import raise_for_operation_status
from ..helpers.rendering import format_live_event, format_live_snapshot
from ..helpers.services import build_status_query_service, load_settings


class CliEventProjector:
    """Render run lifecycle events for CLI and JSON modes."""

    def __init__(self, *, json_mode: bool) -> None:
        self._json_mode = json_mode

    def emit_operation(self, operation_id: str) -> None:
        if self._json_mode:
            typer.echo(
                json.dumps({"type": "operation", "operation_id": operation_id}, ensure_ascii=False)
            )
            return
        typer.echo(f"operation_id={operation_id}", err=True)

    def handle_event(self, event: RunEvent) -> None:
        if self._json_mode:
            typer.echo(
                json.dumps(
                    {"type": "event", "event": event.model_dump(mode="json")}, ensure_ascii=False
                )
            )
            return
        rendered = format_live_event(event)
        if rendered is not None:
            typer.echo(rendered)

    def emit_snapshot(self, snapshot: dict[str, object]) -> None:
        if self._json_mode:
            typer.echo(json.dumps({"type": "snapshot", "snapshot": snapshot}, ensure_ascii=False))
            return
        typer.echo(format_live_snapshot(snapshot))

    def emit_outcome(self, outcome: OperationOutcome) -> None:
        if self._json_mode:
            typer.echo(
                json.dumps(
                    {"type": "outcome", "outcome": outcome.model_dump(mode="json")},
                    ensure_ascii=False,
                )
            )
            return
        typer.echo(f"{outcome.status.value}: {outcome.summary}")


async def emit_run_outcome(
    *,
    outcome: OperationOutcome,
    operation_id: str,
    effective_mode: RunMode,
    wait: bool,
    brief: bool,
    json_mode: bool,
    projector: CliEventProjector,
) -> None:
    """Render the final run outcome and raise on terminal failure statuses."""

    if wait and effective_mode is RunMode.RESUMABLE:
        # The resumable wait path replaces the initial background outcome before rendering.
        operation_id = outcome.operation_id
    if wait:
        if json_mode:
            typer.echo(
                json.dumps(
                    {
                        "operation_id": outcome.operation_id,
                        "status": outcome.status.value,
                        "summary": outcome.summary,
                        "metadata": outcome.metadata,
                    },
                    indent=2,
                    ensure_ascii=False,
                )
            )
        elif brief:
            status_service = build_status_query_service(load_settings())
            operation, _, _, _ = await status_service.build_status_payload(operation_id)
            iteration_count = len(operation.iterations) if operation is not None else 0
            typer.echo(
                "STATUS="
                f"{outcome.status.value} OPERATION={outcome.operation_id} "
                f"ITERATIONS={iteration_count}"
            )
        else:
            projector.emit_outcome(outcome)
        raise_for_operation_status(outcome.status)
    projector.emit_outcome(outcome)
