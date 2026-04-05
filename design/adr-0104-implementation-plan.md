# ADR 0104 Implementation Plan

## Goal

Complete the remaining top application/control-layer boundaries so
[service.py](../src/agent_operator/application/service.py) stops acting as the main callback and
control hub.

This wave is not a line-count cleanup exercise.

The goal is to make shell thinning a consequence of cleaner authority placement.

## Target Outcome

After this wave:

- `OperatorService` is a real shell/composition root
- `OperationLifecycleCoordinator` owns operation-wide lifecycle closure
- `OperationControlStateCoordinator` owns control/checkpoint/state synchronization
- runtime gating / runtime context has a named non-shell home
- current drive/runtime/control/trace collaborators depend on direct collaborators rather than
  shell-hosted wrappers

## Phase 1: OperationControlStateCoordinator

Add a new collaborator:

- `OperationControlStateCoordinator`

Recommended file:

- [src/agent_operator/application/operation_control_state.py](../src/agent_operator/application/operation_control_state.py)

First responsibilities:

- command-effect persistence sequencing
- processed-command tracking
- checkpoint-to-`OperationState` refresh rules

First methods to absorb from
[service.py](../src/agent_operator/application/service.py):

- `_persist_command_effect_state`
- `_remember_processed_command`
- `_refresh_state_from_checkpoint`

First rewiring targets:

- [src/agent_operator/application/operation_commands.py](../src/agent_operator/application/operation_commands.py)
- event-sourced command application paths that still depend on shell-owned refresh/persist glue

Constraint:

- this is not a generic persistence service
- it is specifically the control/checkpoint/state alignment boundary

Current status:

- `implemented`

## Phase 2: Runtime Gating / Runtime Context Capability

Add a smaller capability collaborator.

Recommended file:

- [src/agent_operator/application/operation_runtime_context.py](../src/agent_operator/application/operation_runtime_context.py)

Acceptable alternative:

- [src/agent_operator/application/operation_runtime_gating.py](../src/agent_operator/application/operation_runtime_gating.py)

Responsibilities:

- background wait detection
- attached-turn wait detection
- recoverable retry eligibility
- recoverable session resolution
- runtime mode predicates
- available-agent descriptor projection / runtime capability context

First methods to absorb from
[service.py](../src/agent_operator/application/service.py):

- `_refresh_available_agent_descriptors`
- `_is_blocked_on_background_wait`
- `_is_waiting_on_attached_turn`
- `_should_use_background_runtime`
- `_uses_resumable_wakeup_runtime`
- `_should_retry_from_recoverable_block`
- `_resolve_recoverable_session_for_retry`

First rewiring targets:

- [src/agent_operator/application/decision_execution.py](../src/agent_operator/application/decision_execution.py)
- [src/agent_operator/application/operation_runtime_reconciliation.py](../src/agent_operator/application/operation_runtime_reconciliation.py)
- [src/agent_operator/application/operation_traceability.py](../src/agent_operator/application/operation_traceability.py)
- [src/agent_operator/application/operation_drive_runtime.py](../src/agent_operator/application/operation_drive_runtime.py)

Constraint:

- keep this as a capability boundary first
- do not promote it to a heavyweight peer authority unless later code pressure proves that
  necessary

Current status:

- `implemented`

## Phase 3: OperationLifecycleCoordinator

Add a new collaborator:

- `OperationLifecycleCoordinator`

Recommended file:

- [src/agent_operator/application/operation_lifecycle.py](../src/agent_operator/application/operation_lifecycle.py)

Responsibilities:

- cancel / suspend / terminate sequencing
- external execution finalization when it causes operation transition
- lifecycle-significant event/wakeup/process notification sequencing
- persistence + outcome + history closure for lifecycle transitions

First migration slice:

- move shell-owned lifecycle-adjacent sequencing out of
  [service.py](../src/agent_operator/application/service.py)
- absorb the sequencing burden that is currently split across
  [src/agent_operator/application/operation_cancellation.py](../src/agent_operator/application/operation_cancellation.py),
  [src/agent_operator/application/operation_runtime_reconciliation.py](../src/agent_operator/application/operation_runtime_reconciliation.py),
  and terminal closure edges in
  [src/agent_operator/application/operation_drive.py](../src/agent_operator/application/operation_drive.py)

Constraint:

- public API should be transition-shaped, not helper-shaped
- do not turn this into a second shell

Current status:

- `implemented`

Implemented so far:

- durable terminal closure sequencing
- full-operation cancel closure
- scoped session/run cancellation sequencing
- repeated post-reconciliation terminal fold sequencing
- centralized status-transition helpers for `RUNNING`, `COMPLETED`, `FAILED`, `CANCELLED`, and
  `NEEDS_HUMAN`
- cutover of drive, decision, command, result, and snapshot-command explicit transition paths

Remaining gap:

- no remaining `ADR 0102` gap is required for `ADR 0104`
- lower supervisor/runtime-side terminal-finalization mechanics remain in
  reconciliation/runtime layers by design

## Phase 4: Remove Shell-Hosted Callback Wiring

