from __future__ import annotations

import json
import sys
from collections.abc import Callable
from dataclasses import asdict
from pathlib import Path
from uuid import uuid4

import anyio
import typer
from rich.columns import Columns
from rich.console import Console as RichConsole
from rich.console import Group
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from typer.main import get_command as typer_get_command

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
from agent_operator.config import OperatorSettings
from agent_operator.domain import (
    AgentSessionHandle,
    AgentTurnBrief,
    ArtifactRecord,
    AttentionStatus,
    BackgroundRunStatus,
    BackgroundRuntimeMode,
    CommandTargetScope,
    ExecutionBudget,
    ExecutionState,
    FocusKind,
    InvolvementLevel,
    MemoryEntry,
    MemoryFreshness,
    OperationCommand,
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
    SessionStatus,
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
    agenda_matches_project,
    apply_project_profile_settings,
    build_agenda_item,
    build_agenda_snapshot,
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
    if sys.stdout.isatty():
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


def _build_command_payload(
    command_type: OperationCommandType,
    text: str | None,
    success_criteria: list[str] | None = None,
    clear_success_criteria: bool = False,
    allowed_agents: list[str] | None = None,
    max_iterations: int | None = None,
) -> dict[str, object]:
    if command_type in {
        OperationCommandType.PATCH_OBJECTIVE,
        OperationCommandType.PATCH_HARNESS,
        OperationCommandType.INJECT_OPERATOR_MESSAGE,
        OperationCommandType.ANSWER_ATTENTION_REQUEST,
    }:
        if text is None or not text.strip():
            raise typer.BadParameter("--text is required for this command type.")
        return {"text": text.strip()}
    if command_type is OperationCommandType.PATCH_SUCCESS_CRITERIA:
        if text is not None:
            raise typer.BadParameter("--text is not supported for this command type.")
        if clear_success_criteria:
            if success_criteria:
                raise typer.BadParameter(
                    "--success-criterion cannot be combined with --clear-success-criteria."
                )
            return {"success_criteria": []}
        normalized = [item.strip() for item in success_criteria or [] if item.strip()]
        if not normalized:
            raise typer.BadParameter(
                "--success-criterion or --clear-success-criteria is required for this command type."
            )
        return {"success_criteria": normalized}
    if command_type is OperationCommandType.SET_ALLOWED_AGENTS:
        if text is not None:
            raise typer.BadParameter("--text is not supported for this command type.")
        if success_criteria or clear_success_criteria:
            raise typer.BadParameter(
                "--success-criterion and --clear-success-criteria are not supported for this "
                "command type."
            )
        if max_iterations is not None:
            raise typer.BadParameter("--max-iterations is not supported for this command type.")
        if allowed_agents is None:
            raise typer.BadParameter("--allowed-agent is required for this command type.")
        allowed_agents_payload = [item.strip() for item in allowed_agents if item.strip()]
        if not allowed_agents_payload:
            raise typer.BadParameter("--allowed-agent cannot be empty.")
        return {"allowed_agents": allowed_agents_payload}
    if command_type is OperationCommandType.SET_INVOLVEMENT_LEVEL:
        if text is None or not text.strip():
            raise typer.BadParameter("--text is required for this command type.")
        return {"level": text.strip()}
    if success_criteria or clear_success_criteria:
        raise typer.BadParameter(
            "--success-criterion is not supported for this command type."
        )
    if text is not None:
        raise typer.BadParameter("--text is not supported for this command type.")
    return {}


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
    operation_brief = brief.operation_brief if brief is not None else None
    latest_turn = _latest_agent_turn_brief(brief)
    now_lines: list[str] = []
    if runtime_alert is not None:
        now_lines.append(f"alert: {runtime_alert}")
    blocker = (
        operation_brief.blocker_brief
        if operation_brief is not None
        else operation.final_summary
    )
    if blocker:
        now_lines.append(f"blocker: {_shorten_paragraph_text(blocker, limit=220)}")
    latest = _turn_work_summary(latest_turn)
    if latest is None and operation_brief is not None:
        latest = _shorten_block_text(operation_brief.latest_outcome_brief, limit=320)
    if latest:
        now_lines.append(f"latest: {latest}")
    verification = _turn_verification_summary(latest_turn)
    if verification:
        now_lines.append(f"verification: {verification}")
    blockers = _turn_blockers_summary(latest_turn)
    if blockers:
        now_lines.append(f"remaining blockers: {blockers}")
    next_step = _turn_next_step(latest_turn)
    if next_step:
        now_lines.append(f"recommended next step: {next_step}")

    operation_lines = [
        f"status: {operation.status.value}",
        (
            f"scheduler: {operation.scheduler_state.value}"
            if operation.scheduler_state is not SchedulerState.ACTIVE
            else ""
        ),
        (
            f"involvement: {operation.involvement_level.value}"
            if operation.involvement_level is not InvolvementLevel.AUTO
            else ""
        ),
        (
            f"focus: {operation_brief.focus_brief}"
            if operation_brief is not None and operation_brief.focus_brief
            else ""
        ),
    ]
    objective_lines = [
        f"objective: {operation_brief.objective_brief}"
        if operation_brief is not None
        else f"objective: {_shorten_paragraph_text(operation.goal.objective, limit=220)}",
        (
            f"harness: {_shorten_paragraph_text(operation_brief.harness_brief, limit=220)}"
            if operation_brief is not None and operation_brief.harness_brief
            else ""
        ),
    ]
    iteration_lines: list[str] = []
    for item in _recent_iteration_briefs(brief):
        iteration_lines.append(f"- Iteration {item.iteration}")
        iteration_lines.append(
            f"  intent: {_shorten_paragraph_text(item.operator_intent_brief, limit=180) or '-'}"
        )
        if item.assignment_brief:
            iteration_lines.append(
                f"  assignment: {_shorten_paragraph_text(item.assignment_brief, limit=200) or '-'}"
            )
        if item.result_brief:
            iteration_lines.append(
                f"  result: {_shorten_paragraph_text(item.result_brief, limit=200) or '-'}"
            )
        iteration_lines.append(
            f"  status: {_shorten_paragraph_text(item.status_brief, limit=180) or '-'}"
        )
    turn_lines: list[str] = []
    for turn in _recent_agent_turn_briefs(brief):
        session_label = turn.session_display_name or turn.session_id
        turn_lines.append(f"- {turn.agent_key} ({session_label}) [{turn.status}]")
        turn_lines.append(
            f"  assignment: {_shorten_paragraph_text(turn.assignment_brief, limit=200) or '-'}"
        )
        work = _turn_work_summary(turn)
        if work:
            turn_lines.append(f"  work: {work}")
        verification = _turn_verification_summary(turn)
        if verification:
            turn_lines.append(f"  verification: {verification}")
        blockers = _turn_blockers_summary(turn)
        if blockers:
            turn_lines.append(f"  blockers: {blockers}")
        next_step = _turn_next_step(turn)
        if next_step:
            turn_lines.append(f"  next: {next_step}")
        if turn.raw_log_refs:
            turn_lines.append(
                "  refs: raw_logs="
                + ", ".join(turn.raw_log_refs[:2])
                + ("…" if len(turn.raw_log_refs) > 2 else "")
            )

    open_attention = [a for a in operation.attention_requests if a.status is AttentionStatus.OPEN]
    attention_lines: list[str] = []
    for attention in open_attention:
        blocking_label = "blocking" if attention.blocking else "non-blocking"
        attention_lines.append(
            f"- [{attention.attention_type.value}] {attention.title} ({blocking_label})"
        )
        if attention.question:
            attention_lines.append(
                f"  {_shorten_paragraph_text(attention.question, limit=180)}"
            )
        attention_lines.append(
            f"  → operator answer {operation.operation_id} "
            f"--attention {attention.attention_id} --text '...'"
        )

    lines = [f"Operation {operation.operation_id}", ""]
    for section in (
        _render_section("Operation", operation_lines),
        _render_section("Objective", objective_lines),
        _render_section("Now", now_lines),
        _render_section("Open Attention", attention_lines),
        _render_section("Recent Iterations", iteration_lines),
        _render_section("Recent Agent Turns", turn_lines),
    ):
        if section:
            if lines and lines[-1] != "":
                lines.append("")
            lines.extend(section)
    return "\n".join(lines).rstrip() + "\n"


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
    parts = [f"{operation_id} [{status}] {objective}"]
    if focus:
        parts.append(f"focus={focus}")
    if latest:
        parts.append(f"latest={latest}")
    if blocker:
        parts.append(f"blocker={blocker}")
    if scheduler:
        parts.append(f"scheduler={scheduler}")
    if involvement:
        parts.append(f"involvement={involvement}")
    if runtime_alert:
        parts.append(f"alert={runtime_alert}")
    return " | ".join(parts)


def _build_brief_summary_payload(
    operation: OperationState,
    brief: TraceBriefBundle | None,
    *,
    runtime_alert: str | None,
) -> dict[str, object]:
    operation_brief = brief.operation_brief if brief is not None else None
    latest_turn = _latest_agent_turn_brief(brief)
    return {
        "objective": (
            operation_brief.objective_brief
            if operation_brief is not None
            else _shorten_paragraph_text(operation.goal.objective, limit=220)
        ),
        "harness": (
            _shorten_paragraph_text(operation_brief.harness_brief, limit=220)
            if operation_brief is not None and operation_brief.harness_brief
            else None
        ),
        "focus": operation_brief.focus_brief if operation_brief is not None else None,
        "latest": _turn_work_summary(latest_turn)
        or (
            _shorten_block_text(operation_brief.latest_outcome_brief, limit=320)
            if operation_brief is not None
            else None
        ),
        "verification": _turn_verification_summary(latest_turn),
        "blockers": _turn_blockers_summary(latest_turn),
        "next_step": _turn_next_step(latest_turn),
        "blocker": (
            _shorten_paragraph_text(operation_brief.blocker_brief, limit=220)
            if operation_brief is not None and operation_brief.blocker_brief
            else None
        ),
        "runtime_alert": runtime_alert,
    }


def _format_live_event(event: RunEvent) -> str | None:
    payload = event.payload if isinstance(event.payload, dict) else {}
    prefix = f"[iter {event.iteration}] " if event.iteration > 0 else ""
    if event.event_type == "operation.started":
        objective = _shorten_live_text(str(payload.get("objective", "")).strip())
        if objective is not None:
            return f"starting: {objective}"
        return "starting operation"
    if event.event_type == "brain.decision.made":
        action = str(payload.get("action_type", "")).strip() or "unknown"
        target_agent = str(payload.get("target_agent", "")).strip() or None
        rationale = _shorten_live_text(str(payload.get("rationale", "")).strip())
        rendered = f"{prefix}decision: {action}"
        if target_agent is not None:
            rendered += f" -> {target_agent}"
        if rationale is not None:
            rendered += f" | {rationale}"
        return rendered
    if event.event_type == "agent.invocation.started":
        adapter_key = str(payload.get("adapter_key", "")).strip() or "agent"
        rendered = f"{prefix}agent started: {adapter_key}"
        if event.session_id is not None:
            rendered += f" session={event.session_id}"
        session_name = str(payload.get("session_name", "")).strip() or None
        if session_name is not None:
            rendered += f" name={session_name}"
        return rendered
    if event.event_type == "agent.invocation.background_started":
        adapter_key = str(payload.get("adapter_key", "")).strip() or "agent"
        rendered = f"{prefix}background agent started: {adapter_key}"
        run_id = str(payload.get("run_id", "")).strip() or None
        if run_id is not None:
            rendered += f" run={run_id}"
        return rendered
    if event.event_type == "agent.invocation.completed":
        status = str(payload.get("status", "")).strip() or "unknown"
        output_text = _shorten_live_text(str(payload.get("output_text", "")).strip())
        rendered = f"{prefix}agent completed: {status}"
        if output_text is not None:
            rendered += f" | {output_text}"
        return rendered
    if event.event_type == "evaluation.completed":
        should_continue = bool(payload.get("should_continue"))
        goal_satisfied = bool(payload.get("goal_satisfied"))
        summary = _shorten_live_text(str(payload.get("summary", "")).strip())
        if should_continue:
            rendered = f"{prefix}evaluation: continue"
        elif goal_satisfied:
            rendered = f"{prefix}evaluation: goal satisfied"
        else:
            rendered = f"{prefix}evaluation: stop"
        if summary is not None:
            rendered += f" | {summary}"
        return rendered
    if event.event_type == "command.applied":
        command_type = str(payload.get("command_type", "")).strip() or "unknown"
        return f"{prefix}command applied: {command_type}"
    if event.event_type == "command.rejected":
        command_type = str(payload.get("command_type", "")).strip() or "unknown"
        reason = _shorten_live_text(str(payload.get("rejection_reason", "")).strip())
        rendered = f"{prefix}command rejected: {command_type}"
        if reason is not None:
            rendered += f" | {reason}"
        return rendered
    if event.event_type == "planning_trigger.enqueued":
        reason = str(payload.get("reason", "")).strip() or "unknown"
        return f"{prefix}planning trigger enqueued: {reason}"
    if event.event_type == "planning_trigger.coalesced":
        reason = str(payload.get("reason", "")).strip() or "unknown"
        return f"{prefix}planning trigger coalesced: {reason}"
    if event.event_type == "planning_trigger.applied":
        reason = str(payload.get("reason", "")).strip() or "unknown"
        return f"{prefix}planning trigger applied: {reason}"
    if event.event_type == "background_wakeup.reconciled":
        run_id = str(payload.get("run_id", "")).strip() or "unknown"
        return f"{prefix}background wakeup reconciled: run={run_id}"
    if event.event_type == "background_run.stale_detected":
        run_id = str(payload.get("run_id", "")).strip() or "unknown"
        return f"{prefix}stale background run detected: run={run_id}"
    if event.event_type == "operation.cycle_finished":
        return None
    return f"{prefix}{event.event_type}"


def _build_live_snapshot(
    operation_id: str,
    operation: OperationState | None,
    outcome: OperationOutcome | None,
) -> dict[str, object]:
    payload: dict[str, object] = {"operation_id": operation_id}
    if operation is None:
        payload["status"] = outcome.status.value if outcome is not None else "unknown"
        payload["summary"] = outcome.summary if outcome is not None else "Operation not found."
        return payload
    payload["status"] = operation.status.value
    payload["scheduler_state"] = operation.scheduler_state.value
    payload["involvement_level"] = operation.involvement_level.value
    payload["updated_at"] = operation.updated_at.isoformat()
    if operation.current_focus is not None:
        payload["focus"] = (
            f"{operation.current_focus.kind.value}:{operation.current_focus.target_id}"
        )
        if operation.current_focus.blocking_reason:
            payload["blocking_reason"] = operation.current_focus.blocking_reason
    active_session = operation.active_session_record
    if active_session is not None:
        payload["session_id"] = active_session.session_id
        payload["adapter_key"] = active_session.adapter_key
        payload["session_status"] = active_session.status.value
        if active_session.waiting_reason:
            payload["waiting_reason"] = active_session.waiting_reason
    if operation.attention_requests:
        open_attention = [
            item for item in operation.attention_requests if item.status is AttentionStatus.OPEN
        ]
        if open_attention:
            payload["open_attention_count"] = len(open_attention)
            payload["attention_title"] = open_attention[0].title
            payload["attention_brief"] = (
                f"[{open_attention[0].attention_type.value}] {open_attention[0].title}"
            )
    summary = outcome.summary if outcome is not None else operation.final_summary
    if summary:
        payload["summary"] = summary
    return payload


def _format_live_snapshot(snapshot: dict[str, object]) -> str:
    parts = [f"state: {snapshot.get('status', 'unknown')}"]
    scheduler_state = snapshot.get("scheduler_state")
    if isinstance(scheduler_state, str) and scheduler_state:
        parts.append(f"scheduler={scheduler_state}")
    session_id = snapshot.get("session_id")
    if isinstance(session_id, str) and session_id:
        parts.append(f"session={session_id}")
    adapter_key = snapshot.get("adapter_key")
    if isinstance(adapter_key, str) and adapter_key:
        parts.append(f"agent={adapter_key}")
    session_status = snapshot.get("session_status")
    if isinstance(session_status, str) and session_status and session_status != "idle":
        parts.append(f"session_status={session_status}")
    focus = snapshot.get("focus")
    if isinstance(focus, str) and focus:
        parts.append(f"focus={focus}")
    waiting_reason_raw = snapshot.get("waiting_reason")
    waiting_reason = _shorten_live_text(
        str(waiting_reason_raw) if waiting_reason_raw is not None else None
    )
    if waiting_reason is not None:
        parts.append(f"waiting={waiting_reason}")
    blocking_reason_raw = snapshot.get("blocking_reason")
    blocking_reason = _shorten_live_text(
        str(blocking_reason_raw) if blocking_reason_raw is not None else None
    )
    if blocking_reason is not None:
        parts.append(f"blocked_by={blocking_reason}")
    attention_brief_raw = snapshot.get("attention_brief")
    attention_brief = _shorten_live_text(
        str(attention_brief_raw) if attention_brief_raw is not None else None
    )
    if attention_brief is None:
        attention_title_raw = snapshot.get("attention_title")
        attention_brief = _shorten_live_text(
            str(attention_title_raw) if attention_title_raw is not None else None
        )
    if attention_brief is not None:
        count = snapshot.get("open_attention_count")
        if isinstance(count, int) and count > 0:
            parts.append(f"attention={count}:{attention_brief}")
    summary_raw = snapshot.get("summary")
    summary = _shorten_live_text(str(summary_raw) if summary_raw is not None else None)
    if summary is not None:
        parts.append(f"summary={summary}")
    return " | ".join(parts)


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


def _build_fleet_payload(
    snapshot: AgendaSnapshot,
    *,
    project: str | None,
) -> dict[str, object]:
    return {
        "project": project,
        "total_operations": snapshot.total_operations,
        "mix": _build_fleet_mix(snapshot),
        "needs_attention": [item.model_dump(mode="json") for item in snapshot.needs_attention],
        "active": [item.model_dump(mode="json") for item in snapshot.active],
        "recent": [item.model_dump(mode="json") for item in snapshot.recent],
        "control_hints": _build_fleet_control_hints(snapshot),
    }


def _build_fleet_mix(snapshot: AgendaSnapshot) -> dict[str, dict[str, int]]:
    items = [
        *snapshot.needs_attention,
        *snapshot.active,
        *snapshot.recent,
    ]
    return {
        "bucket_counts": {
            "needs_attention": len(snapshot.needs_attention),
            "active": len(snapshot.active),
            "recent": len(snapshot.recent),
        },
        "status_counts": _count_items_by_key(items, lambda item: item.status.value),
        "scheduler_counts": _count_items_by_key(items, lambda item: item.scheduler_state.value),
        "involvement_counts": _count_items_by_key(items, lambda item: item.involvement_level.value),
    }


def _count_items_by_key(
    items: list[AgendaItem],
    key_fn: Callable[[AgendaItem], str],
) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        key = key_fn(item)
        counts[key] = counts.get(key, 0) + 1
    return counts


def _build_fleet_control_hints(snapshot: AgendaSnapshot) -> list[str]:
    hints: list[str] = []

    def _append_hint(text: str) -> None:
        if text not in hints:
            hints.append(text)

    if snapshot.needs_attention:
        item = snapshot.needs_attention[0]
        _append_hint(f"operator dashboard {item.operation_id}")
        _append_hint(f"operator context {item.operation_id}")
        if item.runtime_alert is not None:
            _append_hint(f"operator resume {item.operation_id}")
        if item.open_attention_count > 0 or item.status is OperationStatus.NEEDS_HUMAN:
            _append_hint(f"operator attention {item.operation_id}")
        if item.scheduler_state in {SchedulerState.PAUSED, SchedulerState.PAUSE_REQUESTED}:
            _append_hint(f"operator unpause {item.operation_id}")
    if snapshot.active:
        item = snapshot.active[0]
        _append_hint(f"operator dashboard {item.operation_id}")
        _append_hint(f"operator watch {item.operation_id}")
        _append_hint(f"operator context {item.operation_id}")
        _append_hint(f"operator pause {item.operation_id}")
    if snapshot.recent:
        item = snapshot.recent[0]
        _append_hint(f"operator report {item.operation_id}")
    return hints


def _render_fleet_items_table(items: list[dict[str, object]]) -> Table:
    table = Table(expand=True)
    table.add_column("Operation", no_wrap=True)
    table.add_column("State", no_wrap=True)
    table.add_column("Objective")
    table.add_column("Focus")
    table.add_column("Attention / Alert")
    table.add_column("Latest")
    if not items:
        table.add_row("-", "-", "none", "-", "-", "-")
        return table
    for item in items[:8]:
        state = str(item.get("status") or "-")
        scheduler_state = str(item.get("scheduler_state") or "")
        if scheduler_state and scheduler_state != SchedulerState.ACTIVE.value:
            state += f" / {scheduler_state}"
        attention_bits: list[str] = []
        runtime_alert = _shorten_live_text(str(item.get("runtime_alert") or ""), limit=48)
        if runtime_alert is not None:
            attention_bits.append(runtime_alert)
        else:
            attention_briefs = item.get("attention_briefs")
            if isinstance(attention_briefs, list) and attention_briefs:
                attention_bits.append(
                    _shorten_live_text(str(attention_briefs[0]), limit=48)
                    or str(attention_briefs[0])
                )
            blocker_brief = _shorten_live_text(str(item.get("blocker_brief") or ""), limit=48)
            if blocker_brief is not None:
                attention_bits.append(blocker_brief)
        latest = _shorten_live_text(str(item.get("latest_outcome_brief") or "-"), limit=56) or "-"
        focus = _shorten_live_text(str(item.get("focus_brief") or "-"), limit=28) or "-"
        objective = _shorten_live_text(str(item.get("objective_brief") or "-"), limit=56) or "-"
        table.add_row(
            str(item.get("operation_id") or "-"),
            state,
            objective,
            focus,
            " | ".join(attention_bits) if attention_bits else "-",
            latest,
        )
    return table


def _render_fleet_dashboard(payload: dict[str, object]) -> Group:
    needs_attention = payload.get("needs_attention")
    active = payload.get("active")
    recent = payload.get("recent")
    hints = payload.get("control_hints")
    mix = payload.get("mix")
    header_lines = [
        f"total_operations={payload.get('total_operations', 0)}",
        (
            f"project={payload.get('project')}"
            if isinstance(payload.get("project"), str) and payload.get("project")
            else "project=all"
        ),
        (
            f"needs_attention={len(needs_attention)} active={len(active)} recent={len(recent)}"
            if isinstance(needs_attention, list)
            and isinstance(active, list)
            and isinstance(recent, list)
            else "needs_attention=0 active=0 recent=0"
        ),
    ]
    if isinstance(mix, dict):
        status_counts = mix.get("status_counts")
        scheduler_counts = mix.get("scheduler_counts")
        involvement_counts = mix.get("involvement_counts")
        if isinstance(status_counts, dict) and status_counts:
            header_lines.append("status_mix=" + _format_fleet_mix_counts(status_counts))
        if isinstance(scheduler_counts, dict) and scheduler_counts:
            header_lines.append("scheduler_mix=" + _format_fleet_mix_counts(scheduler_counts))
        if isinstance(involvement_counts, dict) and involvement_counts:
            header_lines.append("involvement_mix=" + _format_fleet_mix_counts(involvement_counts))
    hint_renderable = "\n".join(str(item) for item in hints if isinstance(item, str)) or "- none"
    recent_renderable = _render_fleet_items_table(recent) if isinstance(recent, list) else "-"
    return Group(
        Panel("\n".join(header_lines), title="Fleet Dashboard", border_style="cyan"),
        Columns(
            [
                Panel(
                    (
                        _render_fleet_items_table(needs_attention)
                        if isinstance(needs_attention, list)
                        else "-"
                    ),
                    title=(
                        f"Needs Attention ({len(needs_attention)})"
                        if isinstance(needs_attention, list)
                        else "Needs Attention"
                    ),
                    border_style="yellow",
                ),
                Panel(
                    _render_fleet_items_table(active) if isinstance(active, list) else "-",
                    title=f"Active ({len(active)})" if isinstance(active, list) else "Active",
                    border_style="green",
                ),
            ]
        ),
        Columns(
            [
                Panel(
                    recent_renderable,
                    title=f"Recent ({len(recent)})" if isinstance(recent, list) else "Recent",
                    border_style="blue",
                ),
                Panel(hint_renderable, title="Suggested Next Commands", border_style="magenta"),
            ]
        ),
    )


def _build_project_dashboard_payload(
    *,
    profile: ProjectProfile,
    resolved: dict[str, object],
    profile_path: Path,
    fleet: dict[str, object],
    active_policies: list[PolicyEntry],
) -> dict[str, object]:
    active_policy_payloads = [_policy_payload(item) for item in active_policies]
    category_counts: dict[str, int] = {}
    for policy in active_policies:
        key = policy.category.value
        category_counts[key] = category_counts.get(key, 0) + 1
    return {
        "project": profile.name,
        "profile_path": str(profile_path),
        "profile": profile.model_dump(mode="json"),
        "resolved": resolved,
        "policy_scope": f"profile:{profile.name}",
        "active_policies": active_policy_payloads,
        "policy_summary": {
            "active_count": len(active_policy_payloads),
            "category_counts": category_counts,
        },
        "fleet": fleet,
        "control_hints": _build_project_dashboard_control_hints(profile.name, fleet=fleet),
    }


def _build_project_dashboard_control_hints(
    project_name: str,
    *,
    fleet: dict[str, object],
) -> list[str]:
    hints = [
        f'operator run --project {project_name} "<objective>"',
        f"operator project inspect {project_name}",
        f"operator project resolve {project_name}",
        f"operator fleet --project {project_name} --all --once",
        f"operator policy list --project profile:{project_name}",
    ]
    fleet_hints = fleet.get("control_hints")
    if isinstance(fleet_hints, list):
        for item in fleet_hints:
            if isinstance(item, str) and item not in hints:
                hints.append(item)
    return hints


def _render_project_policy_table(items: list[dict[str, object]]) -> Table:
    table = Table(expand=True)
    table.add_column("Policy", no_wrap=True)
    table.add_column("Category", no_wrap=True)
    table.add_column("Applicability")
    table.add_column("Rule")
    if not items:
        table.add_row("-", "-", "none", "-")
        return table
    for item in items[:8]:
        table.add_row(
            str(item.get("policy_id") or "-"),
            str(item.get("category") or "-"),
            _shorten_live_text(str(item.get("applicability_summary") or "-"), limit=44) or "-",
            _shorten_live_text(str(item.get("rule_text") or "-"), limit=58) or "-",
        )
    return table


def _render_project_dashboard(payload: dict[str, object]) -> Group:
    resolved = payload.get("resolved")
    fleet = payload.get("fleet")
    policy_summary = payload.get("policy_summary")
    active_policies = payload.get("active_policies")
    hints = payload.get("control_hints")
    header_lines = [
        f"project={payload.get('project')}",
        f"profile_path={payload.get('profile_path')}",
    ]
    if isinstance(resolved, dict):
        cwd = resolved.get("cwd")
        if cwd:
            header_lines.append(f"cwd={cwd}")
        agents = resolved.get("default_agents")
        if isinstance(agents, list) and agents:
            header_lines.append("default_agents=" + ", ".join(str(item) for item in agents))
        header_lines.append(
            "max_iterations="
            + str(resolved.get("max_iterations", "-"))
            + " involvement="
            + str(resolved.get("involvement_level", "-"))
        )
    if isinstance(policy_summary, dict):
        header_lines.append(f"active_policies={policy_summary.get('active_count', 0)}")
        category_counts = policy_summary.get("category_counts")
        if isinstance(category_counts, dict) and category_counts:
            header_lines.append("policy_mix=" + _format_fleet_mix_counts(category_counts))

    resolved_lines = ["- none"]
    if isinstance(resolved, dict):
        resolved_lines = []
        if resolved.get("cwd"):
            resolved_lines.append(f"cwd={resolved['cwd']}")
        agents = resolved.get("default_agents")
        if isinstance(agents, list) and agents:
            resolved_lines.append("default_agents=" + ", ".join(str(item) for item in agents))
        harness = (
            _shorten_live_text(str(resolved.get("harness_instructions") or "-"), limit=88) or "-"
        )
        resolved_lines.append(f"harness={harness}")
        success_criteria = resolved.get("success_criteria")
        if isinstance(success_criteria, list) and success_criteria:
            resolved_lines.append(
                "success_criteria=" + " | ".join(str(item) for item in success_criteria[:3])
            )
        resolved_lines.append(f"max_iterations={resolved.get('max_iterations', '-')}")
        resolved_lines.append(f"involvement={resolved.get('involvement_level', '-')}")
        overrides = resolved.get("overrides")
        if isinstance(overrides, list) and overrides:
            resolved_lines.append("overrides=" + ", ".join(str(item) for item in overrides))

    fleet_payload = fleet if isinstance(fleet, dict) else {}
    needs_attention = fleet_payload.get("needs_attention")
    active = fleet_payload.get("active")
    recent = fleet_payload.get("recent")
    mix = fleet_payload.get("mix")
    fleet_lines = [f"total_operations={fleet_payload.get('total_operations', 0)}"]
    if isinstance(mix, dict):
        bucket_counts = mix.get("bucket_counts")
        if isinstance(bucket_counts, dict) and bucket_counts:
            fleet_lines.append("buckets=" + _format_fleet_mix_counts(bucket_counts))
    hint_renderable = "\n".join(str(item) for item in hints if isinstance(item, str)) or "- none"
    return Group(
        Panel(
            "\n".join(header_lines),
            title=f"Project Dashboard: {payload.get('project')}",
            border_style="cyan",
        ),
        Columns(
            [
                Panel("\n".join(resolved_lines), title="Resolved Defaults", border_style="green"),
                Panel(
                    _render_project_policy_table(active_policies)
                    if isinstance(active_policies, list)
                    else "-",
                    title=(
                        f"Active Policies ({len(active_policies)})"
                        if isinstance(active_policies, list)
                        else "Active Policies"
                    ),
                    border_style="yellow",
                ),
            ]
        ),
        Panel("\n".join(fleet_lines), title="Fleet Summary", border_style="blue"),
        Columns(
            [
                Panel(
                    _render_fleet_items_table(needs_attention)
                    if isinstance(needs_attention, list)
                    else "-",
                    title=(
                        f"Needs Attention ({len(needs_attention)})"
                        if isinstance(needs_attention, list)
                        else "Needs Attention"
                    ),
                    border_style="yellow",
                ),
                Panel(
                    _render_fleet_items_table(active) if isinstance(active, list) else "-",
                    title=f"Active ({len(active)})" if isinstance(active, list) else "Active",
                    border_style="green",
                ),
            ]
        ),
        Columns(
            [
                Panel(
                    _render_fleet_items_table(recent) if isinstance(recent, list) else "-",
                    title=f"Recent ({len(recent)})" if isinstance(recent, list) else "Recent",
                    border_style="blue",
                ),
                Panel(hint_renderable, title="Suggested Next Commands", border_style="magenta"),
            ]
        ),
    )


def _format_fleet_mix_counts(counts: dict[str, int]) -> str:
    return ", ".join(
        f"{key}={count}"
        for key, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
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


def _build_durable_truth_payload(operation: OperationState) -> dict[str, object]:
    return {
        "task_counts": _summarize_task_counts(operation),
        "tasks": [task.model_dump(mode="json") for task in operation.tasks],
        "memory": {
            "current": [
                entry.model_dump(mode="json")
                for entry in _memory_payload(operation, include_inactive=False)
            ],
            "inactive": [
                entry.model_dump(mode="json")
                for entry in _memory_payload(operation, include_inactive=True)
                if entry.freshness is not MemoryFreshness.CURRENT
            ],
        },
        "artifacts": [artifact.model_dump(mode="json") for artifact in operation.artifacts],
    }


def _session_payload(session: SessionRecord) -> dict[str, object]:
    payload = session.model_dump(mode="json")
    payload["session_id"] = session.session_id
    payload["adapter_key"] = session.adapter_key
    payload["status"] = session.status.value
    payload["session_name"] = session.handle.session_name
    payload["display_name"] = session.handle.display_name
    return payload


def _operation_payload(operation: OperationState) -> dict[str, object]:
    payload = operation.model_dump(mode="json")
    payload["sessions"] = [_session_payload(item) for item in operation.sessions]
    return payload


def _resolve_run_mode(operation: OperationState) -> str:
    raw_mode = operation.runtime_hints.metadata.get("run_mode")
    if isinstance(raw_mode, str) and raw_mode.strip():
        return raw_mode.strip()
    return RunMode.ATTACHED.value


def _available_agent_descriptors_payload(operation: OperationState) -> list[dict[str, object]]:
    raw = operation.runtime_hints.metadata.get("available_agent_descriptors")
    if not isinstance(raw, list):
        return []
    rendered: list[dict[str, object]] = []
    for item in raw:
        if isinstance(item, dict):
            rendered.append(item)
    return rendered


def _build_operation_context_payload(operation: OperationState) -> dict[str, object]:
    metadata = operation.goal.metadata
    payload: dict[str, object] = {
        "operation_id": operation.operation_id,
        "status": operation.status.value,
        "scheduler_state": operation.scheduler_state.value,
        "run_mode": _resolve_run_mode(operation),
        "objective": operation.objective_state.objective,
        "harness_instructions": operation.objective_state.harness_instructions,
        "success_criteria": list(operation.objective_state.success_criteria),
        "allowed_agents": list(operation.policy.allowed_agents),
        "available_agent_descriptors": _available_agent_descriptors_payload(operation),
        "max_iterations": operation.execution_budget.max_iterations,
        "involvement_level": operation.involvement_level.value,
    }
    if operation.current_focus is not None:
        payload["current_focus"] = operation.current_focus.model_dump(mode="json")
    active_session = operation.active_session_record
    if active_session is not None:
        payload["active_session"] = {
            "session_id": active_session.session_id,
            "adapter_key": active_session.adapter_key,
            "session_name": active_session.handle.session_name,
            "status": active_session.status.value,
            "waiting_reason": active_session.waiting_reason,
        }
    open_attention = [
        attention.model_dump(mode="json")
        for attention in operation.attention_requests
        if attention.status is AttentionStatus.OPEN
    ]
    payload["open_attention"] = open_attention
    resolved_profile = metadata.get("resolved_project_profile")
    resolved_launch = metadata.get("resolved_operator_launch")
    payload["project_context"] = {
        "profile_name": (
            metadata.get("project_profile_name")
            if isinstance(metadata.get("project_profile_name"), str)
            else None
        ),
        "policy_scope": (
            metadata.get("policy_scope") if isinstance(metadata.get("policy_scope"), str) else None
        ),
        "resolved_profile": resolved_profile if isinstance(resolved_profile, dict) else None,
        "resolved_launch": resolved_launch if isinstance(resolved_launch, dict) else None,
    }
    payload["policy_coverage"] = operation.policy_coverage.model_dump(mode="json")
    payload["active_policies"] = [
        _policy_payload(policy, operation) for policy in operation.active_policies
    ]
    return payload


def _emit_context_lines(operation: OperationState) -> list[str]:
    payload = _build_operation_context_payload(operation)
    lines = [f"Operation {operation.operation_id}", "Goal:"]
    lines.append(f"- Objective: {payload['objective']}")
    harness = payload.get("harness_instructions")
    lines.append(f"- Harness: {harness or '-'}")
    success_criteria = payload.get("success_criteria")
    if isinstance(success_criteria, list) and success_criteria:
        lines.append("- Success criteria: " + " | ".join(str(item) for item in success_criteria))
    else:
        lines.append("- Success criteria: -")

    lines.append("Runtime:")
    lines.append(f"- Status: {payload['status']}")
    lines.append(f"- Scheduler: {payload['scheduler_state']}")
    lines.append(f"- Run mode: {payload['run_mode']}")
    lines.append(f"- Involvement: {payload['involvement_level']}")
    allowed_agents = payload.get("allowed_agents")
    if isinstance(allowed_agents, list) and allowed_agents:
        lines.append("- Allowed agents: " + ", ".join(str(item) for item in allowed_agents))
    else:
        lines.append("- Allowed agents: -")
    descriptors = payload.get("available_agent_descriptors")
    if isinstance(descriptors, list) and descriptors:
        lines.append("- Agent capabilities:")
        for descriptor in descriptors:
            if not isinstance(descriptor, dict):
                continue
            capabilities = descriptor.get("capabilities")
            capability_names = (
                ", ".join(
                    str(item.get("name"))
                    for item in capabilities
                    if isinstance(item, dict) and item.get("name")
                )
                if isinstance(capabilities, list)
                else "-"
            )
            descriptor_line = (
                f"  {descriptor.get('key') or '-'}"
                f" ({descriptor.get('display_name') or '-'})"
                f": capabilities={capability_names}"
            )
            if descriptor.get("supports_follow_up") is not None:
                descriptor_line += (
                    f" follow_up={'yes' if descriptor.get('supports_follow_up') else 'no'}"
                )
            lines.append(descriptor_line)
    else:
        lines.append("- Agent capabilities: -")
    lines.append(f"- Max iterations: {payload['max_iterations']}")

    current_focus = payload.get("current_focus")
    if isinstance(current_focus, dict):
        focus_kind = current_focus.get("kind")
        focus_target = current_focus.get("target_id")
        focus_mode = current_focus.get("mode")
        lines.append(f"- Current focus: {focus_kind}:{focus_target} mode={focus_mode}")

    active_session = payload.get("active_session")
    if isinstance(active_session, dict):
        session_line = (
            "- Active session: "
            f"{active_session.get('session_id')} [{active_session.get('adapter_key')}] "
            f"status={active_session.get('status')}"
        )
        session_name = active_session.get("session_name")
        if isinstance(session_name, str) and session_name:
            session_line += f" name={session_name}"
        lines.append(session_line)
        waiting_reason = active_session.get("waiting_reason")
        if isinstance(waiting_reason, str) and waiting_reason.strip():
            lines.append(f"  waiting: {waiting_reason.strip()}")

    open_attention = payload.get("open_attention")
    if isinstance(open_attention, list):
        lines.append(f"- Open attention: {len(open_attention)}")

    project_context = payload.get("project_context")
    lines.append("Project context:")
    if isinstance(project_context, dict):
        lines.append(f"- Profile: {project_context.get('profile_name') or '-'}")
        lines.append(f"- Policy scope: {project_context.get('policy_scope') or '-'}")
        resolved_launch = project_context.get("resolved_launch")
        if isinstance(resolved_launch, dict):
            lines.append(f"- Data dir: {resolved_launch.get('data_dir') or '-'}")
            lines.append(f"- Data dir source: {resolved_launch.get('data_dir_source') or '-'}")
            lines.append(
                f"- Profile selection: {resolved_launch.get('profile_source') or 'none'}"
            )
        resolved_profile = project_context.get("resolved_profile")
        if isinstance(resolved_profile, dict):
            resolved_cwd = resolved_profile.get("cwd") or "-"
            resolved_agents = resolved_profile.get("default_agents") or []
            resolved_harness = resolved_profile.get("harness_instructions") or "-"
            resolved_involvement = resolved_profile.get("involvement_level") or "-"
            resolved_iterations = resolved_profile.get("max_iterations") or "-"
            overrides = resolved_profile.get("overrides") or []
            lines.append(f"- Resolved cwd: {resolved_cwd}")
            lines.append(
                "- Resolved agents: "
                + (", ".join(str(item) for item in resolved_agents) if resolved_agents else "-")
            )
            lines.append(f"- Resolved harness: {resolved_harness}")
            lines.append(f"- Resolved involvement: {resolved_involvement}")
            lines.append(f"- Resolved max iterations: {resolved_iterations}")
            lines.append(
                "- CLI/profile overrides: "
                + (", ".join(str(item) for item in overrides) if overrides else "none")
            )
    policy_coverage = payload.get("policy_coverage")
    if isinstance(policy_coverage, dict):
        lines.append(
            "- Policy coverage: "
            f"{policy_coverage.get('status') or '-'} "
            f"(scope_entries={policy_coverage.get('scoped_policy_count') or 0}, "
            f"active_now={policy_coverage.get('active_policy_count') or 0})"
        )
        summary = policy_coverage.get("summary")
        if isinstance(summary, str) and summary:
            lines.append(f"  summary: {summary}")

    active_policies = payload.get("active_policies")
    lines.append("Active policy:")
    if not isinstance(active_policies, list) or not active_policies:
        lines.append("- none")
        return lines
    for policy in active_policies:
        if not isinstance(policy, dict):
            continue
        lines.append(
            f"- {policy.get('policy_id')} [{policy.get('category')}] {policy.get('title')}"
        )
        lines.append(f"  rule: {policy.get('rule_text')}")
        applicability = policy.get("applicability_summary")
        if isinstance(applicability, str) and applicability:
            lines.append(f"  applies: {applicability}")
        match_reasons = policy.get("match_reasons")
        if isinstance(match_reasons, list) and match_reasons:
            lines.append("  matched_by: " + " | ".join(str(item) for item in match_reasons))
        rationale = policy.get("rationale")
        if isinstance(rationale, str) and rationale:
            lines.append(f"  rationale: {rationale}")
    return lines


def _format_dashboard_command(command: OperationCommand) -> str:
    rendered = (
        f"{command.command_type.value} [{command.status.value}] "
        f"target={command.target_scope.value}:{command.target_id or '-'}"
    )
    payload_text = _shorten_live_text(json.dumps(command.payload, ensure_ascii=False), limit=80)
    if payload_text is not None and payload_text != "{}":
        rendered += f" | payload={payload_text}"
    if command.rejection_reason:
        rendered += f" | reason={command.rejection_reason}"
    return rendered


def _build_dashboard_control_hints(operation: OperationState) -> list[str]:
    hints = [
        f"operator context {operation.operation_id}",
        f"operator watch {operation.operation_id}",
    ]
    policy_scope = operation.policy_coverage.project_scope
    if operation.status is OperationStatus.RUNNING:
        if operation.scheduler_state in {SchedulerState.PAUSED, SchedulerState.PAUSE_REQUESTED}:
            hints.append(f"operator unpause {operation.operation_id}")
        else:
            hints.append(f"operator pause {operation.operation_id}")
        if (
            operation.active_session_record is not None
            and operation.scheduler_state is not SchedulerState.DRAINING
        ):
            hints.append(f"operator interrupt {operation.operation_id}")
    open_attention = [
        attention
        for attention in operation.attention_requests
        if attention.status is AttentionStatus.OPEN
    ]
    if any(session.adapter_key in {"codex_acp", "claude_acp"} for session in operation.sessions):
        hints.append(f"operator log {operation.operation_id}")
    if open_attention:
        hints.append(
            "operator answer "
            f"{operation.operation_id} {open_attention[0].attention_id} --text '...'"
        )
    if (
        operation.policy_coverage.status.value == "uncovered"
        and isinstance(policy_scope, str)
        and policy_scope.startswith("profile:")
    ):
        hints.append(f"operator policy list --project {policy_scope.removeprefix('profile:')}")
    return hints


def _status_action_hint(operation: OperationState) -> str | None:
    open_attention = [
        attention
        for attention in operation.attention_requests
        if attention.status is AttentionStatus.OPEN
    ]
    if open_attention:
        return (
            f"operator answer {operation.operation_id} "
            f"{open_attention[0].attention_id} --text '...'"
        )
    if (
        operation.active_session_record is not None
        and operation.scheduler_state is not SchedulerState.DRAINING
    ):
        return f"operator interrupt {operation.operation_id}"
    if operation.scheduler_state in {SchedulerState.PAUSED, SchedulerState.PAUSE_REQUESTED}:
        return f"operator unpause {operation.operation_id}"
    return None


def _render_status_brief(operation: OperationState) -> str:
    attention_count = sum(
        1 for attention in operation.attention_requests if attention.status is AttentionStatus.OPEN
    )
    return (
        f"{operation.operation_id} {operation.status.value.upper()} "
        f"iter={len(operation.iterations)}/{operation.execution_budget.max_iterations} "
        f"tasks={_summarize_task_counts(operation) or 'none'} "
        f"att=[!!{attention_count}]"
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
    raw_path = session.metadata.get("log_path")
    if not isinstance(raw_path, str) or not raw_path.strip():
        raise typer.BadParameter(
            f"Claude log path for session {session.session_id!r} is not available."
        )
    path = Path(raw_path)
    if not path.exists():
        raise typer.BadParameter(
            f"Claude log for session {session.session_id!r} was not found at {str(path)!r}."
        )
    return path


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
    if normalized not in {"auto", "codex", "claude"}:
        raise typer.BadParameter("--agent must be one of: auto, codex, claude")
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
    active = operation.active_session
    if active is not None:
        if active.adapter_key == "codex_acp":
            return "codex", active
        if active.adapter_key == "claude_acp":
            return "claude", active
    supported = [
        item
        for item in session_handles
        if item.adapter_key in {"codex_acp", "claude_acp"}
    ]
    adapter_keys = sorted({item.adapter_key for item in supported})
    if len(adapter_keys) == 1 and supported:
        return ("codex" if adapter_keys[0] == "codex_acp" else "claude"), supported[-1]
    raise typer.BadParameter(
        f"Operation {operation.operation_id!r} has multiple agent transcript candidates. "
        "Use --agent codex or --agent claude."
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
    return None


def _build_dashboard_payload(
    operation: OperationState,
    *,
    brief: TraceBriefBundle | None,
    outcome: OperationOutcome | None,
    runtime_alert: str | None,
    commands: list[OperationCommand],
    events: list[RunEvent],
    upstream_transcript: dict[str, object] | None,
) -> dict[str, object]:
    active_session = operation.active_session_record
    context_payload = _build_operation_context_payload(operation)
    open_attention = [
        attention
        for attention in operation.attention_requests
        if attention.status is AttentionStatus.OPEN
    ]
    recent_events = [
        rendered
        for rendered in (_format_live_event(event) for event in events[-8:])
        if rendered is not None
    ]
    tasks = [
        {
            "task_id": task.task_id,
            "task_short_id": f"task-{task.task_short_id}",
            "title": task.title,
            "status": task.status.value,
            "priority": task.effective_priority,
            "assigned_agent": task.assigned_agent,
            "linked_session_id": task.linked_session_id,
        }
        for task in sorted(
            operation.tasks,
            key=lambda item: (-item.effective_priority, item.created_at, item.task_id),
        )[:8]
    ]
    sessions = [
        {
            "session_id": session.session_id,
            "adapter_key": session.adapter_key,
            "status": session.status.value,
            "session_name": session.handle.session_name,
            "waiting_reason": session.waiting_reason,
            "bound_task_ids": list(session.bound_task_ids),
        }
        for session in sorted(
            operation.sessions,
            key=lambda item: (item.created_at, item.session_id),
        )
    ]
    payload: dict[str, object] = {
        "operation_id": operation.operation_id,
        "status": operation.status.value,
        "scheduler_state": operation.scheduler_state.value,
        "run_mode": _resolve_run_mode(operation),
        "involvement_level": operation.involvement_level.value,
        "objective": operation.objective_state.objective,
        "harness_instructions": operation.objective_state.harness_instructions,
        "summary": outcome.summary if outcome is not None else operation.final_summary,
        "focus": (
            f"{operation.current_focus.kind.value}:{operation.current_focus.target_id}"
            if operation.current_focus is not None
            else None
        ),
        "brief_summary": _build_brief_summary_payload(
            operation,
            brief,
            runtime_alert=runtime_alert,
        ),
        "task_counts": _summarize_task_counts(operation),
        "runtime_alert": runtime_alert,
        "active_session": (
            {
                "session_id": active_session.session_id,
                "adapter_key": active_session.adapter_key,
                "status": active_session.status.value,
                "session_name": active_session.handle.session_name,
                "waiting_reason": active_session.waiting_reason,
            }
            if active_session is not None
            else None
        ),
        "available_agent_descriptors": context_payload.get("available_agent_descriptors"),
        "project_context": context_payload.get("project_context"),
        "policy_coverage": context_payload.get("policy_coverage"),
        "active_policies": context_payload.get("active_policies"),
        "attention": [
            {
                "attention_id": attention.attention_id,
                "attention_type": attention.attention_type.value,
                "blocking": attention.blocking,
                "title": attention.title,
                "question": attention.question,
                "context_brief": attention.context_brief,
                "suggested_options": list(attention.suggested_options),
            }
            for attention in open_attention
        ],
        "tasks": tasks,
        "sessions": sessions,
        "recent_events": recent_events,
        "recent_commands": [
            {
                "command_id": command.command_id,
                "command_type": command.command_type.value,
                "status": command.status.value,
                "target_scope": command.target_scope.value,
                "target_id": command.target_id,
                "payload": command.payload,
                "rejection_reason": command.rejection_reason,
                "summary": _format_dashboard_command(command),
            }
            for command in sorted(commands, key=lambda item: item.submitted_at)[-6:]
        ],
        "upstream_transcript": upstream_transcript,
        "codex_log": (
            list(upstream_transcript.get("events", []))
            if isinstance(upstream_transcript, dict)
            and upstream_transcript.get("adapter_key") == "codex_acp"
            else []
        ),
        "control_hints": _build_dashboard_control_hints(operation),
    }
    return payload


def _render_dashboard(payload: dict[str, object]) -> Group:
    active_session = payload.get("active_session")
    brief_summary = payload.get("brief_summary")
    project_context = payload.get("project_context")
    policy_coverage = payload.get("policy_coverage")
    active_policies = payload.get("active_policies")
    header_lines = [
        f"status={payload.get('status')} scheduler={payload.get('scheduler_state')} "
        f"run_mode={payload.get('run_mode')} involvement={payload.get('involvement_level')}",
        (
            f"objective: {brief_summary.get('objective')}"
            if isinstance(brief_summary, dict) and brief_summary.get("objective")
            else f"objective: {payload.get('objective')}"
        ),
        (
            f"harness: {brief_summary.get('harness')}"
            if isinstance(brief_summary, dict) and brief_summary.get("harness")
            else f"harness: {payload.get('harness_instructions') or '-'}"
        ),
        (
            f"focus: {brief_summary.get('focus') or '-'}"
            if isinstance(brief_summary, dict)
            else f"focus: {payload.get('focus') or '-'}"
        ),
        f"task_counts: {payload.get('task_counts') or 'none'}",
    ]
    if isinstance(active_session, dict):
        session_line = (
            "active session: "
            f"{active_session.get('session_id')} [{active_session.get('adapter_key')}] "
            f"status={active_session.get('status')}"
        )
        if active_session.get("session_name"):
            session_line += f" name={active_session.get('session_name')}"
        header_lines.append(session_line)
        waiting_reason = active_session.get("waiting_reason")
        if isinstance(waiting_reason, str) and waiting_reason.strip():
            header_lines.append(f"waiting: {waiting_reason.strip()}")
    if isinstance(brief_summary, dict):
        latest = brief_summary.get("latest")
        if isinstance(latest, str) and latest.strip():
            header_lines.append(f"latest: {latest.strip()}")
        verification = brief_summary.get("verification")
        if isinstance(verification, str) and verification.strip():
            header_lines.append(f"verification: {verification.strip()}")
        blockers = brief_summary.get("blockers")
        if isinstance(blockers, str) and blockers.strip():
            header_lines.append(f"blockers: {blockers.strip()}")
        next_step = brief_summary.get("next_step")
        if isinstance(next_step, str) and next_step.strip():
            header_lines.append(f"next: {next_step.strip()}")
        blocker = brief_summary.get("blocker")
        if isinstance(blocker, str) and blocker.strip():
            header_lines.append(f"blocker: {blocker.strip()}")
        runtime_alert = brief_summary.get("runtime_alert")
    else:
        summary = payload.get("summary")
        if isinstance(summary, str) and summary.strip():
            header_lines.append(f"summary: {summary.strip()}")
        runtime_alert = payload.get("runtime_alert")
    if isinstance(runtime_alert, str) and runtime_alert.strip():
        header_lines.append(f"alert: {runtime_alert.strip()}")

    context_lines = []
    if isinstance(project_context, dict):
        context_lines.append(f"profile: {project_context.get('profile_name') or '-'}")
        context_lines.append(f"policy_scope: {project_context.get('policy_scope') or '-'}")
        resolved_profile = project_context.get("resolved_profile")
        if isinstance(resolved_profile, dict):
            context_lines.append(f"cwd: {resolved_profile.get('cwd') or '-'}")
            agents = resolved_profile.get("default_agents") or []
            context_lines.append(
                "default_agents: " + (", ".join(str(item) for item in agents) if agents else "-")
            )
    available_agent_descriptors = payload.get("available_agent_descriptors")
    if isinstance(available_agent_descriptors, list) and available_agent_descriptors:
        for descriptor in available_agent_descriptors:
            if not isinstance(descriptor, dict):
                continue
            capabilities = descriptor.get("capabilities")
            capability_names = (
                ", ".join(
                    str(item.get("name"))
                    for item in capabilities
                    if isinstance(item, dict) and item.get("name")
                )
                if isinstance(capabilities, list)
                else "-"
            )
            context_lines.append(
                f"agent: {descriptor.get('key') or '-'}"
                f" | follow_up={'yes' if descriptor.get('supports_follow_up') else 'no'}"
                f" | capabilities: {capability_names}"
            )
    if isinstance(policy_coverage, dict):
        context_lines.append(
            "policy_coverage: "
            f"{policy_coverage.get('status') or '-'} "
            f"(scope_entries={policy_coverage.get('scoped_policy_count') or 0}, "
            f"active_now={policy_coverage.get('active_policy_count') or 0})"
        )
        summary = policy_coverage.get("summary")
        if isinstance(summary, str) and summary:
            context_lines.append(f"coverage_summary: {summary}")
    if isinstance(active_policies, list) and active_policies:
        for policy in active_policies[:3]:
            if isinstance(policy, dict):
                policy_line = (
                    f"policy: {policy.get('policy_id')} [{policy.get('category')}] "
                    f"{policy.get('title')}"
                )
                applicability = policy.get("applicability_summary")
                if isinstance(applicability, str) and applicability:
                    policy_line += f" | applies: {applicability}"
                match_reasons = policy.get("match_reasons")
                if isinstance(match_reasons, list) and match_reasons:
                    policy_line += " | matched_by: " + ", ".join(
                        str(item) for item in match_reasons
                    )
                context_lines.append(policy_line)
    if not context_lines:
        context_lines.append("- none")

    attention_table = Table(expand=True)
    attention_table.add_column("Type")
    attention_table.add_column("Title")
    attention_table.add_column("Blocking", justify="center")
    attention_items = payload.get("attention")
    if isinstance(attention_items, list) and attention_items:
        for item in attention_items[:5]:
            if not isinstance(item, dict):
                continue
            attention_table.add_row(
                str(item.get("attention_type") or "-"),
                _shorten_live_text(str(item.get("title") or "-"), limit=60) or "-",
                "yes" if item.get("blocking") else "no",
            )
    else:
        attention_table.add_row("-", "none", "-")

    tasks_table = Table(expand=True)
    tasks_table.add_column("Task")
    tasks_table.add_column("Status")
    tasks_table.add_column("Priority", justify="right")
    tasks_table.add_column("Agent")
    task_items = payload.get("tasks")
    if isinstance(task_items, list) and task_items:
        for item in task_items:
            if not isinstance(item, dict):
                continue
            tasks_table.add_row(
                _shorten_live_text(str(item.get("title") or "-"), limit=50) or "-",
                str(item.get("status") or "-"),
                str(item.get("priority") or "-"),
                str(item.get("assigned_agent") or "-"),
            )
    else:
        tasks_table.add_row("none", "-", "-", "-")

    sessions_table = Table(expand=True)
    sessions_table.add_column("Session")
    sessions_table.add_column("Agent")
    sessions_table.add_column("Status")
    sessions_table.add_column("Waiting")
    session_items = payload.get("sessions")
    if isinstance(session_items, list) and session_items:
        for item in session_items[:6]:
            if not isinstance(item, dict):
                continue
            sessions_table.add_row(
                str(item.get("session_id") or "-"),
                str(item.get("adapter_key") or "-"),
                str(item.get("status") or "-"),
                _shorten_live_text(str(item.get("waiting_reason") or "-"), limit=40) or "-",
            )
    else:
        sessions_table.add_row("none", "-", "-", "-")

    recent_event_lines = payload.get("recent_events")
    event_renderable = (
        "\n".join(str(item) for item in recent_event_lines if isinstance(item, str)) or "- none"
    )
    recent_command_lines = payload.get("recent_commands")
    command_renderable = (
        "\n".join(
            str(item.get("summary"))
            for item in recent_command_lines
            if isinstance(item, dict) and isinstance(item.get("summary"), str)
        )
        or "- none"
    )
    transcript_title = "Upstream Transcript"
    transcript_renderable = "- none"
    transcript_payload = payload.get("upstream_transcript")
    if isinstance(transcript_payload, dict):
        transcript_title = str(transcript_payload.get("title") or transcript_title)
        transcript_lines = []
        session_id = transcript_payload.get("session_id")
        if isinstance(session_id, str) and session_id:
            transcript_lines.append(f"session: {session_id}")
        events = transcript_payload.get("events")
        if isinstance(events, list) and events:
            transcript_lines.extend(str(item) for item in events if isinstance(item, str))
        command_hint = transcript_payload.get("command_hint")
        if isinstance(command_hint, str) and command_hint:
            transcript_lines.append(f"drill-down: {command_hint}")
        transcript_renderable = "\n".join(transcript_lines) or "- none"
    control_hints = payload.get("control_hints")
    hint_renderable = (
        "\n".join(str(item) for item in control_hints if isinstance(item, str)) or "- none"
    )

    return Group(
        Panel(
            "\n".join(header_lines),
            title=f"Operation Dashboard: {payload.get('operation_id')}",
            border_style="cyan",
        ),
        Columns(
            [
                Panel("\n".join(context_lines), title="Control Context", border_style="blue"),
                Panel(attention_table, title="Attention", border_style="yellow"),
            ]
        ),
        Columns(
            [
                Panel(tasks_table, title="Tasks", border_style="green"),
                Panel(sessions_table, title="Sessions", border_style="magenta"),
            ]
        ),
        Columns(
            [
                Panel(event_renderable, title="Recent Events", border_style="blue"),
                Panel(command_renderable, title="Recent Commands", border_style="red"),
            ]
        ),
        Columns(
            [
                Panel(transcript_renderable, title=transcript_title, border_style="magenta"),
                Panel(hint_renderable, title="Control Hints", border_style="cyan"),
            ]
        ),
    )


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
    store = build_store(settings)
    trace_store = build_trace_store(settings)
    event_sink = build_event_sink(settings, operation_id)
    inbox = build_wakeup_inbox(settings)
    supervisor = build_background_run_inspection_store(settings)
    command_inbox = build_command_inbox(settings)

    async def _inspect() -> None:
        operation = await store.load_operation(operation_id)
        outcome = await store.load_outcome(operation_id)
        brief = await trace_store.load_brief_bundle(operation_id)
        report = await trace_store.load_report(operation_id)
        trace_records = await trace_store.load_trace_records(operation_id)
        memos = await trace_store.load_decision_memos(operation_id)
        events = event_sink.read_events(operation_id)
        wakeups = inbox.read_all(operation_id)
        commands = [item.model_dump(mode="json") for item in await command_inbox.list(operation_id)]
        background_runs = [
            item.model_dump(mode="json") for item in await supervisor.list_runs(operation_id)
        ]
        if operation is None:
            raise typer.BadParameter(f"Operation {operation_id!r} was not found.")
        live_runs = [ExecutionState.model_validate(item) for item in background_runs]
        operation = _overlay_live_background_progress(operation, live_runs)
        runtime_alert = _build_runtime_alert(
            status=operation.status,
            wakeups=wakeups,
            background_runs=background_runs,
        )
        if json_mode:
            payload: dict[str, object] = {
                "operation": _operation_payload(operation),
                "outcome": outcome.model_dump(mode="json") if outcome is not None else None,
                "brief": brief.model_dump(mode="json") if brief is not None else None,
                "report": report,
                "commands": commands,
                "durable_truth": _build_durable_truth_payload(operation),
            }
            if runtime_alert is not None:
                payload["runtime_alert"] = runtime_alert
            if full:
                payload["trace_records"] = [item.model_dump(mode="json") for item in trace_records]
                payload["decision_memos"] = [item.model_dump(mode="json") for item in memos]
                payload["events"] = [item.model_dump(mode="json") for item in events]
                payload["wakeups"] = wakeups
                payload["background_runs"] = background_runs
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
            for wakeup in wakeups:
                typer.echo(json.dumps(wakeup, indent=2, ensure_ascii=False))
            typer.echo("\nBackground runs:")
            for run in background_runs:
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
    store = build_store(settings)
    trace_store = build_trace_store(settings)

    async def _report() -> None:
        operation = await store.load_operation(operation_id)
        outcome = await store.load_outcome(operation_id)
        brief = await trace_store.load_brief_bundle(operation_id)
        report_text = await trace_store.load_report(operation_id)
        if operation is None or report_text is None:
            raise typer.BadParameter(f"Report for {operation_id!r} was not found.")
        if json_mode:
            payload = {
                "operation_id": operation_id,
                "brief": brief.model_dump(mode="json") if brief is not None else None,
                "outcome": outcome.model_dump(mode="json") if outcome is not None else None,
                "report": report_text,
                "durable_truth": _build_durable_truth_payload(operation),
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
    store = build_store(settings)

    async def _context() -> None:
        operation = await store.load_operation(operation_id)
        if operation is None:
            raise typer.BadParameter(f"Operation {operation_id!r} was not found.")
        payload = _build_operation_context_payload(operation)
        if json_mode:
            typer.echo(json.dumps(payload, indent=2, ensure_ascii=False))
            return
        for line in _emit_context_lines(operation):
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

    async def _trace() -> None:
        settings = _load_settings()
        store = build_store(settings)
        brief = await trace_store.load_brief_bundle(operation_id)
        trace_records = await trace_store.load_trace_records(operation_id)
        memos = await trace_store.load_decision_memos(operation_id)
        events = event_sink.read_events(operation_id)
        wakeups = inbox.read_all(operation_id)
        commands = [item.model_dump(mode="json") for item in await command_inbox.list(operation_id)]
        operation = await store.load_operation(operation_id)
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
    agent: str = typer.Option("auto", "--agent", help="auto, codex, or claude."),
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
    store = build_store(settings)
    event_sink = build_event_sink(settings, operation_id)
    projector = _CliEventProjector(json_mode=json_mode)

    operation = await store.load_operation(operation_id)
    outcome = await store.load_outcome(operation_id)
    if operation is None and outcome is None:
        raise typer.BadParameter(f"Operation {operation_id!r} was not found.")

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

        operation = await store.load_operation(operation_id)
        outcome = await store.load_outcome(operation_id)
        snapshot = _build_live_snapshot(operation_id, operation, outcome)
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
    store = build_store(settings)
    trace_store = build_trace_store(settings)
    event_sink = build_event_sink(settings, operation_id)
    command_inbox = build_command_inbox(settings)
    inbox = build_wakeup_inbox(settings)
    supervisor = build_background_run_inspection_store(settings)

    async def _load_payload() -> dict[str, object]:
        operation = await store.load_operation(operation_id)
        outcome = await store.load_outcome(operation_id)
        if operation is None:
            raise typer.BadParameter(f"Operation {operation_id!r} was not found.")
        brief = await trace_store.load_brief_bundle(operation_id)
        commands = await command_inbox.list(operation_id)
        events = event_sink.read_events(operation_id)
        wakeups = inbox.read_all(operation_id)
        background_runs = [
            item.model_dump(mode="json") for item in await supervisor.list_runs(operation_id)
        ]
        runtime_alert = _build_runtime_alert(
            status=operation.status,
            wakeups=wakeups,
            background_runs=background_runs,
        )
        upstream_transcript = _build_dashboard_upstream_transcript(
            operation,
            codex_home=codex_home,
        )
        payload = _build_dashboard_payload(
            operation,
            brief=brief,
            outcome=outcome,
            runtime_alert=runtime_alert,
            commands=commands,
            events=events,
            upstream_transcript=upstream_transcript,
        )
        if brief is not None and brief.operation_brief is not None:
            payload["brief"] = brief.operation_brief.model_dump(mode="json")
        return payload

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
    service = build_service(
        settings,
        event_sink=ProjectingEventSink(
            build_event_sink(settings, operation_id),
            projector.handle_event,
        ),
    )
    outcome = await service.resume(
        operation_id,
        options=RunOptions(
            run_mode=RunMode.RESUMABLE,
            max_cycles=max_cycles,
            background_runtime_mode=BackgroundRuntimeMode.RESUMABLE_WAKEUP,
        ),
    )
    projector.emit_outcome(outcome)


async def _status_async(operation_id: str, json_mode: bool, brief: bool) -> None:
    settings = _load_settings()
    store = build_store(settings)
    trace_store = build_trace_store(settings)
    supervisor = build_background_run_inspection_store(settings)

    operation = await store.load_operation(operation_id)
    outcome = await store.load_outcome(operation_id)
    if operation is None and outcome is None:
        raise typer.BadParameter(f"Operation {operation_id!r} was not found.")
    if operation is None and outcome is not None:
        if json_mode:
            typer.echo(
                json.dumps(
                    {
                        "operation_id": operation_id,
                        "status": outcome.status.value,
                        "summary": outcome.summary,
                    },
                    indent=2,
                    ensure_ascii=False,
                )
            )
            return
        typer.echo(f"{operation_id} {outcome.status.value.upper()} {outcome.summary}")
        return

    assert operation is not None
    runs = await supervisor.list_runs(operation_id)
    operation = _overlay_live_background_progress(operation, runs)
    brief_bundle = await trace_store.load_brief_bundle(operation_id)
    runtime_alert = _build_runtime_alert(
        status=operation.status,
        wakeups=[],
        background_runs=[item.model_dump(mode="json") for item in runs],
    )
    if json_mode:
        payload = {
            "operation_id": operation_id,
            "status": operation.status.value,
            "summary": _build_live_snapshot(operation_id, operation, outcome),
            "action_hint": _status_action_hint(operation),
            "durable_truth": _build_durable_truth_payload(operation),
        }
        typer.echo(json.dumps(payload, indent=2, ensure_ascii=False))
        return
    if brief:
        typer.echo(_render_status_brief(operation))
        return
    typer.echo(_render_inspect_summary(operation, brief_bundle, runtime_alert=runtime_alert))
    action_hint = _status_action_hint(operation)
    if action_hint is not None:
        typer.echo(f"\n→ Action required: {action_hint}")


async def _tick_async(operation_id: str) -> None:
    settings = _load_settings()
    service = build_service(settings)
    outcome = await service.tick(
        operation_id,
        options=RunOptions(
            run_mode=RunMode.RESUMABLE,
            background_runtime_mode=BackgroundRuntimeMode.RESUMABLE_WAKEUP,
        ),
    )
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
    service = build_service(
        settings,
        event_sink=ProjectingEventSink(build_event_sink(settings, "sweep"), projector.handle_event),
    )

    async def _sweep() -> int:
        resumed = 0
        for operation_id in inbox.ready_operation_ids():
            if json_mode:
                projector.emit_operation(operation_id)
            outcome = await service.resume(
                operation_id,
                options=RunOptions(
                    run_mode=RunMode.RESUMABLE,
                    max_cycles=max_cycles_per_operation,
                    background_runtime_mode=BackgroundRuntimeMode.RESUMABLE_WAKEUP,
                ),
            )
            projector.emit_outcome(outcome)
            resumed += 1
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
    service = build_service(
        settings,
        event_sink=ProjectingEventSink(
            build_event_sink(settings, operation_id),
            projector.handle_event,
        ),
    )
    outcome = await service.recover(
        operation_id,
        session_id=session_id,
        options=RunOptions(
            run_mode=RunMode.RESUMABLE,
            max_cycles=max_cycles,
            background_runtime_mode=BackgroundRuntimeMode.RESUMABLE_WAKEUP,
        ),
    )
    projector.emit_outcome(outcome)


async def _cancel_async(operation_id: str, session_id: str | None, run_id: str | None) -> None:
    settings = _load_settings()
    service = build_service(settings)
    outcome = await service.cancel(operation_id, session_id=session_id, run_id=run_id)
    typer.echo(f"{outcome.status.value}: {outcome.summary}")
    typer.echo(f"operation_id={outcome.operation_id}", err=True)


async def _stop_turn_async(operation_id: str, task_id: str | None = None) -> None:
    settings = _load_settings()
    store = build_store(settings)
    operation = await store.load_operation(operation_id)
    if operation is None:
        raise typer.BadParameter(f"Operation {operation_id!r} was not found.")
    if operation.scheduler_state is SchedulerState.DRAINING:
        raise typer.BadParameter("The active attached turn is already stopping.")

    if task_id is not None:
        task = _find_task_by_display_id(operation, task_id)
        if task is None:
            raise typer.BadParameter(
                f"Task {task_id!r} was not found in operation {operation_id!r}."
            )
        if task.status is not TaskStatus.RUNNING:
            raise typer.BadParameter(
                "stop_turn_invalid_state: "
                f"task {task_id!r} is in state {task.status.value!r}, "
                "not 'running'."
            )
        # Find the session bound to this task
        target_session = None
        for record in operation.sessions:
            if task.task_id in record.bound_task_ids and record.status is SessionStatus.RUNNING:
                target_session = record
                break
        if target_session is None:
            raise typer.BadParameter(
                f"Task {task_id!r} is running but has no active session bound to it."
            )
    else:
        target_session = operation.active_session_record
        if target_session is None:
            raise typer.BadParameter("This operation has no active session to stop.")

    await _enqueue_command_async(
        operation_id,
        OperationCommandType.STOP_AGENT_TURN,
        None,
        target_scope=CommandTargetScope.SESSION,
        target_id=target_session.session_id,
    )


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
    if not promote and (
        policy_title is not None
        or policy_text is not None
        or policy_rationale is not None
        or policy_objective_keyword is not None
        or policy_task_keyword is not None
        or policy_agent is not None
        or policy_run_mode is not None
        or policy_involvement is not None
    ):
        raise typer.BadParameter("Policy options require --promote.")
    settings = _load_settings()
    inbox = build_command_inbox(settings)
    store = build_store(settings)
    operation = await store.load_operation(operation_id)
    if operation is None:
        raise typer.BadParameter(f"Operation {operation_id!r} was not found.")
    resolved_attention_id = attention_id
    if resolved_attention_id is None:
        blocking = sorted(
            (
                item
                for item in operation.attention_requests
                if item.status is AttentionStatus.OPEN and item.blocking
            ),
            key=lambda item: item.created_at,
        )
        if not blocking:
            raise typer.BadParameter(
                f"Operation {operation_id!r} has no open blocking attention requests."
            )
        resolved_attention_id = blocking[0].attention_id
    answer_command = _build_operation_command(
        operation_id=operation_id,
        command_type=OperationCommandType.ANSWER_ATTENTION_REQUEST,
        payload=_build_command_payload(OperationCommandType.ANSWER_ATTENTION_REQUEST, text),
        target_scope=CommandTargetScope.ATTENTION_REQUEST,
        target_id=resolved_attention_id,
    )
    await inbox.enqueue(answer_command)
    typer.echo(f"enqueued: {answer_command.command_type.value} [{answer_command.command_id}]")
    if promote:
        policy_payload: dict[str, object] = {
            "category": policy_category,
            **_policy_applicability_payload(
                policy_objective_keyword,
                policy_task_keyword,
                policy_agent,
                policy_run_mode,
                policy_involvement,
            ),
        }
        if policy_title is not None:
            policy_payload["title"] = policy_title
        if policy_text is not None:
            policy_payload["text"] = policy_text
        if policy_rationale is not None:
            policy_payload["rationale"] = policy_rationale
        policy_command = _build_operation_command(
            operation_id=operation_id,
            command_type=OperationCommandType.RECORD_POLICY_DECISION,
            payload=policy_payload,
            target_scope=CommandTargetScope.ATTENTION_REQUEST,
            target_id=resolved_attention_id,
        )
        await inbox.enqueue(policy_command)
        typer.echo(f"enqueued: {policy_command.command_type.value} [{policy_command.command_id}]")
    if (
        operation.status is OperationStatus.NEEDS_HUMAN
        and operation.current_focus is not None
        and operation.current_focus.kind is FocusKind.ATTENTION_REQUEST
        and operation.current_focus.target_id == resolved_attention_id
    ):
        service = build_service(settings)
        outcome = await service.resume(
            operation_id,
            options=RunOptions(run_mode=RunMode.ATTACHED),
        )
        typer.echo(f"{outcome.status.value}: {outcome.summary}")


def _build_operation_command(
    *,
    operation_id: str,
    command_type: OperationCommandType,
    payload: dict[str, object],
    target_scope: CommandTargetScope,
    target_id: str,
) -> OperationCommand:
    return OperationCommand(
        operation_id=operation_id,
        command_type=command_type,
        target_scope=target_scope,
        target_id=target_id,
        payload=payload,
    )


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
    settings = _load_settings()
    inbox = build_command_inbox(settings)
    store = build_store(settings)
    payload = _build_command_payload(
        command_type,
        text,
        success_criteria,
        clear_success_criteria,
        allowed_agents,
        max_iterations,
    )
    command = _build_operation_command(
        operation_id=operation_id,
        command_type=command_type,
        payload=payload,
        target_scope=target_scope,
        target_id=target_id or operation_id,
    )
    await inbox.enqueue(command)
    typer.echo(f"enqueued: {command.command_type.value} [{command.command_id}]")
    operation = await store.load_operation(operation_id)
    if operation is None:
        return
    if auto_resume_when_paused and command_type is OperationCommandType.RESUME_OPERATOR:
        if operation.scheduler_state is not SchedulerState.PAUSED:
            if operation.scheduler_state is SchedulerState.PAUSE_REQUESTED:
                typer.echo("resume queued: waiting for the current attached turn to yield.")
            return
        service = build_service(settings)
        outcome = await service.resume(
            operation_id,
            options=RunOptions(run_mode=RunMode.ATTACHED),
        )
        typer.echo(f"{outcome.status.value}: {outcome.summary}")
        return
    if (
        auto_resume_blocked_attention_id is not None
        and operation.status is OperationStatus.NEEDS_HUMAN
        and operation.current_focus is not None
        and operation.current_focus.kind is FocusKind.ATTENTION_REQUEST
        and operation.current_focus.target_id == auto_resume_blocked_attention_id
    ):
        service = build_service(settings)
        outcome = await service.resume(
            operation_id,
            options=RunOptions(run_mode=RunMode.ATTACHED),
        )
        typer.echo(f"{outcome.status.value}: {outcome.summary}")


async def _enqueue_custom_command_async(
    operation_id: str,
    command_type: OperationCommandType,
    payload: dict[str, object],
    target_scope: CommandTargetScope,
    target_id: str,
) -> None:
    settings = _load_settings()
    inbox = build_command_inbox(settings)
    command = OperationCommand(
        operation_id=operation_id,
        command_type=command_type,
        target_scope=target_scope,
        target_id=target_id,
        payload={key: value for key, value in payload.items() if value is not None},
    )
    await inbox.enqueue(command)
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
    store = build_store(settings)
    trace_store = build_trace_store(settings)
    inbox = build_wakeup_inbox(settings)
    supervisor = build_background_run_inspection_store(settings)
    items: list[AgendaItem] = []
    for summary in await store.list_operations():
        operation = await store.load_operation(summary.operation_id)
        if operation is None:
            continue
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
        brief_bundle = await trace_store.load_brief_bundle(summary.operation_id)
        brief = brief_bundle.operation_brief if brief_bundle is not None else None
        item = build_agenda_item(
            operation,
            summary,
            brief=brief,
            runtime_alert=runtime_alert,
        )
        if agenda_matches_project(item, project):
            items.append(item)
    return build_agenda_snapshot(items, include_recent=include_all)


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
    async def _load_payload() -> dict[str, object]:
        snapshot = await _load_agenda_snapshot(project=project, include_all=include_all)
        return _build_fleet_payload(snapshot, project=project)

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
        policy_store = build_policy_store(settings)
        active_policies = await policy_store.list(
            project_scope=f"profile:{profile.name}",
            status=PolicyStatus.ACTIVE,
        )
        fleet_payload = _build_fleet_payload(
            await _load_agenda_snapshot(project=profile.name, include_all=True),
            project=profile.name,
        )
        return _build_project_dashboard_payload(
            profile=profile,
            resolved=resolved.model_dump(mode="json"),
            profile_path=selected_path if selected_path is not None else profile_dir(settings),
            fleet=fleet_payload,
            active_policies=active_policies,
        )

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
