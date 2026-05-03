from __future__ import annotations

import json
import sys
from collections.abc import Callable, Iterator
from pathlib import Path

import anyio
import typer
from rich.console import Console as RichConsole
from rich.live import Live

from agent_operator.application.live_feed import (
    LiveFeedEnvelope,
    iter_live_feed,
    parse_canonical_live_feed_line,
    parse_legacy_live_feed_line,
)
from agent_operator.bootstrap import build_wakeup_inbox
from agent_operator.config import OperatorSettings
from agent_operator.domain import (
    AgentSessionHandle,
    AttentionStatus,
    OperationOutcome,
    OperationState,
    OperationStatus,
    ProjectProfile,
    ResolvedProjectRunConfig,
)
from agent_operator.runtime import (
    apply_effective_adapter_settings_snapshot,
    apply_project_profile_settings,
    load_project_profile_from_path,
    snapshot_effective_adapter_settings,
)

from ..helpers.exit_codes import EXIT_INTERNAL_ERROR, raise_for_operation_status
from ..helpers.rendering import (
    cli_projection_payload,
    format_live_event,
    render_dashboard,
    render_watch_snapshot,
)
from ..helpers.resolution import load_canonical_operation_state_async
from ..helpers.services import (
    build_operation_dashboard_query_service,
    build_projecting_delivery_commands_service,
    build_status_query_service,
    delivery_commands_service,
    load_settings,
)
from .run_output import CliEventProjector


def _build_run_goal_metadata(
    *,
    settings: OperatorSettings,
    resolved: ResolvedProjectRunConfig,
    data_dir_source: str | None,
    profile: ProjectProfile | None,
    selected_profile_path: Path | None,
    profile_source: str | None,
    from_ticket: str | None,
    intake_result: object | None,
    objective: str | None,
    attach_session: str | None,
    attach_agent: str | None,
    attach_name: str | None,
    attach_working_dir: Path | None,
) -> tuple[list[AgentSessionHandle], dict[str, object]]:
    """Build run metadata and attached-session handles for the CLI run workflow."""

    attached_sessions: list[AgentSessionHandle] = []
    goal_metadata: dict[str, object] = {}
    if attach_session is not None:
        if attach_agent is None:
            raise typer.BadParameter("--attach-agent is required when --attach-session is used.")
        session_metadata: dict[str, str] = {}
        effective_attach_working_dir = attach_working_dir or resolved.cwd
        if effective_attach_working_dir is not None:
            session_metadata["working_directory"] = str(effective_attach_working_dir)
        attached_sessions.append(
            AgentSessionHandle(
                adapter_key=attach_agent,
                session_id=attach_session,
                session_name=attach_name,
                metadata=session_metadata,
            )
        )
        goal_metadata["requires_same_agent_session"] = True
        goal_metadata["attached_session_ids"] = [attach_session]
    effective_working_dir = attach_working_dir or resolved.cwd
    if effective_working_dir is not None:
        goal_metadata["working_directory"] = str(effective_working_dir)
    if intake_result is not None:
        goal_metadata["external_ticket_ref"] = from_ticket
        goal_text = getattr(intake_result, "goal_text", None)
        if objective is not None and isinstance(goal_text, str):
            goal_metadata["external_ticket_context"] = goal_text
    goal_metadata["resolved_operator_launch"] = {
        "data_dir": str(settings.data_dir),
        "data_dir_source": data_dir_source,
        "profile_source": profile_source,
        "profile_path": str(selected_profile_path) if selected_profile_path is not None else None,
    }
    if profile is not None:
        goal_metadata["project_profile_name"] = profile.name
        goal_metadata["policy_scope"] = f"profile:{profile.name}"
        goal_metadata["effective_adapter_settings"] = snapshot_effective_adapter_settings(
            settings,
            adapter_keys=resolved.default_agents,
        )
        goal_metadata["resolved_project_profile"] = resolved.model_dump(mode="json")
        goal_metadata["allowed_execution_profiles"] = {
            adapter_key: [
                entry.model_dump(mode="json")
                for entry in overrides.allowed_models
            ]
            for adapter_key, overrides in profile.adapter_settings.items()
            if getattr(overrides, "allowed_models", None)
        }
        ticket_reporting = getattr(profile, "ticket_reporting", None)
        if ticket_reporting is not None and hasattr(ticket_reporting, "model_dump"):
            goal_metadata["ticket_reporting"] = ticket_reporting.model_dump(mode="json")
        if selected_profile_path is not None:
            goal_metadata["project_profile_path"] = str(selected_profile_path)
        if profile_source is not None:
            goal_metadata["project_profile_source"] = profile_source
        goal_metadata["data_dir_source"] = data_dir_source
    elif resolved.cwd is not None:
        goal_metadata["policy_scope"] = f"cwd:{resolved.cwd}"
    return attached_sessions, goal_metadata


