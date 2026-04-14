# ADR 0120: CLI Submodule Organization and Boundary Rules

- Date: 2026-04-09

## Decision Status

Accepted

## Implementation Status

Partial

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

Typer-facing command functions live in `cli/commands/` modules.

Rules:

- command modules collect CLI arguments and call shared workflows/helpers;
- command modules do not own heavy business logic;
- command modules do not import `cli.main`;
- subgroup surfaces are split by user-facing responsibility rather than by internal implementation detail.

Current families include:

- `commands/run.py`
- `commands/fleet.py`
- `commands/operation_control.py`
- `commands/operation_detail.py`
- `commands/project.py`
- `commands/policy.py`
- `commands/debug.py`
- `commands/smoke.py`

### 3. Helpers

Non-command shared logic lives in narrowly-scoped `cli/helpers/` modules plus `cli/options.py`.

Rules:

- helpers are not allowed to register Typer commands;
- helpers should expose deterministic, reusable functions;
- helper modules should be responsibility-shaped, not “misc” buckets.

Current families include:

- `helpers/services.py`
- `helpers/resolution.py`
- `helpers/rendering.py`
- `helpers/logs.py`
- `helpers/policy.py`
- `options.py`

### 4. Workflows

Async orchestration paths that sit between CLI commands and application/runtime services live in
`cli/workflows/`.

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

Interactive TUI code is split into dedicated TUI submodules under `cli/tui/`.

Rules:

- state/payload normalization, controller logic, rendering, and terminal I/O must not accumulate in
  one file again;
- `cli/tui.py` may remain a thin facade exporting the public TUI entry functions.

## Boundary Rules

The following imports are allowed:

- `commands/* -> helpers/*`
- `commands/* -> workflows/*`
- `app -> commands_*`
- `workflows/* -> helpers/*`
- `workflows/* -> rendering/*`
- `tui facade -> tui/* submodules`

The following imports are not allowed:

- `helpers/* -> commands/*`
- `helpers/* -> app`
- `commands/* -> main`
- `tui/* -> main`
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
- command registration still flows through `app.py`;
- CLI families stay separated into explicit `commands/`, `helpers/`, `rendering/`, `tui/`, and
  `workflows/` packages;
- focused CLI/TUI tests continue to pass.

Current repository truth on 2026-04-14 does not satisfy the historical “no CLI source file exceeds
the current line-budget rule” condition from ADR 0119. That regression keeps this ADR at
`Partial` implementation status even though the subpackage boundary shape itself is in place.

## Related

- [ADR 0119](./0119-cli-main-module-decomposition-below-500-lines.md)

Skim-safe current truth on 2026-04-14:

- `implemented`: CLI is organized as `cli/app.py` (registration), `cli/commands/`,
  `cli/rendering/`, `cli/tui/`, `cli/workflows/`, `cli/helpers/`, and `cli/options.py`
- `implemented`: command registration flows through `app.py`; source-level flat family modules such
  as `commands_*.py`, `helpers_*.py`, `rendering*.py`, `tui*.py`, and `workflows*.py` are retired
- `implemented`: `cli/main.py` remains a thin compatibility facade and `cli.app` imports the
  command package modules that register the CLI surface
- `implemented`: direct disallowed upward imports covered by ADR 0120 (`helpers/* -> commands/*`,
  `helpers/* -> app`, `commands/* -> main`, `tui/* -> main`) are structurally checked in
  `tests/test_application_structure.py`, but not repository-verified because full `uv run pytest`
  is currently red
- `partial`: the package boundary shape is in place, but CLI file-size budget compliance has
  regressed; examples above 500 lines include `cli/tui/controller.py` (1347),
  `cli/tui/models.py` (956), `cli/tui/rendering.py` (979), `cli/workflows/control.py` (868),
  `cli/workflows/views.py` (826), `cli/commands/operation_detail.py` (737), and
  `cli/rendering/text.py` (630)
