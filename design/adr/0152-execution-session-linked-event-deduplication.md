# ADR 0152: execution.session_linked event deduplication

- Date: 2026-04-13

## Decision Status

Accepted

## Implementation Status

Implemented

## Context

ADR 0144 Stage 1 added `execution.session_linked` to record when a `session_id` is associated
with a background run. The event is emitted at several sites in
`OperationRuntimeReconciliationService` and `OperationTurnExecutionService`.

One emission site is inside the background-run polling loop in
`OperationRuntimeReconciliationService` (`operation_runtime_reconciliation.py` ~line 155):

```python
if reconciled_session_id is not None:
    await self._event_relay.emit(
        "execution.session_linked",
        ...
    )
```

This guard fires on every `poll_background_turn` call where `reconciled_session_id` is non-None
— which is every poll after the session_id is first set. The session_id does not change between
polls, so the event is re-emitted with the same payload on every reconciliation cycle for the
lifetime of the background run.

### Observed impact

During a representative operation run (062bfa3f), the event log contained dozens of identical
`execution.session_linked` entries for a single execution, all with the same `execution_id` and
`session_id`. The projector slice in `_apply_execution_slice` re-applies the `session_id` patch
on each event — which is idempotent — so there is no functional regression. But the event file
grows significantly and checkpoint replay performs redundant work.

### Scope

The other three `execution.session_linked` emission sites are correctly bounded:
- stale-run path (`~line 404`): fires once per stale-run detection
- wakeup-event path (`~line 465`): fires once per wakeup event
- turn-execution service: fires once per `upsert_background_run` call in a one-shot turn

Only the polling-loop site produces duplicates.

## Decision

`execution.session_linked` must be emitted only when the `session_id` value for the execution
actually changes — specifically, only on the first time `reconciled_session_id` is non-None for
a given execution.

### Fix

Add a guard to the polling loop emission site:

```python
if reconciled_session_id is not None and reconciled_session_id != existing_session_id:
    await self._event_relay.emit(
        "execution.session_linked",
        ...
    )
```

Where `existing_session_id` is the `session_id` of the execution record before the current poll
(already available in the surrounding code as the variable used to compute `reconciled_session_id`).

## Prerequisites for resolution

1. The `execution.session_linked` projector slice must already be in place (done in ADR 0144).
2. A test asserting that a single `execution.session_linked` event is emitted per session-link
   (not per poll) should be added or updated in the relevant reconciliation test file.

## Consequences

- Event log no longer grows with redundant `execution.session_linked` entries per polling cycle.
- Checkpoint replay performs exactly one `session_id` patch per execution.
- No behavioral change — the projector slice is idempotent; deduplication only removes noise.

## Related

- [ADR 0144](./0144-event-sourcing-write-path-contract-and-rfc-0009-closure.md)
