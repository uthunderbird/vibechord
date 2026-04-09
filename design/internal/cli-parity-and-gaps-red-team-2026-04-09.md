# CLI Parity And Gaps Red Team

## Status

Internal critique artifact.

This document records a red-team pass over the current CLI surface against the current TUI workbench
contracts for:

- `Fleet`
- `Operation View`
- `Session View`

Its goal is not to restate the intended UX. Its goal is to identify where repository truth does not
yet support the claimed CLI/TUI parity story.

## Inputs reviewed

- [TUI-UX-VISION.md](/Users/thunderbird/Projects/operator/design/TUI-UX-VISION.md)
- [CLI-UX-VISION.md](/Users/thunderbird/Projects/operator/design/CLI-UX-VISION.md)
- [docs/reference/cli.md](/Users/thunderbird/Projects/operator/docs/reference/cli.md)
- [0115-fleet-workbench-projection-and-cli-tui-parity.md](/Users/thunderbird/Projects/operator/design/adr/0115-fleet-workbench-projection-and-cli-tui-parity.md)
- [main.py](/Users/thunderbird/Projects/operator/src/agent_operator/cli/main.py)
- [tui.py](/Users/thunderbird/Projects/operator/src/agent_operator/cli/tui.py)
- [operation_projections.py](/Users/thunderbird/Projects/operator/src/agent_operator/application/operation_projections.py)
- [operation_dashboard_queries.py](/Users/thunderbird/Projects/operator/src/agent_operator/application/operation_dashboard_queries.py)
- [agenda.py](/Users/thunderbird/Projects/operator/src/agent_operator/runtime/agenda.py)

## Core question

Given the current TUI contracts, what is actually missing or only partial in the public CLI and in
the shared service / projection substrate?

## High-level verdict

The repository does **not** yet have full CLI parity with the current TUI display family.

The gap is not uniform:

- `Fleet`: partial parity, with a major projection-model gap
- `Operation View`: partial-to-strong parity, but still assembled from separate surfaces rather than
  one explicit contract
- `Session View`: weak parity, with the clearest missing public CLI surface

## Result typing

### Verified issue 1

The current fleet substrate still targets the old agenda/dashboard shape rather than the new fleet
workbench contract.

Evidence:

- [agenda.py](/Users/thunderbird/Projects/operator/src/agent_operator/runtime/agenda.py)
  exposes runtime-oriented fields such as:
  - `objective_brief`
  - `focus_brief`
  - `latest_outcome_brief`
  - `blocker_brief`
  - `runtime_alert`
  - `runnable_task_count`
  - `reusable_session_count`
- [operation_projections.py](/Users/thunderbird/Projects/operator/src/agent_operator/application/operation_projections.py)
  `build_fleet_payload()` still returns:
  - `needs_attention`
  - `active`
  - `recent`
  - `mix`
  - `actions`

This does not match the new `Fleet` contract, which requires normalized display-facing fields such
as:

- row-level `state + agent + recency`
- normalized row hint
- compact selected-operation brief sections

Impact:

- TUI `Fleet` cannot yet be backed by the intended shared read model
- CLI `fleet --once` cannot yet expose the same human-first projection as the intended TUI

### Verified issue 2

The current TUI implementation still renders the old fleet and operation/session shapes.

Evidence in [tui.py](/Users/thunderbird/Projects/operator/src/agent_operator/cli/tui.py):

- `_FleetItem` still stores old agenda-facing fields
- `_render_list_table()` still renders columns:
  - `Op`
  - `State`
  - `Signal`
  - `Objective`
- `_render_task_board()` renders a simple lane/task/state/title table
- `_render_operation_panel()` does not implement the new split `Operation Brief + Selected Task`
  structure
- `_render_session_timeline()` plus `_render_timeline_detail_table()` still implement a timeline +
  selected-event-only shape, not the new session split hybrid

Impact:

- current code truth still lags behind the now-synced TUI design docs
- CLI/TUI parity claims cannot be treated as implemented just because the docs are aligned

### Verified issue 3

Important CLI inspection surfaces that would be needed for parity are still hidden from the normal
CLI surface.

Evidence in [main.py](/Users/thunderbird/Projects/operator/src/agent_operator/cli/main.py):

- `inspect` is `@app.command(hidden=True)`
- `context` is `@app.command(hidden=True)`
- `trace` is `@app.command(hidden=True)`

This matters because these commands currently provide part of the only CLI path to richer operation
and session inspection.

Impact:

- parity is weaker for actual end users than it appears from source availability
- some of the current "CLI can already do this" story depends on commands that are not part of the
  visible public command surface

### Verified issue 4

There is no public CLI surface that corresponds cleanly to the new `Session View`.

Closest existing commands are:

- `dashboard op-id`
- `log op-id`
- hidden `trace op-id`
- hidden `inspect op-id`

But none of these expose a session-scoped Level 2 equivalent with:

- session brief
- recent session timeline
- selected-event detail
- explicit transcript escalation

Impact:

