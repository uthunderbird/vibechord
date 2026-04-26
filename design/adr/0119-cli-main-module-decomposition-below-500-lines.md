# ADR 0119: CLI Main Module Decomposition Below 500 Lines

## Decision Status

Accepted

## Implementation Status

Partial

Skim-safe current truth on 2026-04-27:

- `implemented`: `src/agent_operator/cli/main.py` is now a 16-line compatibility facade and
  `src/agent_operator/cli/app.py` is a 119-line Typer assembly module
- `implemented`: command registration, helpers, workflows, rendering, and TUI logic now live in
  separate CLI subpackages under `src/agent_operator/cli/`
- `implemented`: TUI rendering now keeps `agent_operator.cli.tui.rendering` as a 61-line public
  compatibility facade, with list/timeline/task-board rendering split into
  `src/agent_operator/cli/tui/rendering_lists.py` (176 lines), chrome/overlay rendering in
  `src/agent_operator/cli/tui/rendering_chrome.py` (413 lines), and operation/session detail
  rendering in `src/agent_operator/cli/tui/rendering_detail.py` (393 lines)
- `implemented`: TUI models now keep `agent_operator.cli.tui.models` as a 172-line public
  compatibility facade, with extracted helpers in
  `src/agent_operator/cli/tui/model_types.py` (180 lines),
  `src/agent_operator/cli/tui/model_attention.py` (164 lines),
  `src/agent_operator/cli/tui/model_fleet.py` (240 lines),
  `src/agent_operator/cli/tui/model_sessions.py` (413 lines), and
  `src/agent_operator/cli/tui/model_text.py` (98 lines)
- `partial`: ADR 0119's material-satisfaction bar is not yet met because multiple CLI source files
  still exceed the 500-line limit
- `partial`: the largest remaining files are
  `src/agent_operator/cli/tui/controller.py` (1347),
  `src/agent_operator/cli/workflows/views.py` (859),
  `src/agent_operator/cli/workflows/converse.py` (803),
  `src/agent_operator/cli/rendering/text.py` (690),
  `src/agent_operator/cli/workflows/control_runtime.py` (557)

Verification evidence for this slice:

- `verified`: `tests/test_adr_0119_cli_line_budget.py::test_adr_0119_split_cli_modules_stay_under_500_lines`
  now fails if `src/agent_operator/cli/tui/rendering.py`,
  `src/agent_operator/cli/tui/rendering_chrome.py`,
  `src/agent_operator/cli/tui/rendering_detail.py`, or
  `src/agent_operator/cli/tui/rendering_lists.py` regresses above the ADR ceiling
- `verified`: `tests/test_adr_0119_cli_line_budget.py::test_adr_0119_split_cli_modules_stay_under_500_lines`
  now also fails if `src/agent_operator/cli/tui/models.py`,
  `src/agent_operator/cli/tui/model_types.py`,
  `src/agent_operator/cli/tui/model_attention.py`,
  `src/agent_operator/cli/tui/model_display.py`,
  `src/agent_operator/cli/tui/model_fleet.py`,
  `src/agent_operator/cli/tui/model_sessions.py`,
  `src/agent_operator/cli/tui/model_text.py`, or
  `src/agent_operator/cli/tui/model_views.py` regresses above the ADR ceiling
- `verified`: `tests/test_adr_0119_control_line_budget.py::test_control_workflow_modules_stay_under_500_lines`
  now fails if `src/agent_operator/cli/workflows/control.py` or
  `src/agent_operator/cli/workflows/control_converse.py` regresses above the ADR ceiling
- `verified`: the TUI facade import surface now has a direct regression assertion in
  `tests/test_tui.py::test_tui_package_exports_rendering_module` covering
  `render_help_overlay`, `render_session_timeline`, and
  `render_forensic_transcript_panel`
- `verified`: the TUI models facade and grouped-payload bucket rewrite now have direct regression
  assertions in
  `tests/test_tui.py::test_tui_models_facade_exports_split_helpers`,
  `tests/test_tui.py::test_tui_models_facade_selected_task_uses_facade_filter_for_monkeypatching`
  and
  `tests/test_tui.py::test_payload_items_rewrites_bucket_for_legacy_grouped_payloads`
