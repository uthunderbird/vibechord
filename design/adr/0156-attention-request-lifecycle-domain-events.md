# ADR 0156: Attention request lifecycle domain events

- Date: 2026-04-13

## Decision Status

Accepted

## Implementation Status

Implemented

## Context

VISION.md §Event Model states:

> Attention lifecycle transitions (`created`, `answered`, `resolved`) … must produce domain
> events at the point of occurrence. … The event log is the authoritative record of what the
> aggregate did. If a transition is not in the event log, it did not happen as far as any
> downstream consumer is concerned.

The projector in `src/agent_operator/projectors/operation.py` already handles:

```python
if event.event_type == "attention.request.created": ...
elif event.event_type == "attention.request.resolved": ...
```

But no application-layer code emits these events. Searching `src/agent_operator/application`
for `attention.request` yields zero emission sites. The three attention lifecycle transitions
are:

1. **created** — `OperationAttentionCoordinator.open_attention_request()` creates the
   `AttentionRequest` object and appends it to `state.attention_requests`. No event emitted.
2. **answered** — `_apply_answer_attention_request()` in `operation_commands.py:690` sets
   `attention.status = AttentionStatus.ANSWERED`. No event emitted.
3. **resolved** — `finalize_pending_attention_resolutions()` in `operation_commands.py:469`
   sets `attention.status = AttentionStatus.RESOLVED`. No event emitted.

This means the event log cannot reconstruct attention state from events alone — a requirement
violation from the VISION.md event model invariant.

### Scope

The projector handles `attention.request.created` and `attention.request.resolved` today.
`attention.request.answered` is not yet in the projector but is required by the vision.
All three must be added.

## Decision

Emit `attention.request.created`, `attention.request.answered`, and
`attention.request.resolved` at the three lifecycle transition sites.

### Event payloads

Verified implementation detail: the repository now emits payloads that carry the lifecycle fields
needed for faithful replay rather than the narrower minimum sketched in the proposal draft.

**`attention.request.created`**

```python
{
    "attention_id": str,
    "operation_id": str,
    "attention_type": str,            # AttentionType.value
    "title": str,
    "question": str,
    "context_brief": str | None,
    "target_scope": str,
    "target_id": str | None,
    "blocking": bool,
    "suggested_options": list[str],
    "status": "open",
    "answer_text": str | None,
    "answer_source_command_id": str | None,
    "created_at": str,                # ISO 8601 UTC timestamp
    "answered_at": str | None,
    "resolved_at": str | None,
    "resolution_summary": str | None,
    "metadata": dict[str, object],
}
```

**`attention.request.answered`**

```python
{
    "attention_id": str,
    "attention_type": str,
    "status": "answered",
    "answer_text": str,
    "source_command_id": str | None,
    "answered_at": str,               # ISO 8601 UTC timestamp
}
```

**`attention.request.resolved`**

```python
{
    "attention_id": str,
    "attention_type": str,
    "status": "resolved",
    "resolution_summary": str,
    "resolved_at": str,               # ISO 8601 UTC timestamp
}
```

### Emission sites

| Event | File | Location |
|---|---|---|
| `attention.request.created` | `decision_execution.py` | Immediately after the synchronous attention-open call, before block/defer handling |
| `attention.request.created` | `agent_results.py` | Immediately after incomplete-result attention creation, before lifecycle blocking/focus updates |
| `attention.request.answered` | `operation_commands.py` | After `attention.status = AttentionStatus.ANSWERED` in `_apply_answer_attention_request()` |
| `attention.request.resolved` | `operation_commands.py` | After `attention.status = AttentionStatus.RESOLVED` in `finalize_pending_attention_resolutions()`, once per resolved attention |

### Projector

The projector (`src/agent_operator/projectors/operation.py`) already handles
`attention.request.created` and `attention.request.resolved`. Add a handler for
`attention.request.answered`:

```python
elif event.event_type == "attention.request.answered":
    attention_id = payload.get("attention_id")
    attention = next(
        (a for a in state.attention_requests if a.attention_id == attention_id),
        None,
    )
    if attention is not None:
        attention.status = AttentionStatus.ANSWERED
        attention.answer_text = payload.get("answer_text", "")
        attention.answered_at = event.occurred_at
```

### Event relay access

Verified implementation detail: the repository uses the call-site emission approach.

`OperationAttentionCoordinator.open_attention_request()` remains synchronous and owns only lookup
and construction rules. The application services that already own lifecycle side effects and have
`OperationEventRelay` access emit the corresponding domain events immediately after the transition.

## Prerequisites for resolution

1. Confirm call site count for `open_attention_request()` to choose Option A vs B. Completed.
2. Add `attention.request.created` emission at all `open_attention_request` call sites (or
   inject relay into the coordinator). Completed.
3. Add `attention.request.answered` emission in `_apply_answer_attention_request()`. Completed.
4. Add `attention.request.resolved` emission per resolved attention in
   `finalize_pending_attention_resolutions()`. Completed.
5. Add `attention.request.answered` projector slice. Completed.
6. Tests: event log contains all three events in the correct order for the open→answer→resolve
   flow; projector reconstructs correct attention state from events. Completed.

## Consequences

- The event log fully captures the attention lifecycle; checkpoint replay is no longer lossy
  for attention state.
- External consumers (dashboards, audit tools) can observe attention transitions from the
  event file without reading projected state.
- No behavioral change — projector slices are idempotent with existing state mutations.

## Related

- `src/agent_operator/projectors/operation.py:270` — existing projector slices
- `src/agent_operator/application/commands/operation_attention.py` — `open_attention_request`
- `src/agent_operator/application/commands/operation_commands.py` — answer and resolve sites
- [VISION.md §Event Model](../VISION.md)
- [ADR 0153](./0153-attention-request-answered-deduplication-loop.md)
