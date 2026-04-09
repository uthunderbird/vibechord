# Operation View UI Contract

## Status

Internal UI contract.

This document translates the current operation-view decision note into a tighter screen contract for
the TUI `Operation View`. It is intended to guide implementation and review.

Related documents:

- [operation-view-default-and-modes-decision-2026-04-09.md](/Users/thunderbird/Projects/operator/design/internal/operation-view-default-and-modes-decision-2026-04-09.md)
- [operation-view-candidates-2026-04-09.md](/Users/thunderbird/Projects/operator/design/internal/operation-view-candidates-2026-04-09.md)
- [fleet-ui-contract-2026-04-09.md](/Users/thunderbird/Projects/operator/design/internal/fleet-ui-contract-2026-04-09.md)

## Purpose

The default `Operation View` must answer, at a glance:

1. which task is selected
2. what the operation is doing overall
3. what the selected task is doing now
4. whether there is blocking attention or operator action needed
5. whether it makes sense to drill down into session view

It must do this without:

- duplicating `Fleet`
- collapsing into a task-only board with no operation context
- turning into a session transcript or forensic surface

## Canonical shape

The default `Operation View` uses a task-first master-detail layout:

- compact header
- left task board
- right pane split into operation brief and selected-task detail
- compact footer

Canonical body split:

- left pane: 40-46% width
- right pane: 54-60% width

Preferred default:

- 42/58 split

## Screen zones

### Zone 1: Header

The header uses 2 lines by default.

Line 1:

- breadcrumb
- operation state
- compact attention count if relevant
- current clock time

Line 2:

- short operation goal

Allowed header content:

- `fleet > op-id`
- `RUNNING` / `NEEDS_HUMAN` / `PAUSED`
- compact blocking/non-blocking counts
- short goal text

Disallowed header content:

- UUID noise beyond the visible operation label
- long prose paragraphs
- scheduler internals
- raw projection fields

### Zone 2: Left pane

The left pane is the primary navigation surface.

It is a task board grouped by lane.

Default lane order:

1. `RUNNING`
2. `READY`
3. `BLOCKED`
4. `COMPLETED`
5. `FAILED`
6. `CANCELLED`

`BLOCKED` here is a presentation lane for dependency-blocked tasks, not an operation-level
attention synonym.

### Task row schema

Each task row should normally fit on one visual line.

Required task-row elements:

- selection marker
- task status glyph
- task short id
- attention badge if present
- concise task title

Optional continuation line:

- dependency summary for dependency-blocked tasks
- short task-session cue if space allows

Examples:

```text
> ▶ 3a7f2b1c [!!1] auth session runner
  ↳ deps: 7b3f1e9d
```

```text
  ○ 7b3f1e9d adapter wiring
```

### Left-pane rules

- selected task must remain visible
- lane headers must remain visually distinct
- running tasks must not be visually buried under completed tasks
- task attention must be visible inline
- dependency explanations must be compact, not paragraph form

Disallowed left-pane behavior:

- rendering full task descriptions inline
- rendering memory or decision text inline
- using session/transcript text as task-row content

### Zone 3: Right pane

The right pane has two subzones:

1. compact operation brief
2. selected-task detail panel

The selected-task panel may switch modes, but the operation brief remains compact and stable.

#### Zone 3A: Operation brief

The operation brief should stay above the selected-task panel.

Required section order:

1. `Now`
2. `Wait`
3. `Progress`
4. `Attention`
5. `Recent`

Optional:

- `Goal` may be omitted here if already clearly present in the header line 2

Section rules:

`Now`

- one short line describing the current operation-level focus

`Wait`

- one short line describing current blocking/waiting reason
- may be omitted only if there is nothing meaningful to say and the implementation does so
  consistently

`Progress`

- concise staged summary
- preferred structure:
  - `Done: ...`
  - `Doing: ...`
  - `Next: ...`

`Attention`

- operation-level attention summary
- oldest or most actionable item if available

`Recent`

- last 2-3 meaningful operation events only

#### Zone 3B: Selected-task panel

The selected-task panel is the main right-pane working surface.

Default mode:

- `detail`

Alternate modes:

- `decisions`
- `events`
- `memory`

The selected-task panel must always remain clearly scoped to the selected task.

##### Detail mode

Required section order:

1. task title line
2. `Status`
3. `Agent / Session`
4. `Goal`
5. `Latest`
6. `Attention`
7. optional compact metadata:
   - dependencies
   - memory refs
   - artifact refs

##### Decisions mode

Show only recent decision memos for the selected task scope.

Must not:

- switch scope silently to operation-global memos
- flood the pane with long historical text by default

##### Events mode

Show only recent simplified events for the selected task scope.

Must not:

- render the full transcript
- duplicate `Session View`

##### Memory mode

Show task-scoped memory entries first.

