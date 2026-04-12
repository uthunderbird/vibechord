# ADR 0123: CLI Package Submodules and Subpackage Shape

- Date: 2026-04-10

## Decision Status

Accepted

## Implementation Status

Implemented

Skim-safe current truth on 2026-04-12:

- `implemented`: `cli/commands/` now exists as a real package and owns the command-family
  implementation
- `implemented`: `cli/rendering/` now exists as a real package and owns the rendering-family
  implementation
- `implemented`: `cli/tui/` now exists as a real package with `controller.py`, `io.py`,
  `models.py`, `rendering.py`, and `__init__.py`
- `implemented`: `cli/workflows/` now exists as a real package with `control.py`, `views.py`,
  `workspace.py`, and `__init__.py`
- `implemented`: `cli/helpers/` now exists as a real package and owns the helper-family
  implementation
- `implemented`: top-level flat family modules (`commands_*.py`, `rendering*.py`, `tui_*.py`,
  `helpers_*.py`, `workflows.py`) have been retired

This ADR is implemented.

## Context

[ADR 0119](/Users/thunderbird/Projects/operator/design/adr/0119-cli-main-module-decomposition-below-500-lines.md)
and
[ADR 0120](/Users/thunderbird/Projects/operator/design/adr/0120-cli-submodule-organization-and-boundary-rules.md)
already pushed the CLI away from one oversized `main.py` into responsibility-shaped files.

That solved the immediate line-budget and locality problem, but the package still remains mostly
flat:

- `commands_*.py`
- `helpers_*.py`
- `rendering_*.py`
- `tui_*.py`
- `workflows*.py`

all still live side by side in `src/agent_operator/cli/`.

This flat shape has two remaining structural problems:

1. the family boundaries are visible in naming, but not yet in package structure
2. as the CLI keeps growing, the flat namespace will accumulate more sibling files with only
   filename prefixes distinguishing their role

The repository now needs a second structural step:

- move from file-prefix grouping
- to package/submodule grouping

without reopening the already-settled CLI taxonomy or forcing premature deep nesting.

## Decision

The CLI should move from a flat file-prefix layout to package-level submodules.

The target package shape is:

- `cli/main.py`
- `cli/app.py`
- `cli/options.py`
- `cli/commands/`
- `cli/rendering/`
- `cli/tui/`
- `cli/workflows/`

with `cli/helpers/` treated as a later or lower-confidence package move rather than a mandatory
first-wave part of the target.

The first decomposition goal is not maximal nesting.

It is:

- one package per real responsibility family
- minimal top-level file clutter
- stable import boundaries
- room to grow without another naming-prefix explosion
- staged by cohesion rather than moved all at once for symmetry

## Target package shape

### 1. Top-level files that remain top-level

These files remain directly under `cli/`:

- `main.py`
  - compatibility and public entrypoint facade
- `app.py`
  - Typer app assembly and command package loading
- `options.py`
  - shared option/argument declarations
- `__init__.py`
  - stable CLI export facade

These are package entry surfaces, not family members.

### 2. Commands package

Command modules move under:

- `cli/commands/`

Initial target contents:

- `run.py`
- `fleet.py`
- `operation_control.py`
- `operation_detail.py`
- `project.py`
- `policy.py`
- `debug.py`
- `smoke.py`

### 3. Helpers package

Helper modules move under:

- `cli/helpers/`

Initial target contents:

- `services.py`
- `resolution.py`
- `rendering.py`
- `logs.py`
- `policy.py`

This family is weaker than `commands`, `rendering`, `tui`, and `workflows`.

It should therefore be treated as:

- deferred by default
- or introduced only if the migration still benefits after the stronger families move first

The repository should not package-ize `helpers/` in the first wave merely for visual symmetry.

### 4. Rendering package

Rendering modules move under:

- `cli/rendering/`

Initial target contents:

- `text.py`
- `fleet.py`
- `operation.py`
- `project.py`
- `__init__.py` as optional facade if it buys import clarity

### 5. TUI package

TUI modules move under:

- `cli/tui/`

Initial target contents:

- `controller.py`
- `io.py`
- `models.py`
- `rendering.py`
- `__init__.py`

`cli/tui.py` may remain temporarily as a compatibility facade, but the durable target is the TUI
family living inside `cli/tui/`.

This should be read as the package shape for the current CLI-local migration wave, not as the final
delivery-layer package boundary.

See
[RFC 0011](../rfc/0011-delivery-package-boundary-for-cli-and-tui.md)
for the longer-term target in which CLI and TUI become sibling delivery adapters under a common
delivery family.

### 6. Workflows package

Workflow modules move under:

- `cli/workflows/`

Initial target contents:

- `control.py`
- `views.py`
- `__init__.py`

`cli/workflows.py` may remain temporarily as a compatibility facade, but the durable target is the
workflow family living inside `cli/workflows/`.

## Migration waves

### Wave 1 — strong family packages

