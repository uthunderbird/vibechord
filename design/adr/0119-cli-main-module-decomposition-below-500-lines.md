# ADR 0119: CLI Main Module Decomposition Below 500 Lines

## Decision Status

Accepted

## Implementation Status

Partial

Skim-safe current truth on 2026-04-14:

- `implemented`: `src/agent_operator/cli/main.py` is now a 16-line compatibility facade and
  `src/agent_operator/cli/app.py` is a 119-line Typer assembly module
- `implemented`: command registration, helpers, workflows, rendering, and TUI logic now live in
  separate CLI subpackages under `src/agent_operator/cli/`
- `partial`: ADR 0119's material-satisfaction bar is not yet met because multiple CLI source files
  still exceed the 500-line limit
- `partial`: the largest remaining files are
  `src/agent_operator/cli/tui/controller.py` (1347),
  `src/agent_operator/cli/tui/rendering.py` (979),
  `src/agent_operator/cli/tui/models.py` (956),
  `src/agent_operator/cli/workflows/control.py` (868),
  `src/agent_operator/cli/workflows/views.py` (826),
  `src/agent_operator/cli/commands/operation_detail.py` (737),
  `src/agent_operator/cli/rendering/text.py` (630),
  `src/agent_operator/cli/commands/debug.py` (543), and
  `src/agent_operator/cli/workflows/converse.py` (523)

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

- As of 2026-04-14, `wc -l` over `src/agent_operator/cli/**/*.py` shows the CLI is decomposed into
  focused modules, but the 500-line budget is still violated by nine files:
  `tui/controller.py` (1347),
  `tui/rendering.py` (979),
  `tui/models.py` (956),
  `workflows/control.py` (868),
  `workflows/views.py` (826),
  `commands/operation_detail.py` (737),
  `rendering/text.py` (630),
  `commands/debug.py` (543), and
  `workflows/converse.py` (523).
- `src/agent_operator/cli/main.py` now re-exports through `app.py` and no longer centralizes the
  former kitchen-sink responsibilities.
- `tests/test_cli.py` still imports `agent_operator.cli.main:app` and exercises the decomposed CLI
  surface, but ADR 0119 cannot be reported as `Verified` unless `uv run pytest` is green.
