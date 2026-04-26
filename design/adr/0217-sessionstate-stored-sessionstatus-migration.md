# ADR 0217: SessionState stored `SessionStatus` migration

- Date: 2026-04-27

## Decision Status

Accepted

## Implementation Status

Verified

Skim-safe current truth on 2026-04-27:

- `implemented`: `SessionState` now stores one durable `status: SessionStatus` field in
  `src/agent_operator/domain/operation.py`
- `implemented`: legacy serialized two-field session payloads still load through a compatibility
  upgrade path into the one-field stored model
- `implemented`: projector, lifecycle, cancellation, aggregate, and replay paths in this slice no
  longer require stored `observed_state` / `terminal_state` fields
- `verified`: targeted migration regressions and the full `uv run pytest` suite pass at the
  repository state that closes this ADR

## Context

ADR 0150 closed the dead-field cleanup wave:

- `ObjectiveState.status` was removed
- `SessionState.desired_state` was removed
- dead `FeatureStatus` values were removed

That ADR deliberately deferred the larger session-lifecycle storage simplification:

> `SessionState` two-field → single `status` migration

Before this slice, repository truth stored session lifecycle in two fields:

- `observed_state: SessionObservedState`
- `terminal_state: SessionTerminalState | None`

That shape lived in `src/agent_operator/domain/operation.py` and required conversion logic:

- `_upgrade_legacy_session_record()` maps legacy serialized `status` values into the two-field
  storage shape
- the computed `SessionState.status` property maps the two stored fields back into
  `SessionStatus`
- the `status` setter maps the public `SessionStatus` interface back down into
  `observed_state` plus `terminal_state`

Repository truth at proposal time therefore already exposed the simpler interface while keeping the
more complex storage model underneath it.

Current code evidence:

- `src/agent_operator/domain/operation.py:226` stores `observed_state` and `terminal_state`
- `src/agent_operator/domain/operation.py:250` upgrades legacy serialized `status` into the
  two-field storage model
- `src/agent_operator/domain/operation.py:287` computes `SessionState.status` from the two-field
  storage model
- `src/agent_operator/domain/operation.py:301` maps assigned `SessionStatus` values back into the
  two-field storage model

Current verification evidence:

- `tests/test_runtime.py::test_legacy_session_status_upgrades_without_desired_state` verifies the
  legacy-upgrade path and the computed `status` interface
- `tests/test_operation_projector.py::test_operation_projector_coordinates_execution_and_session_slices`
  covers projector behavior against the current session lifecycle shape
- broad repository usage already treats `SessionStatus` as the application-facing contract in
  commands, runtime, query, CLI, and TUI tests

This means the remaining simplification is no longer a product or behavior discovery problem. It
is a storage-shape migration problem.

## Decision

Migrate `SessionState` to one stored `status: SessionStatus` field and retire
`observed_state + terminal_state` from persistent domain storage.

### Target model

`SessionState` should store:

- `status: SessionStatus`

and should no longer persist:

- `observed_state`
- `terminal_state`

The existing public `SessionStatus` interface is the correct durable storage field because it
already expresses the only six valid session lifecycle states the repository actually uses:

- `IDLE`
- `RUNNING`
- `WAITING`
- `COMPLETED`
- `FAILED`
- `CANCELLED`

### Migration constraints

1. Legacy serialized session payloads that still contain only `observed_state` and
   `terminal_state` must continue to load correctly during the migration window.
2. Query, runtime, and command code that already consumes `SessionState.status` should remain
   behaviorally unchanged.
3. New code must not introduce fresh read-path branching on the two-field storage model.
4. The migration should not reintroduce an aspirational desired/observed split through another
   field.

### Scope of this ADR

This ADR covers only the `SessionState` storage simplification.

It does not change:

- `ExecutionObservedState`
- background-run lifecycle
- scheduler-state persistence
- session-manager ownership boundaries from ADR 0170

## Consequences

### Positive

- the durable session model matches the already-public interface
- invalid `observed_state` / `terminal_state` combinations disappear from storage
- lifecycle persistence and projection logic become simpler
- replay and test fixtures become easier to reason about

### Negative

- the migration touches central domain, projector, runtime-reconciliation, and fixture paths
- legacy payload upgrade logic must be kept honest during the transition
- this cannot be treated as a docs-only status flip; it needs a feature-sized code slice

### Neutral / Follow-on

- if the migration succeeds, ADR 0150's remaining session-lifecycle note can retire
- RFC 0005 should then be re-read and either updated or marked stale where it still assumes
  `desired_state`

## Implementation Plan

The minimal truthful implementation wave should:

1. add stored `status: SessionStatus` to `SessionState`
2. keep legacy upgrade logic for serialized two-field payloads during the migration
3. migrate projector, lifecycle, reconciliation, and query paths off direct
   `observed_state` / `terminal_state` storage access
4. remove the two old stored fields once the full repository passes on the new shape

## Closure Criteria

This ADR can move to `Implemented` when:

1. `SessionState` persists one stored `status: SessionStatus` field
2. legacy two-field serialized payloads still load successfully
3. projector, lifecycle, reconciliation, and query paths no longer require stored
   `observed_state` / `terminal_state`

This ADR can move to `Verified` when:

1. targeted regression tests prove legacy upgrade and new storage coexist correctly
2. targeted regression tests prove projector/replay behavior still reconstructs canonical session
   truth correctly
3. `uv run pytest` passes

## Alternatives Considered

### Keep the two-field storage model indefinitely

Rejected.

The repository already exposes `SessionStatus` as the real interface. Keeping the more complex
storage model indefinitely preserves invalid intermediate combinations without adding behavioral
value.

### Collapse session and execution lifecycle into one larger migration

Rejected for this slice.

That would raise the blast radius unnecessarily. The truthful next step is the smaller
`SessionState` storage simplification only.

## Closure Evidence Matrix

| Follow-on claim | Current repository evidence | Verification evidence |
| --- | --- | --- |
| `SessionState` persists one durable `status: SessionStatus` field | `src/agent_operator/domain/operation.py` `SessionState.status` | direct code inspection |
| Legacy serialized two-field payloads still load into the new stored model | `src/agent_operator/domain/operation.py` `_upgrade_legacy_session_record()` | `tests/test_runtime.py::test_legacy_two_field_session_status_upgrades_to_stored_status_only` |
| Legacy serialized `status` payloads still load without reintroducing removed fields | `src/agent_operator/domain/operation.py` `_upgrade_legacy_session_record()` | `tests/test_runtime.py::test_legacy_session_status_upgrades_without_desired_state` |
| Projector and replay paths reconstruct canonical session truth without stored two-field state | `src/agent_operator/projectors/operation.py`; `src/agent_operator/application/operation_lifecycle.py` | `tests/test_operation_projector.py::test_operation_projector_coordinates_execution_and_session_slices`; `tests/test_operation_entrypoints.py::test_targeted_cancel_persists_session_status_via_event_sourced_replay` |
| Aggregate session event application stays compatible with legacy event payloads while storing canonical `status` | `src/agent_operator/domain/aggregate.py` | `tests/test_operation_aggregate.py::test_session_registered_via_event` |
| ADR closure is verified against the current repository state | changed implementation under `src/agent_operator/...`; this ADR document | `uv run pytest tests/test_runtime.py tests/test_operation_projector.py tests/test_operation_entrypoints.py tests/test_operation_aggregate.py`; `uv run pytest` |

## Related

- [ADR 0150](./0150-domain-state-machine-simplification.md)
- [ADR 0170](./0170-session-manager-live-session-ownership-boundary.md)
- [RFC 0005](../rfc/0005-session-execution-data-model.md)
