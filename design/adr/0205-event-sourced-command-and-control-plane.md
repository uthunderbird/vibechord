# ADR 0205: Event-Sourced Command and Control Plane

- Date: 2026-04-23

## Decision Status

Accepted

## Implementation Status

Implemented

Phase 1 grounding on 2026-04-25:

- `implemented`: `EventSourcedCommandApplicationService.apply()` loads canonical replay state,
  builds command outcome events, appends them, advances replay, and materializes the updated
  checkpoint.
- `implemented`: the event-sourced command service covers `stop_operation`, objective/harness/
  success-criteria patching, operator message injection, attention answers, involvement changes,
  allowed-agent changes, execution-profile changes, pause, and resume.
- `implemented`: `OperatorServiceV2.cancel()` synthesizes a `STOP_OPERATION` command and applies it
  through `EventSourcedCommandApplicationService`.
- `partial`: the snapshot-era `OperationCommandService` delegates several operation-target commands
  to the event-sourced command service and then reconciles command intent status, but policy record/
  revoke and stop-agent-turn remain outside this generic event-sourced command path.
- `phase-1-blocked`: the v2 `RuntimeReconciler` still drained pending commands by emitting generic
  `command.processed` events rather than applying the command through the event-sourced command
  application boundary.
- `phase-1-planned`: Phase 2 needed to wire v2 command draining through the event-sourced command application
  service, reconcile intent status after canonical append, and add coverage for every command type
  that remains part of the v2 control plane.

The Phase 1 grounded design artifact is
[`../internal/adr-0205-phase-1-grounded-design.md`](../internal/adr-0205-phase-1-grounded-design.md).

Implementation closure on 2026-04-25:

- `implemented`: v2 `RuntimeReconciler` is wired with
  `EventSourcedCommandApplicationService` through the bootstrap provider
  (`src/agent_operator/bootstrap.py:708-721`) and stores the service on construction
  (`src/agent_operator/application/drive/runtime_reconciler.py:30-42`).
- `implemented`: `RuntimeReconciler.drain_commands()` now applies pending commands through
  `EventSourcedCommandApplicationService.apply()`, updates command intent status to `applied` or
  `rejected` after application, and returns no `command.processed` placeholder events
  (`src/agent_operator/application/drive/runtime_reconciler.py:114-159`; grep:
  `rg -n "command\\.processed" src/agent_operator/application/drive src/agent_operator/application/event_sourcing src/agent_operator/bootstrap.py tests/test_runtime_reconciler.py tests/test_event_sourced_command_application.py`
  returned no matches).
- `implemented`: v2 drive reloads canonical replay state when command draining advanced the
  event-sourced stream, so command-service materialization becomes visible before the next policy
  decision (`src/agent_operator/application/drive/drive_service.py:172-185`).
- `implemented`: accepted duplicate command ids short-circuit from canonical
  `processed_command_ids` and append no duplicate domain events
  (`src/agent_operator/application/event_sourcing/event_sourced_commands.py:74-100`).
- `implemented`: focused tests cover accepted/rejected v2 command draining and idempotent stale
  command reconciliation (`tests/test_runtime_reconciler.py:158-230`,
  `tests/test_runtime_reconciler.py:308-321`).
- `implemented`: focused command-application tests cover success-criteria patch, stop operation,
  operator message, attention answer, involvement, allowed agents, execution profile, pause, resume
  rejection, and duplicate command idempotency (`tests/test_event_sourced_command_application.py:218-585`).
- `implemented`: scoped `stop_agent_turn` / session interrupt remains an explicit execution-control
  exception under `OperationCommandService`, not the generic event-sourced operation-command
  boundary. Grounding: `OperationCommandService` branches on `STOP_AGENT_TURN`
  (`src/agent_operator/application/commands/operation_commands.py:132-137`), applies the
  stop-agent-turn path at `src/agent_operator/application/commands/operation_commands.py:896-957`,
  and `EventSourcedCommandApplicationService` rejects unsupported command types by default
  (`src/agent_operator/application/event_sourcing/event_sourced_commands.py:492`). Existing tests
  prove this boundary in `tests/test_operation_command_service.py:1625-1756` and
  `tests/test_application_structure.py:338-375`.
- `verified`: targeted tests passed:
  `UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/test_event_sourced_command_application.py tests/test_runtime_reconciler.py tests/test_operator_service_v2.py tests/test_drive_service_v2.py tests/test_epoch_fenced_checkpoints.py`
  (`57 passed`) and
  `UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/test_cli.py -k "answer or pause or unpause or message or patch or involvement or allowed_agents or execution_profile or stop_turn"`
  (`30 passed, 175 deselected`).
- `verified`: full suite passed:
  `UV_CACHE_DIR=/tmp/uv-cache uv run pytest` (`968 passed, 11 skipped`).
- `verified`: changed-file lint passed:
  `UV_CACHE_DIR=/tmp/uv-cache uv run ruff check src/agent_operator/application/drive/process_manager_context.py src/agent_operator/application/drive/runtime_reconciler.py src/agent_operator/application/drive/drive_service.py src/agent_operator/application/event_sourcing/event_sourced_commands.py src/agent_operator/bootstrap.py tests/test_runtime_reconciler.py tests/test_event_sourced_command_application.py`.
