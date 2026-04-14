# ADR 0172: Derived Live Status Over Stored Session Summary

## Decision Status

Proposed

## Implementation Status

Partial

Implementation grounding on 2026-04-14:

- `implemented`: `OperationStatusQueryService` already distinguishes durable truth from live
  runtime alerting by reading background inspection and pending wakeups during status queries
- `implemented`: CLI/TUI status surfaces still read `SessionRecord.waiting_reason` as if it were
  current live truth
- `implemented`: `overlay_live_background_progress()` currently mutates a copied `OperationState`
  by writing `run.progress.message` back into `session.waiting_reason`
- `partial`: runtime alerting exists, but live status still mixes reconciled session state with
  transient runtime summary text

## Context

The operator repeatedly shows stale or contradictory short status snapshots such as:

- `session_status: running`
- `waiting_reason: "Agent session completed."`

even while `inspect`, timeline, and background inspection already show that the operation has
either advanced to a new iteration or is carrying unreconciled wakeups that require a resume.

The repository now has enough concrete evidence that this is not a one-off rendering bug. It is
an architectural problem: multiple overlapping status surfaces are being treated as if they were
one source of truth.

Current repository truth mixes at least three distinct layers:

1. durable reconciled operation truth from the checkpoint/store
2. live runtime inspection truth from background run files and wakeup inboxes
3. human-facing session summary fields such as `SessionRecord.waiting_reason`

The main problematic write path is `overlay_live_background_progress()`, which takes runtime
inspection output and writes `run.progress.message` into a copied `SessionRecord.waiting_reason`.
That means a read-time status query mutates a read model into a hybrid object that looks like
canonical session truth even though it is only a transient overlay.

This creates a false-state surface:

- durable session state says one thing,
- runtime inspection says another,
- and the short status view renders the mixed copy as if it were current truth.

## Decision

Treat live status as a derived query product, not a stored or overlaid session-summary field.

Specifically:

- `SessionRecord.waiting_reason` remains reconciled session truth only
- read-time background inspection must not overwrite `SessionRecord.waiting_reason`
- live runtime conditions such as pending wakeups, terminal-but-unreconciled background runs, or
  in-flight background progress must be rendered from dedicated derived fields
- status surfaces must distinguish:
  - reconciled truth
  - live runtime overlay
  rather than collapsing them into one mutable session summary field

The rule is:

> status must be derived, not stored

and:

> runtime overlays may annotate a status response, but must not masquerade as canonical
> `SessionRecord` truth

## Consequences

### Positive

- `status` becomes less misleading during reconciliation lag
- pending wakeups and background-run inspection take precedence over stale session summary text
- the system moves toward one canonical truth path for short status surfaces
- future status bugs become easier to localize because the query layer no longer rewrites session
  summary fields on read

### Negative

- some live status outputs may become less chatty until dedicated derived live-progress fields are
  added everywhere
- callers that implicitly relied on overlaid `waiting_reason` text may need updates

### Neutral / Follow-on

- this ADR does not eliminate `waiting_reason` entirely
- this ADR does not yet remove all summary-like fields from operation/session models
- a later tranche may introduce explicit split payload sections such as:
  - `reconciled_status`
  - `live_runtime_status`

## Alternatives Considered

### 1. Keep storing and overlaying summary strings, but patch contradictory cases one by one

Rejected.

That leaves the root design intact and guarantees repeated stale-status regressions.

### 2. Hide `waiting_reason` only when `runtime_alert` is present

Rejected as the full solution, accepted only as a possible migration aid.

This is a presentation patch, not the architectural correction. It may still be useful as a
bounded implementation slice while removing read-time mutation of session truth.

### 3. Make runtime inspection the only source of status truth

Rejected for now.

Runtime inspection is not durable truth and should not replace canonical reconciled operation
state. The right model is explicit separation, not inversion of authority.

## Implementation Notes

The bounded implementation tranche for this ADR is:

1. stop `overlay_live_background_progress()` from copying runtime progress text into
   `SessionRecord.waiting_reason`
2. prefer `runtime_alert` over stale session wait text in status snapshots and status summaries
3. add regression coverage for unreconciled-background status so the short status surface does not
   report stale session waiting text as current truth

Longer-term follow-on work may:

- add explicit derived live-progress payload fields,
- split `reconciled_status` from `live_status` in query DTOs,
- and reduce the number of summary-like strings stored on the operation/session models.
