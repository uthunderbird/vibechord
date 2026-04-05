# Realtime TUI And Control Brainstorm Ideas

## Core Thesis

If `operator` becomes a true harness, the default product surface should look and feel like a
live control console rather than a pile of forensic CLI commands.

The user should be able to:

- see what is running right now,
- see where attention is needed,
- inspect the important parts of agent conversations,
- and intervene without leaving the operator surface.

## Operator-User Interaction Model

Two primary modes seem necessary.

### 1. Fleet overview

Focus:

- all running operations
- current status
- active agents
- attention hotspots
- stale or degraded runs

This is the "what needs me now?" view.

### 2. Operation detail

Focus:

- one objective
- current task frontier
- active agent sessions
- condensed live transcript
- operator reasoning briefs
- command input for intervention

This is the "workbench" view.

## Panel Ideas

### Overview panel set

- operations list
  - status
  - objective
  - current focus
  - latest outcome
  - alert badge
- attention queue
  - waiting for user
  - degraded
  - stale wakeup
  - approval/escalation needed
- agent activity strip
  - which agents are busy
  - which are blocked
  - which are idle

### Operation detail panel set

- left: objective / tasks / branches
- center: live timeline
  - operator decisions
  - important agent commentary
  - final outputs
  - state changes
- right: sessions / artifacts / attention / controls
- bottom: command line
  - pause
  - resume
  - stop agent
  - stop all
  - message operator
  - message selected agent

The center timeline should prefer condensed operator-facing events, not raw JSON and not full
vendor transcripts by default.

## Underlying Event And State Model Needed

The TUI should not read raw runtime state directly.
It needs a projected read model.

Likely components:

- canonical operation state
- append-only event stream
- attention projector
- live session summaries
- command result stream

The read model probably needs stable concepts like:

- `AttentionItem`
- `LiveOperationSnapshot`
- `LiveSessionSnapshot`
- `UserCommandReceipt`
- `RenderableTimelineEvent`

## Usability Risks

### 1. Mixing forensic and live surfaces

The same surface should not try to be:

- raw trace viewer
- live dashboard
- and full transcript browser

Those should be related but distinct layers.

### 2. Alert fatigue

If everything becomes an alert, nothing is.
The TUI needs strong attention classification:

- informational
- actionable soon
- human required
- degraded / likely broken

### 3. Overly modal controls

If stopping one agent, pausing one branch, and stopping the whole operator all look too similar,
the UX becomes unsafe.

### 4. Hiding determinism behind pretty rendering

Every visible control should map cleanly to a persisted command and a visible resulting state
transition.

## Near-Term ADR Candidates

1. Live TUI read model and rendering boundaries
2. Attention-item taxonomy and priority rules
3. Human command palette semantics and receipts
4. Operation overview vs operation-detail panel model
5. Condensed live transcript projection vs forensic transcript drill-down
