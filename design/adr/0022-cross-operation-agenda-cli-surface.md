# ADR 0022: Expose A Cross-Operation Agenda CLI Surface

## Status

Accepted

## Context

The current repo already exposes strong per-operation surfaces:

- `run`, `watch`, `inspect`, and `trace` for live and forensic control
- `tasks`, `memory`, and `artifacts` for durable operation truth
- attention, policy, and project-profile commands for explicit human control

That means the product gap has shifted.

The remaining missing workflow is not inside one operation.
It is at the operator level:

- which operation needs human attention now
- which one is paused or degraded
- which one is healthy and still active
- and which recent operations are only informational

Without a first-class cross-operation view, the CLI still feels like a bag of useful commands
instead of a true operator console.

## Decision

`operator` will expose a first-class cross-operation `agenda` command backed by a reusable
projection over persisted runtime truth.

The projection will classify operations into a small set of operator-facing buckets:

- `needs_attention`
- `active`
- `recent`

This surface will be built from existing persisted truth:

- `OperationState`
- `OperationSummary`
- `OperationBrief`
- open attention requests
- scheduler state
- and runtime-alert heuristics already used elsewhere

It will not introduce:

- a new store
- hidden dashboard-only state
- or a separate source of truth from persisted operation/runtime data

## Alternatives Considered

- Option A: keep using `list` plus manual drill-down
- Option B: build a TUI before defining a smaller operator-level view
- Option C: add a dedicated agenda projection and CLI surface now

Option A was rejected because it leaves the user without an actionable "what needs me now?"
surface.

Option B was rejected because it overbuilds the delivery layer before the read model is proven.

Option C was accepted because it closes a real workflow gap with a small, reusable slice.

## Consequences

- The CLI gains an operator-level cockpit entrypoint grounded in persisted truth.
- Future TUI or dashboard work can reuse the same agenda projection rather than inventing a new
  overview model.
- `list` can remain a lightweight raw inventory view while `agenda` becomes the actionable
  supervisory surface.
