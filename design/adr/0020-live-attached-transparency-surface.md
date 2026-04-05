# ADR 0020: Live Attached Transparency Surface

## Status

Accepted

## Context

Attached `operator run` is the preferred runtime mode.

The persisted control plane is already authoritative for:

- operation state
- run events
- command records
- and trace artifacts

But live transparency was still split awkwardly:

- the attached `run` command could stream events only from the same in-process execution path
- `inspect` and `trace` were primarily after-the-fact forensic tools
- and there was no first-class way for a second process to watch one live attached operation by
  following persisted runtime truth

This left attached runs less transparent than the architecture intends, especially during active
attached waits where the user needs to see:

- that the operation is still running
- which session is active
- whether the scheduler is `active`, `pause_requested`, or `paused`
- and what the current attached wait is doing

## Decision

`operator` will expose a first-class one-operation live watch surface built on top of the
persisted run event stream and persisted operation state.

The initial product surface is:

- a CLI `watch` command for one operation

The initial data model is:

- replay condensed persisted `RunEvent` records
- follow new persisted `RunEvent` records as they arrive
- supplement quiet periods with concise operation-state snapshots derived from persisted
  `OperationState`

Important boundary:

- this is not a TUI yet
- and it is not a new canonical event schema

The persisted event stream remains the chronological spine.
Operation-state snapshots exist to surface attached-mode truths that are otherwise too quiet in
the event stream alone.

## Alternatives Considered

- Option A: keep live visibility only inside the attached `run` process
- Option B: build a TUI before defining a simpler watch surface
- Option C: redesign the whole event schema before shipping live watch

Option A was rejected because it does not provide a separate-process transparency surface.

Option B was rejected because it would overbuild the delivery layer before proving the runtime
read path.

Option C was rejected because the current event stream is already sufficient for the first honest
slice when combined with concise state snapshots.

## Consequences

- Attached runs become watchable from another process through persisted runtime truth.
- The CLI now has a clear split between:
  - `watch` for live operational visibility
  - `inspect` / `trace` / `report` for forensic detail
- Future TUI work should reuse the same event stream and state projection instead of inventing a
  separate runtime path.
- The runtime still may need additional event types later, but this slice does not require a
  broad event-schema migration.
