from __future__ import annotations

import json
from collections.abc import Callable
from typing import TYPE_CHECKING, cast

import typer

from agent_operator.application.event_sourcing.event_stream_repair import (
    EventStreamRepairService,
)
from agent_operator.application.queries.operation_resolution import OperationResolutionService
from agent_operator.application.queries.operation_state_views import OperationStateViewService
from agent_operator.bootstrap import (
    build_background_run_inspection_store,
    build_command_inbox,
    build_event_sink,
    build_replay_service,
    build_store,
    build_trace_store,
    build_wakeup_inbox,
)
from agent_operator.projectors import DefaultOperationProjector
from agent_operator.runtime import FileOperationCheckpointStore, FileOperationEventStore

from ..helpers.forensics import (
    attention_request_payload,
    decision_memo_payload,
    execution_payload,
    operation_command_payload,
    operation_outcome_payload,
    run_event_payload,
    trace_brief_bundle_payload,
    trace_record_payload,
    wakeup_ref_payload,
)
from ..helpers.rendering import (
    PROJECTIONS,
    artifact_preview,
    emit_context_lines,
    format_task_line,
    memory_payload,
    operation_payload,
    render_inspect_summary,
    session_payload,
    shorten_live_text,
    summarize_task_counts,
)
from ..helpers.resolution import load_required_canonical_operation_state_async
from ..helpers.services import build_status_query_service, load_settings

if TYPE_CHECKING:
    from agent_operator.config import OperatorSettings
    from agent_operator.domain.traceability import TraceBriefBundle
    from agent_operator.runtime import BackgroundRunInspectionStore


