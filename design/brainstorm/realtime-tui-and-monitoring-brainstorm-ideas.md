# Realtime TUI And Monitoring Brainstorm Ideas

## Status

Brainstorm only. Not architecture truth.

## Context

The vision already treats CLI transparency as a product requirement. The next step is not just better logs, but a real-time monitoring and intervention surface comparable in feel to Claude Code or Codex:

- always-on visibility,
- live status,
- attention cues,
- and direct operator interaction.

## Core Thesis

The TUI should be a thin live view over the control plane, not a second implementation of runtime logic.

If the runtime exposes the right event stream and control commands, the TUI can stay small, ergonomic, and truthful.

## Main Design Axes

### 1. Product surface vs forensic surface

Keep a sharp split:

- TUI: live operational view for humans
- trace/report/codex-log: forensic detail

The TUI should summarize and highlight, not dump every raw event.

### 2. Attention-first design

The dashboard should optimize for:

- what is running,
- what is blocked,
- what needs human attention now,
- what just changed,
- and how to intervene quickly.

### 3. One operation vs fleet view

The operator needs both:

- a fleet overview of all runs,
- and a focused per-operation view.

### 4. Read path vs write path

The TUI must support both:

- passive monitoring,
- and active control actions.

Those actions should use the same control bus as non-TUI callers.

## Likely Architecture Direction

### Phaseable shape

Start with one `rich` TUI app with three panes or tabs:

1. fleet view
   - operations
   - status
   - active agents
   - attention badges
2. operation detail
   - objective
   - current focus
   - active sessions
   - recent decisions
   - pending user messages
3. intervention panel
   - send operator message
   - pause/resume
   - stop agent
   - stop all

### Live data model

The TUI should subscribe to a compact live stream of:

- operation state snapshots,
- important trace records,
- attention alerts,
- active session status,
- and control acknowledgements.

### Ergonomic default cues

Important visual buckets:

- `running`
- `paused`
- `waiting on agent`
- `blocked on human`
- `policy decision needed`
- `recovery drift`

Use simple status language instead of transport-heavy runtime jargon.

## Risks And Tradeoffs

### Positive

- turns transparency into a real product surface,
- makes long-lived runs usable without constant `inspect` polling,
- and gives a natural home for human intervention.

### Risks

- a flashy TUI can mask unresolved runtime truth problems,
- too much transcript detail will drown the signal,
- and duplicating CLI inspection logic inside TUI would create drift.

### Design warning

Do not treat the TUI as the canonical truth surface.
The TUI should render the same underlying state that `inspect`, `trace`, and stored artifacts already reflect.

## Recommended ADR Topics

1. `live runtime stream for operator monitoring surfaces`
2. `tui control actions and acknowledgement model`
3. `attention alert taxonomy and escalation states`
4. `operation fleet dashboard semantics`