After the three boundaries above exist, rewire current collaborators so they depend on direct
collaborators instead of `OperatorService._foo` methods.

Priority rewiring targets:

- [src/agent_operator/application/operation_commands.py](../src/agent_operator/application/operation_commands.py)
- [src/agent_operator/application/operation_runtime_reconciliation.py](../src/agent_operator/application/operation_runtime_reconciliation.py)
- [src/agent_operator/application/decision_execution.py](../src/agent_operator/application/decision_execution.py)
- [src/agent_operator/application/operation_turn_execution.py](../src/agent_operator/application/operation_turn_execution.py)
- [src/agent_operator/application/operation_traceability.py](../src/agent_operator/application/operation_traceability.py)
- [src/agent_operator/application/operation_drive_runtime.py](../src/agent_operator/application/operation_drive_runtime.py)
- [src/agent_operator/application/operation_drive_trace.py](../src/agent_operator/application/operation_drive_trace.py)
- [src/agent_operator/application/operation_drive_control.py](../src/agent_operator/application/operation_drive_control.py)

Acceptance target:

- collaborators depend on real collaborators
- not on shell-hosted callback bridges

## Phase 5: Reassess Drive-Layer Collaborators

After callback cutover, reassess:

- which drive collaborators remain useful as-is
- which should delegate to the new boundaries directly
- which were only transitional cut-lines

Expected likely result:

- `OperationDriveRuntime` becomes thinner and delegates to:
  - lifecycle coordination where needed
  - runtime-context capability
  - runtime reconciliation
- `OperationDriveTrace` and `OperationDriveControl` may remain as local loop-facing collaborators if
  they still provide a clean surface

Do not rename or merge them only for aesthetics.

## Phase 6: Final Shell Cleanup

Reduce [service.py](../src/agent_operator/application/service.py) to shell truth:

- constructor/composition root
- `run`
- `resume`
- `recover`
- `tick`
- `cancel`
- `_drive_state`
- only minimal top-level loading/delegation helpers that are genuinely shell concerns

Everything else should either:

- move to one of the new boundaries
- or disappear as obsolete callback glue

## Delivery Order

Recommended order:

1. `OperationControlStateCoordinator`
2. runtime gating / runtime context capability
3. `OperationLifecycleCoordinator`
4. direct collaborator rewiring away from shell callbacks
5. drive-layer reassessment
6. final dead-code cleanup in [service.py](../src/agent_operator/application/service.py)
7. docs sync for [design/ARCHITECTURE.md](./ARCHITECTURE.md),
   [design/adr/0102-explicit-operation-lifecycle-coordinator-above-loaded-operation.md](./adr/0102-explicit-operation-lifecycle-coordinator-above-loaded-operation.md),
   and
   [design/adr/0104-top-application-control-layer-boundary-completion-after-shell-thinning.md](./adr/0104-top-application-control-layer-boundary-completion-after-shell-thinning.md)

Why this order:

- control-state and runtime-context are the safest, most local extractions
- lifecycle is broader and should land after the shell is less entangled
- final shell cleanup should happen after rewiring, not before

## Current progress

- `implemented`: Phase 1
- `implemented`: Phase 2
- `partial`: Phase 3
- `implemented`: most of Phase 4
- `implemented`: most of Phase 6 as far as shell callback-hosting is concerned

Current repository truth:

- [service.py](../src/agent_operator/application/service.py) is now roughly shell-sized
- the remaining private-method tail is down to:
  - `_drive_state`
  - `_merge_runtime_flags`
- the main remaining architectural gap is no longer shell relay hosting, but the narrower
  lifecycle-sequencing tail tracked by `ADR 0102`

## Tests

Add dedicated tests:

- `tests/test_operation_control_state_coordinator.py`
- `tests/test_operation_runtime_context.py` or `tests/test_operation_runtime_gating.py`
- `tests/test_operation_lifecycle_coordinator.py`

Update existing tests:

- [tests/test_operation_command_service.py](../tests/test_operation_command_service.py)
- [tests/test_operation_runtime_reconciliation_service.py](../tests/test_operation_runtime_reconciliation_service.py)
- [tests/test_decision_execution_service.py](../tests/test_decision_execution_service.py)
- [tests/test_operation_drive_service.py](../tests/test_operation_drive_service.py)
- [tests/test_operator_service_shell.py](../tests/test_operator_service_shell.py)
- [tests/test_service.py](../tests/test_service.py)

Verification gate after each slice:

- run touched files plus shell smoke tests

Final gate:

```bash
UV_CACHE_DIR=/tmp/uv-cache uv run pytest -q
```

## Non-Goals

- Do not treat this as a DI/container migration wave.
- Do not introduce a universal command-pattern rewrite.
- Do not extract a builder/assembler layer as part of this wave.
- Do not promote every helper cluster into a heavyweight service noun.

## Main Risks

- `OperationLifecycleCoordinator` becoming a second shell
- `OperationControlStateCoordinator` turning into a generic persistence bag
- overpromoting runtime gating into a heavyweight pseudo-architecture
- shrinking `service.py` cosmetically without actually changing dependency direction
