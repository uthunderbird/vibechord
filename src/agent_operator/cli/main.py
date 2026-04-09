from __future__ import annotations

import json
import sys
import time
from collections.abc import Callable, Iterator
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from uuid import uuid4

import anyio
import typer
from rich.console import Console as RichConsole
from rich.console import Group
from rich.live import Live
from typer.main import get_command as typer_get_command

from agent_operator.application import (
    OperationAgendaQueryService,
    OperationDashboardQueryService,
    OperationDeliveryCommandService,
    OperationProjectDashboardQueryService,
    OperationProjectionService,
)
from agent_operator.bootstrap import (
    build_background_run_inspection_store,
    build_command_inbox,
    build_event_sink,
    build_history_ledger,
    build_policy_store,
    build_service,
    build_store,
    build_trace_store,
    build_wakeup_inbox,
)
from agent_operator.cli.rendering import (
    render_dashboard as _render_dashboard_view,
)
from agent_operator.cli.rendering import (
    render_fleet_dashboard as _render_fleet_dashboard_view,
)
from agent_operator.cli.rendering import (
    render_project_dashboard as _render_project_dashboard_view,
)
from agent_operator.cli.rendering_text import (
    emit_context_lines as _emit_context_lines_view,
)
from agent_operator.cli.rendering_text import (
    format_live_event as _format_live_event_view,
)
from agent_operator.cli.rendering_text import (
    format_live_snapshot as _format_live_snapshot_view,
)
from agent_operator.cli.rendering_text import (
    render_inspect_summary as _render_inspect_summary_view,
)
from agent_operator.cli.rendering_text import (
    render_operation_list_line as _render_operation_list_line_view,
)
from agent_operator.cli.rendering_text import (
    render_status_brief as _render_status_brief_view,
)
from agent_operator.cli.tui import (
    build_fleet_workbench_controller as _build_fleet_workbench_controller,
)
from agent_operator.cli.tui import (
    run_fleet_workbench as _run_fleet_workbench,
)
from agent_operator.config import OperatorSettings
from agent_operator.domain import (
    AgentSessionHandle,
    AgentTurnBrief,
    ArtifactRecord,
    AttentionRequest,
    AttentionStatus,
    BackgroundRunStatus,
    BackgroundRuntimeMode,
    CommandTargetScope,
    ExecutionBudget,
    ExecutionState,
    InvolvementLevel,
    MemoryEntry,
    MemoryFreshness,
    OperationCommandType,
    OperationGoal,
    OperationOutcome,
    OperationPolicy,
    OperationState,
    OperationStatus,
    PolicyEntry,
    PolicyStatus,
    ProjectProfile,
    RunEvent,
    RunMode,
    RunOptions,
    RuntimeHints,
    SchedulerState,
    SessionRecord,
    TaskState,
    TaskStatus,
    TraceBriefBundle,
    describe_policy_applicability,
    policy_match_reasons,
    policy_mismatch_reasons,
)
from agent_operator.runtime import (
    AgendaItem,
    AgendaSnapshot,
    ProjectingEventSink,
    apply_project_profile_settings,
    committed_default_profile_path,
    committed_profile_dir,
    discover_local_project_profile,
    find_codex_session_log,
    format_claude_log_event,
    format_codex_log_event,
    iter_claude_log_events,
    iter_codex_log_events,
    list_project_profiles,
    load_claude_log_events,
    load_codex_log_events,
    load_project_profile,
    profile_dir,
    profile_path,
    resolve_operator_data_dir,
    resolve_project_run_config,
    write_project_profile,
)
from agent_operator.smoke import (
    extract_final_plan,
    run_alignment_post_research_plan_smoke,
    run_codex_continuation_smoke,
    run_mixed_agent_selection_smoke,
    run_mixed_code_agent_selection_smoke,
)

app = typer.Typer(no_args_is_help=False, context_settings={"help_option_names": []})
smoke_app = typer.Typer(no_args_is_help=True)
debug_app = typer.Typer(no_args_is_help=False)
project_app = typer.Typer(no_args_is_help=True)
policy_app = typer.Typer(no_args_is_help=True)
_PROJECTIONS = OperationProjectionService()


def _delivery_commands_service() -> OperationDeliveryCommandService:
    settings = _load_settings()
    return _build_delivery_commands_service(settings)


def _build_agenda_query_service(settings: OperatorSettings) -> OperationAgendaQueryService:
    return OperationAgendaQueryService(
        store=build_store(settings),
        status_service=_build_delivery_commands_service(settings),
    )


def _build_project_dashboard_query_service(
    settings: OperatorSettings,
) -> OperationProjectDashboardQueryService:
    return OperationProjectDashboardQueryService(
        agenda_queries=_build_agenda_query_service(settings),
        projection_service=_PROJECTIONS,
        policy_store=build_policy_store(settings),
    )


def _build_operation_dashboard_query_service(
    settings: OperatorSettings,
    *,
    operation_id: str,
    codex_home: Path,
) -> OperationDashboardQueryService:
    return OperationDashboardQueryService(
        status_service=_build_delivery_commands_service(settings),
        projection_service=_PROJECTIONS,
        command_inbox=build_command_inbox(settings),
        event_reader=build_event_sink(settings, operation_id),
        trace_store=build_trace_store(settings),
        build_upstream_transcript=lambda operation: _build_dashboard_upstream_transcript(
            operation,
            codex_home=codex_home,
        ),
    )


def _build_delivery_commands_service(
    settings: OperatorSettings,
    *,
    service_factory: Callable[[], object] | None = None,
) -> OperationDeliveryCommandService:
    factory = service_factory or (lambda: build_service(settings))
    return OperationDeliveryCommandService(
        store=build_store(settings),
        command_inbox=build_command_inbox(settings),
        projection_service=_PROJECTIONS,
        trace_store=build_trace_store(settings),
        background_inspection_store=build_background_run_inspection_store(settings),
        wakeup_inspection_store=build_wakeup_inbox(settings),
        service_factory=factory,
        overlay_live_background_progress=_overlay_live_background_progress,
        build_runtime_alert=_build_runtime_alert,
        render_status_brief=_render_status_brief,
        render_inspect_summary=_render_inspect_summary,
        find_task_by_display_id=_find_task_by_display_id,
    )


def _build_projecting_delivery_commands_service(
    settings: OperatorSettings,
    *,
    operation_id: str | None,
    projector: _CliEventProjector,
) -> OperationDeliveryCommandService:
    return _build_delivery_commands_service(
        settings,
        service_factory=lambda: build_service(
            settings,
            event_sink=ProjectingEventSink(
                build_event_sink(settings, operation_id),
                projector.handle_event,
            ),
        ),
    )


MAX_ITERATIONS_OPTION = typer.Option(None, help="Maximum operator iterations.")
ALLOWED_AGENT_OPTION = typer.Option(None, help="Allowed adapter keys.")
RUN_AGENT_OPTION = typer.Option(
    None,
    "--agent",
    help="Preferred adapter key. Repeat to replace profile defaults.",
)
ATTACH_SESSION_OPTION = typer.Option(None, help="Attach an existing external session id.")
ATTACH_AGENT_OPTION = typer.Option(None, help="Adapter key for the attached session.")
ATTACH_NAME_OPTION = typer.Option(None, help="Human-readable name for the attached session.")
ATTACH_WORKING_DIR_OPTION = typer.Option(
    None,
    help="Working directory associated with the attached session.",
)
HARNESS_OPTION = typer.Option(
    None,
    "--harness",
    help="Operator harness instructions kept separate from the objective.",
)
RUN_SUCCESS_CRITERION_OPTION = typer.Option(
    None,
    "--success-criterion",
    help="Success criterion to record for this run. Repeat to replace profile defaults.",
)
RUN_MODE_OPTION = typer.Option(
    None,
    "--mode",
    help=(
        "Runtime mode for `run`: attached keeps the operator alive; resumable backgrounds "
        "work and return. Defaults to the project profile when set, otherwise attached."
    ),
)
JSON_OPTION = typer.Option(False, "--json", help="Emit machine-readable JSON lines.")
WATCH_POLL_INTERVAL_OPTION = typer.Option(
    0.5,
    "--poll-interval",
    min=0.05,
    help="Polling interval in seconds for live watch mode.",
)
INVOLVEMENT_OPTION = typer.Option(
    None,
    "--involvement",
    help="User involvement/autonomy level for this run.",
)
PROJECT_OPTION = typer.Option(None, "--project", help="Project profile name.")
PROJECT_CWD_OPTION = typer.Option(None, "--cwd", help="Working directory for the project.")
PROJECT_PATH_OPTION = typer.Option(
    None,
    "--path",
    help="Additional project-relative target paths to keep in the profile.",
)
PROJECT_AGENT_OPTION = typer.Option(
    None,
    "--agent",
    help="Default adapter keys for runs launched with this profile.",
)
PROJECT_OBJECTIVE_OPTION = typer.Option(
    None,
    "--objective",
    help="Default objective for this project profile.",
)
PROJECT_HARNESS_OPTION = typer.Option(
    None,
    "--harness",
    help="Default harness instructions for this project.",
)
PROJECT_SUCCESS_CRITERION_OPTION = typer.Option(
    None,
    "--success-criterion",
    help="Default success criteria to record in the profile.",
)
PROJECT_MAX_ITERATIONS_OPTION = typer.Option(
    None,
    "--max-iterations",
    min=1,
    help="Default maximum operator iterations.",
)
PROJECT_INVOLVEMENT_OPTION = typer.Option(
    None,
    "--involvement",
    help="Default involvement level for this profile.",
)
INVOLVEMENT_LEVEL_OPTION = typer.Option(..., "--level", help="New involvement level.")
COMMAND_TYPE_OPTION = typer.Option(..., "--type", help="Command type to enqueue.")
COMMAND_SUCCESS_CRITERION_OPTION = typer.Option(
    None,
    "--success-criterion",
    help="Success criterion text for patch_success_criteria. Repeat to replace the full list.",
)
COMMAND_ALLOWED_AGENT_OPTION = typer.Option(
    None,
    "--allowed-agent",
    help="Allowed adapter key for set_allowed_agents. Repeat to replace the full list.",
)
COMMAND_MAX_ITERATIONS_OPTION = typer.Option(
    None,
    "--max-iterations",
    min=1,
    help="Maximum operator iterations for run/resume surfaces; unsupported for set_allowed_agents.",
)
COMMAND_CLEAR_SUCCESS_CRITERIA_OPTION = typer.Option(
    False,
    "--clear-success-criteria",
    help="Clear the current success criteria for patch_success_criteria.",
)
POLICY_PROJECT_OPTION = typer.Option(None, "--project", help="Project profile name.")
POLICY_SCOPE_OPTION = typer.Option(None, "--scope", help="Explicit project scope.")
POLICY_JSON_OPTION = typer.Option(False, "--json")
POLICY_TITLE_OPTION = typer.Option(None, "--title", help="Short policy title.")
POLICY_TEXT_OPTION = typer.Option(None, "--text", help="The durable policy rule text.")
POLICY_RULE_OPTION = typer.Option(None, "--rule", help="Alias for --text.")
POLICY_CATEGORY_OPTION = typer.Option("general", "--category", help="Policy category label.")
POLICY_ATTENTION_OPTION = typer.Option(
    None,
    "--attention",
    help="Promote a resolved attention request into policy.",
)
POLICY_OBJECTIVE_KEYWORD_OPTION = typer.Option(
    None,
    "--objective-keyword",
    help="Limit the policy to operations whose objective or harness contains this keyword.",
)
POLICY_TASK_KEYWORD_OPTION = typer.Option(
    None,
    "--task-keyword",
    help="Limit the policy to operations whose task titles, goals, or notes contain this keyword.",
)
POLICY_AGENT_KEY_OPTION = typer.Option(
    None,
    "--agent",
    help="Limit the policy to operations that allow or use this adapter key.",
)
POLICY_RUN_MODE_OPTION = typer.Option(
    None,
    "--run-mode",
    help="Limit the policy to a specific run mode.",
)
POLICY_INVOLVEMENT_MATCH_OPTION = typer.Option(
    None,
    "--when-involvement",
    help="Limit the policy to a specific involvement level.",
)
PROMOTE_POLICY_OBJECTIVE_KEYWORD_OPTION = typer.Option(
    None,
    "--policy-objective-keyword",
    help=(
        "Limit the promoted policy to operations whose objective or harness contains this "
        "keyword."
    ),
)
PROMOTE_POLICY_TASK_KEYWORD_OPTION = typer.Option(
    None,
    "--policy-task-keyword",
    help=(
        "Limit the promoted policy to operations whose task titles, goals, or notes contain "
        "this keyword."
    ),
)
PROMOTE_POLICY_AGENT_OPTION = typer.Option(
    None,
    "--policy-agent",
    help="Limit the promoted policy to operations that allow or use this adapter key.",
)
PROMOTE_POLICY_RUN_MODE_OPTION = typer.Option(
    None,
    "--policy-run-mode",
    help="Limit the promoted policy to a specific run mode.",
)
PROMOTE_POLICY_INVOLVEMENT_OPTION = typer.Option(
    None,
    "--policy-when-involvement",
    help="Limit the promoted policy to a specific involvement level.",
)
POLICY_REASON_OPTION = typer.Option(None, "--reason", help="Optional reason.")
POLICY_ID_OPTION = typer.Option(..., "--policy", help="Policy id to revoke.")
MEMORY_ALL_OPTION = typer.Option(
    False,
    "--all",
    help="Include stale and superseded memory entries.",
)
PROJECT_FORCE_OPTION = typer.Option(False, "--force", help="Overwrite an existing project file.")
CODEX_HOME_OPTION = typer.Option(
    Path.home() / ".codex",
    "--codex-home",
    help="Codex home directory that contains session transcripts.",
)
app.add_typer(smoke_app, name="smoke")
app.add_typer(debug_app, name="debug")
app.add_typer(project_app, name="project")
app.add_typer(policy_app, name="policy")


@debug_app.callback(invoke_without_command=True)
def debug_main(ctx: typer.Context) -> None:
    if ctx.invoked_subcommand is not None:
        return
    typer.echo(ctx.get_help())
    raise typer.Exit()


@app.callback(invoke_without_command=True)
def _iter_click_commands(command) -> list[object]:
    commands = [command]
    nested = getattr(command, "commands", None)
    if isinstance(nested, dict):
        for child in nested.values():
            commands.extend(_iter_click_commands(child))
    return commands


