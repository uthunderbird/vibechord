# ADR 0067: `patch_*` command rejection model

## Status

Accepted

## Context

VISION.md specifies three rejection conditions for `patch_*` commands
(`patch_objective`, `patch_harness`, `patch_success_criteria`):

> "A patch command is rejected with `operation_terminal` if the operation has already reached
> `TERMINAL` state, with `invalid_payload` if the payload is empty or structurally malformed, and
> with `concurrent_patch_conflict` if a conflicting patch on the same field is already pending in
> the inbox."

Gap analysis (2026-04-02) found:

- `invalid_payload` rejection: **implemented** — each handler checks for empty/missing payload
  and rejects with an appropriate message.
- `operation_terminal` rejection: **implemented** — `_drain_commands` routes commands to
  `_reject_command` when the operation is in a terminal status; this fires for all command types
  including `patch_*`.
- `concurrent_patch_conflict` rejection: **was not implemented** — when a `PATCH_OBJECTIVE`
  command was already pending replan and a second `PATCH_OBJECTIVE` arrived, the second silently
  overwrote the first intent. The user's first patch was lost without any signal.

The overwrite happens because `_drain_commands` processes all pending commands sequentially. If
two `patch_objective` commands are in the inbox simultaneously (e.g. user sends a second before the
first replan fires), the second is applied immediately after the first — both take effect, the
second wins, and no rejection is issued.

## Decision

### `concurrent_patch_conflict` detection

At `patch_*` command drain time, before applying the patch, the service checks whether a command
of the same `OperationCommandType` is already recorded in `state.pending_replan_command_ids`. If
so, the incoming command is rejected with reason `concurrent_patch_conflict`.

**Detection predicate:** "a conflicting patch on the same field is already pending" means: a prior
command of the same type has been applied and marked as pending replan (recorded in
`pending_replan_command_ids`) but the replan has not yet executed. Once the replan executes, the
pending ID is cleared, and a new patch on the same field is accepted.

**Scope:** only same-type conflicts are detected. A pending `PATCH_OBJECTIVE` does not block a
`PATCH_HARNESS` — these are independent fields. Each of the three patch types is checked
independently.

**Why not queue instead of reject:** Queuing (accepting the second patch and applying it after the
replan) would require the service to hold user intent across planning cycles and apply it
retroactively. This introduces ordering ambiguity: if the first patch changes the objective and the
brain begins replanning, the second patch arriving after the replan starts is operating on a
different baseline than the user assumed. Rejection is the honest signal: "your intent conflicts
with a pending change; resubmit once the current patch has taken effect."

### Rejection mechanics

Rejection follows the existing `_reject_command` path:
- `command.rejected` domain event emitted with `rejection_reason: "concurrent_patch_conflict"`
- `CommandBrief` updated with `rejected_at` and `rejection_reason` in `TraceBriefBundle`
- CLI surfaces the rejection as a command status update in `watch` and `dashboard`
- No mutation to operation state occurs

### `operation_terminal` and `invalid_payload` — confirmed implemented

For completeness: both conditions are already enforced and no changes are needed.

`operation_terminal` fires via the generic terminal-status guard in `_drain_commands` before any
command-specific handler is reached. `invalid_payload` fires in each patch handler when the payload
text is empty. Both emit `command.rejected` with the appropriate reason.

## Alternatives Considered

### Silent discard of conflicting patch

Rejected. Silent discard has the same information loss as silent overwrite — the user does not know
their intent was not applied. At least the overwrite gives the second patch's content effect.
Discard gives neither; rejection gives the user a recoverable signal.

### Accept all patches, apply last-writer-wins

This was the previous behavior. Rejected because it discards the first user intent silently.
In practice, simultaneous patch commands are unlikely (the inbox is a sequential write path from
the CLI), but when they do occur the VISION contract specifies rejection, not overwrite.

## Consequences

- `_drain_commands` checks `pending_replan_command_ids` for same-type patch conflict before
  applying any `PATCH_*` command
- If a same-type pending replan exists: `_reject_command` with `concurrent_patch_conflict`
- No change to the two already-implemented rejection conditions
- `concurrent_patch_conflict` is added to the documented rejection reasons for `patch_*` commands

## Verification

- `implemented`: `_drain_commands` rejects same-type patch commands while an earlier command of the
  same patch family remains pending replan
- `verified`: covered by
  `tests/test_operation_command_service.py::test_concurrent_patch_conflict_rejects_second_same_type_patch`