- `verified`: focused TUI/models regressions passed with
  `UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/test_adr_0119_cli_line_budget.py tests/test_tui.py tests/test_tui_language_slice.py tests/test_tui_session_summary_jump_to.py`
  (`84 passed`)
- `verified`: full repository verification passed with
  `UV_CACHE_DIR=/tmp/uv-cache uv run pytest`
  (`1030 passed, 11 skipped`)

This ADR is accepted but only partially implemented.

## Context

The current CLI entry module is oversized:

- [main.py](/Users/thunderbird/Projects/operator/src/agent_operator/cli/main.py) is 3981 lines

It currently mixes multiple kinds of responsibility in one file:

- app and subgroup wiring
- command registration
- delivery/query-service builders
- operation and task resolution helpers
- formatting and rendering helpers
- transcript parsing helpers
- async command implementations
- fleet and dashboard polling loops
- TUI bootstrap glue

This creates several concrete problems:

1. the CLI surface is hard to navigate and reason about
2. unrelated edits collide in one file
3. command-level ownership is unclear
4. helper functions for specific subdomains are not discoverable
5. future supervisory-surface work is forced to land in an already overloaded module

This is no longer just a style issue. The repository is actively growing:

- fleet projection work
- operation/session parity work
- public `session` CLI surface

Without decomposition, `main.py` becomes the accidental integration boundary for everything.

## Decision

The repository should decompose [main.py](/Users/thunderbird/Projects/operator/src/agent_operator/cli/main.py) into multiple CLI modules, with a hard working limit:

- **no resulting CLI source file should exceed 500 lines of code**

The decomposition should preserve:

- the existing Typer app model
- current command names and public semantics unless separately changed by other ADRs
- thin adapter behavior over shared application services

The new structure should separate at least these concerns:

1. app assembly and top-level Typer wiring
2. everyday operation commands
3. fleet/project dashboard surfaces
4. policy subgroup commands
5. debug/forensic commands
6. shared resolution / formatting / transcript helper utilities
7. async executor workflows used by multiple commands

## Design constraints

### 1. Do not replace one giant file with a few still-huge files

This ADR explicitly rejects a decomposition that merely moves from:

- one 3981-line module

to:

- three 1200-line modules

The `<500` line limit is part of the architectural decision, not a loose aspiration.

### 2. Keep command semantics stable

This ADR is about module structure, not public CLI redesign.

It should not silently change:

- command names
- help visibility
- addressing rules
- JSON contracts

unless another ADR already governs that change.

### 3. Keep CLI modules thin

The split should not produce fat command modules that re-implement application logic.

CLI modules remain:

- registration layer
- argument parsing layer
- renderer / output layer
- async workflow invocation layer

Core domain and application logic stays outside CLI.

## Intended module shape

The exact filenames may vary, but the decomposition should converge on a structure close to:

- `cli/app.py`
  - top-level Typer app creation
  - subgroup creation
  - help wiring
- `cli/commands_run.py`
  - `run`
  - `init`
  - maybe `history`
- `cli/commands_operation.py`
  - `status`
  - `answer`
  - `pause`
  - `unpause`
  - `interrupt`
  - `cancel`
  - `message`
  - `involvement`
- `cli/commands_fleet.py`
  - `fleet`
  - `agenda` if retained internally
  - fleet/project dashboard entrypoints
- `cli/commands_operation_detail.py`
  - `tasks`
  - `memory`
  - `artifacts`
  - `report`
  - `attention`
  - `dashboard`
  - future `session`
- `cli/commands_debug.py`
  - hidden and debug surfaces
- `cli/commands_project.py`
  - `project ...`
- `cli/commands_policy.py`
  - `policy ...`
- `cli/helpers_resolution.py`
  - operation/task/profile resolution helpers
- `cli/helpers_render.py`
  - human-readable formatting helpers not already covered by existing rendering modules
- `cli/helpers_logs.py`
  - transcript/log parsing and selection helpers
- `cli/workflows.py`
  - shared async executor functions used by multiple command modules

This shape is illustrative, not mandatory, but any accepted decomposition should achieve the same
responsibility split.

## Consequences

### 1. `main.py` stops being the accidental kitchen sink

