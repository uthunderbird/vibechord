# ADR 0027: Add A Live Fleet Dashboard CLI Surface

## Status

Accepted

## Context

The repo already exposes:

- `agenda` as the authoritative cross-operation supervisory projection
- `dashboard` as the live one-operation workbench
- and the persisted runtime truths those surfaces reuse

That leaves a smaller but still real product gap.

`agenda` is strong for triage, but it is still a textual inventory.
Once several operations are active, paused, blocked, or recently completed, the operator still
lacks a live cross-operation workbench that:

- stays grounded in the same persisted agenda truth
- shows the current fleet mix at a glance
- and points directly toward the most relevant follow-up commands

The architecture already rejects dashboard-only state models and hidden runtime stores, so any
fleet-level workbench must remain a thin projection over the read model that `agenda` already
established.

## Decision

`operator` will expose a first-class live `fleet` CLI command.

The command is a live cross-operation dashboard built from the existing `agenda` projection and
related persisted runtime truth:

- `OperationState`
- `OperationSummary`
- `OperationBrief`
- open attention state
- scheduler state
- and runtime-alert heuristics

Initial scope:

- optional project filtering
- one-shot rich rendering or a live polling view
- JSON snapshot output for tooling
- fleet-mix summaries derived from the same agenda buckets and persisted runtime state
- and suggested next commands derived from the same agenda buckets

The command does not introduce:

- a new store
- hidden fleet-only state
- or a second classification path separate from `agenda`

## Alternatives Considered

- Option A: keep `agenda` as the only cross-operation supervisory surface
- Option B: build a fleet dashboard as a separate model from `agenda`
- Option C: add a live fleet dashboard on top of the existing agenda projection

Option A was rejected because it leaves the operator without a live cross-operation workbench even
though the read model already exists.

Option B was rejected because it would create unnecessary drift between the textual supervisory
surface and the richer dashboard surface.

Option C was accepted because it closes the workflow gap with a thin delivery slice over existing
persisted truth.

## Consequences

- The CLI gains a live operator-level workbench without changing runtime semantics.
- `agenda` remains the authoritative cross-operation read model.
- Future TUI work can reuse the same fleet payload and agenda classification instead of inventing a
  new overview state path.
- The product now has both a textual supervisory surface (`agenda`) and a richer live fleet
  surface (`fleet`) without splitting their source of truth.
