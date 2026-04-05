# ADR 0046: Timed Wakeups and Daemon Auto-Resume

## Status

Accepted

## Context

`operator` already had file-backed wakeups for immediate background-run completion and failure events, but rate-limit cooldowns were only stored as session state (`cooldown_until`). Once a session hit a provider limit, the operation stayed blocked until a human ran `resume` or `tick`.

That left two gaps:

- the runtime had no generic way to schedule a future wakeup
- there was no built-in loop that could automatically resume persisted operations when a scheduled time arrived

We needed cooldown expiry to continue automatically without turning one-shot CLI commands into hidden long-lived workers.

## Decision

Introduce generic timed wakeups and a separate CLI daemon.

- `RunEvent` now supports `not_before`
- `FileWakeupInbox.claim()` only claims pending wakeups whose `not_before` is due
- rate-limit cooldowns enqueue a timed wakeup (`session.cooldown_expired`)
- a new `operator daemon` command polls ready wakeups and runs one resumable reconciliation cycle per affected operation

Manual `resume` remains valid and still clears expired cooldowns even if the daemon is not running.

## Alternatives Considered

- Specialized cooldown-only logic with no generic timed wakeup primitive
- Delayed wakeups without any built-in auto-resume loop
- Hidden background threads/timers inside existing one-shot CLI commands

## Consequences

- Positive: future time-based runtime events can reuse the same mechanism
- Positive: auto-resume is explicit and operationally visible through a dedicated daemon command
- Positive: one-shot CLI commands keep their current lifecycle semantics
- Negative: automatic continuation now depends on running the daemon
- Negative: `RunEvent` and wakeup persistence gain a new scheduling field that downstream tooling should tolerate
