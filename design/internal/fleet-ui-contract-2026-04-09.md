# Fleet UI Contract

## Status

Internal UI contract.

This document translates the current fleet decision note into a tighter screen contract for the TUI
`Fleet` window. It is intended to guide implementation and review.

Related documents:

- [fleet-default-and-modes-decision-2026-04-09.md](/Users/thunderbird/Projects/operator/design/internal/fleet-default-and-modes-decision-2026-04-09.md)
- [fleet-window-candidates-2026-04-09.md](/Users/thunderbird/Projects/operator/design/internal/fleet-window-candidates-2026-04-09.md)

## Purpose

The default `Fleet` window must answer, at a glance:

1. where attention is needed
2. what the selected operation is doing now
3. what the operator can do next

It must do this without:

- leaking internal runtime/projection details
- duplicating `Operation View`
- depending on ungrounded explanatory prose

## Canonical shape

The default `Fleet` window uses a stable master-detail layout:

- compact header
- left operation list
- right selected-operation brief
- compact footer

Canonical body split:

- left pane: 42-48% width
- right pane: 52-58% width

Preferred default:

- 45/55 split

## Screen zones

### Zone 1: Header

The header uses 2 lines by default.

Line 1:

- screen title
- active filter or mode if relevant
- refresh hint if shown
- current clock time

Line 2:

- global fleet counts

Allowed global counts:

- active
- needs human
- running
- paused
- optionally hidden-completed count

Disallowed header content:

- UUIDs
- session ids
- raw objective paragraphs
- scheduler internals
- projection dictionaries

Optional third line:

- allowed only for compact operator-load status if the runtime truth is strong enough

Examples:

- `Operator: idle`
- `Operator: following 1 session`
- `Operator: answering 1 attention`

If the operator-load signal is weak or unavailable, this line must be omitted entirely.

### Zone 2: Left pane

The left pane is a selectable list of operations.

The selected item must be visually obvious.

Default row schema:

1. `selection + attention badge + operation name`
2. `state + agent cue + recency`
3. `normalized short summary hint`

Example:

```text
> [!!2] checkout-redesign
  RUNNING · codex_acp · 8s
  now: session drill-down
```

#### Left-pane field rules

Line 1 required fields:

- selection marker if selected
- attention badge
- human-readable operation label

Line 2 required fields:

- operation state
- agent cue
- last-activity recency

Line 3 required fields:

- exactly one normalized short hint

Allowed line-3 hint families:

- `now: ...`
- `waiting: ...`
- `paused: ...`
- `failed: ...`

Preferred examples:

- `now: session drill-down`
- `now: forensic pass`
- `waiting: answer needed`
- `paused: by operator`

Disallowed line-3 content:

- freeform paragraph summaries
- raw event text
- more than one semantic clause
- unstable internal jargon

#### Agent cues

Default line-2 agent cue:

- primary active agent name

If more than one active agent is present and the runtime truth is strong:

- replace the name cue with a compact plurality cue such as `2 agents`
- or show `agent+1`

Do not list multiple agent names inline in the left pane.

### Zone 3: Right pane

The right pane is a concise explanatory brief for the currently selected operation.

It is not an `Operation View`.

Required section order:

1. operation title line
2. `Goal`
3. `Now`
4. `Wait`
5. `Progress`
6. `Attention`
7. `Recent`

Optional sections:

- `Agent`
- `Operator`

Optional sections must appear only if the underlying signal is strong and materially useful.

#### Section rules

`Goal`

- one short objective statement
- truncate aggressively rather than wrapping into a large paragraph

`Now`

- one short line describing current work

`Wait`

- one short line describing why the operation is blocked or what it is waiting on
- if there is no meaningful waiting condition, show an explicit compact neutral state or omit the
  section according to implementation choice, but do so consistently

`Progress`

- concise staged summary
- preferred structure:
  - `Done: ...`
  - `Doing: ...`
  - `Next: ...`

`Attention`

- open blocking/non-blocking summary
- oldest actionable item if available

`Recent`

- last 2-3 meaningful events only
- no raw transcript dump

#### Right-pane anti-sprawl rule

The right pane must not absorb:

- task board columns
- session event timeline in full
- transcript body
- memory detail records
- forensic/debug payloads

If the content starts feeling like drill-down rather than briefing, it belongs in the next zoom level.

### Zone 4: Footer

The footer uses 1 line by default.

It should show primary actions only.

