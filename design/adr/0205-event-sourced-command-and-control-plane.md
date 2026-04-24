# ADR 0205: Event-Sourced Command and Control Plane

- Date: 2026-04-23

## Decision Status

Accepted

## Implementation Status

Implemented

Implementation grounding on 2026-04-24:

- `implemented`: the canonical event-sourced command application boundary already handles v2
  control actions such as `answer_attention_request`, pause/unpause, operator message injection,
  objective/harness/criteria patching, allowed-agent changes, involvement changes, and
  execution-profile changes in
  `src/agent_operator/application/event_sourcing/event_sourced_commands.py`
- `implemented`: whole-operation cancel in `OperatorServiceV2.cancel()` now routes through the same
  canonical control-plane path by synthesizing a `STOP_OPERATION` control command and applying it
  through `EventSourcedCommandApplicationService`, rather than appending a bare terminal status
  event directly
- `implemented`: `STOP_OPERATION` now produces canonical `command.accepted` or `command.rejected`
  events plus the resulting terminal domain events and checkpoint materialization through replay
  in `src/agent_operator/application/event_sourcing/event_sourced_commands.py`
- `implemented`: `OperatorServiceV2.cancel()` now rejects terminal v2 operations through the same
  canonical rejection path instead of silently re-cancelling them
- `verified`: targeted control-plane regressions pass in
  `tests/test_event_sourced_command_application.py` and `tests/test_operator_service_v2.py`
- `verified`: `uv run pytest` passed on 2026-04-24 at the repository state that closes this ADR
  (`947 passed, 11 skipped`)
- `noted`: `uv run mypy` still reports pre-existing bootstrap typing errors outside this slice in
  `src/agent_operator/bootstrap.py:233`, `src/agent_operator/bootstrap.py:661`, and
  `src/agent_operator/bootstrap.py:718`; those were observed during verification but were not
  introduced by this ADR closure work

## Context

The command/control plane is partially event-sourced and partially legacy. `answer` can be accepted
into the v2 event stream while the command intent file remains pending. `cancel` can fail for v2
operations because it routes through legacy snapshot cancellation. This proves the control plane
does not yet have one authority.

## Decision

Every v2 control action is applied through an event-sourced command application service or a
successor single-writer control service.

Covered actions:

- `answer`
- `cancel`
- `pause`
- `unpause`
- `interrupt`
- `message`
- `patch_objective`
- `patch_harness`
- `patch_criteria`
- `set-execution-profile`
- involvement changes
- allowed-agent changes

The canonical result of a control action is a `command.accepted` or `command.rejected` event plus
the domain events caused by accepted commands.

## Required Properties

- Command intent status is updated atomically or transactionally-after canonical event append.
- Rejected commands produce explicit rejection reason and wake/follow-up behavior when the agent
  requires replacement instructions.
- Accepted commands materialize checkpoint state before returning success.
- Control actions do not depend on `.operator/runs`.
- Command replay is idempotent by command id.

## Verification Plan

- accepted/rejected event tests for every command type.
- command intent status changes from `pending` to applied/rejected after v2 application.
- `operator answer` on v2 blocking attention wakes the operator or produces explicit follow-up.
- `operator cancel` on v2 operation yields cancelled status without legacy snapshot.
- Codex permission rejection/escalation produces follow-up instruction path.

## Related

- ADR 0013
- ADR 0078
- ADR 0144
- ADR 0203
- ADR 0204
