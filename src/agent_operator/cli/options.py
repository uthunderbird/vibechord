from __future__ import annotations

from pathlib import Path

import typer

from agent_operator.domain import InvolvementLevel, OperationCommandType, RunMode

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

__all__ = [
    "ALLOWED_AGENT_OPTION",
    "ATTACH_AGENT_OPTION",
    "ATTACH_NAME_OPTION",
    "ATTACH_SESSION_OPTION",
    "ATTACH_WORKING_DIR_OPTION",
    "CODEX_HOME_OPTION",
    "COMMAND_ALLOWED_AGENT_OPTION",
    "COMMAND_CLEAR_SUCCESS_CRITERIA_OPTION",
    "COMMAND_MAX_ITERATIONS_OPTION",
    "COMMAND_SUCCESS_CRITERION_OPTION",
    "COMMAND_TYPE_OPTION",
    "HARNESS_OPTION",
    "INVOLVEMENT_LEVEL_OPTION",
    "INVOLVEMENT_OPTION",
    "JSON_OPTION",
    "MAX_ITERATIONS_OPTION",
    "MEMORY_ALL_OPTION",
    "POLICY_AGENT_KEY_OPTION",
    "POLICY_ATTENTION_OPTION",
    "POLICY_CATEGORY_OPTION",
    "POLICY_ID_OPTION",
    "POLICY_INVOLVEMENT_MATCH_OPTION",
    "POLICY_JSON_OPTION",
    "POLICY_OBJECTIVE_KEYWORD_OPTION",
    "POLICY_PROJECT_OPTION",
    "POLICY_REASON_OPTION",
    "POLICY_RULE_OPTION",
    "POLICY_RUN_MODE_OPTION",
    "POLICY_SCOPE_OPTION",
    "POLICY_TASK_KEYWORD_OPTION",
    "POLICY_TEXT_OPTION",
    "POLICY_TITLE_OPTION",
    "PROJECT_AGENT_OPTION",
    "PROJECT_CWD_OPTION",
    "PROJECT_FORCE_OPTION",
    "PROJECT_HARNESS_OPTION",
    "PROJECT_INVOLVEMENT_OPTION",
    "PROJECT_MAX_ITERATIONS_OPTION",
    "PROJECT_OBJECTIVE_OPTION",
    "PROJECT_OPTION",
    "PROJECT_PATH_OPTION",
    "PROJECT_SUCCESS_CRITERION_OPTION",
    "PROMOTE_POLICY_AGENT_OPTION",
    "PROMOTE_POLICY_INVOLVEMENT_OPTION",
    "PROMOTE_POLICY_OBJECTIVE_KEYWORD_OPTION",
    "PROMOTE_POLICY_RUN_MODE_OPTION",
    "PROMOTE_POLICY_TASK_KEYWORD_OPTION",
    "RUN_AGENT_OPTION",
    "RUN_MODE_OPTION",
    "RUN_SUCCESS_CRITERION_OPTION",
    "WATCH_POLL_INTERVAL_OPTION",
]
