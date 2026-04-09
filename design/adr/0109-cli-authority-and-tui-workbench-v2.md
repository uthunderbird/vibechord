# ADR 0109: CLI Authority And TUI Workbench Evolution

## Status

Implemented

## Context

`ADR 0038` established CLI authority and TUI as a future supervisory workbench. Since then:

- CLI UX was clarified in `CLI-UX-VISION.md`.
- TUI-level controls and navigation were expanded in `TUI-UX-VISION.md`.
- Command surface and operator semantics were stabilized by `ADR 0096` and related control ADRs.

The implementation and specification work is now entering a phase where the boundary is no longer
philosophical, but contract-critical. We need an explicit, reviewable contract to prevent split-brain
behavior between interactive and non-interactive control paths.

`ADR 0038` leaves enough high-level direction, but it does not enumerate the detailed commandable
contract required for:

- mapping every meaningful TUI action to a CLI command,
- defining fallback behavior when input state is unavailable,
- and marking roadmap-only TUI features as intentionally deferred.

## Decision

`operator` keeps CLI as the authoritative control plane and execution contract; TUI remains a
supervisory workbench that consumes the same persisted truth.

### Normative split

1. The following remain authoritative CLI surfaces:
   - operation lifecycle control: `run`, `status`, `pause`, `unpause`, `interrupt`, `answer`, `cancel`
   - lightweight one-operation live following: `watch`
   - one-operation inspection: `tasks`, `memory`, `artifacts`, `report`, `log`
   - fleet/progress supervision: `fleet`, `agenda`, `project dashboard`, `history`, `list`
   - debug/forensics surfaces remain in their established namespaces, including `context`, `trace`,
     and `inspect` under `operator debug`.

2. TUI is authorized to add:
   - faster navigation across operation/task/session levels,
   - compact signal surfacing (attention and badge state),
   - action composition (confirmation, filtering, focus jumps).

   It is not authorized to define novel control semantics that are not present as public CLI commands.

3. On any ambiguity, TUI behavior must follow the CLI contract, even when richer UI affordances could
   provide a shortcut.

4. Missing or unsupported capabilities in TUI must be explicitly marked as non-goals or roadmap items in
   the relevant TUI ADR, not silently added as implicit functionality.

### Surface-role clarification

Within the authoritative CLI contract, the one-operation surfaces have different jobs:

- `status` is the canonical shell-native one-operation summary surface
- `watch` is a retained textual live follower, useful when a full workbench is unnecessary or
  unavailable
- the TUI workbench is the preferred interactive live supervision surface

This ADR treats those roles as complementary, not competing.

## Decision Consequences

- New command work, naming, and confirmation rules are decided centrally in CLI ADR chain; TUI adopts them
  by mapping.
- Product onboarding remains scriptable and non-interactive-first: basic workflows must succeed without launching
  a full-screen interface.
- Any future TUI work is evaluated against this criterion:
  *Does it materially improve supervision while preserving CLI semantics and commandability?*

## TUI-CLI Boundary Rules

- All state-changing TUI actions map to existing public CLI operations.
- TUI must support read-through to CLI snapshots (`--json`/`--brief` forms where available) for
  automation parity.
- TUI must never require a command or mode that cannot be represented by existing CLI semantics.

## Alternatives Considered

### Option A: Keep `ADR 0038` unchanged and defer detailed TUI boundary ADRs

Rejected.

This leaves enough uncertainty for inconsistent action semantics and repeated alignment work during
implementation.

### Option B: Treat TUI and CLI as co-equal primary surfaces

Rejected.

Co-equality breaks command reproducibility guarantees and increases risk of two authoritative control
surfaces diverging over time.

### Option C: Treat CLI as authority and codify action mapping contracts in dedicated ADRs

Accepted.

This keeps the existing architecture direction but turns it into an enforceable implementation contract.

## Verification

- `design/TUI-UX-VISION.md` sections on startup behavior and action mapping remain consistent with this ADR.
- `design/CLI-UX-VISION.md` command taxonomy is authoritative for user-facing control verbs.
- All new TUI design ADRs in this series reference this ADR as an inheritance boundary.

## Implementation outcome

- TUI state-changing actions in `src/agent_operator/cli/workflows_views.py` now pass through
  dedicated command-dispatch helpers that mirror CLI control semantics for pause, unpause, interrupt,
  and cancel.
- `FleetWorkbenchController` action handlers in `src/agent_operator/cli/tui_controller.py` continue
  to expose only those mapped state transitions (`p`, `u`, `s`, and `c`) and avoid introducing
  command surfaces unavailable in CLI.
- TUI read-only navigation (`tab`, `enter`, `r`, `i/d/t/m`) stays non-authoritative and does not
  create new mutable control semantics.
- Existing `tests/test_tui.py` coverage already validates the key mapping and task-targeted interrupt
  behavior in session drill-down.

## Dependencies

- `ADR 0038` for baseline CLI/TUI product split.
- `ADR 0096` for one-operation control semantics.
- `ADR 0114` for the required CLI substrate split before TUI implementation work.
- `design/CLI-UX-VISION.md`.
- `design/TUI-UX-VISION.md`.

## Prerequisite Note

This ADR is not, by itself, authorization to implement TUI directly against the current
`src/agent_operator/cli/main.py` module.

Before implementation begins, the CLI/application boundary must expose the application-facing
command/use-case ports and query/projection services described in `ADR 0114` so TUI work can
consume the same read models and control paths without importing CLI-specific rendering and
command wiring.
