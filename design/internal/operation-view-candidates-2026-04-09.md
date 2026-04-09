# Operation View Candidates

## Status

Internal design artifact.

This document records concrete candidate layouts for the TUI `Operation View` so the repository has
an explicit comparison set before selecting or refining one design.

It is not itself the canonical vision source. The canonical TUI hierarchy remains defined in
[TUI-UX-VISION.md](/Users/thunderbird/Projects/operator/design/TUI-UX-VISION.md).

## Shared Operation View requirements

Every viable `Operation View` candidate should satisfy the same base contract:

- answer `which task is selected and what state is it in?`
- answer `what is the operation doing overall?`
- answer `where is blocking attention or real risk?`
- preserve continuity with `Fleet` rather than feeling like a separate app
- allow drill-down to session view without forcing the user to wade through forensic detail

Minimum common elements:

- breadcrumb and compact header
- left task-navigation surface
- right selected-task or selected-scope detail surface
- compact footer with operation-level actions and pane-switch hints

Data that belongs in `Operation View`:

- task grouping or ordering
- task status and attention cues
- selected-task goal / current state
- selected-task session linkage
- operation-level pause/unpause/interrupt affordances
- decision/event/memory access at task scope

Data that should not dominate `Operation View`:

- raw transcript body
- full forensic payloads
- scheduler internals
- projection dictionaries
- giant operation summary prose blocks

## Candidate A: Task Board Classic

### Intent

This is the most direct continuation of the current vision.

It optimizes for:

- strong task-centric navigation
- immediate recognition of workflow lanes
- low ambiguity around task lifecycle

It accepts:

- some verbosity in the left pane
- weaker operation-level narrative outside the selected task

### Layout

- Header: 2 lines
- Body: split roughly 45/55
- Left pane: grouped task board by status lanes
- Right pane: selected task detail with switchable `detail / decisions / events / memory`
- Footer: 1 line with task and operation actions

### ASCII prototype

```text
┌ fleet > op-codex-1 ─ RUNNING ─ 2 blocking ─────────────────────────── 14:42 ┐
│ Goal: Finish TUI UX, then docs                                              │
├──────────────────────────────────┬───────────────────────────────────────────┤
│ Tasks                            │ Task Detail                               │
│                                  │                                           │
│ [RUNNING]                        │ task-3a7f2b1c · auth session runner      │
│ > ▶ 3a7f2b1c [!!1] session run   │                                           │
│   ▶ 9e1c4d2a      unit tests     │ Status: RUNNING · iter 14 · 40m          │
│                                  │ Agent: codex_acp · sess-8f2a             │
│ [READY]                          │ Goal: Implement ACP session runner        │
│   ○ 7b3f1e9d      adapter        │                                           │
│                                  │ Latest: Writing token refresh handler     │
│ [BLOCKED]                        │                                           │
│   ◐ 2c8a5f3b      integ tests    │ Attention: 1 blocking                     │
│     ↳ 3a7f2b1c, 7b3f1e9d         │ policy_gap: commit directly to main?      │
│                                  │                                           │
│ [COMPLETED]                      │ Next: answer attention or Enter session   │
│   ✓ a1d4e7c2      domain model   │                                           │
├──────────────────────────────────┴───────────────────────────────────────────┤
│ Enter session  Tab next-attn  a answer  d decisions  t events  m memory     │
└───────────────────────────────────────────────────────────────────────────────┘
```

### Strengths

- strongest task-lifecycle clarity
- most natural bridge from fleet into task work
- easy to explain and document

### Risks

- operation-level context can feel too implicit
- blocked lanes can become visually heavy
- very large task sets may overwhelm the left pane

## Candidate B: Task Board + Operation Brief

### Intent

This is the balanced hybrid.

It optimizes for:

- preserving the task board
- adding stronger operation-level narrative
- helping the operator orient before focusing only on one task

It accepts:

- a denser right pane
- slightly less room for task-only detail

### Layout

- Header: 2-3 lines
- Body: split roughly 42/58
- Left pane: task board with slightly compressed rows
- Right pane: top `Operation Brief`, bottom selected-task pane or mode-switch content
- Footer: 1 line