The top-level module should shrink to a narrow assembly role or disappear entirely in favor of a
small app-entry module.

### 2. Future supervisory-surface work becomes localizable

The fleet, operation, and session CLI work can land in focused command and helper modules instead of
expanding one giant file.

### 3. Tests and imports may need light reorganization

Some tests and import paths may need updates, but this ADR does not require broad behavior changes.

## Explicit non-goals

This ADR does not require:

- changing public CLI taxonomy
- changing Typer as the CLI framework
- merging CLI rendering into the TUI layer
- moving domain/application code into CLI modules
- changing docs before implementation lands

## First implementation tranche

### P0

1. Create a small CLI app assembly module.
2. Move debug/forensic commands out first.
3. Move policy and project subgroup commands into dedicated modules.
4. Move transcript/log helpers into a dedicated helper module.
5. Move resolution helpers into a dedicated helper module.
6. Move async shared workflows into a dedicated workflows module.
7. Split remaining public commands into focused modules until every file is below 500 lines.

### P1

1. Normalize naming across CLI modules.
2. Reduce cross-module import tangling where the first split reveals cycles.
3. Add lightweight package-level organization notes if needed.

## Sequencing rule

Prefer extracting the most self-contained slices first:

1. debug/forensic commands
2. subgroup commands (`project`, `policy`)
3. log/transcript helpers
4. resolution/formatting helpers
5. shared async workflows
6. remaining public command groups
7. final app assembly cleanup

This minimizes breakage while reducing line count quickly.

## Verification criteria

This ADR is materially satisfied only when all of the following are true:

1. No CLI source file in [src/agent_operator/cli](/Users/thunderbird/Projects/operator/src/agent_operator/cli) exceeds 500 lines of code.
2. Public CLI behavior remains materially unchanged unless another ADR governs the change.
3. App assembly, command registration, helpers, and async workflows are no longer all mixed in one
   module.
4. The resulting module boundaries are responsibility-based rather than arbitrary line-count chops.

### Evidence

- As of 2026-04-27, `wc -l` over `src/agent_operator/cli/**/*.py` shows the CLI is decomposed into
  focused modules, but the 500-line budget is still violated by five files:
  `tui/controller.py` (1347),
  `workflows/views.py` (859),
  `workflows/converse.py` (803),
  `rendering/text.py` (690),
  `workflows/control_runtime.py` (557).
- As of 2026-04-27, `wc -l` for the extracted TUI models slice is:
  `tui/models.py` (172),
  `tui/model_types.py` (180),
  `tui/model_attention.py` (164),
  `tui/model_fleet.py` (240),
  `tui/model_sessions.py` (413), and
  `tui/model_text.py` (98).
- `src/agent_operator/cli/main.py` now re-exports through `app.py` and no longer centralizes the
  former kitchen-sink responsibilities.
- `src/agent_operator/cli/tui/rendering.py` now retains the public TUI rendering seam at 61 lines
  while `src/agent_operator/cli/tui/rendering_chrome.py`,
  `src/agent_operator/cli/tui/rendering_detail.py`, and
  `src/agent_operator/cli/tui/rendering_lists.py` own the extracted implementation.
- `src/agent_operator/cli/tui/models.py` now retains the public TUI models seam at 172 lines
  while `src/agent_operator/cli/tui/model_types.py`,
  `src/agent_operator/cli/tui/model_attention.py`,
  `src/agent_operator/cli/tui/model_fleet.py`,
  `src/agent_operator/cli/tui/model_sessions.py`, and
  `src/agent_operator/cli/tui/model_text.py` own the extracted implementation.
- `src/agent_operator/cli/workflows/control.py` now retains the public workflow seam at 461 lines
  while `src/agent_operator/cli/workflows/control_converse.py` owns the extracted
  converse-command dispatch logic.
- `tests/test_cli.py` still imports `agent_operator.cli.main:app` and exercises the decomposed CLI
  surface, but ADR 0119 cannot be reported as `Verified` because multiple CLI source files still
  exceed the 500-line ceiling even though the post-extraction focused tests and
  `UV_CACHE_DIR=/tmp/uv-cache uv run pytest` are green for this tranche.
