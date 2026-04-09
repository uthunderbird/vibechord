# CLI Main Decomposition Implementation Note

## Status

Internal implementation note.

This note translates:

- [0119-cli-main-module-decomposition-below-500-lines.md](/Users/thunderbird/Projects/operator/design/adr/0119-cli-main-module-decomposition-below-500-lines.md)

into a narrower implementation-oriented plan for breaking up:

- [main.py](/Users/thunderbird/Projects/operator/src/agent_operator/cli/main.py)

## Goal

Decompose the current 3981-line CLI entry module into responsibility-based modules while keeping:

- public command behavior materially stable
- Typer as the CLI framework
- CLI as a thin adapter over shared services

## Current responsibility clusters inside `main.py`

The file currently mixes at least these clusters:

1. app assembly and subgroup creation
2. service/query builder helpers
3. help/printing helpers
4. project/profile helpers
5. policy helpers
6. live/render formatting helpers
7. operation/task/session resolution helpers
8. transcript/log parsing helpers
9. command registration for:
   - public commands
   - project subgroup
   - policy subgroup
   - debug/hidden commands
10. shared async workflows
11. TUI bootstrap glue

## Proposed target file map

This is the preferred first-pass file map.

### Assembly layer

- [app.py](/Users/thunderbird/Projects/operator/src/agent_operator/cli/app.py)
  - create `app`, `debug_app`, `project_app`, `policy_app`
  - register command modules
  - keep this file small

- [main.py](/Users/thunderbird/Projects/operator/src/agent_operator/cli/main.py)
  - very thin entry module only
  - import `app`
  - preserve current launch/import path compatibility

### Public command modules

- [commands_run.py](/Users/thunderbird/Projects/operator/src/agent_operator/cli/commands_run.py)
  - `run`
  - `init`
  - maybe `history`

- [commands_operation_control.py](/Users/thunderbird/Projects/operator/src/agent_operator/cli/commands_operation_control.py)
  - `status`
  - `answer`
  - `pause`
  - `unpause`
  - `interrupt`
  - `cancel`
  - `message`
  - `involvement`

- [commands_operation_detail.py](/Users/thunderbird/Projects/operator/src/agent_operator/cli/commands_operation_detail.py)
  - `tasks`
  - `memory`
  - `artifacts`
  - `attention`
  - `report`
  - `dashboard`
  - future `session`

- [commands_fleet.py](/Users/thunderbird/Projects/operator/src/agent_operator/cli/commands_fleet.py)
  - `fleet`
  - zero-arg fleet helpers
  - project/fleet dashboard entrypoints if still tightly related

### Subgroup modules

- [commands_project.py](/Users/thunderbird/Projects/operator/src/agent_operator/cli/commands_project.py)
  - `project list`
  - `project create`
  - `project inspect`
  - `project resolve`
  - `project dashboard`

- [commands_policy.py](/Users/thunderbird/Projects/operator/src/agent_operator/cli/commands_policy.py)
  - `policy projects`
  - `policy list`
  - `policy inspect`
  - `policy explain`
  - `policy record`
  - `policy revoke`

### Debug/forensic module

- [commands_debug.py](/Users/thunderbird/Projects/operator/src/agent_operator/cli/commands_debug.py)
  - `debug daemon`
  - `debug tick`
  - `debug recover`
  - `debug resume`
  - `debug wakeups`
  - `debug sessions`
  - `debug command`
  - `debug context`
  - `debug trace`
  - `debug inspect`
  - hidden aliases that should remain hidden

### Shared helper modules

- [helpers_services.py](/Users/thunderbird/Projects/operator/src/agent_operator/cli/helpers_services.py)
  - delivery/query service builders

- [helpers_resolution.py](/Users/thunderbird/Projects/operator/src/agent_operator/cli/helpers_resolution.py)
  - operation resolution
  - task resolution
  - history entry resolution
  - project profile selection helpers

- [helpers_policy.py](/Users/thunderbird/Projects/operator/src/agent_operator/cli/helpers_policy.py)
  - policy payload / applicability helpers

