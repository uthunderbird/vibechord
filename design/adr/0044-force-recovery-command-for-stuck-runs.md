# ADR 0044: Force Recovery Command for Stuck Runs

## Status

Accepted

## Context

The operator already supported automatic attached-turn recovery after timeout, but there was no explicit operator-facing way to force recovery when persisted runtime truth became stale.

In practice this showed up when:

- a background run had already finished and written its result,
- the session log had clearly ended the turn,
- but the operation still appeared to be waiting on an in-flight session or background run.

In that state, `resume` could keep respecting stale runtime markers instead of canonizing the completed result and replanning from it.

## Decision

Add a dedicated `operator recover` command and matching service method.

The recovery path:

- can target a specific session or auto-select the most plausible stuck session,
- can force reconciliation of a completed background run even if no wakeup was processed,
- can force attached-turn recovery without waiting for the configured timeout,
- and then continues normal scheduler driving from the recovered canonical result.

## Alternatives Considered

- Rely only on timeout-based automatic recovery
- Hide forced recovery inside `resume`
- Require users to use `stop-turn` as the only manual escape hatch

## Consequences

- Operators now have an explicit manual tool for stale-state recovery.
- `resume` can remain conservative, while `recover` is the intentional escape hatch.
- The CLI surface grows by one command.
- Recovery semantics become more explicit and testable for both attached and background execution paths.
