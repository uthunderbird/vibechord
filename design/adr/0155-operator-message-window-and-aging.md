# ADR 0155: Operator message window and aging protocol

- Date: 2026-04-13

## Decision Status

Accepted

## Implementation Status

Verified

## Context

`OperatorMessage` in `src/agent_operator/domain/control.py` already carries two fields
intended to support message aging:

```python
class OperatorMessage(BaseModel):
    ...
    planning_cycles_active: int = 0
    dropped_from_context: bool = False
```

`OperationState` in `src/agent_operator/domain/operation.py` already holds:

```python
operator_message_window: int = 3  # default window
operator_messages: list[OperatorMessage]
```

`OperationProfile` in `src/agent_operator/domain/profile.py` exposes:

```python
message_window: int = 3
```

However, the application layer never increments `planning_cycles_active`, never sets
`dropped_from_context`, and never emits an aging event. Messages accumulate indefinitely in
`state.operator_messages`, which means:

- the brain sees all historical operator messages at every planning cycle regardless of age,
- the VISION.md promise of a configurable window is unmet,
- the `operator_message.dropped_from_context` event (required by the vision) is never emitted.

### Vision reference

VISION.md §Free-form operator messages:

> Operator messages persist in the brain's context for a configurable number of planning cycles
> (the **operator message window**, set per project or at run time; default is **3 planning
> cycles**). A window of 0 means the message is injected into the very next planning cycle and
> then immediately aged out; no minimum beyond 0 is enforced. When a message ages out of the
> window, an `operator_message.dropped_from_context` event is emitted — there is no silent expiry.

## Decision

Implement the aging protocol in the drive loop / brain-context assembly path.

### Aging logic

At the start of each planning cycle (after brain decision context is assembled but before
`decide_next_action` is called), the runtime must:

1. Increment `planning_cycles_active` by 1 for every message in `state.operator_messages`
   where `dropped_from_context is False`.
2. For every message where `planning_cycles_active > state.operator_message_window`, set
   `dropped_from_context = True` and emit `operator_message.dropped_from_context`.
3. The brain context assembler must include only messages where `dropped_from_context is False`.

Window semantics:
- `operator_message_window = 3` means a message is active for planning cycles 1, 2, 3, and
  dropped after cycle 3 (i.e., `planning_cycles_active` reaches 3 and then the check fires).
- `operator_message_window = 0` means the message is dropped immediately after the first cycle
  it was present (i.e., it is included in cycle 1, then `planning_cycles_active` becomes 1,
  which exceeds 0, so it is dropped before cycle 2).

### Domain event

```python
"operator_message.dropped_from_context"
payload = {
    "message_id": str,
    "text_preview": str,          # first 120 chars
    "planning_cycles_active": int,
    "operator_message_window": int,
}
```

This is a **domain event** (not a trace event): the brain's context has changed, which is an
observable state transition.

### Configuration

`OperationProfile.message_window` (already present) controls the default. The value is copied
to `OperationState.operator_message_window` at operation creation. A future `patch_*` command
family (ADR 0154) may expose live window mutation via `patch_harness`; no new patch type is
required.

### Brain context assembler contract

The component that builds the brain's prompt context must filter `operator_messages` to only
those where `dropped_from_context is False`. The exact assembler location must be identified
during implementation; the current `operation_traceability.py` already reads `operator_messages`
for the trace summary and caps at `[-5:]` — the brain context reader may be separate.

## Prerequisites for resolution

1. Identify where operator messages are currently injected into brain context (grep for
   `operator_messages` in the brain prompt assembly path).
2. Add aging step to the drive loop (or to a reconciliation helper called each iteration).
3. Emit `operator_message.dropped_from_context` domain event on each expiry.
4. Add projector slice for the drop event (set `dropped_from_context = True` on replay).
5. Tests: message active for exactly `window` cycles; message dropped on cycle `window + 1`;
   `operator_message_window = 0` drops after first cycle; event emitted on expiry.

## Consequences

- The brain no longer accumulates unbounded historical operator messages.
- `operator watch` and status surfaces can show message age or active status.
- The vision promise of configurable, transparent message expiry is fulfilled.
- No structural domain model changes required — fields already exist.

## Related

- `src/agent_operator/domain/control.py` — `OperatorMessage` model
- `src/agent_operator/domain/operation.py` — `operator_message_window`, `operator_messages`
- `src/agent_operator/domain/profile.py` — `message_window`
- `src/agent_operator/application/queries/operation_traceability.py` — current message display
- [VISION.md §Free-form operator messages](../VISION.md)
- [ADR 0154](./0154-patch-command-cli-surface.md)