async def watch_async(operation_id: str, once: bool, json_mode: bool, poll_interval: float) -> None:
    settings = load_settings()
    event_stream_path, event_parser = _resolve_watch_stream(settings, operation_id)
    projector = CliEventProjector(json_mode=json_mode)
    status_queries = build_status_query_service(settings)
    try:
        _, outcome, _, _ = await status_queries.build_status_payload(operation_id)
    except RuntimeError as exc:
        raise typer.BadParameter(str(exc)) from exc
    use_live_tty = not json_mode and sys.stdout.isatty() and sys.stdin.isatty()
    if not use_live_tty and not (once and json_mode):
        projector.emit_operation(operation_id)
    seen_record_ids: set[str] = set()
    latest_update: str | None = None
    pending_answered_attention_id: str | None = None
    for envelope in _iter_watch_feed(event_stream_path, operation_id, event_parser):
        seen_record_ids.add(envelope.record_id)
        rendered, pending_answered_attention_id = _handle_watch_envelope(
            envelope,
            pending_answered_attention_id=pending_answered_attention_id,
        )
        if rendered is not None:
            latest_update = rendered
            if not use_live_tty:
                typer.echo(rendered)
    last_snapshot: dict[str, object] | None = None
    if once:
        operation, outcome, brief, runtime_alert = await status_queries.build_status_payload(
            operation_id
        )
        snapshot = status_queries.build_live_snapshot(
            operation_id,
            operation,
            outcome,
            brief=brief,
            runtime_alert=runtime_alert,
        )
        if json_mode:
            typer.echo(json.dumps(snapshot, indent=2, ensure_ascii=False))
        else:
            projector.emit_snapshot(snapshot)
        if outcome is not None and outcome.status is not OperationStatus.RUNNING:
            projector.emit_outcome(outcome)
        return
    if use_live_tty:
        console = RichConsole()
        (
            initial_operation,
            initial_outcome,
            initial_brief,
            initial_runtime_alert,
        ) = await status_queries.build_status_payload(operation_id)
        initial_snapshot = status_queries.build_live_snapshot(
            operation_id,
            initial_operation,
            initial_outcome,
            brief=initial_brief,
            runtime_alert=initial_runtime_alert,
        )
        last_snapshot = initial_snapshot
        with Live(
            render_watch_snapshot(initial_snapshot, latest_update=latest_update),
            console=console,
            refresh_per_second=4,
        ) as live:
            while True:
                for envelope in _iter_watch_feed(event_stream_path, operation_id, event_parser):
                    if envelope.record_id in seen_record_ids:
                        continue
                    seen_record_ids.add(envelope.record_id)
                    rendered, pending_answered_attention_id = _handle_watch_envelope(
                        envelope,
                        pending_answered_attention_id=pending_answered_attention_id,
                    )
                    if rendered is not None:
                        latest_update = rendered
                operation, outcome, brief, runtime_alert = (
                    await status_queries.build_status_payload(operation_id)
                )
                stale_warning = _build_attention_stale_warning(
                    operation,
                    attention_id=pending_answered_attention_id,
                )
                if stale_warning is not None and stale_warning.record_id not in seen_record_ids:
                    seen_record_ids.add(stale_warning.record_id)
                    latest_update = stale_warning.message
                snapshot = status_queries.build_live_snapshot(
                    operation_id,
                    operation,
                    outcome,
                    brief=brief,
                    runtime_alert=runtime_alert,
                )
                if snapshot != last_snapshot:
                    last_snapshot = snapshot
                live.update(
                    render_watch_snapshot(last_snapshot, latest_update=latest_update),
                    refresh=True,
                )
                if outcome is not None and outcome.status is not OperationStatus.RUNNING:
                    console.print(f"{outcome.status.value}: {outcome.summary}")
                    return
                await anyio.sleep(poll_interval)
    while True:
        for envelope in _iter_watch_feed(event_stream_path, operation_id, event_parser):
            if envelope.record_id in seen_record_ids:
                continue
            seen_record_ids.add(envelope.record_id)
            rendered, pending_answered_attention_id = _handle_watch_envelope(
                envelope,
                pending_answered_attention_id=pending_answered_attention_id,
            )
            if envelope.record_type == "event":
                assert envelope.event is not None
                projector.handle_event(envelope.event)
            elif rendered is not None:
                typer.echo(rendered)
        operation, outcome, brief, runtime_alert = await status_queries.build_status_payload(
            operation_id
        )
        stale_warning = _build_attention_stale_warning(
            operation,
            attention_id=pending_answered_attention_id,
        )
        if stale_warning is not None and stale_warning.record_id not in seen_record_ids:
            seen_record_ids.add(stale_warning.record_id)
            typer.echo(stale_warning.message)
        snapshot = status_queries.build_live_snapshot(
            operation_id,
            operation,
            outcome,
            brief=brief,
            runtime_alert=runtime_alert,
        )
        if snapshot != last_snapshot:
            projector.emit_snapshot(snapshot)
            last_snapshot = snapshot
        if outcome is not None and outcome.status is not OperationStatus.RUNNING:
            projector.emit_outcome(outcome)
            return
        await anyio.sleep(poll_interval)


