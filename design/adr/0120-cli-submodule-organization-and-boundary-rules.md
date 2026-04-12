# ADR 0120: CLI Submodule Organization and Boundary Rules

- Date: 2026-04-09

## Status

Accepted

## Context

ADR 0119 requires decomposing the CLI so that no CLI source file grows beyond a manageable size.
That decision alone is not enough to prevent structural drift from reappearing later.

Before this refactor, the CLI accumulated several unrelated responsibilities in one place:

- Typer app assembly
- command registration
- shared option declarations
- service/query builder helpers
- resolution helpers
- rendering glue
- transcript/log parsing
- async workflows
- interactive TUI controller and event loop

Without an explicit submodule organization rule, future work can slowly collapse these concerns back
into a few oversized files.

## Decision

The CLI package is organized into stable submodule families with explicit boundaries.

### 1. Entry and assembly

- `cli/main.py` is a thin compatibility facade.
- `cli/app.py` owns Typer app creation, subgroup creation, help behavior, and command-module loading.
- Public script entrypoints continue to target `agent_operator.cli.main:app`.

### 2. Commands

Typer-facing command functions live in `cli/commands_*.py` modules.

Rules:

- command modules collect CLI arguments and call shared workflows/helpers;
- command modules do not own heavy business logic;
- command modules do not import `cli.main`;
- subgroup surfaces are split by user-facing responsibility rather than by internal implementation detail.

Current families:

- `commands_run.py`
- `commands_fleet.py`
- `commands_operation_control.py`
- `commands_operation_detail.py`
- `commands_project.py`
- `commands_policy.py`
- `commands_debug.py`
- `commands_smoke.py`

### 3. Helpers

Non-command shared logic lives in narrowly-scoped `cli/helpers_*.py` modules.

Rules:

- helpers are not allowed to register Typer commands;
- helpers should expose deterministic, reusable functions;
- helper modules should be responsibility-shaped, not “misc” buckets.

Current families:

- `helpers_services.py`
- `helpers_resolution.py`
- `helpers_rendering.py`
- `helpers_logs.py`
- `helpers_policy.py`
- `options.py`

### 4. Workflows

Async orchestration paths that sit between CLI commands and application/runtime services live in
`cli/workflows*.py`.

Rules:

- workflows may coordinate multiple helpers/services;
- workflows do not define Typer commands;
- workflows are split by responsibility, for example control/live vs fleet/view surfaces;
- `cli/workflows.py` may exist as a facade/re-export module.

### 5. Rendering

Rich and text rendering code is split from CLI command registration and split further by surface
when needed.

Rules:

- rendering modules remain view-only;
- formatting glue that depends on CLI projection policy belongs in helper/render modules, not in
  command modules.

### 6. TUI

Interactive TUI code is split into dedicated TUI submodules.

Rules:

- state/payload normalization, controller logic, rendering, and terminal I/O must not accumulate in
  one file again;
- `cli/tui.py` may remain a thin facade exporting the public TUI entry functions.

## Boundary Rules

The following imports are allowed:

- `commands_* -> helpers_*`
- `commands_* -> workflows*`
- `app -> commands_*`
- `workflows* -> helpers_*`
- `workflows* -> rendering*`
- `tui facade -> tui_* submodules`

The following imports are not allowed:

- `helpers_* -> commands_*`
- `helpers_* -> app`
- `commands_* -> main`
- `tui_* -> main`
- new “misc” CLI modules that mix commands, helpers, and workflows

## Consequences

Positive:

- the CLI remains navigable and reviewable;
- future feature work has clear placement rules;
- compatibility entrypoints can remain stable while internals continue to evolve.

Tradeoffs:

- more files and more explicit imports;
- some compatibility facades remain intentionally thin rather than disappearing immediately.

## Verification

Changes touching the CLI should preserve these conditions:

- `cli/main.py` remains a thin facade;
- no CLI source file exceeds the repository’s current line-budget rule;
- command registration still flows through `app.py`;
- focused CLI/TUI tests continue to pass.

## Related

- [ADR 0119](./0119-cli-main-module-decomposition-below-500-lines.md)

## Implementation Status

Implemented

Skim-safe current truth on 2026-04-12:

- `implemented`: CLI organized as `cli/app.py` (registration), `cli/commands/` (families),
  `cli/rendering/` (text rendering), `cli/tui/` (TUI workbench), `cli/workflows/` (control),
  `cli/helpers/` (utilities)
- `implemented`: command registration flows through `app.py`; no rogue top-level command modules
- `implemented`: all legacy flat family modules retired per ADR 0123
- `verified`: submodule boundary rules tested in `tests/test_application_structure.py`
