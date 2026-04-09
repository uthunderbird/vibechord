from __future__ import annotations

import json

import anyio
import typer

from agent_operator.bootstrap import (
    build_background_run_inspection_store,
    build_command_inbox,
    build_event_sink,
    build_store,
    build_trace_store,
    build_wakeup_inbox,
)

from .app import app, debug_app
from .helpers_rendering import (
    PROJECTIONS,
    artifact_preview,
    emit_context_lines,
    format_task_line,
    memory_payload,
    operation_payload,
    overlay_live_background_progress,
    render_inspect_summary,
    session_payload,
    shorten_live_text,
    summarize_task_counts,
)
from .helpers_services import build_delivery_commands_service, load_settings
from .options import JSON_OPTION, WATCH_POLL_INTERVAL_OPTION
from .workflows import daemon_async, recover_async, resume_async, tick_async


@app.command(hidden=True)
def resume(operation_id: str, max_cycles: int = typer.Option(8, help="Maximum scheduler cycles for this resume."), json_mode: bool = JSON_OPTION) -> None:
    anyio.run(resume_async, operation_id, max_cycles, json_mode)


@debug_app.command("resume")
def debug_resume(operation_id: str, max_cycles: int = typer.Option(8, help="Maximum scheduler cycles for this resume."), json_mode: bool = JSON_OPTION) -> None:
    resume(operation_id, max_cycles, json_mode)


@app.command(hidden=True)
def tick(operation_id: str) -> None:
    anyio.run(tick_async, operation_id)


@debug_app.command("tick")
def debug_tick(operation_id: str) -> None:
    tick(operation_id)


@app.command(hidden=True)
def daemon(
    once: bool = typer.Option(False, "--once", help="Run a single sweep for ready wakeups and exit."),
    poll_interval: float = WATCH_POLL_INTERVAL_OPTION,
    max_cycles_per_operation: int = typer.Option(1, "--max-cycles-per-operation", min=1, help="Maximum scheduler cycles to run per resumed operation."),
    json_mode: bool = JSON_OPTION,
) -> None:
    anyio.run(daemon_async, once, poll_interval, max_cycles_per_operation, json_mode)


@debug_app.command("daemon")
def debug_daemon(
    once: bool = typer.Option(False, "--once", help="Run a single sweep for ready wakeups and exit."),
    poll_interval: float = WATCH_POLL_INTERVAL_OPTION,
    max_cycles_per_operation: int = typer.Option(1, "--max-cycles-per-operation", min=1, help="Maximum scheduler cycles to run per resumed operation."),
    json_mode: bool = JSON_OPTION,
) -> None:
    daemon(once, poll_interval, max_cycles_per_operation, json_mode)


@app.command(hidden=True)
def recover(
    operation_id: str,
    session_id: str | None = typer.Option(None, "--session", help="Force recovery for a specific session instead of auto-selecting the active stuck one."),
    max_cycles: int = typer.Option(1, help="Maximum scheduler cycles after forced recovery."),
    json_mode: bool = JSON_OPTION,
) -> None:
    anyio.run(recover_async, operation_id, session_id, max_cycles, json_mode)


@debug_app.command("recover")
def debug_recover(
    operation_id: str,
    session_id: str | None = typer.Option(None, "--session", help="Force recovery for a specific session instead of auto-selecting the active stuck one."),
    max_cycles: int = typer.Option(1, help="Maximum scheduler cycles after forced recovery."),
    json_mode: bool = JSON_OPTION,
) -> None:
    recover(operation_id, session_id, max_cycles, json_mode)


@app.command(hidden=True)
def wakeups(operation_id: str, json_mode: bool = typer.Option(False, "--json", help="Emit JSON payload.")) -> None:
    settings = load_settings()
    store = build_store(settings)
    inbox = build_wakeup_inbox(settings)

    async def _wakeups() -> None:
        operation = await store.load_operation(operation_id)
        if operation is None:
            raise typer.BadParameter(f"Operation {operation_id!r} was not found.")
        pending = await inbox.list_pending(operation_id)
        claimed = [item.model_dump(mode="json") for item in operation.pending_wakeups]
        if json_mode:
            typer.echo(json.dumps({"operation_id": operation_id, "pending": [item.model_dump(mode="json") for item in pending], "claimed": claimed}, indent=2, ensure_ascii=False))
            return
        typer.echo(f"Operation {operation_id}")
        typer.echo("Pending wakeups:")
        if pending:
            for event in pending:
                suffix = f" not_before={event.not_before.isoformat()}" if event.not_before is not None else ""
                typer.echo(f"- {event.event_type} [{event.event_id}] session={event.session_id}{suffix}")
        else:
            typer.echo("- none")
        typer.echo("Claimed wakeups:")
        if claimed:
            for item in claimed:
                typer.echo(f"- {item['event_type']} [{item['event_id']}] session={item.get('session_id')}")
        else:
            typer.echo("- none")

    anyio.run(_wakeups)