def _resolve_watch_stream(
    settings: OperatorSettings,
    operation_id: str,
) -> tuple[Path, Callable[[str, str], LiveFeedEnvelope]]:
    canonical_path = settings.data_dir / "operation_events" / f"{operation_id}.jsonl"
    if canonical_path.exists():
        return canonical_path, parse_canonical_live_feed_line
    legacy_path = settings.data_dir / "events" / f"{operation_id}.jsonl"
    return legacy_path, parse_legacy_live_feed_line


def _iter_watch_feed(
    path: Path,
    operation_id: str,
    parser: Callable[[str, str], LiveFeedEnvelope],
) -> Iterator[LiveFeedEnvelope]:
    return iter_live_feed(path, operation_id=operation_id, parser=parser)


def _handle_watch_envelope(
    envelope: LiveFeedEnvelope,
    *,
    pending_answered_attention_id: str | None,
) -> tuple[str | None, str | None]:
    if envelope.record_type == "warning":
        return envelope.message, pending_answered_attention_id
    assert envelope.event is not None
    event = envelope.event
    if event.event_type == "attention.request.answered":
        attention_id = event.payload.get("attention_id")
        if isinstance(attention_id, str) and attention_id:
            pending_answered_attention_id = attention_id
    rendered = format_live_event(event)
    return rendered, pending_answered_attention_id


def _build_attention_stale_warning(
    operation: OperationState | None,
    *,
    attention_id: str | None,
) -> LiveFeedEnvelope | None:
    if operation is None or attention_id is None:
        return None
    stale_attention_open = any(
        item.attention_id == attention_id and item.status is AttentionStatus.OPEN
        for item in operation.attention_requests
    )
    if not stale_attention_open:
        return None
    return LiveFeedEnvelope.warning(
        operation_id=operation.operation_id,
        layer="overlay",
        warning_code="answered_attention_stale",
        message=(
            "Overlay warning: attention "
            f"{attention_id} was answered in the event stream but still appears open in status."
        ),
        record_suffix=f"overlay-stale-attention:{attention_id}",
    )


