# Fleet Window Candidates

## Status

Internal design artifact.

This document records concrete candidate layouts for the TUI `Fleet` window so the repository has
an explicit comparison set before selecting or refining one design.

It is not itself the canonical vision source. Canonical product role remains:

- `status` = canonical shell-native one-operation summary
- TUI workbench = preferred interactive live supervision surface
- `watch` = lightweight textual live follower

## Shared Fleet requirements

Every viable `Fleet` window candidate should satisfy the same base contract:

- answer `where is attention needed?`
- answer `what is the selected operation doing now?`
- preserve a stable master-detail mental model
- keep destructive actions secondary and clearly marked
- avoid projection dumps and internal implementation noise

Minimum common elements:

- a compact global header
- a selectable operation list in the left pane
- a brief/summary pane for the selected operation in the right pane
- a footer with primary actions

Data that belongs in the `Fleet` window:

- operation name
- operation state
- attention signal counts
- recent activity hint
- selected-operation goal
- selected-operation current work / waiting reason
- concise progress summary
- recent events summary

Data that should not dominate the `Fleet` window:

- raw UUIDs
- scheduler internals
- projection dictionaries
- full task board
- full transcript
- detailed forensic traces

## Candidate A: Ultra-Dense

### Intent

This is the power-user, high-throughput operator desk.

It optimizes for:

- fitting many operations on screen
- fast triage under load
- minimal wasted vertical space

It accepts:

- higher visual density
- lower approachability for new users

### Layout

- Header: 2 lines
- Body: split 50/50 or 48/52
- Left pane: 3 short lines per operation
- Right pane: compact but still semantic
- Footer: 1 line

### ASCII prototype

```text
┌ Fleet ─ active 12 · human 3 · running 7 · paused 2 ─────────────── 14:32 ┐
│ Operations                           │ Selected                             │
├──────────────────────────────────────┼──────────────────────────────────────┤
│ > [!!2] checkout-redesign            │ checkout-redesign                    │
│   RUNNING · codex_acp · 8s           │ RUNNING · codex_acp · iter 4        │
│   doing session-drilldown            │                                      │
│                                      │ Goal                                 │
│   [!!1] memory-audit                 │ Finish TUI UX, then docs             │
│   RUNNING · codex_acp · 2s           │                                      │
│   doing forensic pass                │ Now                                  │
│                                      │ Implementing session drill-down      │
│   [!1] docs-cleanup                  │ Wait: current agent turn running     │
│   NEEDS_HUMAN · codex_acp · 21s      │                                      │
│   needs answer                       │ Progress                             │
│                                      │ Done  fleet, operation               │
│   [ ] billing-migration              │ Doing session                        │
│   PAUSED · claude_acp · 4m           │ Next  forensic, docs                 │
│   paused by operator                 │                                      │
│                                      │ Attention                            │
│   [ ] parser-hardening               │ 2 blocking                           │
│   RUNNING · codex_acp · 14s          │ oldest: verify transcript layout     │
│   doing tests                        │                                      │
│                                      │ Recent                               │
│                                      │ 14:31 previous slice landed          │
│                                      │ 14:31 session resumed                │
│                                      │ 14:32 next turn started              │
├──────────────────────────────────────┴──────────────────────────────────────┤
│ Enter open  Tab next-attn  a answer  p/u pause  s interrupt  c cancel  q    │
└──────────────────────────────────────────────────────────────────────────────┘
```

### Strengths

- best scan speed when many operations are active
- high information density without changing levels
- supports experienced operators well

### Risks

- can feel cramped in smaller terminals
- difficult for first-time users to parse
- easier to regress into noisy operator-internal output

## Candidate B: Calm Workbench

### Intent

This is the default-balanced workbench.

It optimizes for:

- readability
- stable visual hierarchy
- lower onboarding cost

It accepts:

- fewer operations visible at once
- slightly slower triage than the dense variant

### Layout

- Header: 2 lines
- Body: split roughly 42/58
- Left pane: 2 short lines per operation with more whitespace
- Right pane: slower, clearer reading rhythm
- Footer: 1 line

