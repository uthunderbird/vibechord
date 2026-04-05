# ADR 0007: Event Wakeups, Preemption, And Wait Semantics

## Status

Accepted

## Context

ADR 0005 established that long-lived work should move toward:

- multiple active sessions,
- event-driven wakeups,
- and `wait_for_agent` treated as an exceptional, interruptible focus choice.

That direction is not implementable without a narrower contract for:

- what kinds of events exist,
- which events wake the operator,
- how replay and duplicate delivery should be interpreted,
- and what `wait_for_agent` actually means.

Without this, the system risks two failure modes:

- pseudo-nonblocking behavior that is race-prone and nondeterministic,
- or hidden reintroduction of global blocking under a softer name.

This ADR defines the minimum semantic contract for event-driven wakeups and for `wait_for_agent` as a dependency-aware, preemptible operator action.

## Decision

The operator will treat events as wakeup inputs for scheduling, not only as trace output.

`wait_for_agent` will mean "establish a temporary blocking focus on a specific dependency or session, while still allowing preemption by material events."

### 1. Event classes

The event model must distinguish between:

- `trace-only events`
  Useful for observability but not intended to wake scheduling logic.
- `wakeup events`
  Events that require operator reevaluation.

The minimum wakeup event classes are:

- agent completion,
- agent failure,
- timeout or deadline expiry,
- explicit operator cancellation,
- and significant externalized progress when configured as wake-relevant.

Not every progress event should wake the operator by default.

### 2. Delivery assumptions

The runtime must be designed so that wakeup processing is safe under:

- replay,
- duplicate delivery,
- and restart recovery.

This ADR does not require exactly-once delivery.

It does require that the operator treat wakeup consumption as idempotent enough that:

- replaying a completion event does not create a second completion,
- duplicate failure or timeout events do not corrupt state,
- and restart recovery can safely resume from persisted event history.

### 3. Ordering rule

The system should not assume a globally perfect event order across all agents.

Instead, the minimum safe assumption is:

- per-source ordering should be preserved when available,
- cross-source events may be observed in near-time order but must still be reconciled against current persisted state,
- and operator decisions must consult current state, not trust event arrival order alone as authority.

In other words, events wake the operator, but persisted state decides what is still true.

### 4. Wakeup handling rule

When a wakeup event arrives, the operator must:

1. reconcile the event against persisted state,
2. determine whether it materially changes runnable work or blocking conditions,
3. reevaluate current focus if needed,
4. and either continue current focus, switch focus, or clear the prior wait.

The operator should not blindly "resume the last plan" just because an event arrived.

### 5. Meaning of `wait_for_agent`

`wait_for_agent` is not a generic sleep and not a global loop stall.

It is a blocking-focus action with three required parts:

- `blocking_reason`
- `interrupt_policy`
- `resume_policy`

Minimum intended meaning:

- `blocking_reason`
  Why the operator is justified in parking on this dependency now.
- `interrupt_policy`
  Which other events are allowed to break the wait.
- `resume_policy`
  Whether the operator should automatically return to the prior focus after servicing an interrupt or instead fully reschedule.

### 6. Dependency-barrier rule

`wait_for_agent` should be used only when a real dependency barrier exists or when the operator intentionally chooses to prioritize one dependency above all other currently useful work.

Examples of legitimate waits:

- a downstream task cannot be planned meaningfully until one upstream agent finishes,
- a human-readable final artifact must be taken from one still-running session and no other runnable task is comparably valuable,
- or the operator has intentionally entered a short blocking focus with explicit interruptibility.

It should not be the default continuation strategy for normal agent execution.

### 7. Preemption rule

An active wait may be preempted by another wakeup event when that event materially affects:

- objective state,
- task priority,
- dependency structure,
- or failure handling.

After preemption, the operator must make an explicit rescheduling decision:

- return to the original wait,
- switch focus permanently,
- or clear the wait because it is no longer justified.

### 8. State authority rule

Events are triggers, not authorities.

Current persisted state remains authoritative for:

- session status,
- task status,
- blocking conditions,
- and whether a wakeup still matters.

An event that no longer matches current state should be treated as stale input, not as a command to mutate state blindly.

## Non-Goals

This ADR does not define:

- exact queue technology,
- exact persistence schema for events,
- exact clock or timeout implementation,
- or exact policy thresholds for "significant progress."

Those remain implementation choices as long as they preserve the semantic rules above.

## Alternatives Considered

### Option A: Treat events as logging only

Rejected because:

- it prevents genuine event-driven orchestration,
- leaves `wait_for_agent` as effectively synchronous blocking,
- and conflicts with the long-lived multi-session direction.

### Option B: Treat every event as an immediate rescheduling trigger

Rejected because:

- it would create excessive churn and focus thrash,
- gives too much power to low-value progress noise,
- and weakens intentional blocking behavior.

### Option C: Distinguish trace events from wakeup events and make waits explicitly preemptible

Accepted because:

- it is the smallest event model that supports long-lived orchestration,
- keeps waits exceptional,
- and makes preemption semantics explicit rather than accidental.

## Consequences

### Positive

- `wait_for_agent` gets a precise meaning.
- Event-driven scheduling can be implemented without pretending event arrival order is authoritative state.
- The future runtime has a clear path to multi-session orchestration with bounded preemption semantics.

### Negative

- The implementation must carry more explicit scheduling state.
- Event handling can no longer be treated as a passive append-only concern once wakeups are enabled.
- Some progress events will need policy classification instead of being handled uniformly.

### Follow-Up Implications

- `design/ARCHITECTURE.md` should reference this ADR from the event and wait sections.
- Future runtime work should introduce enough state to represent:
  - wakeup-relevant events,
  - blocking reasons,
  - interrupt policy,
  - and resume policy.
- Tests for future long-lived runtime should include replay, duplicate-delivery, and preemption scenarios.