def _emit_help(*, show_all: bool) -> None:
    click_command = typer_get_command(app)
    commands = _iter_click_commands(click_command)
    previous_hidden: list[tuple[object, bool]] = []
    for command in commands:
        hidden = getattr(command, "hidden", None)
        if not isinstance(hidden, bool):
            continue
        name = getattr(command, "name", None)
        next_hidden = hidden
        if show_all:
            next_hidden = False
        elif name in {"debug", "smoke"}:
            next_hidden = True
        if next_hidden != hidden:
            previous_hidden.append((command, hidden))
            command.hidden = next_hidden
    try:
        typer.echo(click_command.get_help(typer.Context(click_command)))
        if show_all:
            typer.echo(
                "\nHidden Commands:\n"
                "- debug\n"
                "- smoke\n"
                "- resume\n"
                "- tick\n"
                "- daemon\n"
                "- recover\n"
                "- wakeups\n"
                "- sessions\n"
                "- command\n"
                "- context\n"
                "- trace\n"
                "- inspect"
            )
    finally:
        for command, hidden in previous_hidden:
            command.hidden = hidden


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    help_: bool = typer.Option(
        False,
        "--help",
        "-h",
        help="Show this message and exit.",
        is_eager=True,
    ),
    all_commands: bool = typer.Option(
        False,
        "--all",
        help="Show hidden commands when combined with --help.",
        is_eager=True,
    ),
) -> None:
    """Default fleet-first CLI entry surface."""
    if help_:
        _emit_help(show_all=all_commands)
        raise typer.Exit()
    if ctx.resilient_parsing or ctx.invoked_subcommand is not None:
        return
    if sys.stdout.isatty() and sys.stdin.isatty():
        anyio.run(_fleet_async, None, False, False, False, 0.5)
        raise typer.Exit()
    has_operations = anyio.run(_has_any_operations_async)
    if has_operations:
        anyio.run(_fleet_async, None, False, True, False, 0.5)
        raise typer.Exit()
    typer.echo(ctx.get_help())
    raise typer.Exit()


def _load_settings() -> OperatorSettings:
    settings = OperatorSettings()
    settings.data_dir = resolve_operator_data_dir(settings).path
    return settings


def _load_settings_with_data_dir() -> tuple[OperatorSettings, str]:
    settings = OperatorSettings()
    data_dir = resolve_operator_data_dir(settings)
    settings.data_dir = data_dir.path
    return settings, data_dir.source


def _resolve_project_profile_selection(
    settings: OperatorSettings,
    *,
    name: str | None,
) -> tuple[ProjectProfile | None, Path | None, str | None]:
    if name is not None:
        return load_project_profile(settings, name), profile_path(settings, name), "explicit_cli"
    selection = discover_local_project_profile(settings)
    return selection.profile, selection.path, selection.source


def _emit_free_mode_stub(*, cwd: Path, json_mode: bool) -> None:
    payload = {
        "mode": "free_stub",
        "cwd": str(cwd),
        "message": (
            "No local operator-profile.yaml was found. Project mode is available via "
            "operator-profile.yaml in the launch directory. Freeform live supervision mode "
            "is planned but not implemented yet."
        ),
    }
    if json_mode:
        typer.echo(json.dumps(payload, indent=2, ensure_ascii=False))
        return
    typer.echo(f"# free_mode_stub cwd={cwd}")
    typer.echo(payload["message"])


def _normalize_agent_override(
    *,
    agent: list[str] | None,
) -> list[str] | None:
    if agent is None:
        return None
    normalized = [item.strip() for item in agent if item.strip()]
    return normalized or None


def _update_gitignore_with_operator_dir(root: Path) -> bool:
    path = root / ".gitignore"
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    lines = existing.splitlines()
    if ".operator/" in lines:
        return False
    if existing and not existing.endswith("\n"):
        existing += "\n"
    existing += ".operator/\n"
    path.write_text(existing, encoding="utf-8")
    return True


def _write_default_project_profile(
    *,
    root: Path,
    profile: ProjectProfile,
    force: bool = False,
) -> Path:
    path = committed_default_profile_path(cwd=root)
    if path.exists() and not force:
        raise RuntimeError("Project already configured (operator-profile.yaml found).")
    payload = profile.model_dump(mode="json")
    payload = {key: value for key, value in payload.items() if value not in (None, [], {})}
    import yaml  # type: ignore[import-untyped]

    path.write_text(
        yaml.dump(
            payload,
            sort_keys=False,
            allow_unicode=True,
            default_flow_style=False,
        ),
        encoding="utf-8",
    )
    return path


def _policy_applicability_payload(
    objective_keyword: list[str] | None,
    task_keyword: list[str] | None,
    agent: list[str] | None,
    run_mode: list[RunMode] | None,
    involvement: list[InvolvementLevel] | None,
) -> dict[str, object]:
    payload: dict[str, object] = {}
    if objective_keyword:
        payload["objective_keywords"] = [item.strip() for item in objective_keyword if item.strip()]
    if task_keyword:
        payload["task_keywords"] = [item.strip() for item in task_keyword if item.strip()]
    if agent:
        payload["agent_keys"] = [item.strip() for item in agent if item.strip()]
    if run_mode:
        payload["run_modes"] = [item.value for item in run_mode]
    if involvement:
        payload["involvement_levels"] = [item.value for item in involvement]
    return payload


def _policy_payload(
    policy: PolicyEntry, operation: OperationState | None = None
) -> dict[str, object]:
    payload = policy.model_dump(mode="json")
    payload["applicability_summary"] = describe_policy_applicability(policy)
    if operation is not None:
        payload["match_reasons"] = policy_match_reasons(policy, operation)
    return payload


def _resolve_operation_policy_scope(operation: OperationState) -> str | None:
    policy_scope = operation.policy_coverage.project_scope
    if isinstance(policy_scope, str) and policy_scope.strip():
        return policy_scope.strip()
    raw_scope = operation.goal.metadata.get("policy_scope")
    if isinstance(raw_scope, str) and raw_scope.strip():
        return raw_scope.strip()
    return None


def _policy_evaluation_payload(policy: PolicyEntry, operation: OperationState) -> dict[str, object]:
    payload = _policy_payload(policy, operation)
    match_reasons = payload.get("match_reasons")
    matched = isinstance(match_reasons, list) and len(match_reasons) > 0
    payload["applies_now"] = matched
    payload["skip_reasons"] = [] if matched else policy_mismatch_reasons(policy, operation)
    return payload


def _build_runtime_alert(
    *,
    status: OperationStatus,
    wakeups: list[dict[str, object]],
    background_runs: list[dict[str, object]],
) -> str | None:
    if status is not OperationStatus.RUNNING:
        return None
    if wakeups:
        return (
            f"{len(wakeups)} wakeup(s) are pending reconciliation. "
            "Run `operator resume <operation-id>`."
        )
    has_terminal_run = any(
        run.get("status")
        in {
            BackgroundRunStatus.COMPLETED.value,
            BackgroundRunStatus.FAILED.value,
            BackgroundRunStatus.CANCELLED.value,
        }
        for run in background_runs
    )
    has_live_run = any(
        run.get("status")
        in {
            BackgroundRunStatus.PENDING.value,
            BackgroundRunStatus.RUNNING.value,
        }
        for run in background_runs
    )
    if has_terminal_run and not has_live_run:
        return (
            "A background run is already terminal, but this operation still appears "
            "running. Run `operator resume <operation-id>`."
        )
    return None


@app.command()
def run(
    objective: str | None = typer.Argument(None, help="Objective for this run."),
    project: str | None = PROJECT_OPTION,
    harness: str | None = HARNESS_OPTION,
    success_criterion: list[str] | None = RUN_SUCCESS_CRITERION_OPTION,
    max_iterations: int | None = MAX_ITERATIONS_OPTION,
    agent: list[str] | None = RUN_AGENT_OPTION,
    mode: RunMode | None = RUN_MODE_OPTION,
    involvement: InvolvementLevel | None = INVOLVEMENT_OPTION,
    attach_session: str | None = ATTACH_SESSION_OPTION,
    attach_agent: str | None = ATTACH_AGENT_OPTION,
    attach_name: str | None = ATTACH_NAME_OPTION,
    attach_working_dir: Path | None = ATTACH_WORKING_DIR_OPTION,
    json_mode: bool = JSON_OPTION,
) -> None:
    """Run the operator against a goal."""

    normalized_agents = _normalize_agent_override(agent=agent)

    anyio.run(
        _run_async,
        objective,
        project,
        harness,
        success_criterion,
        max_iterations,
        normalized_agents,
        mode,
        involvement,
        attach_session,
        attach_agent,
        attach_name,
        attach_working_dir,
        json_mode,
    )


@app.command()
def init(
    cwd: Path | None = PROJECT_CWD_OPTION,
    path: list[Path] | None = PROJECT_PATH_OPTION,
    agent: list[str] | None = PROJECT_AGENT_OPTION,
    objective: str | None = PROJECT_OBJECTIVE_OPTION,
    harness: str | None = PROJECT_HARNESS_OPTION,
    success_criterion: list[str] | None = PROJECT_SUCCESS_CRITERION_OPTION,
    max_iterations: int | None = PROJECT_MAX_ITERATIONS_OPTION,
    involvement: InvolvementLevel | None = PROJECT_INVOLVEMENT_OPTION,
    force: bool = PROJECT_FORCE_OPTION,
    json_mode: bool = typer.Option(False, "--json"),
) -> None:
    """Set up operator in the current project."""

    root = committed_default_profile_path().parent
    profile = ProjectProfile(
        name=root.name,
        cwd=cwd or Path("."),
        paths=list(path or []),
        default_objective=objective,
        default_agents=list(agent or []),
        default_harness_instructions=harness,
        default_success_criteria=list(success_criterion or []),
        default_max_iterations=max_iterations,
        default_involvement_level=involvement,
    )
    try:
        profile_path = _write_default_project_profile(root=root, profile=profile, force=force)
    except RuntimeError as exc:
        raise typer.BadParameter(str(exc)) from exc
    committed_dir = committed_profile_dir(cwd=root)
    committed_dir.mkdir(parents=True, exist_ok=True)
    gitignore_updated = _update_gitignore_with_operator_dir(root)
    payload = {
        "project_root": str(root),
        "profile_path": str(profile_path),
        "profiles_dir": str(committed_dir),
        "gitignore_updated": gitignore_updated,
        "profile": profile.model_dump(mode="json"),
    }
    if json_mode:
        typer.echo(json.dumps(payload, indent=2, ensure_ascii=False))
        return
    typer.echo(f"Initialized project profile: {profile_path}")


@app.command(hidden=True)
def resume(
    operation_id: str,
    max_cycles: int = typer.Option(8, help="Maximum scheduler cycles for this resume."),
    json_mode: bool = JSON_OPTION,
) -> None:
    """Resume a persisted operation."""

    anyio.run(_resume_async, operation_id, max_cycles, json_mode)


@debug_app.command("resume")
def debug_resume(
    operation_id: str,
    max_cycles: int = typer.Option(8, help="Maximum scheduler cycles for this resume."),
    json_mode: bool = JSON_OPTION,
) -> None:
    """Resume a persisted operation."""

    resume(operation_id, max_cycles, json_mode)


@app.command(hidden=True)
def tick(operation_id: str) -> None:
    """Advance a persisted operation by exactly one scheduler cycle."""

    anyio.run(_tick_async, operation_id)


@debug_app.command("tick")
def debug_tick(operation_id: str) -> None:
    """Advance a persisted operation by exactly one scheduler cycle."""

    tick(operation_id)


