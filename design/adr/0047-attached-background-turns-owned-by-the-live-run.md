# ADR 0047: Attached Background Turns Owned By The Live Run

## Status

Superseded by ADR 0057

## Context

`operator` already had two real runtime stories:

- attached mode as the preferred user-facing execution surface
- resumable mode with background workers, wakeups, `resume`, and `daemon`

But in practice, long-running work that used background turns behaved like resumable mode even
when users expected a stable long-lived attached run:

- the foreground process launched a background turn
- the worker finished and persisted terminal truth
- but the operation only advanced after `resume` or `daemon`

That contradicted the attached-primary product story and made supposedly live runs feel like
manual-resume workflows.

The old attached-mode text in ADR 0008 and `design/ARCHITECTURE.md` also assumed that attached mode
meant no background worker for the active turn. That constraint is no longer the best fit for the
product goal.

## Decision

Attached mode may use background workers for active agent turns, but the attached foreground
process remains the owner of reconciliation.

The runtime is now split by background ownership semantics:

- attached live mode:
  - may launch a background turn
  - waits on it in-process
  - collects and reconciles its terminal result itself
  - continues scheduling in the same `run()` call
- resumable wakeup mode:
  - launches a background turn
  - persists wakeup truth
  - exits
  - later reconciles through `resume` or `daemon`

To prevent ownership races, attached-owned background turns emit durable events but do not enqueue
wakeups in the inbox.

`WAIT_FOR_AGENT` remains invalid in attached mode.

This wakeup-delivery choice has since been superseded by
[ADR 0057](/Users/thunderbird/Projects/operator/design/adr/0057-attached-mode-inline-wakeup-auto-resume.md),
which keeps attached reconciliation ownership but unifies attached background turns around normal
wakeup enqueue plus in-process attached consumption.

## Alternatives Considered

- Keep attached mode strictly inline and solve the problem only with `drive`/daemon
- Continue using background turns in attached mode but still require wakeup-driven resume
- Replace resumable mode with a single hidden resident process

## Consequences

- Positive: attached `run` can now stay live across long background turns without manual `resume`
- Positive: the preferred product surface matches real runtime behavior better
- Positive: resumable mode keeps the existing wakeup/daemon story without becoming the default
- Negative: attached and resumable background paths now have different ownership semantics
- Negative: docs and tests must distinguish live-owned reconciliation from wakeup-owned
  reconciliation explicitly
- Follow-up: if cross-process attached-driver races become a practical problem, add explicit
  driver lease semantics as a separate decision rather than folding them into this slice