### ASCII prototype

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
│                                  │ Recent: slice landed                      │
│ [COMPLETED]                      │         resumed session                   │
│   ✓ a1d4e7c2      domain model   │                                           │
│                                  │ ───────────────────────────────────────   │
│                                  │ Selected Task                             │
│                                  │ task-3a7f2b1c · auth session runner      │
│                                  │ Status: RUNNING · codex_acp              │
│                                  │ Goal: Implement ACP session runner       │
│                                  │ Latest: Writing token refresh handler    │
├──────────────────────────────────┴───────────────────────────────────────────┤
│ Enter session  Tab next-attn  a answer  d/t/m switch pane  p/u pause  q     │
└───────────────────────────────────────────────────────────────────────────────┘
```

### Strengths

- best operation-level orientation
- smoother continuity from `Fleet`
- gives meaning to the whole operation, not only the selected task

### Risks

- easiest to overgrow into too much summary
- selected-task detail gets less space
- can start to compete with `Fleet` brief and `Session View`

## Candidate C: Attention-Centered Operation

### Intent

This is the intervention-heavy view.

It optimizes for:

- quickly resolving task-scoped blocking items
- surfacing the riskiest task first
- minimizing time-to-answer inside an operation

It accepts:

- less neutral task-board browsing
- stronger visual bias toward blocked/running tasks

### Layout

- Header: 2 lines focused on operation risk and attention counts
- Left pane: tasks grouped by attention urgency first, then status
- Right pane: selected task plus explicit action guidance
- Footer: attention and intervention keys are primary

### ASCII prototype

```text
┌ fleet > op-codex-1 ─ 2 blocking · 1 non-blocking ─────────────────── 14:42 ┐
│ Operation needs human attention before full completion                        │
├──────────────────────────────────┬───────────────────────────────────────────┤
│ Needs Action                     │ Selected                                  │
│                                  │                                           │
│ > [!!1] 3a7f2b1c session runner  │ task-3a7f2b1c · auth session runner      │
│   RUNNING · codex_acp · 40m      │                                           │
│   policy_gap: commit to main?    │ What needs you                            │
│                                  │ policy_gap: commit directly to main?      │
│   [!1] 9e1c4d2a unit tests       │                                           │
│   RUNNING · codex_acp · 12m      │ Suggested action                          │
│   note: decide assertion style   │ answer blocking attention                 │
│                                  │                                           │
│ Other Tasks                      │ Current state                             │
│ ─────────────────────────        │ RUNNING · iter 14 · sess-8f2a            │
│   ○ 7b3f1e9d adapter             │                                           │
│   ◐ 2c8a5f3b integ tests         │ Latest                                    │
│   ✓ a1d4e7c2 domain model        │ Writing token refresh handler             │
├──────────────────────────────────┴───────────────────────────────────────────┤
│ Tab next-attn  a answer  Enter session  s interrupt  p/u pause  q quit      │
└───────────────────────────────────────────────────────────────────────────────┘
```

### Strengths

- best for intervention-heavy operations
- makes task-level attention unmistakable
- keeps the user near the fastest actionable path

### Risks

- weaker for neutral browsing and planning
- can distort the mental model of the operation into “only alerts matter”
- less suitable as a universal default

## Candidate D: Session-Readiness View

### Intent

This variant treats `Operation View` as the launchpad for entering sessions.

It optimizes for:

- choosing which active task/session to inspect next
- showing task-to-session linkage clearly
- making agent activity more explicit than lane semantics alone

It accepts:

- reduced emphasis on task-board lanes
- less familiar kanban-like shape

### Layout

- Header: 2 lines
- Body: split 45/55
- Left pane: flat ordered task/session list with status chips instead of large grouped lanes
- Right pane: selected task/session readiness detail
- Footer: `Enter`, `s`, and mode-switch keys are emphasized

### ASCII prototype

```text
┌ fleet > op-codex-1 ─ RUNNING ─ 4 tasks ─ 1 active session ─────────── 14:42 ┐
│ Goal: Finish TUI UX, then docs                                              │
├──────────────────────────────────┬───────────────────────────────────────────┤
│ Task / Session Readiness         │ Selected                                  │
│                                  │                                           │
│ > [!!1] task-3a7f2b1c            │ task-3a7f2b1c · auth session runner      │
│   RUNNING · codex_acp · sess-8f2a│                                           │
│   ready to inspect               │ Session: sess-8f2a                        │
│                                  │ Agent: codex_acp                          │
│   [ ] task-9e1c4d2a              │ Status: RUNNING                           │
│   RUNNING · codex_acp · sess-8f2a│                                           │
│   background progress            │ Goal: Implement ACP session runner        │
│                                  │                                           │
│   [ ] task-7b3f1e9d              │ Latest: Writing token refresh handler     │
│   READY · no session             │                                           │
│   waiting for execution          │ Decision: task board is current priority  │
│                                  │                                           │
│   [ ] task-2c8a5f3b              │ Memory: keep left pane stable             │
│   BLOCKED · no session           │                                           │
│   deps 3a7f2b1c, 7b3f1e9d        │                                           │
├──────────────────────────────────┴───────────────────────────────────────────┤
│ Enter session  i detail  d decisions  t events  m memory  s interrupt  q    │
└───────────────────────────────────────────────────────────────────────────────┘
```

### Strengths

- strongest transition into `Session View`
- makes linked-session reality very explicit
- good for runtime-heavy operations where session state matters more than lane purity

### Risks

- loses some task-board clarity
- less visually obvious as an operation-wide workflow board
- may be too specialized for the default mental model

## Comparative summary

| Candidate | Primary strength | Primary risk | Best fit |
| --- | --- | --- | --- |
| Task Board Classic | task-lifecycle clarity | weak operation narrative | straightforward default if task board is primary |
| Task Board + Operation Brief | best orientation | summary sprawl | balanced default with stronger operation context |
| Attention-Centered Operation | fastest intervention | alert-centric bias | blocking-heavy operations |
| Session-Readiness View | strongest session drill-down readiness | weaker lane clarity | runtime/session-heavy workflows |

## Current recommendation

No winner is fixed in this document.

If a single default candidate must be chosen next, the strongest starting point is:

- `Task Board + Operation Brief` as the base layout
- with two guardrails:
  - the operation brief must stay compact and not absorb fleet-level summary responsibilities
  - the selected-task panel must remain clearly dominant over generic operation prose

This hybrid best preserves continuity from `Fleet` while still letting `Operation View` feel like a
task-centric working surface rather than a second fleet summary screen.
