# ADR 0151: Active-session initialization event coverage gap

- Date: 2026-04-12

## Decision Status

Superseded

## Implementation Status

N/A

Skim-safe current truth on 2026-04-27:

- `superseded`: the repository no longer carries a durable `active_session` field whose initial
  value must be made canonical at birth
- `implemented`: initial attached sessions are still born canonically through `session.created`
  events
- `implemented`: the operator now exposes only a derived `active_session_record` view from
  canonical session truth, focus, and task linkage
- `verified`: structural regression coverage now enforces that canonical birth must not emit
  `operation.active_session_updated`

Supersession note:

This ADR recorded a transitional gap in the earlier `active_session` dual-write model. Current
repository truth has moved past that model: `active_session` has been retired from durable state,
birth does not emit `operation.active_session_updated`, and the operator derives the active-session
view from canonical session truth instead. The live-session ownership and active-session retirement
direction now lives under [ADR 0170](./0170-session-manager-live-session-ownership-boundary.md).

## Context

ADR 0144 Stage 1 added the `operation.active_session_updated` event and a corresponding projector
slice to make `active_session` event-sourced. All runtime write sites in
`OperationTurnExecutionService`, `AgentResultService`, and `AttachedTurnService` already emitted
this event.

The remaining gap was the initial attached-session path in
`LoadedOperation.attach_initial_sessions()` (`src/agent_operator/application/loaded_operation.py`,
symbol `LoadedOperation.attach_initial_sessions`, lines 34-60), which sets `state.active_session`
after decorating attached sessions.

```python
active = next(
    (record.handle for record in state.sessions if not record.handle.one_shot),
    None,
)
if active is not None:
    state.active_session = active
```

`LoadedOperation` has no event relay and cannot emit events. The method is called at operation
load time, not during a reconcile cycle, so it cannot easily be moved into a service that holds
a relay.

### Consequence: `sync_legacy_active_session` is still load-bearing

`sync_legacy_active_session()` in `OperationRuntimeReconciliationService` was the recovery path
that reconstructed `active_session` from live session state if `state.active_session` was `None`.
It was previously called from `reconcile_state()` at the top of every reconcile cycle.

Before this change, a freshly replayed operation could derive `sessions` and `active_session`
only from mutable fallback state for the initial attached-session path. The canonical checkpoint
after birth did not carry that truth, so replay-only resume depended on the legacy backfill.

### Scope

This debt item is narrowly scoped. It does not affect:

- the `operation.active_session_updated` event path (all runtime write sites are instrumented)
- resume correctness for operations that have already completed at least one reconcile cycle
- the retirement condition for `save_operation()` (ADR 0144)

It does affect:

- strict event-sourced correctness for initial `active_session` on first resume after birth
- the ability to remove `sync_legacy_active_session()` entirely

## Decision

Canonical operation birth must include the initial attached-session state needed for replay-only
resume:

- emit `session.created` for each initial attached session already materialized on `OperationState`
- emit `operation.active_session_updated` when `LoadedOperation.attach_initial_sessions()` selects
  an active session
- keep `LoadedOperation` as the session-selection owner
- remove the legacy reconcile-time `active_session` backfill once replay-only resume is verified

## Prerequisites for resolution

1. The `operation.active_session_updated` projector slice must already be in place.
2. Canonical birth must be able to persist initial session state from `OperationState`.
3. Tests covering initial birth and first replay/resume of the attached-session path must exist.

## Consequences

- Canonical birth now carries initial attached-session truth for replay.
- Replay-only `prepare_run()` and `load_for_resume()` restore the initial attached session and
  `active_session` without mutable-snapshot repair.
- `OperationRuntimeReconciliationService` no longer carries the legacy
  `sync_legacy_active_session()` repair path.

## Closure Evidence Matrix

| ADR closure criterion | Current code evidence | Verification evidence |
| --- | --- | --- |
| Initial attached sessions become canonical at birth | `src/agent_operator/application/event_sourcing/event_sourced_birth.py`, symbol `EventSourcedOperationBirthService.birth`, lines 78-90 append one `session.created` event per `state.sessions`. | `tests/test_event_sourced_birth.py`, `test_event_sourced_operation_birth_appends_initial_event_and_checkpoint`, lines 45-65 asserts `session.created` is stored and projected into the checkpoint. |
| Initial active session becomes canonical at birth | `src/agent_operator/application/event_sourcing/event_sourced_birth.py`, symbol `EventSourcedOperationBirthService.birth`, lines 91-102 append `operation.active_session_updated` when `state.active_session` is set. | `tests/test_event_sourced_birth.py`, `test_event_sourced_operation_birth_appends_initial_event_and_checkpoint`, lines 54-56 asserts projected `checkpoint.active_session.session_id == "session-1"`. |
| The attachment source of truth remains `LoadedOperation` | `src/agent_operator/application/loaded_operation.py`, symbol `LoadedOperation.attach_initial_sessions`, lines 34-60 still decorates attached sessions and selects the first non-one-shot handle into `state.active_session`. | `tests/test_operation_entrypoints.py`, `test_prepare_run_replays_event_sourced_attached_initial_session`, lines 304-323 uses `LoadedOperation.attach_initial_sessions` directly and proves replay preserves its result. |
| Replay path consumes only canonical checkpoint state for initial sessions and active session | `src/agent_operator/projectors/operation.py`, symbols `_apply_session_slice` lines 154-197 and `_apply_active_session_slice` lines 330-343 fold `session.created` and `operation.active_session_updated` into `OperationCheckpoint`; `src/agent_operator/application/operation_entrypoints.py`, symbol `_load_event_sourced`, lines 201-238 rebuilds `OperationState` from the checkpoint without overlaying `sessions` or `active_session` from fallback state. | `tests/test_operation_entrypoints.py`, `test_operation_entrypoint_service_replays_event_sourced_resume_state`, lines 259-280 asserts replayed resume restores both `sessions` and `active_session`; `test_prepare_run_replays_event_sourced_attached_initial_session`, lines 307-323 asserts the same for the initial run path after birth-plus-replay. |
| Legacy reconcile-time backfill is no longer load-bearing | `src/agent_operator/application/runtime/operation_runtime_reconciliation.py`, symbol `OperationRuntimeReconciliationService.reconcile_state`, lines 67-99 no longer calls any `active_session` sync helper, and the previous `sync_legacy_active_session()` helper is removed from the file. | Replay-focused tests above pass without any reconcile-time `active_session` repair. The ADR-relevant suite passes: `pytest -q tests/test_event_sourced_birth.py tests/test_operation_entrypoints.py tests/test_operation_runtime_reconciliation_service.py tests/test_operator_service_shell.py`. |
| Repository-wide behavior remains green after the change | The implementation is localized to canonical birth, replay-driven entrypoint behavior, and removal of the obsolete reconciliation hook. | `uv run pytest` passed with `550 passed, 11 skipped` on 2026-04-13. |

## Verification Notes

- Computed from current codebase by direct file inspection with exact symbol and line references.
- Verified by targeted ADR suite:
  - `pytest -q tests/test_event_sourced_birth.py tests/test_operation_entrypoints.py tests/test_operation_runtime_reconciliation_service.py tests/test_operator_service_shell.py`
- Verified by full repository suite:
  - `uv run pytest`

## Related

- [ADR 0144](./0144-event-sourcing-write-path-contract-and-rfc-0009-closure.md)
- [ADR 0150](./0150-domain-state-machine-simplification.md)
