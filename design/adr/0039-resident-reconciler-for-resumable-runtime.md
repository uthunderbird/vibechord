# ADR 0039: Resident Reconciler For Resumable Runtime

## Status

Proposed

## Context

`operator` already has:

- attached mode as the preferred runtime surface,
- resumable mode as a persisted recovery and control substrate,
- file-backed background runs,
- and a wakeup inbox for background completion events.

In the current resumable runtime, a background worker can finish successfully and emit a durable
wakeup event, but wakeup reconciliation only happens when the scheduler is re-entered through
`run`, `resume`, or `tick`.

This creates a systematic product failure:

- the background turn finishes,
- the wakeup is persisted,
- but no resident control-plane actor consumes it,
- so the user must manually run `resume`.

This is not primarily a `session_id` problem. The first background turn already carries a
`session_id`, and the wakeup path already persists it. The deeper issue is the absence of a
resident wakeup consumer for resumable operations.

The project already decided in
[ADR 0008](/Users/thunderbird/Projects/operator/design/adr/0008-attached-run-as-primary-runtime-mode.md)
that attached mode is the preferred runtime story and resumable mode is substrate, not the main
user mental model. Any fix must preserve that direction.

The project also already decided in
[ADR 0013](/Users/thunderbird/Projects/operator/design/adr/0013-operation-command-inbox-and-command-envelope.md)
to prefer file-backed transparency over hidden daemon-owned truth.

## Decision

`operator` will gain a resident reconciler for resumable operations.

That reconciler will:

- consume persisted wakeups,
- re-enter the scheduler when resumable operations need advancement,
- write all state changes back to the existing persisted control plane,
- and remain transparent and inspectable rather than introducing hidden daemon-owned truth.

Implementation will proceed in two layers:

1. a first public `drive` / `run --until-idle` slice that keeps one explicit long-lived
   reconciler loop alive over persisted truth,
2. a hardened resident service form of that reconciler with explicit ownership, locking, restart,
   and observability semantics.

Attached mode remains the preferred execution surface.
Resumable mode becomes a genuinely event-driven substrate.

## Alternatives Considered

### Option A: Keep manual `resume` as the normal resumable contract

Rejected.

This preserves the current user pain and leaves wakeups only half-realized operationally.

### Option B: Improve summaries and hints only

Rejected.

This may reduce confusion but does not solve the missing consumer.

### Option C: Add only a foreground `drive` loop and stop there

Partially accepted as the first delivery slice, rejected as the full architectural answer.

It is a good way to ship the fix incrementally, but it is not by itself the complete control-plane
shape.

### Option D: Add a resident reconciler over persisted truth

Accepted.

This fixes the root cause while preserving file-backed transparency and the attached-primary
product direction.

## Consequences

- Positive: resumable operations can advance without manual `resume` after every background turn.
- Positive: wakeups become operationally meaningful, not merely durably recorded.
- Positive: `fleet`, `dashboard`, and future TUI work can rely on a live control-plane substrate
  over the same persisted truth.
- Positive: attached mode remains primary while resumable mode becomes a stronger substrate.
- Negative: service ownership, locking, restart, and duplicate-driver semantics must now be
  explicit.
- Negative: runtime complexity increases.
- Follow-up: define reconciler lease and lock semantics.
- Follow-up: define `drive` / `until-idle` CLI surfaces.
- Follow-up: harden outcome and runtime-alert projections once the resident consumption path exists.
