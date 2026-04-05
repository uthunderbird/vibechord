# ADR 0026: Add A Live One-Operation Dashboard CLI Surface

## Status

Accepted

## Context

The current repo already exposes the key persisted control-plane truths needed for a real
operator product:

- `watch` for concise live event and attached-state follow
- `agenda` for cross-operation supervisory triage
- `context` for effective control-plane context
- `tasks`, `memory`, and `artifacts` for durable work-state truth
- and explicit live controls such as pause, unpause, stop-turn, attention answer, and policy
  promotion

Those surfaces are individually useful, but the product still feels fragmented at the exact point
where the vision expects a live harness workbench.

For one active operation, the user still needs to hop across several commands to answer basic
questions such as:

- what is the operator doing right now
- which task and session are active
- whether attention is open
- what recent meaningful events happened
- and which control actions are most relevant now

The vision and architecture already bias toward a future CLI/TUI dashboard, but they also require
that any such surface remain a thin projection over persisted truth rather than a second runtime.

## Decision

`operator` will add a first-class one-operation `dashboard` CLI command.

The command is a live workbench surface built only from existing persisted truth:

- `OperationState`
- persisted `RunEvent` stream
- persisted command history
- trace briefs
- and, when applicable, condensed Codex transcript events

The initial scope is intentionally narrow:

- one operation at a time
- live refresh by polling persisted truth
- rich human-readable rendering plus one-shot JSON snapshot output
- and control hints that point at existing command surfaces rather than embedding a new command
  palette

The dashboard should surface at least:

- control context
- runtime state and active focus
- open attention
- current tasks
- current sessions
- recent meaningful events
- recent commands and receipts
- and concise next-step control hints

## Alternatives Considered

- Option A: build a cross-operation dashboard/TUI first
- Option B: keep adding narrower inspection commands before a dashboard
- Option C: add a one-operation dashboard now

Option A was rejected because `agenda` already covers the most important fleet-overview question,
while the per-operation workbench remains the sharper missing product seam.

Option B was rejected because it would continue the current fragmented UX and delay the moment
when the product feels like a live harness rather than a bag of commands.

Option C was accepted because it is the smallest feature-sized slice that materially changes the
user experience while staying honest to the persisted control plane.

## Consequences

- The CLI gains a real one-operation workbench without introducing new hidden runtime state.
- Future TUI work can reuse the same projections and rendering boundaries instead of inventing a
  separate dashboard-only model.
- Command history becomes more visible in normal operation workflows instead of remaining mostly
  buried in `trace`.
- This ADR does not define multi-operation navigation, interactive control palettes, or richer
  transcript browsing; those remain follow-on slices.
