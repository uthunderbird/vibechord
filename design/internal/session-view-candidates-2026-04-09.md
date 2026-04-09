# Session View Candidates

## Status

Internal design artifact.

This document records concrete candidate layouts for the TUI `Session View` so the repository has
an explicit comparison set before selecting or refining one design.

It is not itself the canonical vision source. The canonical TUI hierarchy remains defined in
[TUI-UX-VISION.md](/Users/thunderbird/Projects/operator/design/TUI-UX-VISION.md).

## Shared Session View requirements

Every viable `Session View` candidate should satisfy the same base contract:

- answer `what is this session doing right now?`
- answer `what changed recently?`
- answer `is intervention needed?`
- preserve continuity with `Operation View`
- keep raw transcript available without making it the default body

Minimum common elements:

- breadcrumb and compact header
- left pane anchored on session events or session navigation context
- right pane explaining the selected session state and/or selected event
- compact footer with transcript and intervention affordances

Data that belongs in `Session View`:

- recent session events
- current session state
- current agent activity or waiting reason
- session-scoped attention
- selected-event detail
- explicit transcript escalation path

Data that should not dominate `Session View`:

- full raw transcript by default
- operation-level summary prose
- complete forensic/debug payloads
- giant cumulative logs with no session-state framing

## Candidate A: Timeline First

### Intent

This is the simplest continuation of the current vision.

It optimizes for:

- chronology
- event-by-event inspection
- low conceptual overhead

It accepts:

- weaker current-state framing
- more burden on the operator to reconstruct what the session is doing now

### Layout

- Header: 1-2 lines
- Left pane: recent session events in reverse chronological order
- Right pane: selected event detail
- Footer: `r` for transcript, `Esc` back, `q` quit

### ASCII prototype

```text
┌ fleet > op-codex-1 > task-3a7f2b1c ─ RUNNING ─────────────────────── 14:53 ┐
│ Session: codex_acp · sess-8f2a                                             │
├──────────────────────────────────┬───────────────────────────────────────────┤
│ Recent Events                    │ Event Detail                              │
│                                  │                                           │
│ > 14:32 ▸ agent output           │ [14:32] agent output (partial)           │
│   14:31 ● brain decision         │ codex-acp · sess-8f2a                    │
│   14:28 ▸ agent output           │                                           │
│   14:20 ⚠ attention opened       │ "Implemented token refresh handler.       │
│   14:15 → session started        │  Moving to validation."                   │
│   14:00 ◆ task assigned          │                                           │
│                                  │ Changes:                                  │
│                                  │ auth/session.py +120 -8                  │
│                                  │ tests/test_auth.py +45                   │
│                                  │                                           │
│                                  │ Artifacts: none yet                      │
├──────────────────────────────────┴───────────────────────────────────────────┤
│ ↑/↓ move  Enter expand  r transcript  Esc back  s interrupt  q quit         │
└───────────────────────────────────────────────────────────────────────────────┘
```

### Strengths

- simplest mental model
- strongest chronological clarity
- easiest to implement and document

### Risks

- too close to a generic event log browser
- weak answer to `what is the session doing right now?`
- transcript may feel like the real destination rather than Level 2 itself

## Candidate B: Split Hybrid

### Intent

This is the balanced hybrid.

It optimizes for:

- combining current session state with chronology
- helping the operator decide whether to keep watching, interrupt, or open transcript
- making `Session View` feel like a live supervisory surface

It accepts:

- more structure in the right pane
- tighter space budget for selected-event detail

### Layout

- Header: 1-2 lines
- Left pane: recent timeline
- Right pane top: compact session brief
- Right pane bottom: selected event detail
- Footer: transcript and interrupt affordances remain visible

### ASCII prototype

```text
┌ fleet > op-codex-1 > task-3a7f2b1c ─ RUNNING ─────────────────────── 14:53 ┐
│ Session: codex_acp · sess-8f2a                                             │
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
│                                  │ [14:32] agent output (partial)           │
│                                  │                                           │
│                                  │ "Implemented token refresh handler.       │
│                                  │  Moving to validation."                   │
│                                  │                                           │
│                                  │ Changes: auth/session.py, tests/auth.py   │
├──────────────────────────────────┴───────────────────────────────────────────┤
│ ↑/↓ move  Enter expand  r transcript  s interrupt  Esc back  q quit         │
└───────────────────────────────────────────────────────────────────────────────┘
```

### Strengths

- strongest balance of current-state clarity and recent history
- clearly answers whether the session is healthy or actionable
- best differentiation from both `Operation View` and `Raw Transcript`

### Risks