@debug_app.command("wakeups")
def debug_wakeups(operation_id: str, json_mode: bool = typer.Option(False, "--json", help="Emit JSON payload.")) -> None:
    wakeups(operation_id, json_mode)


@app.command(hidden=True)
def sessions(operation_id: str, json_mode: bool = typer.Option(False, "--json", help="Emit JSON payload.")) -> None:
    settings = load_settings()
    store = build_store(settings)
    supervisor = build_background_run_inspection_store(settings)

    async def _sessions() -> None:
        operation = await store.load_operation(operation_id)
        if operation is None:
            raise typer.BadParameter(f"Operation {operation_id!r} was not found.")
        runs = await supervisor.list_runs(operation_id)
        operation_view = overlay_live_background_progress(operation, runs)
        if json_mode:
            typer.echo(json.dumps({"operation_id": operation_id, "sessions": [session_payload(item) for item in operation_view.sessions], "background_runs": [item.model_dump(mode="json") for item in runs]}, indent=2, ensure_ascii=False))
            return
        typer.echo(f"Operation {operation_id}")
        typer.echo("Sessions:")
        if operation_view.sessions:
            for session in operation_view.sessions:
                suffix = f" waiting={shorten_live_text(session.waiting_reason, limit=80)}" if session.waiting_reason else ""
                typer.echo(f"- {session.session_id} [{session.adapter_key}] status={session.status.value} run={session.current_execution_id or '-'}{suffix}")
        else:
            typer.echo("- none")
        typer.echo("Background runs:")
        if runs:
            for run in runs:
                suffix = ""
                if run.progress is not None:
                    detail = run.progress.message.strip()
                    if run.progress.partial_output:
                        preview = shorten_live_text(run.progress.partial_output, limit=80)
                        if preview:
                            detail = f"{detail} | {preview}" if detail else preview
                    if detail:
                        suffix = f" progress={detail}"
                typer.echo(f"- {run.run_id} [{run.adapter_key}] session={run.session_id or '-'} status={run.status.value}{suffix}")
        else:
            typer.echo("- none")

    anyio.run(_sessions)


@debug_app.command("sessions")
def debug_sessions(operation_id: str, json_mode: bool = typer.Option(False, "--json", help="Emit JSON payload.")) -> None:
    sessions(operation_id, json_mode)


