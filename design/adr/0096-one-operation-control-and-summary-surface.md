# ADR 0096: One-operation control and summary surface

## Status

Accepted

## Extends

- [CLI UX Vision](../CLI-UX-VISION.md)
- [ADR 0016](./0016-attention-request-taxonomy-and-answer-routing.md)
- [ADR 0037](./0037-stop-operation-command-slice.md)

## Context

The CLI needs one stable contract for the most common one-operation commands:

- `status`
- `message`
- `pause`
- `unpause`
- `interrupt`
- `cancel`

Without a dedicated ADR, implementation slices would keep mixing user-facing UX with internal
typed-command details.

### Current truth

Today:

- the repository now has a public `status` command as the default one-operation summary surface
- `status --brief` now emits a compact single-line summary
- blocked operations now emit an explicit action line from `status`
- `interrupt` is now the public command name
- `cancel` now confirms by default and supports `--yes`
- debug/runtime detail surfaces remain outside this ADR and are still governed by the `0093/0097`
  split

## Decision

The CLI must expose one coherent one-operation control and summary surface centered on `status`.

### `status`

`status` is the default one-operation summary command.

Its default output is a rich human-readable summary with:

- overall operation state
- iteration progress
- task summary
- blocking attention summary
- recent activity

When the operation is blocked, the output ends with an action line showing the next recommended
command.

`status --brief` is the canonical single-line summary form.

### `message`

`message OP TEXT` is the public durable context-injection surface.

It is user-facing and must not be framed as typed command injection.

### `pause` and `unpause`

`pause` requests a soft operation-wide pause at a safe boundary.

`unpause` resumes a paused operation.

These are whole-operation controls, not task- or session-level debug actions.

### `interrupt`

`interrupt` is the public command for stopping the current agent turn without cancelling the
operation.

It replaces `stop_turn` as the user-facing name.

Task-scoped interruption is allowed through `--task`, but the primary mental model remains
operation-first.

### `cancel`

`cancel` is the destructive terminal control.

It must require confirmation unless `--yes` is passed.

The confirmation UX is part of the public contract, not optional polish.

## Consequences

- One-operation UX can be implemented around `status` instead of forcing users into forensic views.
- Control commands gain stable public semantics independent of internal command types.
- `interrupt` replaces older naming without reopening stop-control semantics.
- Destructive behavior is explicit and consistent.

## Implementation notes

The current repository has implemented:

- `status`
- `status --brief`
- blocked-operation action hints in `status`
- public `interrupt`
- confirm-first `cancel`

## Verification

- `tests/test_cli.py`

## This ADR does not decide

- low-level debug command placement beyond the `debug` split
- exact `status --json` schema
- forensic transcript formatting
- session-level debug cancellation surfaces

## Alternatives Considered

### Keep `watch` or `dashboard` as the default one-operation summary entry

Rejected. Those are useful delivery surfaces, but `status` is the canonical shell-native summary.

### Keep `stop_turn` as the public command name

Rejected. `interrupt` better matches user intent and the CLI UX direction.

### Allow `cancel` without confirmation by default

Rejected. The public CLI vision explicitly treats destructive commands as confirm-first.