### ASCII prototype

```text
┌ Operator Fleet ─ active ─ refresh 0.5s ───────────────────────────── 14:32 ┐
│ Active 7   Needs human 2   Running 4   Paused 1                            │
├────────────────────────────────┬────────────────────────────────────────────┤
│ Operations                     │ Brief                                      │
│                                │                                            │
│ > [!!2] checkout-redesign      │ checkout-redesign                          │
│   RUNNING · 8s                 │                                            │
│                                │ Goal                                       │
│   [!!1] memory-audit           │ Finish TUI UX, then docs                  │
│   RUNNING · 2s                 │                                            │
│                                │ Now                                        │
│   [!1] docs-cleanup            │ Implementing session drill-down           │
│   NEEDS_HUMAN · 21s            │                                            │
│                                │ Wait                                       │
│   [ ] billing-migration        │ Agent turn running                         │
│   PAUSED · 4m                  │                                            │
│                                │ Progress                                   │
│                                │ Done: fleet, operation                     │
│                                │ Doing: session                             │
│                                │ Next: forensic, docs                       │
│                                │                                            │
│                                │ Attention                                  │
│                                │ 2 blocking requests open                   │
│                                │                                            │
│                                │ Recent                                     │
│                                │ previous slice landed                      │
│                                │ session resumed                            │
│                                │ next turn started                          │
├────────────────────────────────┴────────────────────────────────────────────┤
│ Enter open  Tab next-attn  a answer  p pause  u unpause  / filter  q quit  │
└──────────────────────────────────────────────────────────────────────────────┘
```

### Strengths

- clearest baseline hierarchy
- easiest variant to document and teach
- least likely to collapse into terminal noise

### Risks

- lower throughput for large fleets
- left pane may become too sparse
- may under-emphasize urgency if attention density grows

## Candidate C: Attention-First

### Intent

This is the triage-heavy supervisory cockpit.

It optimizes for:

- routing the operator toward the next blocking item
- making attention signals first-class
- minimizing time-to-action under intervention load

It accepts:

- less neutral overview behavior
- lower prominence for operations without signals

### Layout

- Header: 1-2 lines focused on blocking/non-blocking totals
- Left pane: split into `Needs Action` and `Other Active`
- Right pane: selected attention context plus current operation summary
- Footer: attention navigation shown as the primary affordance

### ASCII prototype

```text
┌ Fleet Attention ─ blocking 2 · non-blocking 3 ────────────────────── 14:32 ┐
│ Needs Action                    │ Selected                                  │
├─────────────────────────────────┼───────────────────────────────────────────┤
│ > [!!2] checkout-redesign       │ checkout-redesign                         │
│   RUNNING · 8s                  │                                           │
│   oldest blocking:              │ What needs you                            │
│   verify transcript layout      │ 2 blocking requests                       │
│                                 │                                           │
│   [!!1] memory-audit            │ Oldest                                    │
│   RUNNING · 2s                  │ verify transcript layout                  │
│   oldest blocking: approve plan │                                           │
│                                 │ Current operation state                   │
│   [!1] docs-cleanup             │ RUNNING · codex_acp                       │
│   NEEDS_HUMAN · 21s             │                                           │
│   oldest non-blocking:          │ Current work                              │
│   clarify README scope          │ implementing session drill-down           │
│                                 │                                           │
│ Other Active                    │ Suggested next action                     │
│ ───────────────────────────     │ answer oldest blocking attention          │
│   [ ] billing-migration         │                                           │
│   PAUSED · 4m                   │ Recent                                    │
│                                 │ previous slice landed                     │
│   [ ] parser-hardening          │ session resumed                           │
│   RUNNING · 14s                 │ next turn started                         │
├─────────────────────────────────┴───────────────────────────────────────────┤
│ Tab next-blocking  a answer  Enter open  p/u pause  s interrupt  q quit    │
└──────────────────────────────────────────────────────────────────────────────┘
```

### Strengths

- strongest urgency signaling
- best for heavy human-attention workflows
- makes the `Tab` and `a` flows feel central and intentional

### Risks