@app.command(hidden=True)
def daemon(
    once: bool = typer.Option(
        False,
        "--once",
        help="Run a single sweep for ready wakeups and exit.",
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
    """Resume operations automatically when scheduled wakeups become due."""

    anyio.run(_daemon_async, once, poll_interval, max_cycles_per_operation, json_mode)


@debug_app.command("daemon")
def debug_daemon(
    once: bool = typer.Option(
        False,
        "--once",
        help="Run a single sweep for ready wakeups and exit.",
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
    """Resume operations automatically when scheduled wakeups become due."""

    daemon(once, poll_interval, max_cycles_per_operation, json_mode)


@app.command(hidden=True)
def recover(
    operation_id: str,
    session_id: str | None = typer.Option(
        None,
        "--session",
        help=(
            "Force recovery for a specific session instead of auto-selecting "
            "the active stuck one."
        ),
    ),
    max_cycles: int = typer.Option(1, help="Maximum scheduler cycles after forced recovery."),
    json_mode: bool = JSON_OPTION,
) -> None:
    """Force recovery of a stuck agent turn or completed background run."""

    anyio.run(_recover_async, operation_id, session_id, max_cycles, json_mode)


@debug_app.command("recover")
def debug_recover(
    operation_id: str,
    session_id: str | None = typer.Option(
        None,
        "--session",
        help=(
            "Force recovery for a specific session instead of auto-selecting "
            "the active stuck one."
        ),
    ),
    max_cycles: int = typer.Option(1, help="Maximum scheduler cycles after forced recovery."),
    json_mode: bool = JSON_OPTION,
) -> None:
    """Force recovery of a stuck agent turn or completed background run."""

    recover(operation_id, session_id, max_cycles, json_mode)


def _shorten_live_text(text: str | None, *, limit: int = 100) -> str | None:
    if text is None:
        return None
    normalized = " ".join(text.strip().split())
    if not normalized:
        return None
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 1].rstrip() + "…"


def _normalize_block_text(text: str | None) -> str | None:
    if text is None:
        return None
    lines = [" ".join(line.strip().split()) for line in text.splitlines()]
    non_empty = [line for line in lines if line]
    if not non_empty:
        return None
    return "\n".join(non_empty)


def _shorten_block_text(text: str | None, *, limit: int = 320) -> str | None:
    normalized = _normalize_block_text(text)
    if normalized is None:
        return None
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 1].rstrip() + "…"


def _shorten_paragraph_text(text: str | None, *, limit: int = 220) -> str | None:
    normalized = _normalize_block_text(text)
    if normalized is None:
        return None
    single_line = " ".join(normalized.splitlines())
    if len(single_line) <= limit:
        return single_line
    return single_line[: limit - 1].rstrip() + "…"


def _latest_agent_turn_brief(brief: TraceBriefBundle | None) -> AgentTurnBrief | None:
    if brief is None or not brief.agent_turn_briefs:
        return None
    return max(
        brief.agent_turn_briefs,
        key=lambda item: (item.iteration, item.created_at),
    )


def _recent_iteration_briefs(brief: TraceBriefBundle | None, *, limit: int = 3) -> list:
    if brief is None:
        return []
    return sorted(brief.iteration_briefs, key=lambda item: item.iteration)[-limit:]


def _recent_agent_turn_briefs(brief: TraceBriefBundle | None, *, limit: int = 2) -> list:
    if brief is None:
        return []
    return sorted(
        brief.agent_turn_briefs,
        key=lambda item: (item.iteration, item.created_at),
    )[-limit:]


def _turn_work_summary(turn: AgentTurnBrief | None) -> str | None:
    if turn is None:
        return None
    summary = turn.turn_summary
    if summary is not None:
        primary = _shorten_paragraph_text(summary.actual_work_done, limit=220)
        delta = _shorten_paragraph_text(summary.state_delta, limit=220)
        if primary and delta:
            return f"{primary} {delta}"
        return primary or delta
    return _shorten_paragraph_text(turn.result_brief, limit=220)


def _turn_next_step(turn: AgentTurnBrief | None) -> str | None:
    if turn is None or turn.turn_summary is None:
        return None
    return _shorten_paragraph_text(turn.turn_summary.recommended_next_step, limit=220)


def _turn_verification_summary(turn: AgentTurnBrief | None) -> str | None:
    if turn is None or turn.turn_summary is None:
        return None
    return _shorten_paragraph_text(turn.turn_summary.verification_status, limit=180)


def _turn_blockers_summary(turn: AgentTurnBrief | None) -> str | None:
    if turn is None or turn.turn_summary is None or not turn.turn_summary.remaining_blockers:
        return None
    return " | ".join(
        _shorten_paragraph_text(item, limit=90) or item
        for item in turn.turn_summary.remaining_blockers[:3]
    )


def _render_section(title: str, lines: list[str]) -> list[str]:
    content = [line for line in lines if line.strip()]
    if not content:
        return []
    rendered = [title]
    rendered.extend(content)
    return rendered


def _overlay_live_background_progress(
    operation: OperationState,
    runs: list[ExecutionState],
) -> OperationState:
    if not runs:
        return operation
    overlaid = operation.model_copy(deep=True)
    run_by_id = {run.run_id: run for run in runs}
    for session in overlaid.sessions:
        run_id = session.current_execution_id
        if run_id is None:
            continue
        run = run_by_id.get(run_id)
        if run is None or run.progress is None:
            continue
        session.updated_at = run.progress.updated_at
        session.waiting_reason = run.progress.message
        if run.progress.last_event_at is not None:
            session.last_event_at = run.progress.last_event_at
    return overlaid


def _render_inspect_summary(
    operation: OperationState,
    brief: TraceBriefBundle | None,
    *,
    runtime_alert: str | None,
) -> str:
    return _render_inspect_summary_view(
        operation,
        summary=_PROJECTIONS.build_inspect_summary_payload(
            operation,
            brief,
            runtime_alert=runtime_alert,
        ),
        brief=brief,
        recent_iteration_briefs=_recent_iteration_briefs,
        recent_agent_turn_briefs=_recent_agent_turn_briefs,
        shorten_paragraph_text=lambda text: _shorten_paragraph_text(text, limit=180),
        turn_work_summary=_turn_work_summary,
        turn_verification_summary=_turn_verification_summary,
        turn_blockers_summary=_turn_blockers_summary,
        turn_next_step=_turn_next_step,
        open_attention_requests=_open_attention_requests,
        render_section=_render_section,
    )


def _render_operation_list_line(
    operation_id: str,
    status: str,
    *,
    objective: str,
    focus: str | None,
    latest: str | None,
    blocker: str | None,
    runtime_alert: str | None,
    scheduler: str | None = None,
    involvement: str | None = None,
) -> str:
    return _render_operation_list_line_view(
        operation_id,
        status,
        objective=objective,
        focus=focus,
        latest=latest,
        blocker=blocker,
        runtime_alert=runtime_alert,
        scheduler=scheduler,
        involvement=involvement,
    )


def _format_live_event(event: RunEvent) -> str | None:
    return _format_live_event_view(
        event,
        shorten_live_text=lambda text: _shorten_live_text(text, limit=100),
    )


def _open_attention_requests(operation: OperationState) -> list[AttentionRequest]:
    return [item for item in operation.attention_requests if item.status is AttentionStatus.OPEN]


def _build_live_snapshot(
    operation_id: str,
    operation: OperationState | None,
    outcome: OperationOutcome | None,
) -> dict[str, object]:
    return _delivery_commands_service().build_live_snapshot(operation_id, operation, outcome)


def _format_live_snapshot(snapshot: dict[str, object]) -> str:
    return _format_live_snapshot_view(
        snapshot,
        base_formatter=_PROJECTIONS.format_live_snapshot,
        shorten_live_text=lambda text: _shorten_live_text(text, limit=100),
    )


def _format_agenda_item(item: AgendaItem) -> list[str]:
    header = (
        f"- {item.operation_id} [{item.status.value}] "
        f"{_shorten_live_text(item.objective_brief, limit=96) or item.objective_brief}"
    )
    details: list[str] = []
    if item.project_profile_name is not None:
        details.append(f"project={item.project_profile_name}")
    if item.scheduler_state is not SchedulerState.ACTIVE:
        details.append(f"scheduler={item.scheduler_state.value}")
    if item.focus_brief is not None:
        details.append(f"focus={item.focus_brief}")
    if item.open_attention_count > 0:
        details.append(f"attention={item.open_attention_count}")
    if item.runnable_task_count > 0:
        details.append(f"tasks={item.runnable_task_count}")
    if item.reusable_session_count > 0:
        details.append(f"sessions={item.reusable_session_count}")
    lines = [header]
    if details:
        lines.append("  " + " ".join(details))
    if item.runtime_alert is not None:
        lines.append(
            "  alert: "
            f"{_shorten_paragraph_text(item.runtime_alert, limit=180) or item.runtime_alert}"
        )
    elif item.blocker_brief is not None:
        lines.append(
            "  blocker: "
            f"{_shorten_paragraph_text(item.blocker_brief, limit=180) or item.blocker_brief}"
        )
    if item.attention_briefs:
        lines.append(f"  attention: {' | '.join(item.attention_briefs)}")
    elif item.attention_titles:
        lines.append(f"  attention_titles: {' | '.join(item.attention_titles)}")
    if item.latest_outcome_brief is not None:
        latest_brief = (
            _shorten_paragraph_text(item.latest_outcome_brief, limit=220)
            or item.latest_outcome_brief
        )
        lines.append(
            "  latest: "
            f"{latest_brief}"
        )
    return lines


def _print_agenda_section(title: str, items: list[AgendaItem]) -> None:
    typer.echo(title)
    if not items:
        typer.echo("- none")
        return
    for item in items:
        for line in _format_agenda_item(item):
            typer.echo(line)


def _projection_control_hints(payload: dict[str, object]) -> list[str]:
    actions = payload.get("actions")
    if not isinstance(actions, list):
        return []
    hints: list[str] = []
    for item in actions:
        if not isinstance(item, dict):
            continue
        cli_command = item.get("cli_command")
        enabled = item.get("enabled", True)
        if isinstance(cli_command, str) and cli_command and enabled and cli_command not in hints:
            hints.append(cli_command)
    return hints


def _cli_projection_payload(payload: dict[str, object]) -> dict[str, object]:
    payload["control_hints"] = _projection_control_hints(payload)
    return payload


def _render_fleet_dashboard(payload: dict[str, object]) -> Group:
    return _render_fleet_dashboard_view(
        payload,
        shorten_live_text=lambda text: _shorten_live_text(text, limit=48),
    )


def _render_project_dashboard(payload: dict[str, object]) -> Group:
    return _render_project_dashboard_view(
        payload,
        shorten_live_text=lambda text: _shorten_live_text(text, limit=88),
    )


def _render_dashboard(payload: dict[str, object]) -> Group:
    return _render_dashboard_view(
        payload,
        shorten_live_text=lambda text: _shorten_live_text(text, limit=60),
    )


def _resolve_task_title(operation: OperationState, task_id: str | None) -> str | None:
    if task_id is None:
        return None
    for task in operation.tasks:
        if task.task_id == task_id:
            return task.title
    return None


def _resolve_task_short_id(operation: OperationState, task_id: str | None) -> str | None:
    if task_id is None:
        return None
    for task in operation.tasks:
        if task.task_id == task_id:
            return task.task_short_id
    return None


def _find_task_by_display_id(operation: OperationState, display_id: str) -> TaskState | None:
    """Resolve a task by UUID or short display ID (with or without 'task-' prefix)."""
    # Normalise: strip optional 'task-' prefix
    key = display_id.removeprefix("task-")
    for task in operation.tasks:
        if task.task_id == display_id or task.task_short_id == key:
            return task
    return None


async def _resolve_operation_id_async(operation_ref: str) -> str:
    settings = _load_settings()
    store = build_store(settings)
    summaries = await store.list_operations()
    if operation_ref == "last":
        if not summaries:
            raise typer.BadParameter("No persisted operations were found.")
        states: list[OperationState] = []
        for summary in summaries:
            operation = await store.load_operation(summary.operation_id)
            if operation is not None:
                states.append(operation)
        if not states:
            raise typer.BadParameter("No persisted operations were found.")
        latest = max(states, key=lambda item: item.created_at)
        return latest.operation_id
    exact = next(
        (item.operation_id for item in summaries if item.operation_id == operation_ref),
        None,
    )
    if exact is not None:
        return exact
    matches = [
        item.operation_id
        for item in summaries
        if item.operation_id.startswith(operation_ref)
    ]
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        candidates = ", ".join(sorted(matches))
        raise typer.BadParameter(
            f"Operation reference {operation_ref!r} is ambiguous. Matches: {candidates}"
        )
    raise typer.BadParameter(f"Operation {operation_ref!r} was not found.")


def _resolve_operation_id(operation_ref: str) -> str:
    return anyio.run(_resolve_operation_id_async, operation_ref)


def _format_task_line(operation: OperationState, task_id: str | None) -> str:
    title = _resolve_task_title(operation, task_id)
    if title is None:
        return task_id or "-"
    short_id = _resolve_task_short_id(operation, task_id)
    display_id = f"task-{short_id}" if short_id else task_id
    return f"{title} ({display_id})"


def _summarize_task_counts(operation: OperationState) -> str:
    counts = {status: 0 for status in TaskStatus}
    for task in operation.tasks:
        counts[task.status] += 1
    return ", ".join(
        f"{status.value}={counts[status]}"
        for status in (
            TaskStatus.READY,
            TaskStatus.RUNNING,
            TaskStatus.BLOCKED,
            TaskStatus.COMPLETED,
            TaskStatus.FAILED,
            TaskStatus.CANCELLED,
            TaskStatus.PENDING,
        )
        if counts[status] > 0
    )


def _artifact_preview(artifact: ArtifactRecord, *, limit: int = 100) -> str:
    return _shorten_live_text(artifact.content, limit=limit) or artifact.kind


def _memory_payload(
    operation: OperationState,
    *,
    include_inactive: bool,
) -> list[MemoryEntry]:
    entries = sorted(operation.memory_entries, key=lambda item: item.created_at)
    if include_inactive:
        return entries
    return [entry for entry in entries if entry.freshness is MemoryFreshness.CURRENT]


def _operation_payload(operation: OperationState) -> dict[str, object]:
    return _PROJECTIONS.operation_payload(operation)


def _session_payload(session: SessionRecord) -> dict[str, object]:
    return _PROJECTIONS.session_payload(session)


def _emit_context_lines(payload: dict[str, object], *, operation_id: str) -> list[str]:
    return _emit_context_lines_view(payload, operation_id=operation_id)


def _render_status_brief(operation: OperationState) -> str:
    return _render_status_brief_view(
        operation,
        open_attention_count=len(_open_attention_requests(operation)),
        summarize_task_counts=_summarize_task_counts,
    )


def _resolve_history_entry(
    operation_ref: str,
    entries: list[dict[str, object]],
) -> dict[str, object]:
    if not entries:
        raise typer.BadParameter("No committed history entries were found.")
    if operation_ref == "last":
        return entries[-1]
    exact_matches = [item for item in entries if item.get("op_id") == operation_ref]
    if exact_matches:
        return exact_matches[-1]
    prefix_matches = [
        item
        for item in entries
        if isinstance(item.get("op_id"), str) and item["op_id"].startswith(operation_ref)
    ]
    unique_ids = sorted({str(item["op_id"]) for item in prefix_matches})
    if len(unique_ids) == 1:
        for item in reversed(entries):
            if item.get("op_id") == unique_ids[0]:
                return item
    if len(unique_ids) > 1:
        raise typer.BadParameter(
            f"Operation reference {operation_ref!r} is ambiguous in committed history: "
            + ", ".join(unique_ids[:5])
            + ("..." if len(unique_ids) > 5 else "")
        )
    raise typer.BadParameter(
        f"Operation reference {operation_ref!r} was not found in committed history."
    )


def _resolve_claude_log_path_for_session(
    session: AgentSessionHandle,
) -> Path:
    return _resolve_jsonl_log_path_for_session(session, provider="Claude")


def _resolve_jsonl_log_path_for_session(
    session: AgentSessionHandle,
    *,
    provider: str,
) -> Path:
    raw_path = session.metadata.get("log_path")
    if not isinstance(raw_path, str) or not raw_path.strip():
        raise typer.BadParameter(
            f"{provider} log path for session {session.session_id!r} is not available."
        )
    path = Path(raw_path)
    if not path.exists():
        raise typer.BadParameter(
            f"{provider} log for session {session.session_id!r} was not found at {str(path)!r}."
        )
    return path


def _first_non_empty_str(*items: object) -> str | None:
    for item in items:
        if isinstance(item, str) and item.strip():
            return item.strip()
    return None


@dataclass(slots=True)
class OpencodeLogEvent:
    timestamp: str
    category: str
    summary: str
    details: dict[str, Any]


def _parse_opencode_log_line(raw: str) -> OpencodeLogEvent | None:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return OpencodeLogEvent(
            timestamp="-",
            category="raw",
            summary=_shorten_live_text(raw, limit=120) or "",
            details={"raw": raw},
        )
    if not isinstance(payload, dict):
        return OpencodeLogEvent(
            timestamp="-",
            category="raw",
            summary=_shorten_live_text(str(payload), limit=120) or "",
            details={"raw": payload},
        )
    timestamp = str(payload.get("timestamp", "-"))
    category = (
        _first_non_empty_str(
            payload.get("type"),
            payload.get("category"),
            payload.get("event"),
            payload.get("kind"),
            payload.get("subtype"),
        )
        or "event"
    )
    summary = (
        _first_non_empty_str(
            payload.get("summary"),
            payload.get("message"),
            payload.get("result"),
            payload.get("text"),
            payload.get("content"),
        )
        or _shorten_live_text(json.dumps(payload, ensure_ascii=False), limit=120)
        or "-"
    )
    return OpencodeLogEvent(
        timestamp=timestamp,
        category=category,
        summary=summary,
        details=payload,
    )


def load_opencode_log_events(path: Path) -> list[OpencodeLogEvent]:
    events: list[OpencodeLogEvent] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            raw = line.strip()
            if not raw:
                continue
            parsed = _parse_opencode_log_line(raw)
            if parsed is not None:
                events.append(parsed)
    return events


def iter_opencode_log_events(
    path: Path,
    *,
    follow: bool = False,
    poll_interval_seconds: float = 1.0,
) -> Iterator[OpencodeLogEvent]:
    with path.open(encoding="utf-8") as handle:
        while True:
            position = handle.tell()
            line = handle.readline()
            if line:
                parsed = _parse_opencode_log_line(line.strip())
                if parsed is not None:
                    yield parsed
                continue
            if not follow:
                break
            handle.seek(position)
            time.sleep(poll_interval_seconds)


def format_opencode_log_event(event: OpencodeLogEvent) -> str:
    return f"{event.timestamp} [{event.category}] {event.summary}"


def _resolve_claude_log_path(operation: OperationState) -> tuple[AgentSessionHandle, Path]:
    session = next(
        (item.handle for item in operation.sessions if item.adapter_key == "claude_acp"),
        None,
    )
    if session is None:
        raise typer.BadParameter(
            f"Operation {operation.operation_id!r} does not have a claude_acp session."
        )
    return session, _resolve_claude_log_path_for_session(
        session,
    )


def _resolve_log_target(
    operation: OperationState,
    *,
    agent: str,
) -> tuple[str, AgentSessionHandle]:
    normalized = agent.strip().lower()
    if normalized not in {"auto", "codex", "claude", "opencode"}:
        raise typer.BadParameter(
            "--agent must be one of: auto, codex, claude, or opencode"
        )
    session_handles: list[AgentSessionHandle] = [session.handle for session in operation.sessions]
    if normalized == "codex":
        session = next((item for item in session_handles if item.adapter_key == "codex_acp"), None)
        if session is None:
            raise typer.BadParameter(
                f"Operation {operation.operation_id!r} does not have a codex_acp session."
            )
        return "codex", session
    if normalized == "claude":
        session = next((item for item in session_handles if item.adapter_key == "claude_acp"), None)
        if session is None:
            raise typer.BadParameter(
                f"Operation {operation.operation_id!r} does not have a claude_acp session."
            )
        return "claude", session
    if normalized == "opencode":
        session = next(
            (item for item in session_handles if item.adapter_key == "opencode_acp"),
            None,
        )
        if session is None:
            raise typer.BadParameter(
                f"Operation {operation.operation_id!r} does not have an opencode_acp session."
            )
        return "opencode", session
    active = operation.active_session
    if active is not None:
        if active.adapter_key == "codex_acp":
            return "codex", active
        if active.adapter_key == "claude_acp":
            return "claude", active
        if active.adapter_key == "opencode_acp":
            return "opencode", active
    supported = [
        item
        for item in session_handles
        if item.adapter_key in {"codex_acp", "claude_acp", "opencode_acp"}
    ]
    adapter_keys = sorted({item.adapter_key for item in supported})
    if len(adapter_keys) == 1 and supported:
        if adapter_keys[0] == "codex_acp":
            return "codex", supported[-1]
        if adapter_keys[0] == "claude_acp":
            return "claude", supported[-1]
        return "opencode", supported[-1]
    raise typer.BadParameter(
        f"Operation {operation.operation_id!r} has multiple agent transcript candidates. "
        "Use --agent codex, --agent claude, or --agent opencode."
    )


def _build_dashboard_upstream_transcript(
    operation: OperationState,
    *,
    codex_home: Path,
) -> dict[str, object] | None:
    candidates: list[AgentSessionHandle] = []
    if operation.active_session is not None:
        candidates.append(operation.active_session)
    for session in reversed(operation.sessions):
        handle = session.handle
        if all(existing.session_id != handle.session_id for existing in candidates):
            candidates.append(handle)
    for session in candidates:
        if session.adapter_key == "codex_acp":
            path = find_codex_session_log(codex_home, session.session_id)
            if path is None:
                continue
            return {
                "adapter_key": session.adapter_key,
                "session_id": session.session_id,
                "title": "Codex Log",
                "path": str(path),
                "events": [
                    format_codex_log_event(event) for event in load_codex_log_events(path)[-6:]
                ],
                "command_hint": f"operator log {operation.operation_id} --agent codex",
            }
        if session.adapter_key == "claude_acp":
            try:
                path = _resolve_claude_log_path_for_session(
                    session,
                )
            except typer.BadParameter:
                continue
            return {
                "adapter_key": session.adapter_key,
                "session_id": session.session_id,
                "title": "Claude Log",
                "path": str(path),
                "events": [
                    format_claude_log_event(event) for event in load_claude_log_events(path)[-6:]
                ],
                "command_hint": f"operator log {operation.operation_id} --agent claude",
            }
        if session.adapter_key == "opencode_acp":
            try:
                path = _resolve_jsonl_log_path_for_session(session, provider="OpenCode")
            except typer.BadParameter:
                continue
            return {
                "adapter_key": session.adapter_key,
                "session_id": session.session_id,
                "title": "OpenCode Log",
                "path": str(path),
                "events": [
                    format_opencode_log_event(event)
                    for event in load_opencode_log_events(path)[-6:]
                ],
                "command_hint": f"operator log {operation.operation_id} --agent opencode",
            }
    return None


class _CliEventProjector:
    def __init__(self, *, json_mode: bool) -> None:
        self._json_mode = json_mode

    def emit_operation(self, operation_id: str) -> None:
        if self._json_mode:
            typer.echo(
                json.dumps(
                    {"type": "operation", "operation_id": operation_id},
                    ensure_ascii=False,
                )
            )
            return
        typer.echo(f"operation_id={operation_id}", err=True)

    def handle_event(self, event: RunEvent) -> None:
        if self._json_mode:
            typer.echo(
                json.dumps(
                    {"type": "event", "event": event.model_dump(mode="json")},
                    ensure_ascii=False,
                )
            )
            return
        rendered = _format_live_event(event)
        if rendered is not None:
            typer.echo(rendered)

    def emit_snapshot(self, snapshot: dict[str, object]) -> None:
        if self._json_mode:
            typer.echo(
                json.dumps(
                    {"type": "snapshot", "snapshot": snapshot},
                    ensure_ascii=False,
                )
            )
            return
        typer.echo(_format_live_snapshot(snapshot))

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


@app.command(hidden=True)
def wakeups(
    operation_id: str,
    json_mode: bool = typer.Option(False, "--json", help="Emit JSON payload."),
) -> None:
    """Show pending and recently claimed wakeups for an operation."""

    settings = _load_settings()
    store = build_store(settings)
    inbox = build_wakeup_inbox(settings)

    async def _wakeups() -> None:
        operation = await store.load_operation(operation_id)
        if operation is None:
            raise typer.BadParameter(f"Operation {operation_id!r} was not found.")
        pending = await inbox.list_pending(operation_id)
        claimed = [item.model_dump(mode="json") for item in operation.pending_wakeups]
        if json_mode:
            typer.echo(
                json.dumps(
                    {
                        "operation_id": operation_id,
                        "pending": [item.model_dump(mode="json") for item in pending],
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

    anyio.run(_wakeups)


@debug_app.command("wakeups")
def debug_wakeups(
    operation_id: str,
    json_mode: bool = typer.Option(False, "--json", help="Emit JSON payload."),
) -> None:
    """Show pending and recently claimed wakeups for an operation."""

    wakeups(operation_id, json_mode)


@app.command(hidden=True)
def sessions(
    operation_id: str,
    json_mode: bool = typer.Option(False, "--json", help="Emit JSON payload."),
) -> None:
    """Show session records and background run state for an operation."""

    settings = _load_settings()
    store = build_store(settings)
    supervisor = build_background_run_inspection_store(settings)

    async def _sessions() -> None:
        operation = await store.load_operation(operation_id)
        if operation is None:
            raise typer.BadParameter(f"Operation {operation_id!r} was not found.")
        runs = await supervisor.list_runs(operation_id)
        operation = _overlay_live_background_progress(operation, runs)
        if json_mode:
            typer.echo(
                json.dumps(
                    {
                        "operation_id": operation_id,
                        "sessions": [_session_payload(item) for item in operation.sessions],
                        "background_runs": [item.model_dump(mode="json") for item in runs],
                    },
                    indent=2,
                    ensure_ascii=False,
                )
            )
            return
        typer.echo(f"Operation {operation_id}")
        typer.echo("Sessions:")
        if operation.sessions:
            for session in operation.sessions:
                suffix = (
                    f" waiting={_shorten_live_text(session.waiting_reason, limit=80)}"
                    if session.waiting_reason
                    else ""
                )
                typer.echo(
                    f"- {session.session_id} [{session.adapter_key}] "
                    f"status={session.status.value} run={session.current_execution_id or '-'}"
                    f"{suffix}"
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
                        preview = _shorten_live_text(run.progress.partial_output, limit=80)
                        if preview:
                            detail = f"{detail} | {preview}" if detail else preview
                    if detail:
                        suffix = f" progress={detail}"
                typer.echo(
                    f"- {run.run_id} [{run.adapter_key}] session={run.session_id or '-'} "
                    f"status={run.status.value}{suffix}"
                )
        else:
            typer.echo("- none")

    anyio.run(_sessions)


@debug_app.command("sessions")
def debug_sessions(
    operation_id: str,
    json_mode: bool = typer.Option(False, "--json", help="Emit JSON payload."),
) -> None:
    """Show session records and background run state for an operation."""

    sessions(operation_id, json_mode)


@app.command()
def status(
    operation_ref: str,
    json_mode: bool = typer.Option(False, "--json", help="Emit machine-readable JSON."),
    brief: bool = typer.Option(False, "--brief", help="Emit a single-line summary."),
) -> None:
    """Show the default one-operation summary."""

    anyio.run(_status_async, _resolve_operation_id(operation_ref), json_mode, brief)


@app.command()
def cancel(
    operation_ref: str,
    yes: bool = typer.Option(False, "--yes", help="Skip confirmation prompt."),
    session_id: str | None = typer.Option(None, "--session", help="Cancel a specific session."),
    run_id: str | None = typer.Option(None, "--run", help="Cancel a specific background run."),
) -> None:
    """Cancel an operation or one of its background runs."""

    resolved_operation_id = _resolve_operation_id(operation_ref)
    if session_id is None and run_id is None and not yes:
        confirmed = typer.confirm(f"Cancel operation {resolved_operation_id}?")
        if not confirmed:
            typer.echo("cancelled")
            raise typer.Exit()
    anyio.run(_cancel_async, resolved_operation_id, session_id, run_id)


@app.command(hidden=True)
def command(
    operation_id: str,
    type: OperationCommandType = COMMAND_TYPE_OPTION,
    text: str | None = typer.Option(None, "--text", help="Command text payload."),
    success_criterion: list[str] | None = COMMAND_SUCCESS_CRITERION_OPTION,
    clear_success_criteria: bool = COMMAND_CLEAR_SUCCESS_CRITERIA_OPTION,
    allowed_agent: list[str] | None = COMMAND_ALLOWED_AGENT_OPTION,
    max_iterations: int | None = COMMAND_MAX_ITERATIONS_OPTION,
) -> None:
    """Enqueue a live command for an operation."""

    anyio.run(
        _enqueue_command_async,
        operation_id,
        type,
        text,
        False,
        CommandTargetScope.OPERATION,
        None,
        None,
        success_criterion,
        clear_success_criteria,
        allowed_agent,
        max_iterations,
    )


@debug_app.command("command")
def debug_command(
    operation_id: str,
    type: OperationCommandType = COMMAND_TYPE_OPTION,
    text: str | None = typer.Option(None, "--text", help="Command text payload."),
    success_criterion: list[str] | None = COMMAND_SUCCESS_CRITERION_OPTION,
    clear_success_criteria: bool = COMMAND_CLEAR_SUCCESS_CRITERIA_OPTION,
    allowed_agent: list[str] | None = COMMAND_ALLOWED_AGENT_OPTION,
    max_iterations: int | None = COMMAND_MAX_ITERATIONS_OPTION,
) -> None:
    """Enqueue a live command for an operation."""

    command(
        operation_id,
        type,
        text,
        success_criterion,
        clear_success_criteria,
        allowed_agent,
        max_iterations,
    )


@app.command()
def involvement(
    operation_id: str,
    level: InvolvementLevel = INVOLVEMENT_LEVEL_OPTION,
) -> None:
    """Update the involvement level for a running operation."""

    anyio.run(
        _enqueue_command_async,
        operation_id,
        OperationCommandType.SET_INVOLVEMENT_LEVEL,
        level.value,
    )


@app.command()
def pause(operation_id: str) -> None:
    """Request a soft pause for an attached operation."""

    anyio.run(
        _enqueue_command_async,
        _resolve_operation_id(operation_id),
        OperationCommandType.PAUSE_OPERATOR,
        None,
    )


@app.command()
def unpause(operation_id: str) -> None:
    """Resume an operation that is paused or pause-requested."""

    anyio.run(
        _enqueue_command_async,
        _resolve_operation_id(operation_id),
        OperationCommandType.RESUME_OPERATOR,
        None,
        True,
    )


@app.command("interrupt")
def interrupt(
    operation_ref: str,
    task_id: str | None = typer.Option(
        None,
        "--task",
        help="Task ID (UUID or task-XXXX short ID) whose session to stop.",
    ),
) -> None:
    """Stop the current attached agent turn without cancelling the whole operation."""

    anyio.run(_stop_turn_async, _resolve_operation_id(operation_ref), task_id)


@app.command(hidden=True)
def stop_turn(
    operation_ref: str,
    task_id: str | None = typer.Option(
        None,
        "--task",
        help="Task ID (UUID or task-XXXX short ID) whose session to stop.",
    ),
) -> None:
    """Legacy alias for interrupt."""

    interrupt(operation_ref, task_id)


@app.command()
def message(operation_ref: str, text: str) -> None:
    """Send a durable operator-level message to a running operation."""

    anyio.run(
        _enqueue_command_async,
        _resolve_operation_id(operation_ref),
        OperationCommandType.INJECT_OPERATOR_MESSAGE,
        text,
    )


@app.command()
def attention(
    operation_ref: str,
    json_mode: bool = typer.Option(False, "--json", help="Emit machine-readable JSON."),
) -> None:
    """Show attention requests for an operation."""

    settings = _load_settings()
    store = build_store(settings)

    async def _attention() -> None:
        resolved_operation_id = await _resolve_operation_id_async(operation_ref)
        operation = await store.load_operation(resolved_operation_id)
        if operation is None:
            raise typer.BadParameter(f"Operation {resolved_operation_id!r} was not found.")
        payload = [item.model_dump(mode="json") for item in operation.attention_requests]
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
            typer.echo(
                f"- {item['attention_id']} [{item['status']}] "
                f"type={item['attention_type']} blocking={item['blocking']}"
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


@app.command()
def tasks(
    operation_ref: str,
    json_mode: bool = typer.Option(False, "--json", help="Emit machine-readable JSON."),
) -> None:
    """Show the task board for an operation."""

    settings = _load_settings()
    store = build_store(settings)

    async def _tasks() -> None:
        resolved_operation_id = await _resolve_operation_id_async(operation_ref)
        operation = await store.load_operation(resolved_operation_id)
        if operation is None:
            raise typer.BadParameter(f"Operation {resolved_operation_id!r} was not found.")
        payload = [task.model_dump(mode="json") for task in operation.tasks]
        if json_mode:
            typer.echo(
                json.dumps(
                    {
                        "operation_id": resolved_operation_id,
                        "task_counts": _summarize_task_counts(operation),
                        "tasks": payload,
                    },
                    indent=2,
                    ensure_ascii=False,
                )
            )
            return
        typer.echo(f"Operation {resolved_operation_id}")
        typer.echo(f"Task counts: {_summarize_task_counts(operation) or 'none'}")
        typer.echo("Tasks:")
        if not operation.tasks:
            typer.echo("- none")
            return
        for task in sorted(
            operation.tasks,
            key=lambda item: (-item.effective_priority, item.created_at, item.task_id),
        ):
            typer.echo(
                f"- {task.title} [{task.status.value}] "
                f"task-{task.task_short_id} ({task.task_id})"
            )
            typer.echo(
                "  "
                f"priority={task.effective_priority} agent={task.assigned_agent or '-'} "
                f"session={task.linked_session_id or '-'}"
            )
            typer.echo(f"  goal: {task.goal}")
            typer.echo(f"  done: {task.definition_of_done}")
            if task.dependencies:
                typer.echo(f"  depends_on: {', '.join(task.dependencies)}")
            if task.notes:
                typer.echo(f"  notes: {' | '.join(task.notes)}")
            if task.memory_refs or task.artifact_refs:
                if task.memory_refs:
                    typer.echo(f"  memory_refs: {', '.join(task.memory_refs)}")
                if task.artifact_refs:
                    typer.echo(f"  artifact_refs: {', '.join(task.artifact_refs)}")

    anyio.run(_tasks)


@app.command()
def memory(
    operation_ref: str,
    include_all: bool = MEMORY_ALL_OPTION,
    json_mode: bool = typer.Option(False, "--json", help="Emit machine-readable JSON."),
) -> None:
    """Show distilled memory entries for an operation."""

    settings = _load_settings()
    store = build_store(settings)

    async def _memory() -> None:
        resolved_operation_id = await _resolve_operation_id_async(operation_ref)
        operation = await store.load_operation(resolved_operation_id)
        if operation is None:
            raise typer.BadParameter(f"Operation {resolved_operation_id!r} was not found.")
        entries = _memory_payload(operation, include_inactive=include_all)
        payload = [entry.model_dump(mode="json") for entry in entries]
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
            typer.echo(
                f"- {entry.memory_id} [{entry.scope.value}:{entry.scope_id}] "
                f"{entry.freshness.value}"
            )
            typer.echo(f"  summary: {entry.summary}")
            if entry.scope.value == "task":
                typer.echo(f"  target: {_format_task_line(operation, entry.scope_id)}")
            if entry.source_refs:
                source_text = ", ".join(f"{ref.kind}:{ref.ref_id}" for ref in entry.source_refs)
                typer.echo(f"  sources: {source_text}")

    anyio.run(_memory)


@app.command()
def artifacts(
    operation_ref: str,
    json_mode: bool = typer.Option(False, "--json", help="Emit machine-readable JSON."),
) -> None:
    """Show durable artifacts for an operation."""

    settings = _load_settings()
    store = build_store(settings)

    async def _artifacts() -> None:
        resolved_operation_id = await _resolve_operation_id_async(operation_ref)
        operation = await store.load_operation(resolved_operation_id)
        if operation is None:
            raise typer.BadParameter(f"Operation {resolved_operation_id!r} was not found.")
        payload = [artifact.model_dump(mode="json") for artifact in operation.artifacts]
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
            typer.echo(
                f"- {artifact.artifact_id} [{artifact.kind}] producer={artifact.producer} "
                f"task={_format_task_line(operation, artifact.task_id)} "
                f"session={artifact.session_id or '-'}"
            )
            typer.echo(f"  content: {_artifact_preview(artifact)}")
            if artifact.raw_ref:
                typer.echo(f"  raw_ref: {artifact.raw_ref}")

    anyio.run(_artifacts)


@app.command()
def answer(
    operation_ref: str,
    attention_id: str | None = typer.Argument(None, help="Attention request id."),
    text: str = typer.Option(..., "--text", help="Human answer text."),
    promote: bool = typer.Option(
        False,
        "--promote",
        help="Also promote this answered attention into durable project policy.",
    ),
    policy_title: str | None = typer.Option(
        None,
        "--policy-title",
        help="Optional policy title override when --promote is used.",
    ),
    policy_text: str | None = typer.Option(
        None,
        "--policy-text",
        help="Optional policy text override when --promote is used.",
    ),
    policy_category: str = typer.Option(
        "general",
        "--policy-category",
        help="Policy category for --promote.",
    ),
    policy_objective_keyword: list[str] | None = PROMOTE_POLICY_OBJECTIVE_KEYWORD_OPTION,
    policy_task_keyword: list[str] | None = PROMOTE_POLICY_TASK_KEYWORD_OPTION,
    policy_agent: list[str] | None = PROMOTE_POLICY_AGENT_OPTION,
    policy_run_mode: list[RunMode] | None = PROMOTE_POLICY_RUN_MODE_OPTION,
    policy_involvement: list[InvolvementLevel] | None = PROMOTE_POLICY_INVOLVEMENT_OPTION,
    policy_rationale: str | None = typer.Option(
        None,
        "--policy-rationale",
        help="Optional rationale for the promoted policy.",
    ),
) -> None:
    """Answer an open attention request."""

    anyio.run(
        _answer_async,
        _resolve_operation_id(operation_ref),
        attention_id,
        text,
        promote,
        policy_title,
        policy_text,
        policy_category,
        policy_objective_keyword,
        policy_task_keyword,
        policy_agent,
        policy_run_mode,
        policy_involvement,
        policy_rationale,
    )


@app.command("list")
def list_operations(
    json_mode: bool = typer.Option(
        False,
        "--json",
        help="Emit one JSON object per operation instead of human-readable output.",
    ),
) -> None:
    """List persisted operations."""

    anyio.run(_list_async, json_mode)


@app.command("history")
def history(
    operation_ref: str | None = typer.Argument(
        None,
        metavar="[OP]",
        help="Optional operation reference (full id, short prefix, or 'last').",
    ),
    json_mode: bool = typer.Option(False, "--json", help="Emit machine-readable JSON."),
) -> None:
    """Show committed project history from operator-history.jsonl."""

    anyio.run(_history_async, operation_ref, json_mode)


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
    """Show the cross-operation operator agenda from persisted runtime truth."""

    anyio.run(_agenda_async, project, include_all, json_mode)


@app.command()
def fleet(
    project: str | None = typer.Option(None, "--project", help="Project profile name."),
    include_all: bool = typer.Option(
        False,
        "--all",
        help="Include recent terminal operations even when actionable work exists.",
    ),
    once: bool = typer.Option(
        False,
        "--once",
        help="Render a single fleet snapshot and exit.",
    ),
    json_mode: bool = typer.Option(False, "--json", help="Emit a machine-readable fleet snapshot."),
    poll_interval: float = WATCH_POLL_INTERVAL_OPTION,
) -> None:
    """Show a live cross-operation fleet dashboard over persisted runtime truth."""

    anyio.run(_fleet_async, project, include_all, once, json_mode, poll_interval)


@project_app.command("list")
def project_list() -> None:
    """List available project profiles."""

    settings = _load_settings()
    for name in list_project_profiles(settings):
        typer.echo(name)


@project_app.command("create")
def project_create(
    name: str,
    cwd: Path | None = PROJECT_CWD_OPTION,
    path: list[Path] | None = PROJECT_PATH_OPTION,
    agent: list[str] | None = PROJECT_AGENT_OPTION,
    objective: str | None = PROJECT_OBJECTIVE_OPTION,
    harness: str | None = PROJECT_HARNESS_OPTION,
    success_criterion: list[str] | None = PROJECT_SUCCESS_CRITERION_OPTION,
    max_iterations: int | None = PROJECT_MAX_ITERATIONS_OPTION,
    involvement: InvolvementLevel | None = PROJECT_INVOLVEMENT_OPTION,
    local: bool = typer.Option(
        False,
        "--local",
        help="Write the profile to .operator/profiles instead of operator-profiles.",
    ),
    force: bool = PROJECT_FORCE_OPTION,
    json_mode: bool = typer.Option(False, "--json"),
) -> None:
    """Create or overwrite a named project profile."""

    settings = _load_settings()
    profile = ProjectProfile(
        name=name,
        cwd=cwd or Path.cwd(),
        paths=list(path or []),
        default_objective=objective,
        default_agents=list(agent or []),
        default_harness_instructions=harness,
        default_success_criteria=list(success_criterion or []),
        default_max_iterations=max_iterations,
        default_involvement_level=involvement,
    )
    try:
        profile_path = write_project_profile(settings, profile, force=force, local=local)
    except RuntimeError as exc:
        raise typer.BadParameter(str(exc)) from exc
    payload = {
        "profile_path": str(profile_path),
        "profile_scope": "local" if local else "committed",
        "profile": profile.model_dump(mode="json"),
    }
    if json_mode:
        typer.echo(json.dumps(payload, indent=2, ensure_ascii=False))
        return
    typer.echo(f"Wrote project profile: {profile_path}")


@project_app.command("inspect")
def project_inspect(
    name: str | None = typer.Argument(None),
    json_mode: bool = typer.Option(False, "--json"),
) -> None:
    """Inspect a project profile."""

    settings, _ = _load_settings_with_data_dir()
    try:
        profile, _, _ = _resolve_project_profile_selection(settings, name=name)
    except RuntimeError as exc:
        raise typer.BadParameter(str(exc)) from exc
    if profile is None:
        raise typer.BadParameter("No local operator-profile.yaml was found.")
    if json_mode:
        typer.echo(json.dumps(profile.model_dump(mode="json"), indent=2, ensure_ascii=False))
        return
    typer.echo(json.dumps(profile.model_dump(mode="json"), indent=2, ensure_ascii=False))


@project_app.command("resolve")
def project_resolve(
    name: str | None = typer.Argument(None),
    json_mode: bool = typer.Option(False, "--json"),
) -> None:
    """Show the resolved run defaults for a project profile."""

    settings, data_dir_source = _load_settings_with_data_dir()
    try:
        profile, selected_path, profile_source = _resolve_project_profile_selection(
            settings,
            name=name,
        )
    except RuntimeError as exc:
        raise typer.BadParameter(str(exc)) from exc
    if profile is None:
        raise typer.BadParameter("No local operator-profile.yaml was found.")
    resolved = resolve_project_run_config(
        settings,
        profile=profile,
        objective=None,
        harness=None,
        success_criteria=None,
        allowed_agents=None,
        max_iterations=None,
        run_mode=None,
        involvement_level=None,
    )
    payload = {
        "profile": profile.model_dump(mode="json"),
        "resolved": resolved.model_dump(mode="json"),
        "data_dir": str(settings.data_dir),
        "data_dir_source": data_dir_source,
        "profile_path": str(selected_path) if selected_path is not None else None,
        "profile_source": profile_source,
    }
    if json_mode:
        typer.echo(json.dumps(payload, indent=2, ensure_ascii=False))
        return
    typer.echo(json.dumps(payload, indent=2, ensure_ascii=False))


@project_app.command("dashboard")
def project_dashboard(
    name: str | None = typer.Argument(None),
    once: bool = typer.Option(
        False,
        "--once",
        help="Render a single dashboard snapshot and exit.",
    ),
    json_mode: bool = typer.Option(
        False,
        "--json",
        help="Emit a machine-readable project dashboard snapshot.",
    ),
    poll_interval: float = WATCH_POLL_INTERVAL_OPTION,
) -> None:
    """Show a live project-scoped dashboard over persisted truth."""

    anyio.run(_project_dashboard_async, name, once, json_mode, poll_interval)


@policy_app.command("projects")
def policy_projects() -> None:
    """List projects that already have policy entries."""

    settings = _load_settings()
    store = build_policy_store(settings)

    async def _projects() -> None:
        scopes = sorted({entry.project_scope for entry in await store.list()})
        for scope in scopes:
            typer.echo(scope)

    anyio.run(_projects)


@policy_app.command("list")
def policy_list(
    project: str | None = typer.Argument(None, help="Project profile name."),
    project_option: str | None = typer.Option(None, "--project", help="Project profile name."),
    scope: str | None = typer.Option(None, "--scope", help="Explicit project scope."),
    include_inactive: bool = typer.Option(
        False,
        "--all",
        help="Include revoked and superseded entries.",
    ),
    json_mode: bool = typer.Option(False, "--json"),
) -> None:
    """List policy entries for a project scope."""

    settings = _load_settings()
    store = build_policy_store(settings)
    resolved_scope = scope or project_option or project

    async def _list_policies() -> None:
        entries = await store.list(project_scope=resolved_scope)
        if not entries and resolved_scope is not None:
            entries = await store.list(project_scope=f"profile:{resolved_scope}")
        if not include_inactive:
            entries = [entry for entry in entries if entry.status is PolicyStatus.ACTIVE]
        payload = [_policy_payload(entry) for entry in entries]
        if json_mode:
            typer.echo(
                json.dumps(
                    {"project_scope": resolved_scope, "policy_entries": payload},
                    indent=2,
                    ensure_ascii=False,
                )
            )
            return
        typer.echo(f"Project scope: {resolved_scope or '(all)'}")
        typer.echo("Policy entries:")
        if not payload:
            typer.echo("- none")
            return
        for item in payload:
            typer.echo(f"- {item['policy_id']} [{item['status']}] {item['title']}")
            typer.echo(f"  category: {item['category']}")
            typer.echo(f"  rule: {item['rule_text']}")
            typer.echo(f"  applies: {item['applicability_summary']}")

    anyio.run(_list_policies)


@policy_app.command("inspect")
def policy_inspect(
    policy_id: str,
    json_mode: bool = POLICY_JSON_OPTION,
) -> None:
    """Inspect a single policy entry."""

    settings = _load_settings()
    store = build_policy_store(settings)

    async def _inspect_policy() -> None:
        entry = await store.load(policy_id)
        if entry is None:
            raise typer.BadParameter(f"Policy entry {policy_id!r} was not found.")
        payload = _policy_payload(entry)
        if json_mode:
            typer.echo(json.dumps(payload, indent=2, ensure_ascii=False))
            return
        typer.echo(json.dumps(payload, indent=2, ensure_ascii=False))

    anyio.run(_inspect_policy)


@policy_app.command("explain")
def policy_explain(
    operation_id: str,
    include_inactive: bool = typer.Option(
        False,
        "--all",
        help="Include revoked and superseded entries from the same project scope.",
    ),
    json_mode: bool = POLICY_JSON_OPTION,
) -> None:
    """Explain which stored project policy applies to an operation right now."""

    settings = _load_settings()
    store = build_store(settings)
    policy_store = build_policy_store(settings)

    async def _explain_policy() -> None:
        operation = await store.load_operation(operation_id)
        if operation is None:
            raise typer.BadParameter(f"Operation {operation_id!r} was not found.")
        project_scope = _resolve_operation_policy_scope(operation)
        entries = (
            await policy_store.list(project_scope=project_scope)
            if project_scope is not None
            else []
        )
        if not include_inactive:
            entries = [entry for entry in entries if entry.status is PolicyStatus.ACTIVE]
        evaluations = [_policy_evaluation_payload(entry, operation) for entry in entries]
        matched = [item for item in evaluations if bool(item.get("applies_now"))]
        skipped = [item for item in evaluations if not bool(item.get("applies_now"))]
        payload = {
            "operation_id": operation_id,
            "project_scope": project_scope,
            "matched_policy_entries": matched,
            "skipped_policy_entries": skipped,
            "has_policy_scope": project_scope is not None,
        }
        if json_mode:
            typer.echo(json.dumps(payload, indent=2, ensure_ascii=False))
            return
        typer.echo(f"Operation {operation_id}")
        typer.echo(f"Project scope: {project_scope or '-'}")
        if project_scope is None:
            typer.echo(
                "Policy evaluation: operation has no persisted policy scope, so scoped project "
                "policy cannot be evaluated."
            )
            return
        typer.echo("Matched policy:")
        if not matched:
            typer.echo("- none")
        for item in matched:
            typer.echo(f"- {item['policy_id']} [{item['status']}] {item['title']}")
            typer.echo(f"  category: {item['category']}")
            typer.echo(f"  rule: {item['rule_text']}")
            typer.echo(f"  applies: {item['applicability_summary']}")
            match_reasons = item.get("match_reasons")
            if isinstance(match_reasons, list) and match_reasons:
                typer.echo("  matched_by: " + " | ".join(str(reason) for reason in match_reasons))
        typer.echo("Skipped policy:")
        if not skipped:
            typer.echo("- none")
        for item in skipped:
            typer.echo(f"- {item['policy_id']} [{item['status']}] {item['title']}")
            typer.echo(f"  category: {item['category']}")
            typer.echo(f"  rule: {item['rule_text']}")
            typer.echo(f"  applies: {item['applicability_summary']}")
            skip_reasons = item.get("skip_reasons")
            if isinstance(skip_reasons, list) and skip_reasons:
                typer.echo("  skipped_by: " + " | ".join(str(reason) for reason in skip_reasons))

    anyio.run(_explain_policy)


@policy_app.command("record")
def policy_record(
    operation_id: str,
    title: str | None = POLICY_TITLE_OPTION,
    text: str | None = POLICY_TEXT_OPTION,
    rule: str | None = POLICY_RULE_OPTION,
    category: str = POLICY_CATEGORY_OPTION,
    objective_keyword: list[str] | None = POLICY_OBJECTIVE_KEYWORD_OPTION,
    task_keyword: list[str] | None = POLICY_TASK_KEYWORD_OPTION,
    agent: list[str] | None = POLICY_AGENT_KEY_OPTION,
    run_mode: list[RunMode] | None = POLICY_RUN_MODE_OPTION,
    involvement: list[InvolvementLevel] | None = POLICY_INVOLVEMENT_MATCH_OPTION,
    rationale: str | None = typer.Option(None, "--rationale", help="Optional rationale."),
    attention_id: str | None = POLICY_ATTENTION_OPTION,
) -> None:
    """Enqueue an explicit policy-promotion command for an operation."""

    effective_text = (text or rule or "").strip()
    effective_title = (title or "").strip() or None
    if attention_id is None and effective_title is None:
        raise typer.BadParameter("--title is required unless --attention is provided.")
    if attention_id is None and not effective_text:
        raise typer.BadParameter("--text or --rule is required unless --attention is provided.")
    anyio.run(
        _enqueue_custom_command_async,
        operation_id,
        OperationCommandType.RECORD_POLICY_DECISION,
        {
            "title": effective_title,
            "text": effective_text,
            "category": category,
            **_policy_applicability_payload(
                objective_keyword,
                task_keyword,
                agent,
                run_mode,
                involvement,
            ),
            "rationale": rationale,
        },
        (
            CommandTargetScope.ATTENTION_REQUEST
            if attention_id is not None
            else CommandTargetScope.OPERATION
        ),
        attention_id or operation_id,
    )


@policy_app.command("revoke")
def policy_revoke(
    operation_id: str,
    policy_id: str = POLICY_ID_OPTION,
    reason: str | None = POLICY_REASON_OPTION,
) -> None:
    """Enqueue a policy revocation command for an operation."""

    anyio.run(
        _enqueue_custom_command_async,
        operation_id,
        OperationCommandType.REVOKE_POLICY_DECISION,
        {"policy_id": policy_id, "reason": reason},
        CommandTargetScope.OPERATION,
        operation_id,
    )


@app.command(hidden=True)
def inspect(
    operation_id: str,
    full: bool = typer.Option(False, "--full", help="Show full forensic trace output."),
    json_mode: bool = typer.Option(
        False,
        "--json",
        help="Emit a single JSON object instead of human-readable output.",
    ),
) -> None:
    """Inspect a prior operation and its events."""

    settings = _load_settings()
    trace_store = build_trace_store(settings)
    event_sink = build_event_sink(settings, operation_id)
    command_inbox = build_command_inbox(settings)
    delivery = _build_delivery_commands_service(settings)

    async def _inspect() -> None:
        try:
            operation, outcome, brief, runtime_alert = await delivery.build_status_payload(
                operation_id
            )
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
                "operation": _operation_payload(operation),
                "outcome": outcome.model_dump(mode="json") if outcome is not None else None,
                "brief": brief.model_dump(mode="json") if brief is not None else None,
                "report": report,
                "commands": commands,
                "durable_truth": _PROJECTIONS.build_durable_truth_payload(
                    operation,
                    include_inactive_memory=True,
                ),
            }
            if runtime_alert is not None:
                payload["runtime_alert"] = runtime_alert
            if full:
                payload["trace_records"] = [item.model_dump(mode="json") for item in trace_records]
                payload["decision_memos"] = [item.model_dump(mode="json") for item in memos]
                payload["events"] = [item.model_dump(mode="json") for item in events]
                payload["wakeups"] = build_wakeup_inbox(settings).read_all(operation_id)
                payload["background_runs"] = [
                    item.model_dump(mode="json")
                    for item in await build_background_run_inspection_store(settings).list_runs(
                        operation_id
                    )
                ]
            typer.echo(json.dumps(payload, indent=2, ensure_ascii=False))
            return
        if brief is not None:
            typer.echo(_render_inspect_summary(operation, brief, runtime_alert=runtime_alert))
        else:
            typer.echo("Operation:")
            typer.echo(json.dumps(_operation_payload(operation), indent=2, ensure_ascii=False))
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
            typer.echo(f"Counts: {_summarize_task_counts(operation)}")
            for task in operation.tasks:
                typer.echo(
                    f"- task-{task.task_short_id} [{task.status.value}] {task.title} "
                    f"agent={task.assigned_agent or '-'}"
                )
        memory_entries = _memory_payload(operation, include_inactive=False)
        if memory_entries:
            typer.echo("\nCurrent memory:")
            for entry in memory_entries:
                scope_target = (
                    _format_task_line(operation, entry.scope_id)
                    if entry.scope.value == "task"
                    else entry.scope_id
                )
                typer.echo(
                    f"- {entry.memory_id} [{entry.scope.value}] {scope_target}: {entry.summary}"
                )
        if operation.artifacts:
            typer.echo("\nArtifacts:")
            for artifact in operation.artifacts:
                typer.echo(
                    f"- {artifact.artifact_id} [{artifact.kind}] {_artifact_preview(artifact)}"
                )
        if operation.attention_requests:
            typer.echo("\nAttention requests:")
            for attention in operation.attention_requests:
                typer.echo(
                    json.dumps(
                        attention.model_dump(mode="json"),
                        indent=2,
                        ensure_ascii=False,
                    )
                )
        if commands:
            typer.echo("\nCommands:")
            for command_payload in commands:
                typer.echo(json.dumps(command_payload, indent=2, ensure_ascii=False))
        if full:
            typer.echo("\nOperation state:")
            typer.echo(json.dumps(_operation_payload(operation), indent=2, ensure_ascii=False))
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
            for run in [
                item.model_dump(mode="json")
                for item in await build_background_run_inspection_store(settings).list_runs(
                    operation_id
                )
            ]:
                typer.echo(json.dumps(run, indent=2, ensure_ascii=False))

    anyio.run(_inspect)


@debug_app.command("inspect")
def debug_inspect(
    operation_id: str,
    full: bool = typer.Option(
        False,
        "--full",
        help="Include the full stored state, trace, events, wakeups, and background runs.",
    ),
    json_mode: bool = typer.Option(
        False,
        "--json",
        help="Emit a machine-readable forensic payload.",
    ),
) -> None:
    """Show a forensic dump for an operation."""

    inspect(operation_id, full, json_mode)


@app.command()
def report(
    operation_id: str,
    json_mode: bool = typer.Option(
        False,
        "--json",
        help="Emit a machine-readable report payload.",
    ),
) -> None:
    """Print the human-readable report for an operation."""

    settings = _load_settings()
    trace_store = build_trace_store(settings)
    delivery = _build_delivery_commands_service(settings)

    async def _report() -> None:
        try:
            operation, outcome, brief, _ = await delivery.build_status_payload(operation_id)
        except RuntimeError as exc:
            raise typer.BadParameter(f"Report for {operation_id!r} was not found.") from exc
        report_text = await trace_store.load_report(operation_id)
        if operation is None or report_text is None:
            raise typer.BadParameter(f"Report for {operation_id!r} was not found.")
        if json_mode:
            payload = {
                "operation_id": operation_id,
                "brief": brief.model_dump(mode="json") if brief is not None else None,
                "outcome": outcome.model_dump(mode="json") if outcome is not None else None,
                "report": report_text,
                "durable_truth": _PROJECTIONS.build_durable_truth_payload(
                    operation,
                    include_inactive_memory=True,
                ),
            }
            typer.echo(json.dumps(payload, indent=2, ensure_ascii=False))
            return
        typer.echo(report_text)

    anyio.run(_report)


@app.command(hidden=True)
def context(
    operation_id: str,
    json_mode: bool = typer.Option(
        False,
        "--json",
        help="Emit a machine-readable effective control-plane context payload.",
    ),
) -> None:
    """Show the effective control-plane context steering an operation."""

    settings = _load_settings()
    delivery = _build_delivery_commands_service(settings)

    async def _context() -> None:
        try:
            operation, _, _, _ = await delivery.build_status_payload(operation_id)
        except RuntimeError as exc:
            raise typer.BadParameter(str(exc)) from exc
        if operation is None:
            raise typer.BadParameter(f"Operation {operation_id!r} was not found.")
        payload = _PROJECTIONS.build_operation_context_payload(operation)
        if json_mode:
            typer.echo(json.dumps(payload, indent=2, ensure_ascii=False))
            return
        for line in _emit_context_lines(payload, operation_id=operation.operation_id):
            typer.echo(line)

    anyio.run(_context)


@debug_app.command("context")
def debug_context(
    operation_id: str,
    json_mode: bool = typer.Option(
        False,
        "--json",
        help="Emit a machine-readable effective control-plane context payload.",
    ),
) -> None:
    """Show the effective control-plane context steering an operation."""

    context(operation_id, json_mode)


@app.command()
def dashboard(
    operation_id: str,
    once: bool = typer.Option(
        False,
        "--once",
        help="Render a single dashboard snapshot and exit.",
    ),
    json_mode: bool = typer.Option(
        False,
        "--json",
        help="Emit a machine-readable dashboard snapshot.",
    ),
    poll_interval: float = WATCH_POLL_INTERVAL_OPTION,
    codex_home: Path = CODEX_HOME_OPTION,
) -> None:
    """Show a live one-operation dashboard over persisted control-plane truth."""

    anyio.run(_dashboard_async, operation_id, once, json_mode, poll_interval, codex_home)


@app.command(hidden=True)
def trace(
    operation_id: str,
    json_mode: bool = typer.Option(
        False,
        "--json",
        help="Emit a machine-readable forensic trace payload.",
    ),
) -> None:
    """Show forensic trace data for an operation."""

    settings = _load_settings()
    trace_store = build_trace_store(settings)
    event_sink = build_event_sink(settings, operation_id)
    inbox = build_wakeup_inbox(settings)
    supervisor = build_background_run_inspection_store(settings)
    command_inbox = build_command_inbox(settings)
    delivery = _build_delivery_commands_service(settings)

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
        background_runs = [
            item.model_dump(mode="json") for item in await supervisor.list_runs(operation_id)
        ]
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
                "attention_requests": (
                    [item.model_dump(mode="json") for item in operation.attention_requests]
                    if operation is not None
                    else []
                ),
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
                typer.echo(
                    json.dumps(
                        attention.model_dump(mode="json"),
                        indent=2,
                        ensure_ascii=False,
                    )
                )
        if raw_log_refs:
            typer.echo("\nRaw log refs:")
            for raw_log_ref in raw_log_refs:
                typer.echo(raw_log_ref)

    anyio.run(_trace)


@debug_app.command("trace")
def debug_trace(
    operation_id: str,
    json_mode: bool = typer.Option(
        False,
        "--json",
        help="Emit a machine-readable forensic trace payload.",
    ),
) -> None:
    """Show forensic trace data for an operation."""

    trace(operation_id, json_mode)


@app.command()
def watch(
    operation_id: str,
    json_mode: bool = JSON_OPTION,
    poll_interval: float = WATCH_POLL_INTERVAL_OPTION,
) -> None:
    """Watch one operation live via the persisted event stream and operation state."""

    anyio.run(_watch_async, operation_id, json_mode, poll_interval)


@app.command()
def log(
    operation_ref: str,
    limit: int = typer.Option(40, "--limit", min=1, help="Maximum events to print."),
    follow: bool = typer.Option(False, "--follow", help="Follow the agent transcript."),
    agent: str = typer.Option("auto", "--agent", help="auto, codex, claude, or opencode."),
    json_mode: bool = typer.Option(False, "--json", help="Emit machine-readable JSON."),
    codex_home: Path = CODEX_HOME_OPTION,
) -> None:
    """Show condensed human-readable events from the selected agent transcript."""

    resolved_operation_id = _resolve_operation_id(operation_ref)
    settings = _load_settings()
    store = build_store(settings)

    async def _log() -> None:
        operation = await store.load_operation(resolved_operation_id)
        if operation is None:
            raise typer.BadParameter(f"Operation {resolved_operation_id!r} was not found.")
        log_kind, session = _resolve_log_target(operation, agent=agent)
        if log_kind == "codex":
            path = find_codex_session_log(codex_home, session.session_id)
            if path is None:
                raise typer.BadParameter(
                    f"Codex transcript for session {session.session_id!r} was not found under "
                    f"{str(codex_home)!r}."
                )
            if follow:
                typer.echo(f"# Codex log for operation {resolved_operation_id}")
                typer.echo(f"# session={session.session_id}")
                typer.echo(f"# file={path}")
                for event in iter_codex_log_events(path, follow=True):
                    if json_mode:
                        typer.echo(json.dumps(asdict(event), ensure_ascii=False))
                    else:
                        typer.echo(format_codex_log_event(event))
                return
            events = load_codex_log_events(path)[-limit:]
            if json_mode:
                payload = {
                    "operation_id": resolved_operation_id,
                    "session_id": session.session_id,
                    "path": str(path),
                    "agent": "codex",
                    "events": [asdict(event) for event in events],
                }
                typer.echo(json.dumps(payload, indent=2, ensure_ascii=False))
                return
            typer.echo(f"# Codex log for operation {resolved_operation_id}")
            typer.echo(f"# session={session.session_id}")
            typer.echo(f"# file={path}")
            for event in events:
                typer.echo(format_codex_log_event(event))
            return
        if log_kind == "claude":
            claude_session, path = _resolve_claude_log_path(operation)
            if follow:
                typer.echo(f"# Claude log for operation {resolved_operation_id}")
                typer.echo(f"# session={claude_session.session_id}")
                typer.echo(f"# file={path}")
                for event in iter_claude_log_events(path, follow=True):
                    if json_mode:
                        typer.echo(json.dumps(asdict(event), ensure_ascii=False))
                    else:
                        typer.echo(format_claude_log_event(event))
                return
            events = load_claude_log_events(path)[-limit:]
            if json_mode:
                payload = {
                    "operation_id": resolved_operation_id,
                    "session_id": claude_session.session_id,
                    "path": str(path),
                    "agent": "claude",
                    "events": [asdict(event) for event in events],
                }
                typer.echo(json.dumps(payload, indent=2, ensure_ascii=False))
                return
            typer.echo(f"# Claude log for operation {resolved_operation_id}")
            typer.echo(f"# session={claude_session.session_id}")
            typer.echo(f"# file={path}")
            for event in events:
                typer.echo(format_claude_log_event(event))
            return

        path = _resolve_jsonl_log_path_for_session(session, provider="OpenCode")
        if follow:
            typer.echo(f"# OpenCode log for operation {resolved_operation_id}")
            typer.echo(f"# session={session.session_id}")
            typer.echo(f"# file={path}")
            for event in iter_opencode_log_events(path, follow=True):
                if json_mode:
                    typer.echo(json.dumps(asdict(event), ensure_ascii=False))
                else:
                    typer.echo(format_opencode_log_event(event))
            return
        events = load_opencode_log_events(path)[-limit:]
        if json_mode:
            payload = {
                "operation_id": resolved_operation_id,
                "session_id": session.session_id,
                "path": str(path),
                "agent": "opencode",
                "events": [asdict(event) for event in events],
            }
            typer.echo(json.dumps(payload, indent=2, ensure_ascii=False))
            return
        typer.echo(f"# OpenCode log for operation {resolved_operation_id}")
        typer.echo(f"# session={session.session_id}")
        typer.echo(f"# file={path}")
        for event in events:
            typer.echo(format_opencode_log_event(event))

    anyio.run(_log)


async def _run_async(
    objective: str | None,
    project: str | None,
    harness: str | None,
    success_criteria: list[str] | None,
    max_iterations: int | None,
    allowed_agent: list[str] | None,
    mode: RunMode | None,
    involvement: InvolvementLevel | None,
    attach_session: str | None,
    attach_agent: str | None,
    attach_name: str | None,
    attach_working_dir: Path | None,
    json_mode: bool,
) -> None:
    settings, data_dir_source = _load_settings_with_data_dir()
    settings.data_dir = Path(settings.data_dir)
    launch_dir = Path.cwd().resolve()
    try:
        profile, selected_profile_path, profile_source = _resolve_project_profile_selection(
            settings,
            name=project,
        )
    except RuntimeError as exc:
        raise typer.BadParameter(str(exc)) from exc
    if profile is None and project is None:
        _emit_free_mode_stub(cwd=launch_dir, json_mode=json_mode)
        return
    apply_project_profile_settings(settings, profile)
    resolved = resolve_project_run_config(
        settings,
        profile=profile,
        objective=objective,
        harness=harness,
        success_criteria=success_criteria,
        allowed_agents=allowed_agent,
        max_iterations=max_iterations,
        run_mode=mode,
        involvement_level=involvement,
    )
    if resolved.objective_text is None:
        prompted_objective = typer.prompt("Goal")
        resolved = resolve_project_run_config(
            settings,
            profile=profile,
            objective=prompted_objective,
            harness=harness,
            success_criteria=success_criteria,
            allowed_agents=allowed_agent,
            max_iterations=max_iterations,
            run_mode=mode,
            involvement_level=involvement,
        )
    effective_mode = resolved.run_mode
    operation_id = str(uuid4())
    projector = _CliEventProjector(json_mode=json_mode)
    service = build_service(
        settings,
        event_sink=ProjectingEventSink(
            build_event_sink(settings, operation_id),
            projector.handle_event,
        ),
    )
    attached_sessions = []
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
    goal_metadata["resolved_operator_launch"] = {
        "data_dir": str(settings.data_dir),
        "data_dir_source": data_dir_source,
        "profile_source": profile_source,
        "profile_path": str(selected_profile_path) if selected_profile_path is not None else None,
    }
    if profile is not None:
        goal_metadata["project_profile_name"] = profile.name
        goal_metadata["policy_scope"] = f"profile:{profile.name}"
        goal_metadata["resolved_project_profile"] = resolved.model_dump(mode="json")
        if selected_profile_path is not None:
            goal_metadata["project_profile_path"] = str(selected_profile_path)
        if profile_source is not None:
            goal_metadata["project_profile_source"] = profile_source
        goal_metadata["data_dir_source"] = data_dir_source
    elif resolved.cwd is not None:
        goal_metadata["policy_scope"] = f"cwd:{resolved.cwd}"
    if not json_mode:
        typer.echo(
            f"# data_dir={settings.data_dir} source={data_dir_source}",
            err=True,
        )
        if profile is not None:
            typer.echo(
                "# project_profile="
                f"{profile.name} source={profile_source or 'unknown'}"
                + (
                    f" path={selected_profile_path}"
                    if selected_profile_path is not None
                    else ""
                ),
                err=True,
            )
    projector.emit_operation(operation_id)
    outcome = await service.run(
        OperationGoal(
            objective=resolved.objective_text,
            harness_instructions=resolved.harness_instructions,
            success_criteria=resolved.success_criteria,
            metadata=goal_metadata,
        ),
        policy=OperationPolicy(
            allowed_agents=resolved.default_agents,
            involvement_level=resolved.involvement_level,
        ),
        budget=ExecutionBudget(
            max_iterations=resolved.max_iterations,
        ),
        runtime_hints=RuntimeHints(
            operator_message_window=resolved.message_window,
        ),
        options=RunOptions(
            run_mode=effective_mode,
            background_runtime_mode=(
                BackgroundRuntimeMode.ATTACHED_LIVE
                if effective_mode is RunMode.ATTACHED
                else BackgroundRuntimeMode.RESUMABLE_WAKEUP
            ),
        ),
        operation_id=operation_id,
        attached_sessions=attached_sessions or None,
    )
    projector.emit_outcome(outcome)


async def _watch_async(
    operation_id: str,
    json_mode: bool,
    poll_interval: float,
) -> None:
    settings = _load_settings()
    event_sink = build_event_sink(settings, operation_id)
    projector = _CliEventProjector(json_mode=json_mode)
    delivery = _build_delivery_commands_service(settings)

    try:
        operation, outcome, _, _ = await delivery.build_status_payload(operation_id)
    except RuntimeError as exc:
        raise typer.BadParameter(str(exc)) from exc

    projector.emit_operation(operation_id)
    seen_event_ids: set[str] = set()
    for event in event_sink.iter_events(operation_id):
        seen_event_ids.add(event.event_id)
        projector.handle_event(event)

    last_snapshot: dict[str, object] | None = None
    while True:
        for event in event_sink.iter_events(operation_id):
            if event.event_id in seen_event_ids:
                continue
            seen_event_ids.add(event.event_id)
            projector.handle_event(event)

        operation, outcome, _, _ = await delivery.build_status_payload(operation_id)
        snapshot = delivery.build_live_snapshot(operation_id, operation, outcome)
        if snapshot != last_snapshot:
            projector.emit_snapshot(snapshot)
            last_snapshot = snapshot

        if outcome is not None and outcome.status is not OperationStatus.RUNNING:
            projector.emit_outcome(outcome)
            return
        await anyio.sleep(poll_interval)


async def _dashboard_async(
    operation_id: str,
    once: bool,
    json_mode: bool,
    poll_interval: float,
    codex_home: Path,
) -> None:
    settings = _load_settings()
    queries = _build_operation_dashboard_query_service(
        settings,
        operation_id=operation_id,
        codex_home=codex_home,
    )

    async def _load_payload() -> dict[str, object]:
        try:
            payload = await queries.load_payload(operation_id)
        except RuntimeError as exc:
            raise typer.BadParameter(str(exc)) from exc
        return _cli_projection_payload(payload)

    payload = await _load_payload()
    if json_mode:
        typer.echo(json.dumps(payload, indent=2, ensure_ascii=False))
        return
    console = RichConsole()
    if once:
        console.print(_render_dashboard(payload))
        return
    with Live(_render_dashboard(payload), console=console, refresh_per_second=4) as live:
        while True:
            payload = await _load_payload()
            live.update(_render_dashboard(payload), refresh=True)
            if payload.get("status") != OperationStatus.RUNNING.value:
                return
            await anyio.sleep(poll_interval)


async def _resume_async(operation_id: str, max_cycles: int, json_mode: bool) -> None:
    settings = _load_settings()
    projector = _CliEventProjector(json_mode=json_mode)
    if json_mode:
        projector.emit_operation(operation_id)
    service = _build_projecting_delivery_commands_service(
        settings,
        operation_id=operation_id,
        projector=projector,
    )
    outcome = await service.resume(operation_id, max_cycles=max_cycles)
    projector.emit_outcome(outcome)


async def _status_async(operation_id: str, json_mode: bool, brief: bool) -> None:
    service = _delivery_commands_service()
    try:
        typer.echo(
            await service.render_status_output(
                operation_id,
                json_mode=json_mode,
                brief=brief,
            )
        )
    except RuntimeError as exc:
        raise typer.BadParameter(str(exc)) from exc


async def _tick_async(operation_id: str) -> None:
    service = _delivery_commands_service()
    outcome = await service.tick(operation_id)
    typer.echo(f"{outcome.status.value}: {outcome.summary}")
    typer.echo(f"operation_id={outcome.operation_id}", err=True)


async def _daemon_async(
    once: bool,
    poll_interval: float,
    max_cycles_per_operation: int,
    json_mode: bool,
) -> None:
    settings = _load_settings()
    inbox = build_wakeup_inbox(settings)
    projector = _CliEventProjector(json_mode=json_mode)
    delivery = _build_projecting_delivery_commands_service(
        settings,
        operation_id="sweep",
        projector=projector,
    )

    async def _sweep() -> int:
        resumed = await delivery.daemon_sweep(
            ready_operation_ids=list(inbox.ready_operation_ids()),
            max_cycles_per_operation=max_cycles_per_operation,
            emit_operation=projector.emit_operation if json_mode else None,
            emit_outcome=projector.emit_outcome,
        )
        if json_mode:
            typer.echo(
                json.dumps(
                    {"daemon_once": True, "resumed_operations": resumed},
                    ensure_ascii=False,
                )
            )
        elif resumed > 0:
            typer.echo(f"resumed_operations={resumed}")
        return resumed

    if once:
        await _sweep()
        return

    while True:
        await _sweep()
        await anyio.sleep(poll_interval)


async def _recover_async(
    operation_id: str,
    session_id: str | None,
    max_cycles: int,
    json_mode: bool,
) -> None:
    settings = _load_settings()
    projector = _CliEventProjector(json_mode=json_mode)
    if json_mode:
        projector.emit_operation(operation_id)
    delivery = _build_projecting_delivery_commands_service(
        settings,
        operation_id=operation_id,
        projector=projector,
    )
    outcome = await delivery.recover(
        operation_id,
        session_id=session_id,
        max_cycles=max_cycles,
    )
    projector.emit_outcome(outcome)


async def _cancel_async(operation_id: str, session_id: str | None, run_id: str | None) -> None:
    service = _delivery_commands_service()
    outcome = await service.cancel(operation_id, session_id=session_id, run_id=run_id)
    typer.echo(f"{outcome.status.value}: {outcome.summary}")
    typer.echo(f"operation_id={outcome.operation_id}", err=True)


async def _stop_turn_async(operation_id: str, task_id: str | None = None) -> None:
    service = _delivery_commands_service()
    try:
        command = await service.enqueue_stop_turn(operation_id, task_id=task_id)
    except RuntimeError as exc:
        raise typer.BadParameter(str(exc)) from exc
    typer.echo(f"enqueued: {command.command_type.value} [{command.command_id}]")


async def _answer_async(
    operation_id: str,
    attention_id: str | None,
    text: str,
    promote: bool,
    policy_title: str | None,
    policy_text: str | None,
    policy_category: str,
    policy_objective_keyword: list[str] | None,
    policy_task_keyword: list[str] | None,
    policy_agent: list[str] | None,
    policy_run_mode: list[RunMode] | None,
    policy_involvement: list[InvolvementLevel] | None,
    policy_rationale: str | None,
) -> None:
    service = _delivery_commands_service()
    try:
        policy_payload = service.build_policy_decision_payload(
            promote=promote,
            category=policy_category,
            title=policy_title,
            text=policy_text,
            objective_keyword=policy_objective_keyword,
            task_keyword=policy_task_keyword,
            agent=policy_agent,
            run_mode=policy_run_mode,
            involvement=policy_involvement,
            rationale=policy_rationale,
        )
        answer_command, policy_command, outcome = await service.answer_attention(
            operation_id,
            attention_id=attention_id,
            text=text,
            promote=promote,
            policy_payload=policy_payload,
        )
    except RuntimeError as exc:
        raise typer.BadParameter(str(exc)) from exc
    typer.echo(f"enqueued: {answer_command.command_type.value} [{answer_command.command_id}]")
    if policy_command is not None:
        typer.echo(f"enqueued: {policy_command.command_type.value} [{policy_command.command_id}]")
    if outcome is not None:
        typer.echo(f"{outcome.status.value}: {outcome.summary}")


async def _enqueue_command_async(
    operation_id: str,
    command_type: OperationCommandType,
    text: str | None,
    auto_resume_when_paused: bool = False,
    target_scope: CommandTargetScope = CommandTargetScope.OPERATION,
    target_id: str | None = None,
    auto_resume_blocked_attention_id: str | None = None,
    success_criteria: list[str] | None = None,
    clear_success_criteria: bool = False,
    allowed_agents: list[str] | None = None,
    max_iterations: int | None = None,
) -> None:
    service = _delivery_commands_service()
    try:
        payload = service.build_command_payload(
            command_type,
            text,
            success_criteria,
            clear_success_criteria,
            allowed_agents,
            max_iterations,
        )
    except RuntimeError as exc:
        raise typer.BadParameter(str(exc)) from exc
    command, outcome, note = await service.enqueue_command(
        operation_id,
        command_type,
        payload,
        target_scope=target_scope,
        target_id=target_id or operation_id,
        auto_resume_when_paused=auto_resume_when_paused,
        auto_resume_blocked_attention_id=auto_resume_blocked_attention_id,
    )
    typer.echo(f"enqueued: {command.command_type.value} [{command.command_id}]")
    if note is not None:
        typer.echo(note)
    if outcome is not None:
        typer.echo(f"{outcome.status.value}: {outcome.summary}")


async def _enqueue_custom_command_async(
    operation_id: str,
    command_type: OperationCommandType,
    payload: dict[str, object],
    target_scope: CommandTargetScope,
    target_id: str,
) -> None:
    service = _delivery_commands_service()
    command, _, _ = await service.enqueue_command(
        operation_id,
        command_type,
        payload,
        target_scope=target_scope,
        target_id=target_id,
    )
    typer.echo(f"enqueued: {command.command_type.value} [{command.command_id}]")


async def _list_async(json_mode: bool) -> None:
    settings = _load_settings()
    store = build_store(settings)
    trace_store = build_trace_store(settings)
    inbox = build_wakeup_inbox(settings)
    supervisor = build_background_run_inspection_store(settings)
    for summary in await store.list_operations():
        wakeups = inbox.read_all(summary.operation_id)
        background_runs = [
            item.model_dump(mode="json")
            for item in await supervisor.list_runs(summary.operation_id)
        ]
        runtime_alert = _build_runtime_alert(
            status=summary.status,
            wakeups=wakeups,
            background_runs=background_runs,
        )
        brief = await trace_store.load_brief_bundle(summary.operation_id)
        if brief is not None and brief.operation_brief is not None:
            if json_mode:
                payload = brief.operation_brief.model_dump(mode="json")
                if runtime_alert is not None:
                    payload["runtime_alert"] = runtime_alert
                typer.echo(json.dumps(payload, ensure_ascii=False))
            else:
                operation_brief = brief.operation_brief
                latest_turn = _latest_agent_turn_brief(brief)
                focus = (
                    _shorten_live_text(operation_brief.focus_brief, limit=28)
                    if operation_brief.focus_brief
                    else None
                )
                latest = _shorten_live_text(
                    _turn_work_summary(latest_turn) or operation_brief.latest_outcome_brief,
                    limit=56,
                )
                blocker = _shorten_live_text(operation_brief.blocker_brief, limit=48)
                scheduler = (
                    operation_brief.scheduler_state.value
                    if operation_brief.scheduler_state.value != "active"
                    else None
                )
                involvement = (
                    operation_brief.involvement_level.value
                    if operation_brief.involvement_level.value != "auto"
                    else None
                )
                typer.echo(
                    _render_operation_list_line(
                        operation_brief.operation_id,
                        operation_brief.status.value,
                        objective=operation_brief.objective_brief,
                        focus=focus,
                        latest=latest,
                        blocker=blocker,
                        runtime_alert=_shorten_live_text(runtime_alert, limit=48),
                        scheduler=scheduler,
                        involvement=involvement,
                    )
                )
            continue
        if json_mode:
            payload = summary.model_dump(mode="json")
            if runtime_alert is not None:
                payload["runtime_alert"] = runtime_alert
            typer.echo(json.dumps(payload, ensure_ascii=False))
        else:
            typer.echo(
                _render_operation_list_line(
                    summary.operation_id,
                    summary.status.value,
                    objective=_shorten_live_text(summary.objective_prompt, limit=96)
                    or summary.objective_prompt,
                    focus=_shorten_live_text(summary.focus, limit=28),
                    latest=_shorten_live_text(summary.final_summary, limit=56),
                    blocker=None,
                    runtime_alert=_shorten_live_text(runtime_alert, limit=48),
                )
            )


async def _history_async(operation_ref: str | None, json_mode: bool) -> None:
    settings = _load_settings()
    ledger = build_history_ledger(settings)
    profile_selection = discover_local_project_profile(settings)
    if profile_selection.profile is not None and not profile_selection.profile.history_ledger:
        typer.echo("Committed history ledger is disabled for this project.")
        return
    entries = [entry.model_dump(mode="json") for entry in ledger.list_entries()]
    if operation_ref is not None:
        entries = [_resolve_history_entry(operation_ref, entries)]
    if json_mode:
        typer.echo(json.dumps(entries, indent=2, ensure_ascii=False))
        return
    if not entries:
        typer.echo("No committed history entries yet.")
        return
    for entry in entries:
        line = (
            f"{entry['op_id']} {str(entry['status']).upper()} "
            f"{entry['goal']} "
            f"[reason={entry['stop_reason']}]"
        )
        profile = entry.get("profile")
        if isinstance(profile, str) and profile.strip():
            line += f" [profile={profile}]"
        typer.echo(line)


async def _agenda_async(
    project: str | None,
    include_all: bool,
    json_mode: bool,
) -> None:
    snapshot = await _load_agenda_snapshot(project=project, include_all=include_all)
    if json_mode:
        typer.echo(
            json.dumps(
                snapshot.model_dump(mode="json"),
                indent=2,
                ensure_ascii=False,
            )
        )
        return
    typer.echo("Agenda")
    if project is not None:
        typer.echo(f"Project: {project}")
    typer.echo(f"Operations: {snapshot.total_operations}")
    _print_agenda_section("Needs attention:", snapshot.needs_attention)
    _print_agenda_section("Active:", snapshot.active)
    if snapshot.recent:
        _print_agenda_section("Recent:", snapshot.recent)


async def _load_agenda_snapshot(
    *,
    project: str | None,
    include_all: bool,
) -> AgendaSnapshot:
    settings = _load_settings()
    service = _build_agenda_query_service(settings)
    return await service.load_snapshot(project=project, include_recent=include_all)


async def _has_any_operations_async() -> bool:
    snapshot = await _load_agenda_snapshot(project=None, include_all=False)
    return snapshot.total_operations > 0


async def _fleet_async(
    project: str | None,
    include_all: bool,
    once: bool,
    json_mode: bool,
    poll_interval: float,
) -> None:
    if sys.stdout.isatty() and sys.stdin.isatty() and not once and not json_mode:
        await _fleet_tui_async(project, include_all, poll_interval)
        return

    async def _load_payload() -> dict[str, object]:
        snapshot = await _load_agenda_snapshot(project=project, include_all=include_all)
        return _cli_projection_payload(_PROJECTIONS.build_fleet_payload(snapshot, project=project))

    payload = await _load_payload()
    if json_mode:
        typer.echo(
            json.dumps(
                payload,
                indent=2,
                ensure_ascii=False,
            )
        )
        return
    console = RichConsole()
    if once:
        console.print(_render_fleet_dashboard(payload))
        return
    with Live(_render_fleet_dashboard(payload), console=console, refresh_per_second=4) as live:
        while True:
            payload = await _load_payload()
            live.update(_render_fleet_dashboard(payload), refresh=True)
            await anyio.sleep(poll_interval)


async def _fleet_tui_async(
    project: str | None,
    include_all: bool,
    poll_interval: float,
) -> None:
    settings = _load_settings()
    codex_home = Path.home() / ".codex"

    async def _load_payload() -> dict[str, object]:
        snapshot = await _load_agenda_snapshot(project=project, include_all=include_all)
        return _PROJECTIONS.build_fleet_payload(snapshot, project=project)

    async def _load_operation_payload(operation_id: str) -> dict[str, object] | None:
        queries = _build_operation_dashboard_query_service(
            settings,
            operation_id=operation_id,
            codex_home=codex_home,
        )
        return await queries.load_payload(operation_id)

    async def _enqueue_simple_command(
        operation_id: str,
        command_type: OperationCommandType,
        *,
        auto_resume_when_paused: bool = False,
    ) -> str:
        delivery = _build_delivery_commands_service(settings)
        command, outcome, note = await delivery.enqueue_command(
            operation_id,
            command_type,
            {},
            target_scope=CommandTargetScope.OPERATION,
            target_id=operation_id,
            auto_resume_when_paused=auto_resume_when_paused,
        )
        message = f"enqueued: {command.command_type.value} [{command.command_id}]"
        if note is not None:
            message += f" | {note}"
        if outcome is not None:
            message += f" | {outcome.status.value}: {outcome.summary}"
        return message

    async def _interrupt_operation(operation_id: str) -> str:
        delivery = _build_delivery_commands_service(settings)
        command = await delivery.enqueue_stop_turn(operation_id)
        return f"enqueued: {command.command_type.value} [{command.command_id}]"

    async def _cancel_operation(operation_id: str) -> str:
        outcome = await _delivery_commands_service().cancel(
            operation_id,
            session_id=None,
            run_id=None,
        )
        return f"{outcome.status.value}: {outcome.summary}"

    controller = _build_fleet_workbench_controller(
        load_payload=_load_payload,
        load_operation_payload=_load_operation_payload,
        pause_operation=lambda operation_id: _enqueue_simple_command(
            operation_id,
            OperationCommandType.PAUSE_OPERATOR,
        ),
        unpause_operation=lambda operation_id: _enqueue_simple_command(
            operation_id,
            OperationCommandType.RESUME_OPERATOR,
            auto_resume_when_paused=True,
        ),
        interrupt_operation=_interrupt_operation,
        cancel_operation=_cancel_operation,
    )
    await _run_fleet_workbench(controller=controller, poll_interval=poll_interval)


async def _project_dashboard_async(
    name: str | None,
    once: bool,
    json_mode: bool,
    poll_interval: float,
) -> None:
    async def _load_payload() -> dict[str, object]:
        settings = _load_settings()
        try:
            profile, selected_path, _ = _resolve_project_profile_selection(settings, name=name)
        except RuntimeError as exc:
            raise typer.BadParameter(str(exc)) from exc
        if profile is None:
            raise typer.BadParameter("No local operator-profile.yaml was found.")
        resolved = resolve_project_run_config(
            settings,
            profile=profile,
            objective=None,
            harness=None,
            success_criteria=None,
            allowed_agents=None,
            max_iterations=None,
            run_mode=None,
            involvement_level=None,
        )
        payload = await _build_project_dashboard_query_service(settings).load_payload(
            profile=profile,
            resolved=resolved,
            profile_path=selected_path if selected_path is not None else profile_dir(settings),
        )
        return _cli_projection_payload(payload)

    payload = await _load_payload()
    if json_mode:
        typer.echo(json.dumps(payload, indent=2, ensure_ascii=False))
        return
    console = RichConsole()
    if once:
        console.print(_render_project_dashboard(payload))
        return
    with Live(_render_project_dashboard(payload), console=console, refresh_per_second=4) as live:
        while True:
            payload = await _load_payload()
            live.update(_render_project_dashboard(payload), refresh=True)
            await anyio.sleep(poll_interval)


@smoke_app.command("alignment-post-research-plan")
def smoke_alignment_post_research_plan() -> None:
    """Run the live smoke scenario for AI Alignment post research planning."""

    outcome = anyio.run(run_alignment_post_research_plan_smoke)
    typer.echo(extract_final_plan(outcome))
    typer.echo(f"operation_id={outcome.operation_id}", err=True)


@smoke_app.command("alignment-post-research-plan-claude-acp")
def smoke_alignment_post_research_plan_claude_acp() -> None:
    """Run the AI Alignment research-plan smoke using Claude ACP."""

    outcome = anyio.run(run_alignment_post_research_plan_smoke, "claude_acp")
    typer.echo(extract_final_plan(outcome))
    typer.echo(f"operation_id={outcome.operation_id}", err=True)


@smoke_app.command("mixed-agent-selection")
def smoke_mixed_agent_selection() -> None:
    """Run the live smoke scenario where the operator chooses between Claude and Codex ACP."""

    outcome = anyio.run(run_mixed_agent_selection_smoke)
    typer.echo(extract_final_plan(outcome))
    typer.echo(f"operation_id={outcome.operation_id}", err=True)


@smoke_app.command("mixed-agent-selection-claude-acp")
def smoke_mixed_agent_selection_claude_acp() -> None:
    """Run the mixed-agent selection smoke using Claude ACP as the Claude option."""

    outcome = anyio.run(run_mixed_agent_selection_smoke, "claude_acp")
    typer.echo(extract_final_plan(outcome))
    typer.echo(f"operation_id={outcome.operation_id}", err=True)


@smoke_app.command("mixed-code-agent-selection")
def smoke_mixed_code_agent_selection() -> None:
    """Run the live smoke scenario where the operator should prefer a repo-aware code agent."""

    outcome = anyio.run(run_mixed_code_agent_selection_smoke)
    typer.echo(extract_final_plan(outcome))
    typer.echo(f"operation_id={outcome.operation_id}", err=True)


@smoke_app.command("mixed-code-agent-selection-claude-acp")
def smoke_mixed_code_agent_selection_claude_acp() -> None:
    """Run the code-oriented mixed-agent smoke using Claude ACP as the Claude option."""

    outcome = anyio.run(run_mixed_code_agent_selection_smoke, "claude_acp")
    typer.echo(extract_final_plan(outcome))
    typer.echo(f"operation_id={outcome.operation_id}", err=True)


@smoke_app.command("codex-continuation")
def smoke_codex_continuation() -> None:
    """Run the live smoke scenario that requires continuing the same Codex ACP session."""

    outcome = anyio.run(run_codex_continuation_smoke)
    typer.echo(extract_final_plan(outcome))
    typer.echo(f"operation_id={outcome.operation_id}", err=True)