async def _wait_for_operation_outcome(
    *,
    operation_id: str,
    poll_interval: float,
    timeout: float | None,
    json_mode: bool,
) -> OperationOutcome:
    """Poll operation state until it reaches a terminal or needs-human status."""

    service = build_status_query_service(load_settings())
    deadline = anyio.current_time() + timeout if timeout is not None else None
    while True:
        _, outcome, _, _ = await service.build_status_payload(operation_id)
        if outcome is not None and outcome.status is not OperationStatus.RUNNING:
            return outcome
        if deadline is not None and anyio.current_time() >= deadline:
            if json_mode:
                typer.echo(
                    json.dumps(
                        {
                            "operation_id": operation_id,
                            "status": "timeout",
                            "summary": "Timed out while waiting for operation state.",
                        },
                        indent=2,
                        ensure_ascii=False,
                    )
                )
            else:
                typer.echo("Timed out while waiting for operation state.")
            raise typer.Exit(code=EXIT_INTERNAL_ERROR)
        await anyio.sleep(poll_interval)


async def dashboard_async(
    operation_id: str,
    once: bool,
    json_mode: bool,
    poll_interval: float,
    codex_home: Path,
) -> None:
    settings = load_settings()
    queries = build_operation_dashboard_query_service(
        settings,
        operation_id=operation_id,
        codex_home=codex_home,
    )

    async def load_payload() -> dict[str, object]:
        try:
            payload = await queries.load_payload(operation_id)
        except RuntimeError as exc:
            raise typer.BadParameter(str(exc)) from exc
        return cli_projection_payload(payload)

    payload = await load_payload()
    if json_mode:
        typer.echo(json.dumps(payload, indent=2, ensure_ascii=False))
        return
    console = RichConsole()
    if once:
        console.print(render_dashboard(payload))
        return
    with Live(render_dashboard(payload), console=console, refresh_per_second=4) as live:
        while True:
            payload = await load_payload()
            live.update(render_dashboard(payload), refresh=True)
            if payload.get("status") != OperationStatus.RUNNING.value:
                return
            await anyio.sleep(poll_interval)


async def resume_async(operation_id: str, max_cycles: int, json_mode: bool) -> None:
    try:
        settings = load_settings()
        await _restore_operation_scoped_runtime_settings(settings, operation_id)
        projector = CliEventProjector(json_mode=json_mode)
        if json_mode:
            projector.emit_operation(operation_id)
        delivery = build_projecting_delivery_commands_service(
            settings,
            operation_id=operation_id,
            projector=projector,
        )
        outcome = await delivery.resume(operation_id, max_cycles=max_cycles)
        projector.emit_outcome(outcome)
    except typer.Exit:
        raise
    except Exception as exc:
        typer.echo(f"{exc.__class__.__name__}: {exc}", err=True)
        raise typer.Exit(code=EXIT_INTERNAL_ERROR) from exc


