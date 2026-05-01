from __future__ import annotations

import json
from pathlib import Path

import anyio
import typer

from agent_operator.application.commands.operation_attention import OperationAttentionCoordinator
from agent_operator.application.ticketing import TicketReportingService
from agent_operator.bootstrap import build_store, build_trace_store
from agent_operator.config import load_global_config

from ..app import app, show_app
from ..helpers.rendering import (
    PROJECTIONS,
    artifact_preview,
    format_task_line,
    memory_payload,
    summarize_task_counts,
)
from ..helpers.resolution import (
    load_required_canonical_operation_state_async,
    resolve_operation_id,
    resolve_operation_id_async,
)
from ..helpers.services import (
    build_operation_dashboard_query_service,
    build_status_query_service,
    load_settings,
)
from ..options import CODEX_HOME_OPTION, JSON_OPTION, MEMORY_ALL_OPTION, WATCH_POLL_INTERVAL_OPTION
from ..workflows import dashboard_async, watch_async


@app.command()
def attention(
    operation_ref: str,
    json_mode: bool = typer.Option(False, "--json", help="Emit machine-readable JSON."),
) -> None:
    settings = load_settings()

    async def _attention() -> None:
        resolved_operation_id = await resolve_operation_id_async(operation_ref)
        operation = await load_required_canonical_operation_state_async(
            settings, resolved_operation_id
        )
        payload = [PROJECTIONS.attention_payload(item) for item in operation.attention_requests]
        if json_mode:
            typer.echo(
                json.dumps(
                    {"operation_id": resolved_operation_id, "attention_requests": payload},
                    indent=2,
                    ensure_ascii=False,
                )
            )
            return
        typer.echo(f"Operation {resolved_operation_id}")
        typer.echo("Attention requests:")
        if not payload:
            typer.echo("- none")
            return
        for item in payload:
            status = item["status"]
            attention_type = item["attention_type"]
            blocking = item["blocking"]
            typer.echo(
                f"- {item['attention_id']} [{status}] type={attention_type} blocking={blocking}"
            )
            typer.echo(f"  title: {item['title']}")
            typer.echo(f"  question: {item['question']}")
            if item.get("context_brief"):
                typer.echo(f"  context: {item['context_brief']}")
            if item.get("suggested_options"):
                typer.echo(
                    "  options: " + ", ".join(str(option) for option in item["suggested_options"])
                )
            if item.get("answer_text"):
                typer.echo(f"  answer: {item['answer_text']}")

    anyio.run(_attention)


@show_app.command("attention")
def show_attention(
    operation_ref: str,
    json_mode: bool = typer.Option(False, "--json", help="Emit machine-readable JSON."),
) -> None:
    attention(operation_ref, json_mode)


@app.command()
def tasks(
    operation_ref: str,
    json_mode: bool = typer.Option(False, "--json", help="Emit machine-readable JSON."),
) -> None:
    settings = load_settings()

    async def _tasks() -> None:
        resolved_operation_id = await resolve_operation_id_async(operation_ref)
        operation = await load_required_canonical_operation_state_async(
            settings, resolved_operation_id
        )
        payload = [PROJECTIONS.task_payload(task) for task in operation.tasks]
        if json_mode:
            typer.echo(
                json.dumps(
                    {
                        "operation_id": resolved_operation_id,
                        "task_counts": summarize_task_counts(operation),
                        "tasks": payload,
                    },
                    indent=2,
                    ensure_ascii=False,
                )
            )
            return
        typer.echo(f"Operation {resolved_operation_id}")
        typer.echo(f"Task counts: {summarize_task_counts(operation) or 'none'}")
        typer.echo("Tasks:")
        if not operation.tasks:
            typer.echo("- none")
            return
        for task in sorted(
            operation.tasks,
            key=lambda item: (-item.effective_priority, item.created_at, item.task_id),
        ):
            task_scope = task.linked_session_id or "-"
            agent = task.assigned_agent or "-"
            typer.echo(
                f"- {task.title} [{task.status.value}] task-{task.task_short_id} ({task.task_id})"
            )
            typer.echo(f"  priority={task.effective_priority} agent={agent} session={task_scope}")
            typer.echo(f"  goal: {task.goal}")
            typer.echo(f"  done: {task.definition_of_done}")
            if task.dependencies:
                typer.echo(f"  depends_on: {', '.join(task.dependencies)}")
            if task.notes:
                typer.echo(f"  notes: {' | '.join(task.notes)}")
            if task.memory_refs:
                typer.echo(f"  memory_refs: {', '.join(task.memory_refs)}")
            if task.artifact_refs:
                typer.echo(f"  artifact_refs: {', '.join(task.artifact_refs)}")

    anyio.run(_tasks)


