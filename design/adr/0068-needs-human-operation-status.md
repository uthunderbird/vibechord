# ADR 0068: `NEEDS_HUMAN` operation status

## Status

Accepted

## Context

VISION.md defines three user-visible macro-states for an operation:

> - **RUNNING** — the operator is actively driving work.
> - **NEEDS_HUMAN** — the operation has surfaced a typed attention request that the user should
>   address. Non-blocking tasks may continue; blocking attentions gate forward progress. Once all
>   blocking attentions are answered, the operation returns to RUNNING automatically at the next
>   scheduler cycle.
> - **TERMINAL** — the operation has completed, failed, or been cancelled.
>
> `NEEDS_HUMAN` acts as an overlay condition: the scheduler keeps working, but is gated on the
> blocking attention.

The current `OperationStatus` enum uses `BLOCKED` for the state that corresponds to VISION's
`NEEDS_HUMAN`. This creates two problems:

**Problem 1 — Semantic ambiguity.** `BLOCKED` is used in both `OperationStatus` (attention-blocked
operation) and `TaskStatus` (dependency-blocked task). A reader encountering `BLOCKED` in any
context has to check which type it belongs to. VISION separates these concepts cleanly: tasks are
`PENDING` with a `[BLOCKED]` display alias when they have unresolved dependencies; operations are
`NEEDS_HUMAN` when a blocking attention is open. The implementation conflates both under `BLOCKED`.

**Problem 2 — Name contract violation.** VISION explicitly uses `NEEDS_HUMAN` as the user-visible
state label in the operation lifecycle description, the `watch` surface design, and the CLI
drill-down model. The persisted event log, `operation.status.changed` payloads, and CLI output
currently emit `"blocked"` where VISION says users should see `"needs_human"`. Any documentation,
test, or external consumer written against the VISION spec encounters a mismatch.

**Problem 3 — `TERMINAL` framing.** VISION says `TERMINAL` is the macro-state for completed,
failed, and cancelled. The current implementation uses `COMPLETED`, `FAILED`, and `CANCELLED` as
distinct `OperationStatus` values — there is no single `TERMINAL` value. This is not a gap: VISION
uses `TERMINAL` as a conceptual grouping label, not a single enum value. The current three-value
representation is correct and more informative.

## Decision

### Rename `OperationStatus.BLOCKED` → `OperationStatus.NEEDS_HUMAN`

`OperationStatus.BLOCKED` is renamed to `OperationStatus.NEEDS_HUMAN`. The string value changes
from `"blocked"` to `"needs_human"`.

This affects:
- The `OperationStatus` enum definition
- All `state.status = OperationStatus.BLOCKED` assignments in `service.py` (attention-blocking
  transitions)
- All `state.status is OperationStatus.BLOCKED` comparisons
- `operation.status.changed` event payloads emitted when an operation becomes attention-blocked
- CLI rendering of operation status
- `OperationBrief.status` field (written to `TraceBriefBundle`)
- Tests that assert `"blocked"` as an operation status string

### `TaskStatus.BLOCKED` is not changed

`TaskStatus.BLOCKED` remains. It is the correct name for a task with unresolved dependency
blockers. The rename is scoped to `OperationStatus` only — these are different types with different
semantics.

### VISION's `[BLOCKED]` display label for tasks is preserved

VISION uses `[BLOCKED]` as a CLI display grouping label for `PENDING` tasks that have at least one
dependency that has not completed. This is a presentation alias, not a status value. It is not
affected by this rename.

### Iteration-limit exhaustion uses `FAILED`, not `NEEDS_HUMAN`

The current runtime still sets `state.status = OperationStatus.NEEDS_HUMAN` when the iteration
limit is reached. This remains semantically wrong: iteration-limit exhaustion is a stop policy
firing — the operation did not complete its goal, and no user attention is being requested. The
desired end state is `FAILED` with `final_summary = "Maximum iterations reached."`, consistent
with how ADR 0065 handles the time-limit stop condition.

This is a secondary correction included in this ADR because the rename touched the same status
surface. That correction is still outstanding.

### Event log compatibility

The string value `"blocked"` in persisted event logs becomes `"needs_human"` after this change.
Existing persisted operations with `"blocked"` in their event log will not be automatically
migrated — they pre-date the rename. The CLI must treat both `"blocked"` (legacy) and
`"needs_human"` (current) as the same semantic state when reading historical event logs.

This backward-compat read path is a one-time migration shim, not a permanent API surface. Once all
operations in active use have cycled through, the shim can be removed.

## Implementation Notes

Current repository truth:

- `implemented`: the enum rename to `OperationStatus.NEEDS_HUMAN` is in place
- `implemented`: operation-state hydration upgrades legacy persisted `"blocked"` values to
  `"needs_human"`
- `implemented`: CLI and projector code use `NEEDS_HUMAN` as the active operation status
- `implemented`: iteration-limit exhaustion now transitions to `FAILED`, not `NEEDS_HUMAN`
- `verified`: repository tests cover both the `NEEDS_HUMAN` rename surface and the corrected
  iteration-limit classification

## Why now

The rename was deferred in the original implementation because `BLOCKED` was in use before the
VISION's `NEEDS_HUMAN` language was finalized. Now that the VISION is stable and the gap analysis
has named this as a contract violation, the rename is the correct action. Continued deferral
accumulates more places where `"blocked"` is embedded in tests, docs, and external consumer
expectations.

## Consequences

- `OperationStatus.BLOCKED` → `OperationStatus.NEEDS_HUMAN` (value: `"blocked"` → `"needs_human"`)
- `TaskStatus.BLOCKED` unchanged
- Iteration-limit exhaustion transitions to `OperationStatus.FAILED` (not `NEEDS_HUMAN`)
- Event log emits `"needs_human"` for attention-blocked operations going forward
- CLI reads both `"blocked"` (legacy) and `"needs_human"` as the same state for historical ops
- All tests asserting `"blocked"` as an operation status string are updated to `"needs_human"`
- `OperationBrief.status` values in new `TraceBriefBundle` files will reflect `"needs_human"`

## Verification

- `implemented`: enum, state-upgrade, CLI, and projector surfaces now use `NEEDS_HUMAN`
- `verified`: covered by existing CLI/service assertions that read and emit
  `OperationStatus.NEEDS_HUMAN`
- `verified`: iteration-limit exhaustion now transitions to `FAILED` and passes the full repository
  test suite
