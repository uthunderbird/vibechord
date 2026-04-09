# Session View UI Contract

## Status

Internal design contract.

This document defines the canonical default shape for the TUI `Session View`.

It translates the product direction from:

- [session-view-default-and-modes-decision-2026-04-09.md](/Users/thunderbird/Projects/operator/design/internal/session-view-default-and-modes-decision-2026-04-09.md)
- [tui-display-family-red-team-2026-04-09.md](/Users/thunderbird/Projects/operator/design/internal/tui-display-family-red-team-2026-04-09.md)

into an implementation-facing screen contract.

It is not itself the canonical vision source. Canonical TUI hierarchy remains:

- [TUI-UX-VISION.md](/Users/thunderbird/Projects/operator/design/TUI-UX-VISION.md)

## Canonical shape

The default `Session View` uses a split-hybrid layout:

- compact header
- left timeline pane
- right-top compact session brief
- right-bottom selected-event detail
- compact footer

It is the first zoom level that should make a live agent session legible as a running process
without collapsing into raw transcript.

## Screen zones

### Header

The header should stay to 1-2 lines.

It should include:

- breadcrumb
- session identity
- session state
- compact recency or activity hint

It must not include:

- raw ids beyond the short session cue
- full operation prose
- scheduler internals

Recommended shape:

```text
┌ fleet > op-codex-1 > task-3a7f2b1c ─ RUNNING ─────────────────────── 14:53 ┐
│ Session: codex_acp · sess-8f2a · agent turn running                        │
```

### Left pane

The left pane is the recent session timeline.

It remains the primary navigation surface at this level.

The selected row schema is:

1. time
2. glyph
3. short event label
4. optional compact suffix

Example:

```text
> 14:32 ▸ agent output
  14:31 ● brain decision: continue
  14:28 ▸ agent output
  14:20 ⚠ attention opened: policy_gap
  14:15 → session started
  14:00 ◆ task assigned
```

### Event glyphs

| Glyph | Meaning |
|-------|---------|
| `▸` | agent event |
| `●` | brain decision |
| `⚠` | attention event |
| `→` | session lifecycle |
| `◆` | task lifecycle |

### Right pane

The right pane has two layers.

#### Top: Session Brief

The top section explains current live session state.

Section order:

1. `Now`
2. `Wait`
3. `Attention`
4. `Latest output`

The brief must stay compact.

It is allowed to summarize:

- current agent activity
- waiting reason
- session-scoped open attention
- short normalized latest output summary

It is not allowed to absorb:

- operation-level summary prose
- raw transcript chunks beyond a short latest-output summary
- cumulative forensic payloads

#### Bottom: Selected Event

The bottom section explains the currently selected event.

Section order:

1. event title and time
2. event source / session cue
3. concise body or summary
4. scoped changes / artifacts if present

This section must remain substantive.

If space pressure exists, truncate the brief before making selected-event detail unreadable.

## Reference layout

```text
┌ fleet > op-codex-1 > task-3a7f2b1c ─ RUNNING ─────────────────────── 14:53 ┐
│ Session: codex_acp · sess-8f2a · agent turn running                        │
├──────────────────────────────────┬───────────────────────────────────────────┤
│ Recent Events                    │ Session Brief                             │
│                                  │                                           │
│ > 14:32 ▸ agent output           │ Now: validating token refresh flow        │
│   14:31 ● brain decision         │ Wait: agent turn running                  │
│   14:28 ▸ agent output           │                                           │
│   14:20 ⚠ attention opened       │ Attention: 1 open policy_gap              │
│   14:15 → session started        │                                           │
│   14:00 ◆ task assigned          │ Latest output: implemented refresh        │
│                                  │ handler; moving to validation             │
│                                  │                                           │
│                                  │ ───────────────────────────────────────   │
│                                  │ Selected Event                            │
│                                  │ [14:32] agent output                     │
│                                  │ codex_acp · sess-8f2a                    │
│                                  │                                           │
│                                  │ Implemented token refresh handler.        │
│                                  │ Moving to validation.                     │
│                                  │                                           │
│                                  │ Changes: auth/session.py, tests/auth.py   │
├──────────────────────────────────┴───────────────────────────────────────────┤
│ ↑/↓ move  Enter expand  r transcript  s interrupt  Esc back  q quit         │
└───────────────────────────────────────────────────────────────────────────────┘
```

## Dominance rule

The primary working object at this level is the selected event.

That means:

- the timeline stays primary on the left
- the selected-event section stays substantive on the right
- the session brief may orient, but must not dominate

If the right pane starts reading mostly as a session dashboard, the contract has been violated.

## Transcript escalation rule

Raw transcript remains explicitly one action away.

Rules:

- transcript is entered with `r`
- transcript is not rendered by default inside the main `Session View`
- transcript snippets may appear only as short event or latest-output summaries

If the screen starts feeling like transcript preview plus timeline, the Level 2 / Level 3 boundary
has collapsed.

## Action semantics

The `Session View` footer should prioritize:

- event navigation
- transcript access
- interrupt
- back / quit

Recommended footer:

```text
↑/↓ move  Enter expand  r transcript  s interrupt  Esc back  q quit
```

## Truncation rules

The contract prefers preserving timeline readability and selected-event readability over richer
summary.

Order of truncation:

1. shorten `Latest output`
2. shorten `Attention`
3. shorten `Wait`
4. shorten event suffixes
5. truncate event detail body only after the above

Do not remove the selected event title/time block.

## Narrow-terminal fallback

For narrower terminals, preserve the same information hierarchy in a stacked form:

1. header
2. selected event summary
3. session brief
4. recent events list
5. footer

This fallback should remain temporary and readability-first.

It should not invent a different conceptual model.

## Alternate mode policy

The default contract stands on its own.

At most one future named mode is acceptable:

- `debug`

If introduced later, that mode may:

- emphasize chronology more strongly
- show denser event inspection
- bring transcript-adjacent context closer

But it still must not become `Raw Transcript` in all but name.

## Anti-sprawl rule

`Session View` must not absorb:

- full operation brief
- full task board semantics
- full transcript body
- forensic/debug payloads better suited to a deeper level

Its job is:

- current session legibility
- recent change legibility
- explicit escalation path

No more.