@show_app.command("tasks")
def show_tasks(
    operation_ref: str,
    json_mode: bool = typer.Option(False, "--json", help="Emit machine-readable JSON."),
) -> None:
    tasks(operation_ref, json_mode)


@app.command()
def memory(
    operation_ref: str,
    include_all: bool = MEMORY_ALL_OPTION,
    json_mode: bool = typer.Option(False, "--json", help="Emit machine-readable JSON."),
) -> None:
    settings = load_settings()

    async def _memory() -> None:
        resolved_operation_id = await resolve_operation_id_async(operation_ref)
        operation = await load_required_canonical_operation_state_async(
            settings, resolved_operation_id
        )
        entries = memory_payload(operation, include_inactive=include_all)
        payload = [PROJECTIONS.memory_entry_payload(entry) for entry in entries]
        if json_mode:
            typer.echo(
                json.dumps(
                    {"operation_id": resolved_operation_id, "memory_entries": payload},
                    indent=2,
                    ensure_ascii=False,
                )
            )
            return
        typer.echo(f"Operation {resolved_operation_id}")
        typer.echo("Memory:")
        if not entries:
            typer.echo("- none")
            return
        for entry in entries:
            scope_id = entry.scope_id
            scope_value = entry.scope.value
            freshness = entry.freshness.value
            typer.echo(f"- {entry.memory_id} [{scope_value}:{scope_id}] {freshness}")
            typer.echo(f"  summary: {entry.summary}")
            if entry.scope.value == "task":
                typer.echo(f"  target: {format_task_line(operation, entry.scope_id)}")
            if entry.source_refs:
                typer.echo(
                    "  sources: "
                    + ", ".join(f"{ref.kind}:{ref.ref_id}" for ref in entry.source_refs)
                )

    anyio.run(_memory)


@show_app.command("memory")
def show_memory(
    operation_ref: str,
    include_all: bool = MEMORY_ALL_OPTION,
    json_mode: bool = typer.Option(False, "--json", help="Emit machine-readable JSON."),
) -> None:
    memory(operation_ref, include_all, json_mode)


@app.command()
def artifacts(
    operation_ref: str,
    json_mode: bool = typer.Option(False, "--json", help="Emit machine-readable JSON."),
) -> None:
    settings = load_settings()

    async def _artifacts() -> None:
        resolved_operation_id = await resolve_operation_id_async(operation_ref)
        operation = await load_required_canonical_operation_state_async(
            settings, resolved_operation_id
        )
        payload = [PROJECTIONS.artifact_payload(artifact) for artifact in operation.artifacts]
        if json_mode:
            typer.echo(
                json.dumps(
                    {"operation_id": resolved_operation_id, "artifacts": payload},
                    indent=2,
                    ensure_ascii=False,
                )
            )
            return
        typer.echo(f"Operation {resolved_operation_id}")
        typer.echo("Artifacts:")
        if not operation.artifacts:
            typer.echo("- none")
            return
        for artifact in operation.artifacts:
            task_ref = format_task_line(operation, artifact.task_id)
            artifact_session = artifact.session_id or "-"
            typer.echo(
                f"- {artifact.artifact_id} [{artifact.kind}] producer={artifact.producer} "
                f"task={task_ref} session={artifact_session}"
            )
            typer.echo(f"  content: {artifact_preview(artifact)}")
            if artifact.raw_ref:
                typer.echo(f"  raw_ref: {artifact.raw_ref}")

    anyio.run(_artifacts)


@show_app.command("artifacts")
def show_artifacts(
    operation_ref: str,
    json_mode: bool = typer.Option(False, "--json", help="Emit machine-readable JSON."),
) -> None:
    artifacts(operation_ref, json_mode)