Preferred footer:

```text
Enter open  Tab next-attn  a answer  p/u pause  s interrupt  / filter  q quit
```

Allowed footer additions:

- `c cancel` if the surface actually supports it in this mode

Disallowed footer behavior:

- encyclopedic hotkey list
- debug-heavy actions mixed with primary actions
- destructive actions made visually equal to safe navigation without distinction

## Sorting and grouping

Default sort priority:

1. operations with blocking attention
2. `FAILED`
3. `NEEDS_HUMAN`
4. `RUNNING`
5. `PAUSED`
6. completed operations hidden or pushed below active rows

Within a priority group:

- higher attention count first
- then more recent activity first

The goal is triage-first ordering, not alphabetic browsing.

## Truncation rules

### Left pane

Operation name:

- truncate with ellipsis
- preserve badge and selection marker first

Line-2 fields:

- preserve state first
- preserve recency second
- compress agent cue before dropping state or recency

Line-3 hint:

- always truncate to one line
- do not wrap

### Right pane

Goal:

- single-line preferred
- allow at most 2 lines in normal widths

Recent:

- max 3 items
- truncate each item to one line

Progress:

- each of `Done`, `Doing`, `Next` is single-line preferred

## Narrow-terminal fallback

If the terminal is too narrow for the canonical split:

### Medium narrow state

Keep both panes, but:

- shrink left pane toward 40%
- compress header to essential counts only
- reduce right pane sections to:
  - `Goal`
  - `Now`
  - `Attention`
  - `Recent`

### Very narrow state

Switch to stacked master-detail rhythm:

1. header
2. selected row block or short list block
3. brief block
4. footer

The mental model must remain master-detail even when the panes stack.

The fallback must not:

- drop the selected-operation brief entirely
- devolve into raw single-line event spam

## Operator-load policy

Operator-load is conditional, not guaranteed.

Render operator-load only if:

- the runtime model is stable
- the signal is materially useful
- the summary can be stated compactly and truthfully

Allowed placements:

- header line 3
- tiny right-pane `Operator` section

Disallowed placements:

- large dedicated pane
- verbose prose block
- precise-looking counters without strong grounding

## Multi-agent cue policy

Multi-agent cues are also conditional.

If the underlying operation model supports them reliably:

- left pane may show a compact plurality cue
- right pane may show a tiny `Agent` section

If not:

- show only the primary visible agent

The UI must not imply coordinated multi-agent state it cannot actually justify.

## Default-mode ASCII reference

```text
┌ Operator Fleet ─ active 7 · human 2 · running 4 ──────────────────── 14:32 ┐
│ Active 7   Needs human 2   Running 4   Paused 1                            │
├──────────────────────────────────┬───────────────────────────────────────────┤
│ Operations                       │ Brief                                     │
│                                  │                                           │
│ > [!!2] checkout-redesign        │ checkout-redesign                         │
│   RUNNING · codex_acp · 8s       │ Goal: Finish TUI UX, then docs           │
│   now: session drill-down        │                                           │
│                                  │ Now: Implementing session drill-down      │
│   [!!1] memory-audit             │ Wait: Agent turn running                  │
│   RUNNING · 2 agents · 2s        │                                           │
│   now: forensic pass             │ Progress: Done fleet, operation           │
│                                  │           Doing session                   │
│   [!1] docs-cleanup              │           Next forensic, docs             │
│   NEEDS_HUMAN · codex_acp · 21s  │                                           │
│   waiting: answer needed         │ Attention: 2 blocking                     │
│                                  │                                           │
│   [ ] billing-migration          │ Recent: previous slice landed             │
│   PAUSED · claude_acp · 4m       │         session resumed                   │
│   paused: by operator            │         next turn started                 │
├──────────────────────────────────┴───────────────────────────────────────────┤
│ Enter open  Tab next-attn  a answer  p/u pause  s interrupt  / filter  q    │
└───────────────────────────────────────────────────────────────────────────────┘
```

## Future mode appendix

If explicit named modes are added later:

### `dense`

May change:

- row spacing
- whitespace budget
- how many operations fit on screen

Must not change:

- master-detail mental model
- hotkey semantics
- section meanings

### `attention`

May change:

- sorting emphasis
- grouping by blocking/non-blocking urgency
- footer emphasis for `Tab` and `a`

Must not change:

- underlying selection/zoom grammar
- action semantics
- truthfulness requirements for summaries