async def wakeups_async(operation_id: str, json_mode: bool) -> None:
    settings = load_settings()
    inbox = build_wakeup_inbox(settings)
    try:
        operation = await load_required_canonical_operation_state_async(settings, operation_id)
    except RuntimeError as exc:
        raise typer.BadParameter(str(exc)) from exc
    pending = await inbox.list_pending(operation_id)
    claimed = [wakeup_ref_payload(item) for item in operation.pending_wakeups]
    if json_mode:
        typer.echo(
            json.dumps(
                {
                    "operation_id": operation_id,
                    "pending": [run_event_payload(item) for item in pending],
                    "claimed": claimed,
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        return
    typer.echo(f"Operation {operation_id}")
    typer.echo("Pending wakeups:")
    if pending:
        for event in pending:
            suffix = (
                f" not_before={event.not_before.isoformat()}"
                if event.not_before is not None
                else ""
            )
            typer.echo(
                f"- {event.event_type} [{event.event_id}] session={event.session_id}{suffix}"
            )
    else:
        typer.echo("- none")
    typer.echo("Claimed wakeups:")
    if claimed:
        for item in claimed:
            typer.echo(
                f"- {item['event_type']} [{item['event_id']}] session={item.get('session_id')}"
            )
    else:
        typer.echo("- none")


async def event_append_async(
    operation_ref: str,
    event_type: str,
    payload_json: str,
    reason: str | None,
    expected_last_sequence: int | None,
    yes: bool,
    json_mode: bool,
) -> None:
    settings = load_settings()
    try:
        payload = json.loads(payload_json)
    except json.JSONDecodeError as exc:
        raise typer.BadParameter(f"Invalid JSON payload: {exc.msg}.") from exc
    if not isinstance(payload, dict):
        raise typer.BadParameter("payload-json must decode to a JSON object.")
    resolver = OperationResolutionService(
        store=build_store(settings),
        replay_service=build_replay_service(settings),
        event_root=settings.data_dir / "operation_events",
        state_view_service=OperationStateViewService(),
    )
    try:
        operation_id = await resolver.resolve_operation_id(operation_ref)
    except RuntimeError as exc:
        raise typer.BadParameter(str(exc)) from exc
    service = EventStreamRepairService(
        event_store=FileOperationEventStore(settings.data_dir / "operation_events"),
        checkpoint_store=FileOperationCheckpointStore(settings.data_dir / "operation_checkpoints"),
        projector=DefaultOperationProjector(),
    )
    if not yes:
        try:
            preview = await service.preview_append(
                operation_id=operation_id,
                event_type=event_type,
                payload=payload,
                reason=reason,
            )
        except ValueError as exc:
            raise typer.BadParameter(str(exc)) from exc
        rendered = {
            "dry_run": True,
            "operation_id": preview.operation_id,
            "current_last_sequence": preview.current_last_sequence,
            "recognized": preview.recognized,
            "proposed_events": preview.proposed_events,
            "projected_status": preview.projected_status,
            "warnings": preview.warnings,
        }
        if json_mode:
            typer.echo(json.dumps(rendered, indent=2, ensure_ascii=False))
            return
        typer.echo(f"operation_id={preview.operation_id}")
        typer.echo(f"current_last_sequence={preview.current_last_sequence}")
        typer.echo(f"recognized={str(preview.recognized).lower()}")
        typer.echo(f"projected_status={preview.projected_status}")
        typer.echo("proposed_events:")
        typer.echo(json.dumps(preview.proposed_events, indent=2, ensure_ascii=False))
        for warning in preview.warnings:
            typer.echo(f"warning={warning}")
        return
    if reason is None or not reason.strip():
        raise typer.BadParameter("--reason is required unless running in dry-run mode.")
    try:
        result = await service.append(
            operation_id=operation_id,
            event_type=event_type,
            payload=payload,
            reason=reason,
            expected_last_sequence=expected_last_sequence,
        )
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    except Exception as exc:
        if exc.__class__.__name__ == "OperationEventStoreAppendConflict":
            raise typer.BadParameter(str(exc)) from exc
        raise
    rendered = {
        "dry_run": False,
        "operation_id": result.operation_id,
        "previous_last_sequence": result.previous_last_sequence,
        "stored_events": [
            {
                "sequence": item.sequence,
                "event_type": item.event_type,
                "payload": item.payload,
                "metadata": item.metadata,
            }
            for item in result.stored_events
        ],
        "projected_status": result.projected_status,
        "warnings": result.warnings,
    }
    if json_mode:
        typer.echo(json.dumps(rendered, indent=2, ensure_ascii=False))
        return
    typer.echo(f"operation_id={result.operation_id}")
    typer.echo(f"previous_last_sequence={result.previous_last_sequence}")
    typer.echo(f"projected_status={result.projected_status}")
    for item in rendered["stored_events"]:
        typer.echo(f"stored_event={item['sequence']}:{item['event_type']}")
    for warning in result.warnings:
        typer.echo(f"warning={warning}")


async def sessions_async(
    operation_id: str,
    json_mode: bool,
    inspection_store_factory: Callable[[OperatorSettings], BackgroundRunInspectionStore] = (
        build_background_run_inspection_store
    ),
) -> None:
    settings = load_settings()
    supervisor = inspection_store_factory(settings)
    try:
        operation = await load_required_canonical_operation_state_async(settings, operation_id)
    except RuntimeError as exc:
        raise typer.BadParameter(str(exc)) from exc
    runs = await supervisor.list_runs(operation_id)
    run_by_id = {run.run_id: run for run in runs}
    session_views: list[dict[str, object]] = []
    for session in operation.sessions:
        payload: dict[str, object] = session_payload(session)
        run_id = session.current_execution_id
        if run_id is not None:
            run = run_by_id.get(run_id)
            if run is not None and run.progress is not None:
                payload["live_progress_updated_at"] = run.progress.updated_at.isoformat()
                payload["live_progress_message"] = run.progress.message
                if run.progress.last_event_at is not None:
                    payload["live_progress_last_event_at"] = run.progress.last_event_at.isoformat()
                if run.progress.partial_output:
                    payload["live_progress_partial_output"] = run.progress.partial_output
        session_views.append(payload)
    if json_mode:
        typer.echo(
            json.dumps(
                {
                    "operation_id": operation_id,
                    "sessions": session_views,
                    "background_runs": [execution_payload(item) for item in runs],
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        return
    typer.echo(f"Operation {operation_id}")
    typer.echo("Sessions:")
    if session_views:
        for session_view in session_views:
            suffix = (
                f" waiting={shorten_live_text(str(session_view.get('waiting_reason')), limit=80)}"
                if session_view.get("waiting_reason")
                else ""
            )
            typer.echo(
                f"- {session_view.get('session_id')} [{session_view.get('adapter_key')}] "
                f"status={session_view.get('status')} "
                f"run={session_view.get('current_execution_id') or '-'}{suffix}"
            )
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
            typer.echo(
                f"- {run.run_id} [{run.adapter_key}] "
                f"session={run.session_id or '-'} "
                f"status={run.status.value}{suffix}"
            )
    else:
        typer.echo("- none")


async def inspect_async(operation_id: str, full: bool, json_mode: bool) -> None:
    settings = load_settings()
    trace_store = build_trace_store(settings)
    event_sink = build_event_sink(settings, operation_id)
    command_inbox = build_command_inbox(settings)
    status_queries = build_status_query_service(settings)
    try:
        operation, outcome, brief, runtime_alert = await status_queries.build_status_payload(
            operation_id
        )
    except RuntimeError as exc:
        raise typer.BadParameter(str(exc)) from exc
    report = await trace_store.load_report(operation_id)
    trace_records = await trace_store.load_trace_records(operation_id)
    memos = await trace_store.load_decision_memos(operation_id)
    events = event_sink.read_events(operation_id)
    commands = [operation_command_payload(item) for item in await command_inbox.list(operation_id)]
    if operation is None:
        raise typer.BadParameter(f"Operation {operation_id!r} was not found.")
    typed_brief = cast("TraceBriefBundle | None", brief)
    if json_mode:
        payload: dict[str, object] = {
            "operation": operation_payload(operation),
            "outcome": operation_outcome_payload(outcome) if outcome is not None else None,
            "brief": trace_brief_bundle_payload(typed_brief) if typed_brief is not None else None,
            "report": report,
            "commands": commands,
            "durable_truth": PROJECTIONS.build_durable_truth_payload(
                operation, include_inactive_memory=True
            ),
        }
        if runtime_alert is not None:
            payload["runtime_alert"] = runtime_alert
        if full:
            payload["trace_records"] = [trace_record_payload(item) for item in trace_records]
            payload["decision_memos"] = [decision_memo_payload(item) for item in memos]
            payload["events"] = [run_event_payload(item) for item in events]
            payload["wakeups"] = build_wakeup_inbox(settings).read_all(operation_id)
            payload["background_runs"] = [
                execution_payload(item)
                for item in await build_background_run_inspection_store(settings).list_runs(
                    operation_id
                )
            ]
        typer.echo(json.dumps(payload, indent=2, ensure_ascii=False))
        return
    if typed_brief is not None:
        typer.echo(render_inspect_summary(operation, typed_brief, runtime_alert=runtime_alert))
    else:
        typer.echo("Operation:")
        typer.echo(json.dumps(operation_payload(operation), indent=2, ensure_ascii=False))
    if runtime_alert is not None and typed_brief is None:
        typer.echo("\nRuntime alert:")
        typer.echo(runtime_alert)
    if outcome is not None:
        typer.echo("\nOutcome:")
        typer.echo(json.dumps(operation_outcome_payload(outcome), indent=2, ensure_ascii=False))
    if report is not None:
        typer.echo("\nReport:")
        typer.echo(report)
    if operation.tasks:
        typer.echo("\nTasks:")
        typer.echo(f"Counts: {summarize_task_counts(operation)}")
        for task in operation.tasks:
            typer.echo(
                f"- task-{task.task_short_id} [{task.status.value}] "
                f"{task.title} agent={task.assigned_agent or '-'}"
            )
    memory_entries = memory_payload(operation, include_inactive=False)
    if memory_entries:
        typer.echo("\nCurrent memory:")
        for entry in memory_entries:
            scope_target = (
                format_task_line(operation, entry.scope_id)
                if entry.scope.value == "task"
                else entry.scope_id
            )
            typer.echo(f"- {entry.memory_id} [{entry.scope.value}] {scope_target}: {entry.summary}")
    if operation.artifacts:
        typer.echo("\nArtifacts:")
        for artifact in operation.artifacts:
            typer.echo(f"- {artifact.artifact_id} [{artifact.kind}] {artifact_preview(artifact)}")
    if operation.attention_requests:
        typer.echo("\nAttention requests:")
        for attention in operation.attention_requests:
            typer.echo(
                json.dumps(attention_request_payload(attention), indent=2, ensure_ascii=False)
            )
    if commands:
        typer.echo("\nCommands:")
        for command_payload in commands:
            typer.echo(json.dumps(command_payload, indent=2, ensure_ascii=False))
    if full:
        typer.echo("\nOperation state:")
        typer.echo(json.dumps(operation_payload(operation), indent=2, ensure_ascii=False))
        typer.echo("\nTrace:")
        for record in trace_records:
            typer.echo(json.dumps(trace_record_payload(record), indent=2, ensure_ascii=False))
        typer.echo("\nDecision memos:")
        for memo in memos:
            typer.echo(json.dumps(decision_memo_payload(memo), indent=2, ensure_ascii=False))
        typer.echo("\nEvents:")
        for event in events:
            typer.echo(json.dumps(run_event_payload(event), indent=2, ensure_ascii=False))
        typer.echo("\nWakeups:")
        for wakeup in build_wakeup_inbox(settings).read_all(operation_id):
            typer.echo(json.dumps(wakeup, indent=2, ensure_ascii=False))
        typer.echo("\nBackground runs:")
        for run in [
            execution_payload(item)
            for item in await build_background_run_inspection_store(settings).list_runs(
                operation_id
            )
        ]:
            typer.echo(json.dumps(run, indent=2, ensure_ascii=False))


async def context_async(operation_id: str, json_mode: bool) -> None:
    status_queries = build_status_query_service(load_settings())
    try:
        operation, _, _, _ = await status_queries.build_status_payload(operation_id)
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


async def trace_async(operation_id: str, json_mode: bool) -> None:
    settings = load_settings()
    trace_store = build_trace_store(settings)
    event_sink = build_event_sink(settings, operation_id)
    inbox = build_wakeup_inbox(settings)
    supervisor = build_background_run_inspection_store(settings)
    command_inbox = build_command_inbox(settings)
    status_queries = build_status_query_service(settings)
    try:
        operation, _, brief, _ = await status_queries.build_status_payload(operation_id)
    except RuntimeError:
        operation = None
        brief = await trace_store.load_brief_bundle(operation_id)
    trace_records = await trace_store.load_trace_records(operation_id)
    memos = await trace_store.load_decision_memos(operation_id)
    events = event_sink.read_events(operation_id)
    wakeups = inbox.read_all(operation_id)
    commands = [operation_command_payload(item) for item in await command_inbox.list(operation_id)]
    background_runs = [execution_payload(item) for item in await supervisor.list_runs(operation_id)]
    if not trace_records and not memos and not events:
        raise typer.BadParameter(f"Trace for {operation_id!r} was not found.")
    raw_log_refs: list[str] = []
    typed_brief = cast("TraceBriefBundle | None", brief)
    if typed_brief is not None:
        seen_raw_log_refs: set[str] = set()
        for turn_brief in typed_brief.agent_turn_briefs:
            for raw_log_ref in turn_brief.raw_log_refs:
                if raw_log_ref not in seen_raw_log_refs:
                    raw_log_refs.append(raw_log_ref)
                    seen_raw_log_refs.add(raw_log_ref)
    if json_mode:
        payload = {
            "operation_id": operation_id,
            "trace_records": [trace_record_payload(item) for item in trace_records],
            "decision_memos": [decision_memo_payload(item) for item in memos],
            "events": [run_event_payload(item) for item in events],
            "wakeups": wakeups,
            "background_runs": background_runs,
            "raw_log_refs": raw_log_refs,
            "commands": commands,
            "attention_requests": (
                [attention_request_payload(item) for item in operation.attention_requests]
                if operation is not None
                else []
            ),
        }
        typer.echo(json.dumps(payload, indent=2, ensure_ascii=False))
        return
    typer.echo("Trace:")
    for record in trace_records:
        typer.echo(json.dumps(trace_record_payload(record), indent=2, ensure_ascii=False))
    typer.echo("\nDecision memos:")
    for memo in memos:
        typer.echo(json.dumps(decision_memo_payload(memo), indent=2, ensure_ascii=False))
    typer.echo("\nEvents:")
    for event in events:
        typer.echo(json.dumps(run_event_payload(event), indent=2, ensure_ascii=False))
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
            typer.echo(
                json.dumps(attention_request_payload(attention), indent=2, ensure_ascii=False)
            )
    if raw_log_refs:
        typer.echo("\nRaw log refs:")
        for raw_log_ref in raw_log_refs:
            typer.echo(raw_log_ref)