- weaker as a neutral overview
- operations without attention can feel hidden
- may overfit one workload mode

## Candidate D: Supervisory Summary

### Intent

This is the summary-heavy supervisory desk.

It optimizes for:

- understanding what running operations are doing without opening them
- making operator-level load visible
- preserving overview while still showing richer summaries than the calm baseline

It accepts:

- fewer visible operations than the dense design
- a more opinionated right pane and left-row summary contract

### Layout

- Header: 2-3 lines
- Header includes global fleet counts and explicit operator workload state
- Body: split roughly 45/55
- Left pane: 3 lines per operation with a mandatory summary hint for running items
- Right pane: selected operation brief with `Now`, `Progress`, `Agent`, and `Operator` sections
- Footer: same primary action bar as other candidates

### ASCII prototype

```text
┌ Operator Fleet ─ active 7 · human 2 · running 4 ──────────────────── 14:32 ┐
│ Operator: following 1 session · answering 0 · idle for 2m                  │
├──────────────────────────────────┬───────────────────────────────────────────┤
│ Operations                       │ Supervisory Summary                      │
├──────────────────────────────────┼───────────────────────────────────────────┤
│ > [!!2] checkout-redesign        │ checkout-redesign                         │
│   RUNNING · codex_acp · 8s       │ RUNNING · codex_acp · iter 4            │
│   now: session drill-down        │                                           │
│                                  │ Goal                                      │
│   [!!1] memory-audit             │ Finish TUI UX, then docs                 │
│   RUNNING · 2 agents · 2s        │                                           │
│   now: forensic pass             │ Now                                       │
│                                  │ Implementing session drill-down          │
│   [!1] docs-cleanup              │ Wait: current agent turn running         │
│   NEEDS_HUMAN · codex_acp · 21s  │                                           │
│   waiting: answer needed         │ Progress                                  │
│                                  │ Done: fleet, operation                   │
│   [ ] billing-migration          │ Doing: session                            │
│   PAUSED · claude_acp · 4m       │ Next: forensic, docs                     │
│   paused by operator             │                                           │
│                                  │ Agents                                    │
│                                  │ 1 active agent                            │
│                                  │ codex_acp: running current turn           │
│                                  │                                           │
│                                  │ Operator                                  │
│                                  │ not blocked                               │
│                                  │ no pending manual action                  │
│                                  │                                           │
│                                  │ Recent                                    │
│                                  │ 14:31 previous slice landed               │
│                                  │ 14:31 session resumed                     │
│                                  │ 14:32 next turn started                   │
├──────────────────────────────────┴───────────────────────────────────────────┤
│ Enter open  Tab next-attn  a answer  p/u pause  s interrupt  / filter  q    │
└──────────────────────────────────────────────────────────────────────────────┘
```

### Strengths

- better answers `what is the system doing right now?`
- makes multi-agent and operator-load cues first-class without dropping the master-detail model
- gives running operations more explanatory value before drill-down

### Risks

- easy to over-expand into a second `Operation View`
- if summaries are not tightly normalized, left-pane rows can become noisy
- operator workload section can become misleading if the underlying model is weak

## Comparative summary

| Candidate | Primary strength | Primary risk | Best fit |
| --- | --- | --- | --- |
| Ultra-Dense | scan speed and throughput | overload / cramped feel | power-user, large active fleets |
| Calm Workbench | readability and hierarchy | lower density | default general-purpose fleet surface |
| Attention-First | urgency and fast intervention | weaker neutral overview | attention-heavy supervision workflows |
| Supervisory Summary | richer live understanding of running work | summary sprawl | overview with stronger running-state narration |

## Current recommendation

No winner is fixed in this document.

If a single default candidate must be chosen next, the strongest starting point is:

- `Calm Workbench` as the base layout
- with two borrowings:
  - a third short hint line in the left pane from `Ultra-Dense`
  - explicit `Tab next-attn` prominence from `Attention-First`
  - a normalized `now:` summary hint and optional operator-load line from `Supervisory Summary`

That hybrid remains easier to read than the dense design while preserving stronger triage affordance
than the calm baseline alone.
