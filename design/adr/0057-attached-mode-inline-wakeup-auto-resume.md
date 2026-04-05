# ADR 0057: Attached-mode inline wakeup auto-resume

## Status

Accepted

## Context

The operator already has file-backed background-run wakeups and a resumable reconciliation path.

That is enough to preserve truth, but it is not enough to continue an operation automatically by
itself.

In the incident that drove this ADR:

- a background Claude turn completed successfully,
- the background worker wrote a result file,
- the worker also enqueued a `background_run.completed` wakeup,
- the wakeup remained pending in `.operator/wakeups/`,
- and the aggregate operation stayed in `running` until a human or external process ran
  `operator resume`.

The runtime evidence was therefore correct, but orchestration stalled anyway.

This happened because:

- background workers only produce wakeups,
- `OperatorService` only consumes wakeups during a `run()` or `resume()` cycle,
- and the current auto-resume design in ADR 0046 depends on a separate daemon process.

That daemon-based design is acceptable for detached resumable operations, but it is too indirect for
attached mode. In attached mode, the operator process is already alive and already owns the
scheduler/event loop for the current operation.

Requiring a second daemon just to notice a wakeup for an operation that the attached loop itself
started is unnecessary and was a direct cause of the observed stall.

## Decision

Add an inline wakeup auto-resume path for attached mode and unify attached background ownership
around wakeups.

The chosen behavior is:

- when an operation is running in attached mode, the same scheduler/event loop that launched the
  operation also remains responsible for consuming wakeups for that operation;
- if the attached loop becomes blocked on a background wait or other wakeup-driven wait, it does not
  terminate immediately;
- instead, it enters an in-process wait loop that periodically:
  - polls due wakeups for the current `operation_id`,
  - polls runtime evidence needed to detect terminal background runs,
  - and runs one bounded reconciliation cycle when new wakeup evidence is available;
- attached background turns now enqueue normal wakeups instead of using a separate `event_only`
  delivery path;
- `WAIT_FOR_AGENT` becomes valid in attached mode when background wakeups are enabled and the brain
  provides a real blocking focus;
- attached waiting remains interruptible:
  - the scheduler continues draining operator commands,
  - reacts to material wakeups,
  - and does not treat one waiting agent as exclusive ownership of the whole run;
- wakeup consumption stays operation-scoped and single-writer:
  - the same attached loop that owns the operation state applies the wakeup,
  - updates canonical session/execution truth,
  - and decides the next action.

This is not a new daemon.

It is an attached-mode scheduler responsibility inside the existing process.

The daemon from ADR 0046 remains valid for detached resumable operations and timed wakeups where no
attached owner process exists.

## Alternatives Considered

- Keep daemon-only auto-resume for all modes
- Replace wakeups with direct background-worker callbacks into `OperatorService`
- Introduce a generic global resident reconciler inside every `operator run`
- Auto-resume all resumable operations from any attached process, not just the one it owns

## Consequences

- Positive consequence: attached operations no longer need a separate daemon or manual `resume` to
  continue after a background turn completes.
- Positive consequence: wakeup-to-reconcile latency becomes bounded by the attached loop tick
  interval rather than by human intervention.
- Positive consequence: lifecycle ownership stays coherent because the same attached loop remains the
  single writer of canonical operation truth.
- Positive consequence: attached and resumable background paths now share the same wakeup delivery
  primitive even though they still differ in who consumes those wakeups.
- Positive consequence: existing file-backed wakeups remain the runtime-evidence boundary; this ADR
  changes consumption orchestration, not persistence shape.
- Negative consequence: attached mode becomes a longer-lived scheduler process that may sit idle in a
  wait loop between wakeups.
- Negative consequence: mode semantics diverge more clearly:
  - attached mode gets inline auto-resume,
  - detached resumable mode still depends on daemon or manual resume.
- Follow-up implication: ADR 0047 is superseded on the wakeup-delivery point; attached ownership is
  retained, but no longer via `event_only` delivery.
- Follow-up implication: ADR 0046 should be read as the detached/resumable continuation mechanism,
  not as the preferred path for operations already owned by a live attached loop.
