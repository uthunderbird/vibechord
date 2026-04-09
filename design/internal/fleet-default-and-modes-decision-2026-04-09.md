# Fleet Default And Modes Decision

## Status

Internal decision note.

This document records the current product recommendation after adversarial review of the `Fleet`
window candidates in [fleet-window-candidates-2026-04-09.md](/Users/thunderbird/Projects/operator/design/internal/fleet-window-candidates-2026-04-09.md).

It is not a canonical ADR. It is a decision artifact intended to guide the next round of TUI
contracts and implementation.

## Decision

The `Fleet` window should use:

- one canonical default layout
- optionally one or two explicit named modes
- no arbitrary configurable screen composition

The canonical default should be a hybrid:

- base layout from `Calm Workbench`
- a normalized third-line running summary hint in the left pane
- explicit `Tab next-attn` prominence
- a concise explanatory right pane

This is the current recommended product shape:

- `default`: calm-summary hybrid
- optional `dense` mode: for power-user / high-fleet throughput
- optional `attention` mode: for intervention-heavy triage

## Why this won

The critique result was not that one existing candidate was clearly sufficient as-is.
Instead:

- `Calm Workbench` was the most robust base shape
- `Supervisory Summary` contributed the missing explanatory value for running operations
- `Ultra-Dense` was useful as a specialized future mode, not as the default
- `Attention-First` was useful as a specialized future mode, not as the default

The best surviving route was therefore:

- a hybrid default
- plus limited productized modes
- without opening the door to full configurability

## Rejected routes

### 1. `Supervisory Summary` as default, unchanged

Rejected because:

- it overreaches if its extra signals are weak or inconsistently grounded
- it easily expands into a second `Operation View`
- operator-load rendering is too easy to overclaim

### 2. `Calm Workbench` as default, unchanged

Rejected because:

- it under-explains what running operations are doing
- it makes a live system feel too static
- it pushes too much explanatory burden into drill-down

### 3. `Attention-First` as default

Rejected because:

- it over-centers interruption workflows
- it weakens neutral overview behavior
- it makes low-attention operations visually secondary too early

### 4. `Ultra-Dense` as default

Rejected because:

- it is too fragile on readability
- it is more appropriate for experienced operators under heavier load
- it increases the risk of terminal noise and overly compressed semantics

### 5. Fully configurable `Fleet`

Rejected because:

- configurability does not itself guarantee better UX
- it weakens the canonical visual grammar of the product
- it increases docs, support, and testing complexity
- it is too likely to function as design avoidance rather than design resolution

The only surviving part of the configurability instinct was:

- explicit named modes may be justified
- arbitrary layout composition is not

## Default layout contract

The default `Fleet` should keep a stable master-detail shape:

- compact global header
- selectable operation list in the left pane
- selected-operation brief in the right pane
- compact footer with primary actions

### Left pane

Each active operation row should normally use up to 3 lines:

1. operation name + attention badge
2. state + agent cue + recency
3. normalized short summary hint

Examples of acceptable third-line hints:

- `now: session drill-down`
- `now: forensic pass`
- `waiting: answer needed`
- `paused by operator`

This third line is the main improvement over the earlier calm baseline.

### Right pane

The right pane should stay concise and explanatory.

Recommended sections:

- `Goal`
- `Now`
- `Wait`
- `Progress`
- `Attention`
- `Recent`

It should not absorb:

- full task board
- transcript content
- detailed forensic output
- large memory views

## Mode policy

If alternate modes are added, they should be explicit product modes with fixed semantics.

Allowed direction:

- `dense`: more rows, tighter spacing, less whitespace
- `attention`: stronger urgency ordering and attention-focused grouping

Disallowed direction:

- arbitrary pane selection
- arbitrary field toggling that changes the core reading grammar
- user-built layout composition as the primary answer

## Guardrails

### P0 guardrails

These are required for the recommendation to stand.

1. Running summaries must be normalized and grounded in stable runtime truth.
2. The default `Fleet` must not duplicate `Operation View`.
3. Operator-load signals must not appear as always-on UI unless the model is strong enough to
   support them truthfully.
4. The default `Fleet` must remain readable in normal terminal widths.

### P1 guardrails

These strengthen the solution but are not required for the weaker claim.

1. Add `dense` and `attention` only if they have crisp, documented semantics.
2. Keep the number of named modes small.
3. If operator-load becomes reliable later, surface it compactly rather than as a dominant pane.

## Current recommendation for operator-load visibility

Operator-load is not rejected forever, but it should be treated as conditional.

Short version:

- if the runtime truth is weak, hide it
- if the runtime truth is strong, render it compactly

Acceptable forms:

- a short global header line
- a tiny status block

Unacceptable forms:

- a large dedicated panel
- precise-looking numbers unsupported by stable runtime truth

## Practical next step

Translate this note into a tighter UI contract for `Fleet`:

- exact row schema
- truncation rules
- section ordering
- mode boundaries
- conditions for rendering operator-load and multi-agent cues