Operation-scoped memory may appear only if clearly labeled and only if task-scoped entries are absent
or intentionally supplemented.

### Right-pane anti-sprawl rule

The right pane must not absorb:

- full task board logic
- session timeline in full
- raw transcript body
- forensic/debug payloads
- a second fleet-style operation summary block

If the content starts feeling like `Fleet` plus `Session View` at once, it is too much.

### Zone 4: Footer

The footer uses 1 line by default.

It should show primary actions only.

Preferred footer:

```text
Enter session  Tab next-attn  a answer  d/t/m switch pane  p/u pause  s interrupt  q quit
```

Allowed additions:

- `Esc back`
- `? help`

Disallowed footer behavior:

- encyclopedic hotkey lists
- raw internal action names
- destructive actions presented without distinction

## Selection and navigation rules

- `↑` / `↓` move task selection
- `Enter` drills into `Session View` for the selected task
- `Esc` returns to `Fleet`
- `Tab` jumps to the next task with blocking attention
- pane-mode keys never change task selection

The left-pane task selection is the primary anchor for all right-pane modes.

## Truncation rules

### Left pane

Task title:

- single-line preferred
- truncate with ellipsis

Dependency continuation:

- one compact continuation line at most

Lane headers:

- never truncated into ambiguity

### Right pane

Operation brief sections:

- each line single-line preferred
- `Recent` max 3 items

Selected-task detail:

- `Goal` may use up to 2 lines in normal widths
- `Latest` may use up to 2 lines
- metadata lines should stay compact and scannable

## Narrow-terminal fallback

If the terminal is too narrow for the canonical split:

### Medium narrow state

Keep both panes, but:

- reduce operation brief to:
  - `Now`
  - `Attention`
  - `Recent`
- keep selected-task detail dominant

### Very narrow state

Switch to stacked rhythm:

1. header
2. task board block
3. operation brief block
4. selected-task block
5. footer

The fallback must preserve:

- task-first navigation
- visible selected-task detail
- visible operation-level context

It must not degrade into:

- a raw list of tasks only
- a transcript-like scrolling dump

## Attention policy

Task-scoped and operation-scoped attention are distinct.

Display rules:

- task-scoped attention appears inline on task rows and in selected-task detail
- operation-scoped attention appears in the operation brief
- the UI must not blur dependency-blocked tasks with operation-level human-blocked state

## Session cue policy

Session linkage is important but secondary to the task board.

Allowed:

- compact `Agent / Session` line in selected-task detail
- optional compact cue in left pane if space allows

Disallowed:

- turning the entire operation view into a flat session list in the default mode

## Default-mode ASCII reference

```text
┌ fleet > op-codex-1 ─ RUNNING ─ 2 blocking ─────────────────────────── 14:42 ┐
│ Goal: Finish TUI UX, then docs                                              │
├──────────────────────────────────┬───────────────────────────────────────────┤
│ Tasks                            │ Operation Brief                           │
│                                  │                                           │
│ [RUNNING]                        │ Now: implementing session drill-down      │
│ > ▶ 3a7f2b1c [!!1] session run   │ Wait: current agent turn running          │
│   ▶ 9e1c4d2a      unit tests     │                                           │
│                                  │ Progress: Done fleet, operation           │
│ [READY]                          │           Doing session                   │
│   ○ 7b3f1e9d      adapter        │           Next forensic, docs             │
│                                  │                                           │
│ [BLOCKED]                        │ Attention: 2 blocking                     │
│   ◐ 2c8a5f3b      integ tests    │                                           │
│     ↳ 3a7f2b1c, 7b3f1e9d         │ Recent: slice landed                      │
│                                  │         resumed session                   │
│ [COMPLETED]                      │                                           │
│   ✓ a1d4e7c2      domain model   │ ───────────────────────────────────────   │
│                                  │ Selected Task                             │
│                                  │ task-3a7f2b1c · auth session runner      │
│                                  │ Status: RUNNING · iter 14 · 40m          │
│                                  │ Agent: codex_acp · sess-8f2a             │
│                                  │ Goal: Implement ACP session runner       │
│                                  │ Latest: Writing token refresh handler    │
│                                  │ Attention: policy_gap                    │
├──────────────────────────────────┴───────────────────────────────────────────┤
│ Enter session  Tab next-attn  a answer  d/t/m switch pane  p/u pause  q     │
└───────────────────────────────────────────────────────────────────────────────┘
```

## Future mode appendix

If explicit named modes are added later:

### `attention`

May change:

- task grouping emphasis
- ordering of attention-bearing tasks
- footer emphasis for `Tab` and `a`

Must not change:

- task-first navigation anchor
- task selection semantics
- action meanings

### `session`

May change:

- prominence of session linkage cues
- readiness ordering for active-session tasks

Must not change:

- the fact that this is still an operation-level view
- the distinction between task board and session detail
- the deeper role of `Session View`