- `Session View` is the weakest CLI parity area
- the current public CLI has transcript-ish or forensic-ish building blocks, but not a real
  session-scoped supervisory surface

### Bounded concern 1

`Operation View` parity exists mostly as a composition of several commands rather than a single
explicit CLI contract.

Evidence:

- `dashboard op-id` exposes most one-operation data
- `tasks op-id` exposes the task board
- `memory op-id` exposes memory
- `report op-id` and hidden `inspect` / `trace` expose richer history

This is stronger than `Fleet` and much stronger than `Session View`, but it still has a weakness:

- the public CLI does not expose one unified operation snapshot that mirrors the new `Operation
  View` split between compact operation brief and selected-task panel

### Bounded concern 2

The current one-operation dashboard payload is rich, but not yet normalized for the new operation
or session contracts.

Evidence in [operation_projections.py](/Users/thunderbird/Projects/operator/src/agent_operator/application/operation_projections.py):

- `build_dashboard_payload()` already exposes:
  - `tasks`
  - `attention`
  - `decision_memos`
  - `memory_entries`
  - `sessions`
  - `recent_events`
  - `timeline_events`
- but it does not expose dedicated normalized blocks like:
  - `operation_brief`
  - `session_brief`

Impact:

- TUI and CLI still need local assembly logic or heuristics
- this increases drift risk between display surfaces

### Working criticism 1

The current CLI reference language overstates practical parity by listing commands rather than
separating:

- public end-user surfaces
- hidden/internal surfaces
- composable lower-level data surfaces

The result is that the CLI can appear more feature-complete than it is for actual human workflows.

## Per-level parity assessment

### Fleet

#### Implemented

- public `fleet`
- public `status`
- public `watch`
- public action commands:
  - `answer`
  - `pause`
  - `unpause`
  - `interrupt`
  - `cancel`

#### Partial

- live fleet supervision exists
- TUI entry surface exists
- CLI snapshot exists
- agenda/fleet sorting buckets exist

#### Missing

- dedicated fleet workbench projection
- normalized row contract for the new fleet design
- normalized selected-operation fleet brief
- shared CLI/TUI fleet rendering truth

### Operation View

#### Implemented

- task board truth via `tasks`
- rich one-operation payload via `dashboard`
- action parity through shared command commands
- memory, artifacts, and attention are all separately accessible

#### Partial

- current dashboard payload is already close to supporting the new operation contract
- most data exists, but not as a dedicated `operation_brief` block

#### Missing

- one explicit public CLI surface that mirrors the new `Operation View` contract
- normalized compact `operation_brief`
- stronger parity between task-selected TUI reading and public CLI presentation

### Session View

#### Implemented

- transcript-ish data via `log`
- one-operation timeline/event data via `dashboard`
- forensic event stream via hidden `trace`

#### Partial

- session-related data exists in the broader dashboard payload
- interrupt-by-task exists

#### Missing

- public session-scoped CLI command
- normalized `session_brief`
- public CLI equivalent for Level 2 timeline + selected-event detail
- explicit public bridge from session view to raw transcript

## Mechanism audit

### Promise under test

The current design direction strongly implies:

- "the TUI workbench is a thin driving adapter over shared truth"
- "the same meaningful information is or should be available through CLI surfaces"

### What the current mechanism actually guarantees

It guarantees:

- shared control semantics for major actions
- shared one-operation truth for many operation-level details
- partial read-model reuse across CLI and TUI

It does **not** yet guarantee:

- parity of display-facing projections
- a public CLI surface for every meaningful TUI level
- one shared normalized read model for the new fleet and session contracts

### Where the stronger reading fails

The stronger reading fails in two places:

1. the repository has more shared raw data than shared display contracts
2. the CLI has more underlying commands than public human-facing parity surfaces

### Minimal fix set

#### P0

- Introduce a dedicated fleet workbench projection as already captured in
  [0115-fleet-workbench-projection-and-cli-tui-parity.md](/Users/thunderbird/Projects/operator/design/adr/0115-fleet-workbench-projection-and-cli-tui-parity.md)
- Add normalized `operation_brief` and `session_brief` display blocks instead of forcing every
  renderer to assemble them ad hoc
- Decide which hidden inspection surfaces are actually public product surfaces and unhide them if
  they are part of the claimed CLI story
- Define a public CLI story for `Session View` parity rather than treating `dashboard + log + trace`
  as "good enough"

#### P1

- Add one textual CLI snapshot per level where it sharpens parity:
  - fleet snapshot
  - operation snapshot
  - session snapshot
- Reduce documentation drift by distinguishing public parity surfaces from lower-level forensic
  surfaces

## Bottom line

The CLI is not missing everything.

It already has:

- strong control parity
- solid one-operation substrate
- most operation-level underlying data

But the current parity story breaks at the exact point where the new TUI design becomes more
human-first:

- `Fleet` lacks the right shared projection
- `Operation View` lacks a normalized brief contract
- `Session View` lacks a real public CLI equivalent

If the repository wants to keep saying "TUI is a thin adapter over shared CLI truth," these gaps
need to be treated as real product and architecture gaps, not just future polish.