@app.command()
def report(
    operation_ref: str,
    ticket: bool = typer.Option(False, "--ticket", help="Retry PM ticket reporting."),
    json_mode: bool = typer.Option(False, "--json", help="Emit a machine-readable report payload."),
) -> None:
    resolved_operation_id = resolve_operation_id(operation_ref)
    settings = load_settings()
    trace_store = build_trace_store(settings)
    status_queries = build_status_query_service(settings)
    store = build_store(settings)

    async def _report() -> None:
        if ticket:
            operation = await load_required_canonical_operation_state_async(
                settings, resolved_operation_id
            )
            outcome = await store.load_outcome(resolved_operation_id)
            if outcome is None:
                raise typer.BadParameter(
                    f"Ticket report for {resolved_operation_id!r} was not found."
                )
            reporter = TicketReportingService(
                store=store,
                global_config=load_global_config(),
                attention_coordinator=OperationAttentionCoordinator(),
            )
            changed = await reporter.retry(operation, outcome)
            payload = {
                "operation_id": resolved_operation_id,
                "ticket_reported": operation.goal.external_ticket.reported
                if operation.goal.external_ticket is not None
                else False,
                "changed": changed,
            }
            if json_mode:
                typer.echo(json.dumps(payload, indent=2, ensure_ascii=False))
                return
            typer.echo(
                "Ticket reporting retried."
                if changed
                else "Ticket reporting was already complete or silent."
            )
            return
        try:
            operation, outcome, brief, _ = await status_queries.build_status_payload(
                resolved_operation_id
            )
        except RuntimeError as exc:
            raise typer.BadParameter(
                f"Report for {resolved_operation_id!r} was not found."
            ) from exc
        report_text = await trace_store.load_report(resolved_operation_id)
        if json_mode:
            dashboard_queries = build_operation_dashboard_query_service(
                settings,
                operation_id=resolved_operation_id,
                codex_home=Path.home() / ".codex",
            )
            try:
                dashboard_payload = await dashboard_queries.load_payload(resolved_operation_id)
            except RuntimeError as exc:
                raise typer.BadParameter(
                    f"Report for {resolved_operation_id!r} was not found."
                ) from exc
            payload = {
                "operation_id": resolved_operation_id,
                "brief": dashboard_payload.get("brief")
                or dashboard_payload.get("operation_brief")
                or (PROJECTIONS.brief_bundle_payload(brief) if brief is not None else None),
                "outcome": dashboard_payload.get("outcome")
                or (PROJECTIONS.outcome_payload(outcome) if outcome is not None else None),
                "report": dashboard_payload.get("report")
                or dashboard_payload.get("report_text")
                or report_text,
                "durable_truth": dashboard_payload.get("durable_truth")
                or (
                    PROJECTIONS.build_durable_truth_payload(operation, include_inactive_memory=True)
                    if operation is not None
                    else None
                ),
            }
            typer.echo(json.dumps(payload, indent=2, ensure_ascii=False))
            return
        if operation is None or report_text is None:
            raise typer.BadParameter(f"Report for {resolved_operation_id!r} was not found.")
        typer.echo(report_text)

    anyio.run(_report)


@show_app.command("report")
def show_report(
    operation_ref: str,
    ticket: bool = typer.Option(False, "--ticket", help="Retry PM ticket reporting."),
    json_mode: bool = typer.Option(False, "--json", help="Emit a machine-readable report payload."),
) -> None:
    report(operation_ref, ticket, json_mode)


@app.command()
def dashboard(
    operation_ref: str,
    once: bool = typer.Option(False, "--once", help="Render a single dashboard snapshot and exit."),
    json_mode: bool = typer.Option(
        False, "--json", help="Emit a machine-readable dashboard snapshot."
    ),
    poll_interval: float = WATCH_POLL_INTERVAL_OPTION,
    codex_home: Path = CODEX_HOME_OPTION,
) -> None:
    anyio.run(
        dashboard_async,
        resolve_operation_id(operation_ref),
        once,
        json_mode,
        poll_interval,
        codex_home,
    )


@show_app.command("dashboard")
def show_dashboard(
    operation_ref: str,
    once: bool = typer.Option(False, "--once", help="Render a single dashboard snapshot and exit."),
    json_mode: bool = typer.Option(
        False, "--json", help="Emit a machine-readable dashboard snapshot."
    ),
    poll_interval: float = WATCH_POLL_INTERVAL_OPTION,
    codex_home: Path = CODEX_HOME_OPTION,
) -> None:
    dashboard(operation_ref, once, json_mode, poll_interval, codex_home)


@app.command()
def watch(
    operation_ref: str,
    once: bool = typer.Option(False, "--once", help="Render one watch snapshot and exit."),
    json_mode: bool = JSON_OPTION,
    poll_interval: float = WATCH_POLL_INTERVAL_OPTION,
) -> None:
    anyio.run(watch_async, resolve_operation_id(operation_ref), once, json_mode, poll_interval)
