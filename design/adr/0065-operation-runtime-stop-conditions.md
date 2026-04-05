# ADR 0065: Operation run-time stop conditions

## Status

Accepted

## Context

VISION.md specifies six stop conditions as deterministic guardrails for the operator loop:

1. **iteration limit** — the run has reached the maximum number of operator iterations.
2. **time limit** — the run has exceeded the allowed wall-clock duration.
3. **budget limit** — the accumulated token or cost budget has been exhausted.
4. **explicit success signal** — the brain has marked the goal as satisfied.
5. **explicit failure signal** — the brain or a guardrail has declared the goal unachievable.
6. **user cancellation** — the user has issued a `cancel` command.

The VISION is explicit: "Stop conditions are part of the control plane. They are not subject to
LLM override. When a stop condition fires, the operation moves to TERMINAL with a specific
`stop_reason` that is visible in `inspect` and `trace`."

Gap analysis (2026-04-02) found that stop conditions 1, 4, 5, and 6 were already enforced in
`_drive_state`. Stop condition 2 (time limit) had a field
(`OperationConstraints.timeout_seconds`) but the field was not read in the loop. Stop condition 3
(budget limit) had no field, no tracking infrastructure, and no enforcement.

A user who sets `timeout_seconds=3600` believing it will prevent runaway operations is wrong.
That is a behavioral contract violation.

## Decision

### Stop condition 1 — Iteration limit (already enforced)

`OperationConstraints.max_iterations` is checked in the `while` loop condition at every iteration
boundary. When the limit is reached, the operation currently moves to `NEEDS_HUMAN` with
`final_summary = "Maximum iterations reached."`

This ADR does not change that behavior. The question whether iteration-limit exhaustion should be
classified as `FAILED` instead is handled separately by [`ADR 0068`](./0068-needs-human-operation-status.md).

### Stop condition 2 — Time limit (enforced; this ADR)

`OperationConstraints.timeout_seconds: int | None` already exists. The loop must check elapsed
wall-clock time at each iteration boundary.

**Enforcement point:** before beginning the next cycle in `_drive_state`, before new work starts
for that iteration. The check reads `state.run_started_at` (persisted on `OperationState`) against
`datetime.now(UTC)`. If `timeout_seconds` is set and the elapsed time exceeds it, the loop fires
the stop condition.

**`state.run_started_at`:** A `run_started_at: datetime | None` field is stored on
`OperationState`. It is set on the first run and preserved across resume calls, so elapsed time is
measured from the original operation start rather than from the latest attached process. This
matches VISION semantics: the time limit is on the operation, not on a single process run.

**Terminal transition:** When the time limit fires, the operation moves to `FAILED` with a timeout
summary and emits `operation.status.changed`. The reason `FAILED` (not `NEEDS_HUMAN`) is used:
the time limit firing is a stop policy decision. This is distinct from attention-blocking
(`NEEDS_HUMAN`).

**Why not a hard timeout via `anyio`:** Using `anyio.move_on_after` or a cancellation scope would
interrupt mid-turn, potentially leaving an agent session in an unknown state. The iteration-boundary
check is deliberate: the loop completes whatever it is currently doing, then checks the stop
condition before beginning the next iteration. This is the same model used for cancellation
(`cancel` commands are drained between iterations, not mid-turn).

### Stop condition 3 — Budget limit (deferred; this ADR records the deferral)

Budget limit enforcement requires two prerequisites that do not yet exist:

1. **Token/cost tracking:** Provider responses must capture `input_tokens`, `output_tokens`, and
   optionally estimated cost per brain call. These must be accumulated in `OperationState` across
   iterations.
2. **Budget field:** `OperationConstraints` must carry a `max_tokens: int | None` or
   `max_cost_usd: float | None` field (or both) that the loop checks against the accumulator.

Neither prerequisite exists in the current codebase. Implementing enforcement without tracking
would require the budget field to enforce against zero — immediately firing on the first iteration.
The correct sequencing is: tracking infrastructure first, then field addition, then enforcement.

**Deferral condition:** This stop condition remains deferred until token tracking is added to
provider responses. When that prerequisite is met, this ADR should be updated or a follow-up ADR
written to record the enforcement implementation.

**What is not deferred:** The field `OperationConstraints.max_tokens` is reserved in intent but
not added to the model until tracking exists, to avoid a field that silently does nothing — the
same failure mode that motivated this ADR for `timeout_seconds`.

### Stop conditions 4, 5, 6 — Already enforced

- **Explicit success / failure:** The brain's `STOP` and `FAIL` action types are handled in
  `_decide_next_action`; the operation transitions to `COMPLETED` or `FAILED` with the brain's
  rationale as `final_summary`.
- **User cancellation:** `cancel` commands are processed in `_drain_commands`; the operation
  transitions to `CANCELLED`.

These are not changed by this ADR.

## Why `FAILED` for time limit, not `COMPLETED`

The VISION says the three terminal outcomes are: completed (goal satisfied), failed (stop policy
fired or goal unachievable), cancelled (user issued `cancel`). Time limit firing is a stop policy
event — the goal was not satisfied. `FAILED` with a specific `final_summary` matches the VISION
intent and distinguishes the outcome from user cancellation and from goal satisfaction.

## Consequences

- `OperationState` stores `run_started_at: datetime | None = None`
- `_drive_state` sets `state.run_started_at` on first run and preserves it on resume
- `_drive_state` checks `timeout_seconds` at the next-cycle boundary and fires `FAILED` + event if
  exceeded
- Budget stop condition remains absent; no `max_tokens` field added until tracking exists
- `timeout_seconds` is now an enforced constraint, not a stored-but-ignored field
- The fix closes the gap between VISION stop condition 2 and the running system

## Verification

- `implemented`: timeout enforcement exists in `OperatorService._drive_state`
- `verified`: covered by `tests/test_service.py::test_timeout_seconds_fires_failed_when_elapsed`
  and `tests/test_service.py::test_timeout_seconds_none_does_not_fire`