@app.command(hidden=True)
def inspect(
    operation_id: str,
    full: bool = typer.Option(False, "--full", help="Show full forensic trace output."),
    json_mode: bool = typer.Option(False, "--json", help="Emit a single JSON object instead of human-readable output."),
) -> None:
    settings = load_settings()
    trace_store = build_trace_store(settings)
    event_sink = build_event_sink(settings, operation_id)
    command_inbox = build_command_inbox(settings)
    delivery = build_delivery_commands_service(settings)

    async def _inspect() -> None:
        try:
            operation, outcome, brief, runtime_alert = await delivery.build_status_payload(operation_id)
        except RuntimeError as exc:
            raise typer.BadParameter(str(exc)) from exc
        report = await trace_store.load_report(operation_id)
        trace_records = await trace_store.load_trace_records(operation_id)
        memos = await trace_store.load_decision_memos(operation_id)
        events = event_sink.read_events(operation_id)
        commands = [item.model_dump(mode="json") for item in await command_inbox.list(operation_id)]
        if operation is None:
            raise typer.BadParameter(f"Operation {operation_id!r} was not found.")
        if json_mode:
            payload: dict[str, object] = {
                "operation": operation_payload(operation),
                "outcome": outcome.model_dump(mode="json") if outcome is not None else None,
                "brief": brief.model_dump(mode="json") if brief is not None else None,
                "report": report,
                "commands": commands,
                "durable_truth": PROJECTIONS.build_durable_truth_payload(operation, include_inactive_memory=True),
            }
            if runtime_alert is not None:
                payload["runtime_alert"] = runtime_alert
            if full:
                payload["trace_records"] = [item.model_dump(mode="json") for item in trace_records]
                payload["decision_memos"] = [item.model_dump(mode="json") for item in memos]
                payload["events"] = [item.model_dump(mode="json") for item in events]
                payload["wakeups"] = build_wakeup_inbox(settings).read_all(operation_id)
                payload["background_runs"] = [item.model_dump(mode="json") for item in await build_background_run_inspection_store(settings).list_runs(operation_id)]
            typer.echo(json.dumps(payload, indent=2, ensure_ascii=False))
            return
        if brief is not None:
            typer.echo(render_inspect_summary(operation, brief, runtime_alert=runtime_alert))
        else:
            typer.echo("Operation:")
            typer.echo(json.dumps(operation_payload(operation), indent=2, ensure_ascii=False))
        if runtime_alert is not None and brief is None:
            typer.echo("\nRuntime alert:")
            typer.echo(runtime_alert)
        if outcome is not None:
            typer.echo("\nOutcome:")
            typer.echo(json.dumps(outcome.model_dump(mode="json"), indent=2, ensure_ascii=False))
        if report is not None:
            typer.echo("\nReport:")
            typer.echo(report)
        if operation.tasks:
            typer.echo("\nTasks:")
            typer.echo(f"Counts: {summarize_task_counts(operation)}")
            for task in operation.tasks:
                typer.echo(f"- task-{task.task_short_id} [{task.status.value}] {task.title} agent={task.assigned_agent or '-'}")
        memory_entries = memory_payload(operation, include_inactive=False)
        if memory_entries:
            typer.echo("\nCurrent memory:")
            for entry in memory_entries:
                scope_target = format_task_line(operation, entry.scope_id) if entry.scope.value == "task" else entry.scope_id
                typer.echo(f"- {entry.memory_id} [{entry.scope.value}] {scope_target}: {entry.summary}")
        if operation.artifacts:
            typer.echo("\nArtifacts:")
            for artifact in operation.artifacts:
                typer.echo(f"- {artifact.artifact_id} [{artifact.kind}] {artifact_preview(artifact)}")
        if operation.attention_requests:
            typer.echo("\nAttention requests:")
            for attention in operation.attention_requests:
                typer.echo(json.dumps(attention.model_dump(mode="json"), indent=2, ensure_ascii=False))
        if commands:
            typer.echo("\nCommands:")
            for command_payload in commands:
                typer.echo(json.dumps(command_payload, indent=2, ensure_ascii=False))
        if full:
            typer.echo("\nOperation state:")
            typer.echo(json.dumps(operation_payload(operation), indent=2, ensure_ascii=False))
            typer.echo("\nTrace:")
            for record in trace_records:
                typer.echo(json.dumps(record.model_dump(mode="json"), indent=2, ensure_ascii=False))
            typer.echo("\nDecision memos:")
            for memo in memos:
                typer.echo(json.dumps(memo.model_dump(mode="json"), indent=2, ensure_ascii=False))
            typer.echo("\nEvents:")
            for event in events:
                typer.echo(json.dumps(event.model_dump(mode="json"), indent=2, ensure_ascii=False))
            typer.echo("\nWakeups:")
            for wakeup in build_wakeup_inbox(settings).read_all(operation_id):
                typer.echo(json.dumps(wakeup, indent=2, ensure_ascii=False))
            typer.echo("\nBackground runs:")
            for run in [item.model_dump(mode="json") for item in await build_background_run_inspection_store(settings).list_runs(operation_id)]:
                typer.echo(json.dumps(run, indent=2, ensure_ascii=False))

    anyio.run(_inspect)


@debug_app.command("inspect")
def debug_inspect(
    operation_id: str,
    full: bool = typer.Option(False, "--full", help="Include the full stored state, trace, events, wakeups, and background runs."),
    json_mode: bool = typer.Option(False, "--json", help="Emit a machine-readable forensic payload."),
) -> None:
    inspect(operation_id, full, json_mode)


@app.command(hidden=True)
def context(
    operation_id: str,
    json_mode: bool = typer.Option(False, "--json", help="Emit a machine-readable effective control-plane context payload."),
) -> None:
    settings = load_settings()
    delivery = build_delivery_commands_service(settings)

    async def _context() -> None:
        try:
            operation, _, _, _ = await delivery.build_status_payload(operation_id)
        except RuntimeError as exc:
            raise typer.BadParameter(str(exc)) from exc
        if operation is None:
            raise typer.BadParameter(f"Operation {operation_id!r} was not found.")
        payload = PROJECTIONS.build_operation_context_payload(operation)
        if json_mode:
            typer.echo(json.dumps(payload, indent=2, ensure_ascii=False))
            return
        for line in emit_context_lines(payload, operation_id=operation.operation_id):
            typer.echo(line)

    anyio.run(_context)