- [helpers_rendering.py](/Users/thunderbird/Projects/operator/src/agent_operator/cli/helpers_rendering.py)
  - status/fleet/dashboard/inspect text rendering helpers not already owned by:
    - [rendering.py](/Users/thunderbird/Projects/operator/src/agent_operator/cli/rendering.py)
    - [rendering_text.py](/Users/thunderbird/Projects/operator/src/agent_operator/cli/rendering_text.py)

- [helpers_logs.py](/Users/thunderbird/Projects/operator/src/agent_operator/cli/helpers_logs.py)
  - log target selection
  - codex/claude/opencode parsing helpers

### Async workflow module

- [workflows.py](/Users/thunderbird/Projects/operator/src/agent_operator/cli/workflows.py)
  - `_run_async`
  - `_watch_async`
  - `_dashboard_async`
  - `_status_async`
  - `_cancel_async`
  - `_stop_turn_async`
  - `_answer_async`
  - `_enqueue_command_async`
  - `_enqueue_custom_command_async`
  - `_fleet_async`
  - `_fleet_tui_async`
  - `_project_dashboard_async`
  - and similar shared async execution paths

## Preferred extraction order

### Wave 1 — low-risk extractions

Move the most self-contained code first:

1. `helpers_logs.py`
2. `helpers_policy.py`
3. `commands_project.py`
4. `commands_policy.py`
5. `commands_debug.py`

Reason:

- these areas have strong local cohesion
- they reduce `main.py` size quickly
- they are less entangled with zero-arg app startup flow

### Wave 2 — shared support extraction

Then extract:

1. `helpers_resolution.py`
2. `helpers_services.py`
3. `helpers_rendering.py`

Reason:

- public command modules become easier to split once shared helpers are no longer buried in
  `main.py`

### Wave 3 — async workflow extraction

Move the async executor bodies into:

- `workflows.py`

Reason:

- command modules should not carry large async implementation bodies inline
- this also reduces duplication pressure as `session` and fleet work advance

### Wave 4 — public command module split

Finally split the remaining public command registration into:

1. `commands_run.py`
2. `commands_operation_control.py`
3. `commands_operation_detail.py`
4. `commands_fleet.py`
5. `app.py` + thin `main.py`

## Line-budget rule

The target is not merely “smaller than before.”

Each resulting CLI source file should stay below 500 lines of code.

If a proposed destination module grows above that threshold during extraction:

- split it again by responsibility
- do not accept a large “temporary” module as the final state

## Import strategy

Prefer:

- command modules registering onto an imported `app` / subgroup object
- helper modules with no Typer registration
- workflows with no Typer decorators

Avoid:

- circular imports between command modules
- command modules importing each other for helper behavior
- pushing application-layer logic into CLI helpers

## Suggested first concrete cuts

These are the first likely moves with minimal semantic risk:

1. extract log helpers around:
   - `_resolve_claude_log_path_for_session`
   - `_resolve_jsonl_log_path_for_session`
   - `_parse_opencode_log_line`
   - `_resolve_log_target`
   - `_build_dashboard_upstream_transcript`

2. extract project commands and helpers

3. extract policy commands and helpers

4. extract debug/hidden commands:
   - `resume`
   - `tick`
   - `daemon`
   - `recover`
   - `wakeups`
   - `sessions`
   - `command`
   - `inspect`
   - `context`
   - `trace`

These four cuts should already remove a large portion of `main.py` with low public-risk churn.

## Test expectations

After each extraction wave:

1. imports still resolve from the existing CLI entry path
2. Typer command registration remains complete
3. hidden commands remain hidden
4. JSON/human output behavior remains materially unchanged

Recommended verification focus:

- [test_cli.py](/Users/thunderbird/Projects/operator/tests/test_cli.py)
- [test_tui.py](/Users/thunderbird/Projects/operator/tests/test_tui.py) where fleet/TUI bootstrap paths are touched

## Deliberate deferrals

This note does not require:

- renaming the final modules exactly as proposed
- reworking the whole CLI help formatter first
- touching end-user docs during decomposition
- mixing decomposition with new behavior unless another ADR already requires that behavior
