# Operation View Default And Modes Decision

## Status

Internal decision note.

This document records the current product recommendation after reviewing the `Operation View`
candidates in [operation-view-candidates-2026-04-09.md](/Users/thunderbird/Projects/operator/design/internal/operation-view-candidates-2026-04-09.md).

It is not a canonical ADR. It is a decision artifact intended to guide the next round of TUI
contracts and implementation.

## Decision

The `Operation View` should use:

- one canonical default layout
- optionally one or two explicit named modes later
- no arbitrary configurable composition

The canonical default should be:

- `Task Board + Operation Brief`

This is the current recommended product shape:

- `default`: task board with compact operation brief and selected-task detail
- optional `attention` mode: for intervention-heavy operations
- optional `session` mode: for session-readiness emphasis if runtime-heavy workflows justify it

## Why this won

The review result was that no candidate should win purely on one axis.

Instead:

- `Task Board Classic` preserved the clearest task-centric structure
- `Task Board + Operation Brief` closed the operation-level narrative gap
- `Attention-Centered Operation` was strong only for blocking-heavy workflows
- `Session-Readiness View` was strong only for session-heavy workflows

The best surviving route was therefore:

- a task-board-centered default
- with a compact operation brief
- and with specialized alternate modes deferred unless clearly justified

## Ranking

Current ranking as a default:

1. `Task Board + Operation Brief`
2. `Task Board Classic`
3. `Session-Readiness View`
4. `Attention-Centered Operation`

## Rejected routes

### 1. `Task Board Classic` as default, unchanged

Rejected because:

- it under-explains what the operation is doing overall
- it leaves too much operation-level meaning implicit
- it is weaker at carrying continuity from `Fleet`

### 2. `Attention-Centered Operation` as default

Rejected because:

- it over-centers intervention workflows
- it distorts the operation into an alerts-first surface
- it weakens neutral browsing and planning inside the operation

### 3. `Session-Readiness View` as default

Rejected because:

- it weakens task-board clarity
- it privileges runtime/session linkage over the broader operation workflow
- it is too specialized for the universal default mental model

### 4. Fully configurable `Operation View`

Rejected because:

- configurability does not solve the default-shape problem
- it weakens the continuity of the zoom hierarchy
- it creates unnecessary docs and testing complexity
- it is too likely to function as design avoidance

The only surviving part of the configurability instinct was:

- explicit named modes may be justified later
- arbitrary composition is not

## Default layout contract

The default `Operation View` should keep a stable task-first master-detail shape:

- compact header and breadcrumb
- left task board
- right pane split between compact operation brief and selected-task detail
- compact footer

### Left pane

The left pane remains the primary navigation anchor.

Default behavior:

- tasks grouped by status lanes
- selected task always visible
- task-level attention visible inline
- dependency-blocked tasks remain visually distinct from operation-level blocking

The left pane should stay task-centric rather than becoming a general operation outline.

### Right pane

The right pane should contain two layers:

1. compact operation brief
2. selected-task detail or selected-task mode panel

The operation brief should answer:

- what the operation is doing now
- what it is waiting on
- how progress is staged
- where operation-level attention exists

The selected-task detail should answer:

- what this task is
- what session/agent is attached
- what the task is currently doing
- what attention, decision, event, or memory detail matters at this scope

## Guardrails

### P0 guardrails

These are required for the recommendation to stand.

1. The task board must remain the dominant navigation model.
2. The operation brief must stay compact.
3. The right pane must not become a second fleet summary surface.
4. The right pane must not become a session transcript or forensic dump.
5. Selected-task detail must remain clearly actionable and not be crowded out by operation prose.

### P1 guardrails

These strengthen the solution but are not required for the weaker claim.

1. Alternate task-detail modes (`decisions`, `events`, `memory`) should remain one-keystroke switches.
2. If named modes are later added, keep them few and semantically crisp.
3. Session-readiness or attention-heavy variants should be treated as explicit alternate modes, not
   as the default grammar.

## Current recommendation for alternate modes

Alternate modes are not rejected forever, but they should be treated as conditional.

Short version:

- if blocking-heavy intervention becomes a common workflow, add an `attention` mode
- if session-heavy runtime inspection becomes a dominant workflow, add a `session` mode
- do not add either unless the default really proves insufficient

## Practical next step

Translate this note into a tighter UI contract for `Operation View`:

- exact task-row schema
- lane/grouping rules
- right-pane split rules
- task detail section order
- truncation rules
- narrow-terminal fallback