@debug_app.command("context")
def debug_context(
    operation_id: str,
    json_mode: bool = typer.Option(False, "--json", help="Emit a machine-readable effective control-plane context payload."),
) -> None:
    context(operation_id, json_mode)


@app.command(hidden=True)
def trace(
    operation_id: str,
    json_mode: bool = typer.Option(False, "--json", help="Emit a machine-readable forensic trace payload."),
) -> None:
    settings = load_settings()
    trace_store = build_trace_store(settings)
    event_sink = build_event_sink(settings, operation_id)
    inbox = build_wakeup_inbox(settings)
    supervisor = build_background_run_inspection_store(settings)
    command_inbox = build_command_inbox(settings)
    delivery = build_delivery_commands_service(settings)

    async def _trace() -> None:
        try:
            operation, _, brief, _ = await delivery.build_status_payload(operation_id)
        except RuntimeError:
            operation = None
            brief = await trace_store.load_brief_bundle(operation_id)
        trace_records = await trace_store.load_trace_records(operation_id)
        memos = await trace_store.load_decision_memos(operation_id)
        events = event_sink.read_events(operation_id)
        wakeups = inbox.read_all(operation_id)
        commands = [item.model_dump(mode="json") for item in await command_inbox.list(operation_id)]
        background_runs = [item.model_dump(mode="json") for item in await supervisor.list_runs(operation_id)]
        if not trace_records and not memos and not events:
            raise typer.BadParameter(f"Trace for {operation_id!r} was not found.")
        raw_log_refs: list[str] = []
        if brief is not None:
            seen_raw_log_refs: set[str] = set()
            for turn_brief in brief.agent_turn_briefs:
                for raw_log_ref in turn_brief.raw_log_refs:
                    if raw_log_ref not in seen_raw_log_refs:
                        raw_log_refs.append(raw_log_ref)
                        seen_raw_log_refs.add(raw_log_ref)
        if json_mode:
            payload = {
                "operation_id": operation_id,
                "trace_records": [item.model_dump(mode="json") for item in trace_records],
                "decision_memos": [item.model_dump(mode="json") for item in memos],
                "events": [item.model_dump(mode="json") for item in events],
                "wakeups": wakeups,
                "background_runs": background_runs,
                "raw_log_refs": raw_log_refs,
                "commands": commands,
                "attention_requests": [item.model_dump(mode="json") for item in operation.attention_requests] if operation is not None else [],
            }
            typer.echo(json.dumps(payload, indent=2, ensure_ascii=False))
            return
        typer.echo("Trace:")
        for record in trace_records:
            typer.echo(json.dumps(record.model_dump(mode="json"), indent=2, ensure_ascii=False))
        typer.echo("\nDecision memos:")
        for memo in memos:
            typer.echo(json.dumps(memo.model_dump(mode="json"), indent=2, ensure_ascii=False))
        typer.echo("\nEvents:")
        for event in events:
            typer.echo(json.dumps(event.model_dump(mode="json"), indent=2, ensure_ascii=False))
        typer.echo("\nWakeups:")
        for wakeup in wakeups:
            typer.echo(json.dumps(wakeup, indent=2, ensure_ascii=False))
        typer.echo("\nBackground runs:")
        for run in background_runs:
            typer.echo(json.dumps(run, indent=2, ensure_ascii=False))
        if commands:
            typer.echo("\nCommands:")
            for command_payload in commands:
                typer.echo(json.dumps(command_payload, indent=2, ensure_ascii=False))
        if operation is not None and operation.attention_requests:
            typer.echo("\nAttention requests:")
            for attention in operation.attention_requests:
                typer.echo(json.dumps(attention.model_dump(mode="json"), indent=2, ensure_ascii=False))
        if raw_log_refs:
            typer.echo("\nRaw log refs:")
            for raw_log_ref in raw_log_refs:
                typer.echo(raw_log_ref)

    anyio.run(_trace)


@debug_app.command("trace")
def debug_trace(
    operation_id: str,
    json_mode: bool = typer.Option(False, "--json", help="Emit a machine-readable forensic trace payload."),
) -> None:
    trace(operation_id, json_mode)