- easiest to overgrow if the session brief becomes too verbose
- selected event detail can become cramped
- requires stricter section discipline

## Candidate C: Current-State First

### Intent

This is the strongest “live process” interpretation.

It optimizes for:

- instantly understanding current session health and current work
- making intervention decisions quickly
- treating events as supporting context rather than the primary frame

It accepts:

- less emphasis on chronology
- weaker event-browser feel

### Layout

- Header: 2 lines
- Left pane: compact session state and current activity list
- Right pane: current session detail with small recent-events subsection
- transcript access remains explicit

### ASCII prototype

```text
┌ fleet > op-codex-1 > task-3a7f2b1c ─ RUNNING ─────────────────────── 14:53 ┐
│ Session: codex_acp · sess-8f2a · iter 14                                    │
├──────────────────────────────────┬───────────────────────────────────────────┤
│ Session State                    │ Current Session                           │
│                                  │                                           │
│ Status: RUNNING                  │ Now: validating token refresh flow        │
│ Wait: none                       │                                           │
│ Attention: 1 policy_gap          │ Latest output                             │
│                                  │ Implemented token refresh handler.        │
│ Recent                           │ Moving to validation.                     │
│ > 14:32 ▸ agent output           │                                           │
│   14:31 ● brain decision         │ Attention                                 │
│   14:20 ⚠ attention opened       │ policy_gap: commit directly to main?      │
│   14:15 → session started        │                                           │
│                                  │ Event focus                               │
│                                  │ [14:32] agent output (partial)            │
│                                  │ auth/session.py +120 -8                  │
├──────────────────────────────────┴───────────────────────────────────────────┤
│ r transcript  s interrupt  ↑/↓ move recent  Esc back  q quit                │
└───────────────────────────────────────────────────────────────────────────────┘
```

### Strengths

- best immediate answer to `what is happening now?`
- strongest intervention-readiness
- feels the most “live”

### Risks

- event chronology becomes secondary
- can feel too close to a compact dashboard instead of a session view
- easier to blur with the operation-level brief above it

## Candidate D: Transcript-Proximate

### Intent

This variant treats `Session View` as the final step before raw transcript.

It optimizes for:

- rapid escalation into full transcript
- reading agent output and event context together
- minimizing friction for debugging and verification

It accepts:

- weaker separation from `Raw Transcript`
- more forensic bias than supervisory bias

### Layout

- Header: 1 line
- Left pane: recent events
- Right pane: transcript preview around the selected event
- footer emphasizes `r` and event movement

### ASCII prototype

```text
┌ fleet > op-codex-1 > task-3a7f2b1c ─ sess-8f2a ───────────────────── 14:53 ┐
├──────────────────────────────────┬───────────────────────────────────────────┤
│ Events                           │ Transcript Preview                        │
│                                  │                                           │
│ > 14:32 ▸ agent output           │ ...                                       │
│   14:31 ● brain decision         │ assistant: implementing refresh handler   │
│   14:28 ▸ agent output           │ assistant: wiring validation path         │
│   14:20 ⚠ attention opened       │ assistant: moving to validation           │
│   14:15 → session started        │ ...                                       │
│                                  │                                           │
│                                  │ Focused event: [14:32] agent output       │
│                                  │ auth/session.py +120 -8                  │
├──────────────────────────────────┴───────────────────────────────────────────┤
│ ↑/↓ move  r full transcript  Esc back  q quit                               │
└───────────────────────────────────────────────────────────────────────────────┘
```

### Strengths

- strongest bridge into raw transcript
- useful for debugging-heavy workflows
- good when transcript inspection is the main reason to enter Level 2

### Risks

- too close to Level 3
- weak current-state framing
- loses much of the value of a distinct `Session View`

## Comparative summary

| Candidate | Primary strength | Primary risk | Best fit |
| --- | --- | --- | --- |
| Timeline First | chronology clarity | generic log-browser feel | simplest baseline |
| Split Hybrid | balance of live state and history | right-pane crowding | strongest general-purpose default |
| Current-State First | immediate live understanding | weaker chronology | intervention-heavy supervision |
| Transcript-Proximate | fastest forensic escalation | weak Level 2 identity | debugging-heavy workflows |

## Current recommendation

No winner is fixed in this document.

If a single default candidate must be chosen next, the strongest starting point is:

- `Split Hybrid`

With two guardrails:

- the session brief must stay compact and session-scoped
- the selected event detail must remain substantive enough that Level 2 does not collapse into a
  shallow summary layer

This route best differentiates `Session View` from both `Operation View` above it and `Raw
Transcript` below it.
