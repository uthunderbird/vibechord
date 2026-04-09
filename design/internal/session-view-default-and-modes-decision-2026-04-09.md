# Session View Default And Modes Decision

## Status

Internal decision note.

This document records the current product recommendation after reviewing the `Session View`
candidates in [session-view-candidates-2026-04-09.md](/Users/thunderbird/Projects/operator/design/internal/session-view-candidates-2026-04-09.md).

It is not a canonical ADR. It is a decision artifact intended to guide the next round of TUI
contracts and implementation.

## Decision

The `Session View` should use:

- one canonical default layout
- optionally one explicit named alternate mode later
- no arbitrary configurable composition

The canonical default should be:

- `Split Hybrid`

This is the current recommended product shape:

- `default`: recent timeline on the left, compact session brief on the right-top, selected event
  detail on the right-bottom
- optional future `debug` mode: for chronology-heavy or debugging-heavy inspection if real usage
  justifies it

## Why this won

The review result was that `Session View` must do more than browse chronology.

Instead:

- `Timeline First` preserved the clearest chronological structure
- `Split Hybrid` added the missing current-session-state frame
- `Current-State First` was strong on live understanding but too easy to blur with a compact
  dashboard
- `Transcript-Proximate` was strong only for debugging-heavy workflows and too close to `Raw
  Transcript`

The best surviving route was therefore:

- a split hybrid default
- with one possible specialized debug-oriented mode left as a conditional future option

## Ranking

Current ranking as a default:

1. `Split Hybrid`
2. `Timeline First`
3. `Current-State First`
4. `Transcript-Proximate`

## Rejected routes

### 1. `Timeline First` as default, unchanged

Rejected because:

- it is too close to a generic event-log browser
- it under-answers `what is this session doing right now?`
- it makes the operator reconstruct current state from chronology alone

### 2. `Current-State First` as default

Rejected because:

- it weakens chronology too much for a level whose identity still depends on session events
- it risks feeling like a compact dashboard instead of a session view
- it is not distinct enough from the winning hybrid to justify replacing it

### 3. `Transcript-Proximate` as default

Rejected because:

- it is too close to `Raw Transcript`
- it weakens the identity of Level 2 as its own supervisory surface
- it over-biases the level toward debugging-heavy usage

### 4. Fully configurable `Session View`

Rejected because:

- configurability does not solve the default-shape problem
- it weakens the zoom hierarchy and docs clarity
- it is too likely to function as design avoidance

The only surviving part of the configurability instinct was:

- one explicit named alternate mode may be justified later
- arbitrary composition is not

## Default layout contract

The default `Session View` should keep a stable split-hybrid shape:

- compact header and breadcrumb
- left recent-event timeline
- right-top compact session brief
- right-bottom selected event detail
- compact footer

### Left pane

The left pane remains timeline-first:

- recent events in reverse chronological order
- selected event always visible
- event glyphs and timestamps stay compact and scannable

### Right pane

The right pane has two layers:

1. compact session brief
2. selected-event detail

The session brief should answer:

- what the session is doing now
- what it is waiting on
- whether session-scoped attention exists
- what the latest meaningful output says

The selected-event detail should answer:

- what this event is
- why it matters
- what concrete change/output/context it carries

## Guardrails

### P0 guardrails

These are required for the recommendation to stand.

1. The session brief must stay compact and session-scoped.
2. The selected-event detail must remain substantive.
3. The default `Session View` must not duplicate `Operation View`.
4. The default `Session View` must not become a transcript preview screen by default.
5. Transcript access must remain explicit and one action away.

### P1 guardrails

These strengthen the solution but are not required for the weaker claim.

1. A future `debug` mode should remain clearly distinct from `Raw Transcript`.
2. If a mode is added later, keep it singular and semantically crisp.
3. The default and any future mode must preserve the same drill-down semantics and action meanings.

## Current recommendation for alternate modes

Alternate modes are not rejected forever, but they should be treated as conditional.

Short version:

- default should stand on its own first
- if debugging-heavy inspection repeatedly proves awkward, add one `debug` mode
- do not add a mode merely because an alternate candidate exists on paper

The `debug` mode, if ever added, should emphasize chronology and inspection, but must still stop
short of becoming `Level 3` transcript-in-all-but-name.

## Practical next step

Translate this note into a tighter UI contract for `Session View`:

- exact event-row schema
- session-brief section order
- selected-event detail rules
- truncation rules
- transcript escalation behavior
- narrow-terminal fallback
