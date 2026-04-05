# ADR 0023: Stop The Active Attached Agent Turn

## Status

Accepted

## Context

The preferred runtime surface is an attached long-lived `operator run`.

Recent accepted slices already made that runtime more observable and controllable:

- ADR 0013 introduced a durable command inbox
- ADR 0014 separated deterministic command effects from brain-mediated replanning
- ADR 0015 introduced honest pause semantics for attached runs
- ADR 0020 added a live `watch` surface
- ADR 0022 adds a cross-operation `agenda`

That leaves one important control-plane gap on the preferred path.

Today the user can:

- see that an attached agent turn is still running
- request a scheduler pause after the current turn yields
- or cancel the whole operation

But the user cannot issue a first-class command that means:

- stop this active attached agent turn
- without cancelling the whole operation
- and then let the operator replan from the yielded result

Without that seam, long-running or obviously misguided attached turns are still operationally
awkward.

## Decision

`operator` will introduce an explicit `stop_agent_turn` command for the currently active
attached agent turn.

The command semantics are:

- distinct from `pause_operator`
- distinct from cancelling the whole operation
- targeted at the active session for the attached turn
- deterministic in transport effect
- and followed by operator replanning rather than blind continuation

The accepted first slice is intentionally narrow:

- only the active attached turn is in scope
- the command targets the active session
- the runtime asks the adapter to cancel that turn
- scheduler state becomes `draining` while the cancellation yields a terminal result
- and once the turn yields, the scheduler returns to `active` and the operator replans

## Alternatives Considered

- Option A: keep only `pause` plus whole-operation `cancel`
- Option B: overload `pause` to interrupt the active turn
- Option C: introduce a distinct `stop_agent_turn` command

Option A was rejected because it leaves the preferred attached runtime without an honest
mid-flight escape hatch.

Option B was rejected because it blurs scheduler pause semantics with transport interruption.

Option C was accepted because it preserves the pause/stop distinction while closing the most
important remaining live-control gap.

## Consequences

- Attached runs gain a real control primitive for stopping bad or stale active turns.
- `watch`, `inspect`, `report`, and `agenda` can surface `draining` as truthful runtime state.
- A stopped attached turn now becomes an explicit replanning seam instead of silently collapsing
  into success or whole-operation cancellation.
- This ADR still does not define richer stop semantics for background runs, branch-aware
  schedulers, or multi-turn partial interruption.