async def ask_async(operation_ref: str, question: str, json_mode: bool) -> None:
    settings = load_settings()
    try:
        from .control import _build_cli_service
        from .converse import resolve_ask_operation_id

        operation_id = await resolve_ask_operation_id(operation_ref)
        service = _build_cli_service(settings)
        answer = (await service.answer_question(operation_id, question)).strip()
    except RuntimeError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=EXIT_INTERNAL_ERROR) from exc
    if json_mode:
        typer.echo(
            json.dumps(
                {
                    "question": question,
                    "answer": answer,
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        return
    typer.echo(f"Question: {question}\n")
    typer.echo(answer)


async def status_async(operation_id: str, json_mode: bool, brief: bool) -> None:
    service = build_status_query_service(load_settings())
    try:
        typer.echo(
            await service.render_status_output(operation_id, json_mode=json_mode, brief=brief)
        )
    except RuntimeError as exc:
        raise typer.BadParameter(str(exc)) from exc


async def tick_async(operation_id: str) -> None:
    settings = load_settings()
    await _restore_operation_scoped_runtime_settings(settings, operation_id)
    service = build_projecting_delivery_commands_service(
        settings,
        operation_id=operation_id,
        projector=CliEventProjector(json_mode=False),
    )
    outcome = await service.tick(operation_id)
    typer.echo(f"{outcome.status.value}: {outcome.summary}")
    typer.echo(f"operation_id={outcome.operation_id}", err=True)


async def daemon_async(
    once: bool,
    poll_interval: float,
    max_cycles_per_operation: int,
    json_mode: bool,
) -> None:
    settings = load_settings()
    inbox = build_wakeup_inbox(settings)
    projector = CliEventProjector(json_mode=json_mode)
    delivery = build_projecting_delivery_commands_service(
        settings, operation_id="sweep", projector=projector
    )

    async def sweep() -> int:
        resumed = await delivery.daemon_sweep(
            ready_operation_ids=list(inbox.ready_operation_ids()),
            max_cycles_per_operation=max_cycles_per_operation,
            emit_operation=projector.emit_operation if json_mode else None,
            emit_outcome=projector.emit_outcome,
        )
        if json_mode:
            typer.echo(
                json.dumps({"daemon_once": True, "resumed_operations": resumed}, ensure_ascii=False)
            )
        elif resumed > 0:
            typer.echo(f"resumed_operations={resumed}")
        return resumed

    if once:
        await sweep()
        return
    while True:
        await sweep()
        await anyio.sleep(poll_interval)


async def recover_async(
    operation_id: str, session_id: str | None, max_cycles: int, json_mode: bool
) -> None:
    settings = load_settings()
    await _restore_operation_scoped_runtime_settings(settings, operation_id)
    projector = CliEventProjector(json_mode=json_mode)
    if json_mode:
        projector.emit_operation(operation_id)
    delivery = build_projecting_delivery_commands_service(
        settings, operation_id=operation_id, projector=projector
    )
    outcome = await delivery.recover(operation_id, session_id=session_id, max_cycles=max_cycles)
    projector.emit_outcome(outcome)


async def cancel_async(
    operation_id: str,
    session_id: str | None,
    run_id: str | None,
    json_mode: bool,
) -> None:
    service = delivery_commands_service()
    outcome = await service.cancel(operation_id, session_id=session_id, run_id=run_id)
    is_operation_level = session_id is None and run_id is None
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
        if is_operation_level or outcome.status is not OperationStatus.RUNNING:
            raise_for_operation_status(outcome.status)
        return
    typer.echo(f"{outcome.status.value}: {outcome.summary}")
    typer.echo(f"operation_id={outcome.operation_id}", err=True)
    if is_operation_level or outcome.status is not OperationStatus.RUNNING:
        raise_for_operation_status(outcome.status)


async def _restore_operation_scoped_runtime_settings(
    settings: OperatorSettings, operation_id: str
) -> None:
    """Restore per-operation adapter settings from persisted goal metadata when present."""

    operation = await load_canonical_operation_state_async(settings, operation_id)
    metadata: dict[str, object] = {}
    if operation is not None:
        metadata = operation.goal.metadata if operation.goal is not None else {}
    snapshot = metadata.get("effective_adapter_settings")
    if isinstance(snapshot, dict):
        apply_effective_adapter_settings_snapshot(settings, snapshot)
        return
    profile_path = metadata.get("project_profile_path")
    if not isinstance(profile_path, str):
        return
    candidate = Path(profile_path)
    if not candidate.is_file():
        return
    try:
        profile = load_project_profile_from_path(candidate)
    except Exception:
        return
    apply_project_profile_settings(settings, profile)
