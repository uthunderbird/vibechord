# Operator Realtime TUI And Intervention Brainstorm Ideas

## Status

Brainstorm only. Not a source-of-truth architecture document.

## Core Thesis

If `operator` becomes a true harness, its default UX cannot remain "run, then inspect later."
It needs a real-time monitoring and intervention surface that feels closer to Claude Code or Codex:

- one live surface,
- continuously updated,
- easy to steer,
- and explicit about where human attention is needed.

The TUI should be a control-and-observability shell over the persisted control plane, not a separate runtime.

## Primary UX Goal

The user should be able to answer, at a glance:

- what operations are running,
- which agent is currently doing what,
- what changed recently,
- what is blocked,
- where human attention is required,
- and what intervention actions are possible right now.

## Candidate Panel Model

### Main operations list

Shows all live operations with compact state:

- objective label
- mode
- current focus
- current agent activity
- attention level
- pause/blocked/error badges
- recent activity timestamp

### Focus pane

Shows the selected operation in more detail:

- current objective
- active harness instructions
- recent operator decisions
- active tasks
- active sessions
- recent user interventions

### Agent pane

Shows live agent-facing activity:

- session name
- adapter
- last instruction sent
- progress state
- latest meaningful output
- cancellability

### Attention pane

Dedicated human-attention queue:

- user question pending
- approval/escalation needed
- runtime degraded
- blocked by policy
- stale/no-heartbeat

This should be louder than the normal activity log.

### Event / transcript pane

Condensed chronological stream:

- operator decisions
- agent starts/completions
- major progress
- user messages
- guardrail triggers

This is not the full transcript. It is the live important-events view.

## Interaction Model

The TUI should support direct control actions such as:

- pause operation
- resume operation
- stop one agent
- stop all agents for selected operation
- cancel operation
- send message to operator
- answer pending question
- inspect condensed Codex or Claude transcript

Important usability bias:

- the user should not need to drop out into many subcommands for common actions
- but all actions should still map to explicit control-plane events

## Event/State Requirements Underneath

To make the TUI honest, the runtime needs stronger live state than today:

- stable operation attention state
- explicit in-flight agent-turn summaries
- typed user interventions
- per-session live status
- last meaningful agent event
- heartbeat / stale indicators
- pending-question objects

The dashboard can only be ergonomic if the control plane already models these states explicitly.

## Ergonomic Principles

- default to one main dashboard, not many disconnected tools
- allow drill-down from operation -> task -> session -> transcript
- keep destructive actions confirmable
- keep human-attention items visually distinct from normal progress
- keep condensed views fast even when raw logs are huge

## Risks

### Risk: terminal eye-candy without control value

If the TUI is just a pretty log viewer, it will not justify itself.
It must expose decisive control actions.

### Risk: renderer becomes runtime

The TUI must stay thin over the application layer.
Otherwise tests, automation, and recovery get much harder.

### Risk: too much raw log volume

A useful TUI must prioritize summaries, recent meaningful events, and attention states.
Raw logs should remain drill-down.

## Candidate ADR Topics

1. Realtime dashboard state model and delivery boundaries
2. Human-attention queue semantics and severity model
3. Operator intervention command set inside the TUI
4. Condensed live event stream vs raw transcript boundaries
5. TUI renderer contract over the application layer

## Open Questions

- Should one TUI manage multiple operations by default, or open directly into one operation?
- How should the TUI behave when the underlying operation is resumable and currently detached?
- Should user messages be modal, queued, or inline in the event stream?
- Do we want one-pane "monitor everything" first, or one-operation "control shell" first?
