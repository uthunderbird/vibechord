# Realtime TUI And Human Control Brainstorm Ideas

## Purpose

This note is a brainstorming artifact, not a final architecture decision.

The target theme is a transparent, ergonomic, CLI/TUI-first surface for watching and controlling live operator work.

## Core Thesis

If `operator` becomes a true harness, the main user experience cannot remain "fire a command, inspect files later".

The user needs a live operational surface that shows:

- what the operator is doing now,
- what each agent is doing now,
- where attention is required,
- and what commands the user can issue immediately.

## Interaction Model

The TUI should behave less like a chat transcript and more like an operator console.

The user should be able to:

- see all active operations,
- drill into one operation,
- inspect each agent/session,
- read condensed logs,
- issue control commands,
- and send messages to the operator.

This suggests two levels:

- global dashboard
- focused operation view

## Candidate Panels

### Global dashboard

- active operations
- status, focus, autonomy level
- active agents
- attention queue
- stale/waiting alerts

### Focused operation view

- objective and harness
- current focus / current branch
- task fronts and blockers
- active sessions / active agents
- operator decision stream
- condensed agent transcript
- pending human questions

### Command surface

Likely command palette or hotkey-driven actions:

- pause operation
- resume operation
- stop operation
- stop agent
- send message to operator
- answer question
- change involvement level
- open raw logs

## Event And State Model Needed Underneath

The UI should not infer truth by scraping logs.

It needs explicit state for:

- active operations,
- active branches,
- current focus,
- attention requests,
- operation inbox messages,
- agent run control state,
- last meaningful event per session,
- and live progress summaries.

The existing traceability layer is useful, but not enough by itself for a live console.

## UX Constraints

- default view should be brief-first, not raw-log-first
- full forensic detail should remain one drill-down away
- the dashboard should highlight anomalies, not just stream text
- pause/stop actions must visibly acknowledge what changed
- user commands must show whether they were accepted, queued, or rejected

## Risks And Tradeoffs

- A log viewer masquerading as a dashboard will still be cognitively expensive.
- If the TUI owns business logic, CLI and automation will drift.
- If alerts are too noisy, attention surfaces become useless.
- If the operator cannot explain why it is blocked or why it chose not to ask the user, trust will collapse.
- If command handling is not durable, the TUI will look live but behave unreliably under restart.

## Recommended Next ADR Topics

1. Live dashboard state model and attention surfaces
2. Operation inbox / user command protocol
3. Condensed live event model vs forensic log model
4. TUI panel structure and command palette semantics
5. Human-visible alert severity model