- `noted`: changed-file `mypy` still reports repository-wide pre-existing typing debt outside this
  closure path, including the previously observed bootstrap/runtime protocol mismatch at
  `src/agent_operator/bootstrap.py:720` and many unrelated imported-module errors. Because those
  failures are not isolated to ADR 0205 behavior, this ADR is marked `Implemented` rather than
  `Verified`.

## Context

At ADR proposal time, the command/control plane was partially event-sourced and partially legacy.
Event-sourced command application existed, but there was still more than one command authority
depending on which runtime path was active.

The current codebase has three relevant control paths:

1. `EventSourcedCommandApplicationService`, which is the intended canonical single-writer boundary
   for v2 operation-control commands.
2. Snapshot-era `OperationCommandService`, which processes pending commands against an
   `OperationState` and delegates a subset of commands to the event-sourced command service.
3. v2 `RuntimeReconciler`, which drained pending commands during v2 drive reconciliation but
   emitted generic processed-command events instead of applying the command semantics. This was
   corrected in Phase 2.

This means the decision target is not whether an event-sourced command boundary should exist. It
already exists. The decision target is that v2 control-plane command draining must use that boundary
as the only semantic writer for covered control actions.

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

Scoped session-turn interruption (`STOP_AGENT_TURN`) is the explicit exception: it remains a
runtime/execution-control command under `OperationCommandService`, where it owns session-targeted
turn interruption and replay-backed persistence. It is not treated as a generic operation-control
command in `EventSourcedCommandApplicationService`.

The canonical result of a control action is a `command.accepted` or `command.rejected` event plus
the domain events caused by accepted commands.

## Required Properties

- Command intent status is updated transactionally-after canonical event append.
- Rejected commands produce explicit rejection reasons.
- Accepted commands materialize checkpoint state before returning success.
- Control actions do not depend on `.operator/runs`.
- Command replay is idempotent by command id.
- v2 command draining does not emit semantic placeholder events in place of command application.

## Implementation Record

Phase 1 was design-only. Phase 2 closed the v2 operation-control command drain and kept
session-turn interruption as an explicit exception with its own authority.

Required code changes:

1. Inject `EventSourcedCommandApplicationService` into the v2 `RuntimeReconciler` or replace the
   reconciler command-drain method with a small collaborator that owns command application.
2. Replace v2 `RuntimeReconciler.drain_commands()` placeholder `command.processed` emission with
   command application through `EventSourcedCommandApplicationService.apply()`.
3. After each canonical append, update the durable command intent record to `applied` or `rejected`
   via `FileOperationCommandInbox.update_status()`.
4. Preserve idempotency for commands already present in canonical replay state by checking
   `processed_command_ids` before application and reconciling matching command intent records.
5. Extend `EventSourcedCommandApplicationService` to handle any command types intentionally owned
   by the v2 control plane but not yet covered by the service, or explicitly document why they are
   excluded from ADR 0205 scope.
6. Ensure accepted commands that require replanning or follow-up wake behavior emit canonical domain
   events or planning triggers that v2 replay/query paths consume.
7. Keep `OperatorServiceV2.cancel()` on the command-service path and preserve terminal-operation
   rejection semantics.
8. Remove or retire any v2 placeholder `command.processed` semantics that would compete with
   `command.accepted` / `command.rejected` as the command outcome source of truth.

Required tests:

1. Unit tests for accepted and rejected event output for each covered command type in
   `tests/test_event_sourced_command_application.py`.
2. Unit tests that v2 command draining applies pending commands through the event-sourced service
   and updates command intent files from `pending` to `applied` / `rejected`.
3. Regression tests that duplicate command ids are idempotent and do not append duplicate domain
   events.
4. Regression tests for `OperatorServiceV2.cancel()` success, default summary, and terminal
   rejection.
5. Integration or CLI-level tests showing `operator answer`, `pause`, `unpause`, `message`,
   `patch-objective`, `patch-harness`, `patch-criteria`, `set-execution-profile`, involvement
   change, and allowed-agent change enqueue commands that the v2 command drain consumes correctly.
6. A targeted test for the interrupt/stop-agent-turn boundary that either proves it is handled by
   the event-sourced command service or proves its scoped-execution cancellation remains an explicit
   out-of-scope exception with its own authority.

Verification steps:

1. `UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/test_event_sourced_command_application.py`
2. `UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/test_operator_service_v2.py`
3. `UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/test_cli.py -k "answer or pause or unpause or message or patch or involvement or allowed_agents or execution_profile or stop_turn"`
4. `UV_CACHE_DIR=/tmp/uv-cache uv run pytest`

## Risks

- If v2 command draining applies commands and the snapshot-era service also drains the same inbox,
  duplicated command side effects are possible unless idempotency is anchored on canonical
  `processed_command_ids`.
- If command intent status is updated before event append/materialization, a crash can lose an
  accepted command. Status updates must happen after canonical append succeeds.
- If rejected commands lack follow-up wake/planning behavior where the operator is waiting for
  replacement instructions, v2 runs can appear idle even though the command was rejected correctly.
- If stop-agent-turn/interrupt remains partly session-runtime-owned, ADR 0205 must keep that
  exception explicit to avoid inventing a fake single authority.
- If tests only assert emitted event names, they can miss checkpoint materialization regressions.

## Verification Plan

See Implementation Record for the Phase 2 verification sequence. Phase 1 performed only read/grep
grounding and documentation edits.

## Related

- ADR 0013
- ADR 0078
- ADR 0144
- ADR 0203
- ADR 0204
