# ADR 0066: `stop_turn` task-addressing model

## Status

Accepted

## Context

VISION.md specifies:

> "The user addresses the turn through its task, not through a session id. Session ids are not a
> primary user-facing concept."

And:

> "If `stop_turn` targets a task that is not in `RUNNING` state, the command is rejected with
> reason `stop_turn_invalid_state` and the actual state of the task is included in the rejection
> message (e.g., `task is COMPLETED`). The rejection is surfaced as a CLI error message and emitted
> as an event in the operation trace. No side effects occur."

The original implementation had a `stop_turn` CLI command that stopped the active agent turn for
the whole operation, without a `--task` flag and without a task-state rejection path.

This was acceptable when each operation had at most one active session at a time. Multi-session
parallel coordination via background runs is now implemented (ADR confirmed in gap analysis
2026-04-02): the brain dispatches session A at iteration N and session B at iteration N+1; both run
concurrently as background processes. With two or more active sessions, `stop_turn` with no task
specifier is ambiguous — which session should stop?

## Decision

### `--task` flag on `stop_turn`

`stop_turn op-id --task task-short-id-or-uuid` becomes the primary form of the command. The task
identifier resolves to the agent session currently bound to that task. The CLI accepts both the
short display ID (`task-{8hex}`) and the full UUID for flexibility, matching how the task is shown
in `tasks op-id` output.

**Single-session fallback:** When `--task` is omitted and exactly one session is currently active,
the command stops that session without requiring a task specifier. This preserves the ergonomics of
the common single-session case. When `--task` is omitted and zero or more than one sessions are
active, the command is rejected with a clear error message: "Multiple active sessions — use
`--task task-id` to specify which to stop."

**Rationale for fallback (not mandatory flag):** Requiring `--task` unconditionally would make the
command more verbose in the common case (single agent, one active task) with no benefit. The
fallback degrades gracefully without hiding the multi-session complexity from the user.

### `stop_turn_invalid_state` rejection

When `--task` is specified and the target task is not in `RUNNING` state, the command is rejected:
- rejection reason: `stop_turn_invalid_state`
- rejection message includes the actual current status of the task (e.g. `task is COMPLETED`)
- emitted as a `command.rejected` domain event in the operation trace
- surfaced as a CLI error message with the task state
- no side effects — the session is not touched

This contract matters for two reasons:
1. It prevents silent no-ops. Without explicit rejection, a user who targets a completed task
   might believe the stop was applied, when nothing happened.
2. It provides a diagnostic. In a multi-session scenario the user may not know the current state
   of each task; the rejection message tells them exactly where the task is.

### Session resolution

A task `--task` argument resolves to a session via `SessionState.bound_task_ids`. The session that
has the specified `task_id` in its `bound_task_ids` and is currently in an active state
(`SessionObservedState` not terminal) is the target. If no such session is found but the task
exists and is `RUNNING`, this is an internal consistency error — the command is rejected with
`stop_turn_invalid_state` and the discrepancy is recorded in the trace.

### Why task, not session id

Session ids are internal routing artefacts. They are assigned at session creation, change when a
session is replaced, and are not shown in primary CLI surfaces (`watch`, `tasks`). Exposing them
as the addressing mechanism for `stop_turn` would require the user to run a secondary command
(`sessions op-id`) to find the session id before they can stop a turn — a two-step interaction for
a common supervisory action.

Task short IDs (`task-{8hex}`) are shown directly in `watch` and `tasks` output. The user sees
the task, identifies it, and stops it — one step. This is consistent with the broader CLI design
principle: "commands named by user intent, not system mechanism."

## Consequences

- `stop_turn op-id` gains an optional `--task task-id` argument
- When `--task` is provided: task lookup → session resolution → stop; if task not RUNNING → reject
  with `stop_turn_invalid_state` + actual state
- When `--task` is omitted and one active session exists: stop that session (existing behavior)
- When `--task` is omitted and zero or multiple active sessions exist: reject with descriptive
  error message
- `stop_turn_invalid_state` is added to the domain event catalog as a `command.rejected` reason
- The CLI help text for `stop_turn` is updated to document the `--task` option and the fallback
  behavior

## Verification

- `implemented`: `stop-turn` accepts `--task`, resolves task UUID and `task-{short_id}`, and
  rejects non-running tasks with `stop_turn_invalid_state`
- `verified`: covered by `tests/test_cli.py::test_stop_turn_enqueues_session_targeted_command`,
  `tests/test_cli.py::test_stop_turn_task_flag_resolves_bound_session`,
  `tests/test_cli.py::test_stop_turn_task_flag_short_id_resolves`, and
  `tests/test_cli.py::test_stop_turn_task_flag_invalid_state_rejected`
