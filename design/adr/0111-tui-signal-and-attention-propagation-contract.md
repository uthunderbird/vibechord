# ADR 0111: TUI Signal and Attention Propagation Contract

## Status

Implemented

## Context

TUI supervision depends on signal density and correctness:

- users need to triage where help is required,
- operations can be blocked at different scopes (operation-level vs task-level),
- and attention can be ambient or blocking depending on urgency.

The current TUI vision defines badge types and propagation, but the contract must align with existing
operation/task status semantics:

- operation-level blocking is represented as `NEEDS_HUMAN` (not task status `BLOCKED`),
- non-blocking requests and ambient observations are informational,
- terminal states must remain explicit (`completed`, `failed`, `cancelled`).

## Decision

The TUI signal system is defined as a projection over persisted runtime truth with three badge classes:

1. **Blocking attention (`[!!N]`)**:
   - represents open blocking `AttentionRequest`s.
   - must be surfaced at the item level and propagated to all ancestors.
2. **Non-blocking attention (`[!N]`)**:
   - represents open non-blocking attentions.
   - surfaced similarly with ancestor aggregation.
3. **Ambient observation (`[~N]`)**:
   - surfaced only at operation level in the right pane.
   - does **not** propagate to operation ancestors or fleet aggregate by default.

Each count is displayed as the number of open requests for that aggregation scope.

## Aggregation and ordering rules

1. Aggregation is by open request list, not by resolved/rejected history.
2. Badge propagation is monotonic by ancestry: any node with open attentions contributes count to all
   ancestors.
3. `Tab` action targets the next visible node with at least one `[!!N]`.
4. Within the same node, `a` targets the oldest blocking attention first (creation time ascending).
5. If a blocking attention is answered and additional blocking attentions remain, next-focus follows the
   same oldest-first order.

## Clarifications

- `[BLOCKED]` in task views is a task grouping display alias for dependency-blocked `PENDING` tasks.
  It is **not** equivalent to operation `NEEDS_HUMAN`.
- `[!!N]` indicates gating attention that can block progression;
  `[!N]` does not block scheduling or continuation.

## What is out of scope

- TUI-specific signal algorithms not grounded in persisted attentions.
- New priority classes beyond the three described above.
- Automatic action suggestions without user-level commandability.

## Alternatives Considered

### Option A: Hide all attention signals until the user opens the affected operation

Rejected.

This makes fleet-level triage slower and violates the TUI purpose as a supervisory cockpit.

### Option B: Propagate all signals identically regardless of urgency

Rejected.

Urgency flattening causes alert fatigue and makes blocking triage ambiguous.

### Option C: Keep `blocking`/`non-blocking` as pure display hints without strict propagation rules

Rejected.

Without propagation invariants, users lose predictable routing from fleet overview to actionable item.

### Option D: Adopt the three-tier badge model with explicit propagation and ordering rules

Accepted.

This preserves orientation, gives explicit triage priority, and remains compatible with CLI attention
and status models.

## Consequences

- Attention triage paths become deterministic and testable.
- The operator can jump to actionability (`Tab`, then `a`) without context switching.
- The design avoids misuse of task `BLOCKED` semantics at operation scope.

## Verification

- Blocking and non-blocking counts reconcile with persisted attention state.
- The `[BLOCKED]` task presentation label remains a rendering alias, not an operation-state substitute.
- Ambient observations, if implemented, must be represented as a separate model and scoped to operation
  right pane only unless upstream ADRs expand scope.

### Evidence

- Implemented in CLI/TUI stack refactor dated 2026-04-09 (`signal_text`, `task_signal_text`,
  Tab/`a` navigation semantics).
- Coverage: `tests/test_tui.py` and `tests/test_operation_projections.py`.