The first package-level migration wave should move only the strongest families:

- `cli/commands/`
- `cli/tui/`
- `cli/workflows/`
- `cli/rendering/`

These families already have strong internal cohesion and clear user or implementation meaning.

### Wave 2 — evaluate `helpers/`

Only after wave 1 lands should the repository decide whether `cli/helpers/` should become a real
package.

That decision should be based on whether `helpers_*` still reads as a coherent family rather than a
residual bucket of miscellaneous support code.

## Decision on deeper nesting

### Commands: do not create `commands/operation/` yet

The repository should **not** introduce `cli/commands/operation/` in the first package-level
submodule wave.

Instead, keep:

- `cli/commands/operation_control.py`
- `cli/commands/operation_detail.py`

flat inside `cli/commands/`.

#### Why

At the current scale, the operation command family is real, but not yet large enough to justify a
second layer of nesting.

Introducing:

- `commands/operation/control.py`
- `commands/operation/detail.py`

now would add path depth and import churn without a strong semantic gain.

The repository should prefer:

- one level of packaging first
- deeper subpackages only when a family becomes internally crowded

### Threshold for later `commands/operation/`

A later move to `cli/commands/operation/` becomes reasonable only if one of these becomes true:

1. the operation command family grows beyond two or three files
2. operation commands need shared local helpers that should not live in generic `helpers/`
3. task/session-specific command surfaces create a real internal family of their own

Until then, keep the command package shallow.

## `__init__.py` policy

Subpackages should have `__init__.py`.

But they should stay minimal by default.

Rules:

- do not create barrel-export modules by default
- only define `__all__` when it buys a clear import surface or compatibility bridge
- prefer explicit imports in `app.py` and other package users over magical star-export patterns

That means:

- `commands/__init__.py` may remain tiny or empty
- `helpers/__init__.py` may remain tiny or empty if that package is introduced later
- `rendering/__init__.py`, `tui/__init__.py`, and `workflows/__init__.py` may expose narrow public
  facades when compatibility needs them, but should not re-export their whole directory

## Boundary rules

The package move does not change the existing authority boundaries from `ADR 0120`.

It only changes structural packaging.

Still required:

- command modules stay thin
- helpers do not register Typer commands
- rendering remains view-only
- TUI code stays within the TUI family
- workflows stay between commands and application/runtime services
- command or helper modules must not import `cli.main`

## Migration strategy

The package move should happen with compatibility facades where needed.

Preferred sequence:

1. create package directories with `__init__.py`
2. move strong-family implementations under those packages first
3. keep old top-level modules as thin import/re-export facades when tests or imports still rely on
   them
4. migrate internal imports
5. evaluate whether `helpers/` should move as a second wave
6. remove obsolete facades in a later cleanup wave

This avoids needless breakage while still making the structural direction explicit.

## Consequences

Positive:

- `cli/` becomes navigable by package family instead of filename prefix scanning
- future CLI growth has a clear structural landing zone
- deeper family-specific decomposition can happen locally without polluting the top-level namespace

Tradeoffs:

- temporary compatibility facades may exist for a while
- import paths become slightly longer
- package migration should be done carefully to avoid churn-only patches
- top-level `cli/` may remain temporarily mixed while only the strongest families move first

## Explicit non-goals

This ADR does not require:

- changing public CLI command names
- changing the Typer model
- forcing immediate deeper nesting like `commands/operation/`
- merging helper, rendering, and workflow concerns
- moving application logic into CLI packages

## Verification criteria

This ADR is fully implemented when:

1. `cli/commands/`, `cli/rendering/`, `cli/tui/`, and `cli/workflows/` exist
2. `cli/helpers/` is either:
   - introduced later as a justified family package
   - or explicitly deferred without blocking the rest of the package migration
3. top-level `cli/` is reduced to entry/facade files plus transitional compatibility stubs
4. command families are package-grouped without premature second-level nesting
5. `commands/operation/` has **not** been introduced unless a later ADR or implementation note
   justifies it explicitly
6. CLI behavior and import compatibility remain materially stable through the transition

## Evidence for implemented status

As of 2026-04-10, the repository satisfies the full closure criteria:

1. `cli/commands/`, `cli/rendering/`, `cli/tui/`, and `cli/workflows/` exist as real packages
2. `cli/helpers/` also exists as a real package rather than remaining deferred
3. top-level `cli/` is reduced to entry/facade files rather than family-prefixed implementation
   modules
4. command families are package-grouped without introducing `commands/operation/`
5. top-level compatibility facades for the migrated families have been retired rather than
   lingering as parallel truth

## Related

- [ADR 0119](./0119-cli-main-module-decomposition-below-500-lines.md)
- [ADR 0120](./0120-cli-submodule-organization-and-boundary-rules.md)
- [RFC 0011](../rfc/0011-delivery-package-boundary-for-cli-and-tui.md)
- [RFC 0012](../rfc/0012-delivery-package-migration-tranche.md)
