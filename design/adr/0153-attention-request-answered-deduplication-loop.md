# ADR 0153: Attention request answered-deduplication loop

- Date: 2026-04-13

## Decision Status

Accepted

## Implementation Status

Implemented

## Context

During operation `062bfa3f` (the ADR 0144–0151 closure wave), the operation entered an infinite
loop generating new `blocked_external_dependency` attention requests immediately after each one
was answered. The operation cycled through `NEEDS_HUMAN` at iter 17, 18, 19 without making
progress, and had to be manually cancelled.

### Root cause

Two bugs interact to produce the loop.

#### Bug 1 — `open_attention_request` deduplicates against ANSWERED requests

`OperationAttentionCoordinator.open_attention_request()` in
`src/agent_operator/application/commands/operation_attention.py:47–60`:

```python
existing = next(
    (
        item
        for item in state.attention_requests
        if item.status in {AttentionStatus.OPEN, AttentionStatus.ANSWERED}  # BUG
        and item.attention_type is attention_type
        ...
    ),
    None,
)
if existing is not None:
    return existing
```

When the brain decides to raise `blocked_external_dependency` again after a human answer, it
calls `open_attention_request()`. The deduplication check matches the already-ANSWERED request
and returns it. The caller receives an ANSWERED request and sets it as `decision.blocking_focus`,
which puts the operation back into `NEEDS_HUMAN` — blocked on a request that has already been
answered.

#### Bug 2 — `finalize_pending_attention_resolutions` is gated on `consumed_triggers`

In `src/agent_operator/application/drive/operation_drive.py:285`:

```python
if consumed_triggers:
    await self._control._finalize_pending_attention_resolutions(state)
```

`finalize_pending_attention_resolutions` transitions ANSWERED → RESOLVED. It is only called
when `_drain_pending_planning_triggers` returns a non-empty result. When the brain immediately
re-blocks on a new attention request (no planning triggers consumed), the finalization is skipped.
The ANSWERED request stays in `state.attention_requests` and is matched again by Bug 1 on the
next iteration.

### Resulting cycle

1. Human answers attention request → `status = ANSWERED`, id added to
   `pending_attention_resolution_ids`
2. `pending_attention_resolution_ids` non-empty → loop condition remains true
3. Brain iterates: no consumed planning triggers → `finalize_pending_attention_resolutions` not
   called → ANSWERED request survives in `attention_requests`
4. Brain decides to raise the same `blocked_external_dependency` again →
   `open_attention_request` matches the ANSWERED request → returns it
5. `decision.blocking_focus` is set to the ANSWERED request → operation enters `NEEDS_HUMAN`
   again
6. Goto 1

### Contributing factor — unreconciled background wakeups

The status output showed 9–11 pending wakeups during the loop. These wakeups kept the operation
active and fed the loop condition alongside `pending_attention_resolution_ids`, preventing the
drive loop from exiting cleanly between iterations.

## Decision

Both bugs must be fixed.

### Fix 1 — Remove ANSWERED from deduplication in `open_attention_request`

An ANSWERED attention request is not open. The deduplication guard must only match OPEN
requests:

```python
# src/agent_operator/application/commands/operation_attention.py
if item.status is AttentionStatus.OPEN   # was: in {OPEN, ANSWERED}
```

If the brain raises the same question again after an answer, a new OPEN request should be
created — this is the correct behaviour. The caller can inspect the prior answered request
separately if needed.

### Fix 2 — Call `finalize_pending_attention_resolutions` unconditionally before brain decision

The ANSWERED → RESOLVED transition must not be gated on `consumed_triggers`. It should be
called at the top of each loop iteration, before the brain makes its next decision:

```python
# src/agent_operator/application/drive/operation_drive.py
# before brain decision, unconditionally:
await self._control._finalize_pending_attention_resolutions(state)
# remove the if consumed_triggers: guard
```

This ensures that by the time the brain evaluates `open_attention_request`, all answered
requests have already been transitioned to RESOLVED and will not match the deduplication check.

### Fix 1 alone is sufficient to break the cycle

Fix 1 is the minimal fix. With ANSWERED excluded from deduplication, the brain will create a
new OPEN request instead of re-blocking on the answered one. The human can answer it again, and
the loop advances.

Fix 2 is a correctness improvement that prevents ANSWERED requests from lingering in
`attention_requests` across iterations longer than necessary. Both fixes together are the
complete resolution.

## Prerequisites for resolution

1. Tests covering the re-answer scenario: a single `blocked_external_dependency` raised, answered,
   and the drive loop re-entering must not re-block on the answered request.
2. Tests confirming that `finalize_pending_attention_resolutions` transitions ANSWERED → RESOLVED
   even when no planning triggers are consumed.

## Consequences

- The infinite NEEDS_HUMAN loop is eliminated.
- Answered attention requests are correctly retired before the next brain decision.
- The brain may legitimately raise a new attention request of the same type after an answer
  (e.g. if the answer was insufficient and the block condition persists) — this remains possible
  because a new OPEN request will be created rather than blocked by deduplication.

## Related

- `src/agent_operator/application/commands/operation_attention.py` — Bug 1 fix site
- `src/agent_operator/application/drive/operation_drive.py` — Bug 2 fix site
- `src/agent_operator/application/commands/operation_commands.py` — `finalize_pending_attention_resolutions` implementation
- [ADR 0152](./0152-execution-session-linked-event-deduplication.md)
