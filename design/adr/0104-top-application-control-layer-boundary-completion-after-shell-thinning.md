# ADR 0104: Top application/control-layer boundary completion after shell thinning

## Decision Status

Accepted

## Implementation Status

Implemented

## Context

`ADR 0099` extracted the major workflow-authority services from `OperatorService`.

`ADR 0100` established `LoadedOperation` plus a pluggable operator-policy seam.

`ADR 0101` described the ideal top application-layer organization.

`ADR 0102` identified one missing explicit authority above `LoadedOperation`:

- operation-wide lifecycle coordination

Those decisions materially improved the architecture, and the code now reflects much of that
direction.

At proposal time, the current repository truth was still not a fully honest shell boundary in
`OperatorService`.

`OperatorService` was smaller than before, but still remained the host for:

- callback-shaped collaborator wiring
- top-layer runtime/control glue
- and several private methods with real behavior rather than mere assembly

The remaining shell residue was not random.

Code in [service.py](../../src/agent_operator/application/service.py) still clustered around three
distinct responsibility families:

1. lifecycle closure
2. control-state synchronization and persistence
3. runtime gating / runtime context projection

The repository already has partial cuts around these concerns:

- drive runtime/control/trace collaborators
- event relay
- process-signal dispatch
- attention coordination
- policy-context coordination
- turn execution

But the shell still acts as a callback nexus among them.

The result is that `OperatorService` is now smaller, yet still not a true façade in the strict
architectural sense.

This ADR is therefore not about shrinking one file cosmetically.

It is about deciding how to complete the remaining top application/control layer so that shell
thinning becomes a consequence of cleaner authority placement rather than an endless local cleanup
exercise.

## Decision

The remaining top application/control layer should be completed by introducing and stabilizing the
missing authority boundaries above `LoadedOperation`, rather than by continuing shell-local cleanup
indefinitely.

The intended final shape is:

1. `OperatorService` remains the system shell and composition root
2. `OperationLifecycleCoordinator` becomes the enduring authority for operation-wide lifecycle
   closure
3. `OperationControlStateCoordinator` becomes the enduring authority for control-state
   synchronization and persistence
4. runtime gating / runtime context logic becomes a named capability boundary, but not necessarily
   a heavyweight top-level authority peer
5. current drive runtime/control/trace splits are treated as transitional collaborator cut-lines
   unless later evidence proves them to be enduring top-level authorities

### 1. `OperatorService` remains the shell

`OperatorService` should retain:

- public entrypoints
- top-level loading and delegation
- graph assembly / composition-root responsibilities

It should not remain the default host for:

- callback relay methods between collaborators
- control-state synchronization logic
- lifecycle sequencing
- runtime gating predicates
- traceability or reconciliation helper forwarding

### 2. `OperationLifecycleCoordinator` is one enduring missing authority

`ADR 0102` already establishes this boundary.

It remains part of the top-layer completion story because lifecycle closure is still one of the
main reasons the shell retains architectural gravity.

Current repository truth:

- `implemented`: the coordinator now exists in code and already owns durable terminal closure plus
  most explicit operation-status transitions
- `partial`: broader reconcile-driven lifecycle sequencing and scoped execution-cancellation
  sequencing are still split across adjacent services

### 3. `OperationControlStateCoordinator` is the second enduring missing authority

There is a distinct top-layer concern around synchronizing durable control/checkpoint truth with
the in-memory operation view.

This authority owns concerns such as:

- command-effect persistence sequencing
- processed-command tracking
- checkpoint-to-`OperationState` refresh rules
- related control-state refresh or projection logic where the issue is durable-state alignment
  rather than planning semantics

This is not the same concern as:

- lifecycle closure
- `LoadedOperation` local mechanics
- or generic workflow execution

It should therefore have its own explicit home.

### 4. Runtime gating / runtime context is a capability boundary

Some remaining shell logic is real but does not obviously deserve the same architectural weight as
lifecycle or control-state coordination.

This includes:

- waiting-on-attached/background determination
- recoverable retry eligibility
- runtime mode predicates
- available-agent descriptor projection / runtime capability context

This boundary should still be named and moved out of the shell, but the repository should avoid
inflating it into a heavyweight top-level authority unless later evidence requires that.

The default assumption is:

- capability boundary first
- peer authority only if code reality later proves that necessary

### 5. Transitional collaborators should be treated honestly

Current drive runtime/control/trace collaborators are useful refactoring cuts.

But they should not automatically be treated as the final architecture just because they already
exist.

Until their ownership becomes direct rather than shell-hosted callback wiring, they should be
treated as transitional collaborators that helped narrow surfaces, not as proof that the top layer
is already fully organized.

## Alternatives Considered

### Continue shell thinning locally without naming further boundaries

Rejected.

Current code evidence shows that the remaining shell residue is clustered and semantically
meaningful.

Continuing local cleanup without naming the missing boundaries would preserve the current callback
hub shape and make future contributors rediscover the same problem again.

### Treat lifecycle coordination as the only missing top-layer authority

Rejected.

Lifecycle is one important missing boundary, but it does not explain the remaining control-state
and runtime-gating clusters that still live in or through the shell.

`ADR 0102` is therefore necessary but not sufficient.

### Elevate every remaining cluster into a top-level peer service

Rejected.

Not every remaining predicate or helper cluster deserves heavyweight architectural status.

In particular, runtime gating / runtime context should begin as a named capability boundary rather
than being prematurely promoted to the same narrative weight as lifecycle or control-state
coordination.

### Treat the problem primarily as DI/container migration

Rejected.

Manual wiring contributes to constructor size, but current code shows that the dominant issue is
still authority placement and callback hosting rather than composition tooling.

`ADR 0103` remains relevant, but it is not the main answer to the surviving shell residue.

## Consequences

- The repository gets a clearer explanation for why `OperatorService` had remained too heavy even
  after major extraction waves.
- Future refactors can target missing authorities rather than chasing line count.
- `ADR 0102` becomes one part of a broader top-layer completion story instead of being mistaken for
  the whole remaining problem.
- The next implementation waves should prioritize:
  - explicit lifecycle coordination
  - explicit control-state coordination
  - extracting runtime gating/context as a named capability boundary
- The repository should avoid promoting every extracted collaborator into a top-level architectural
  noun; enduring authorities and smaller capability boundaries must remain distinct.
- Current repository truth now materially matches this ADR:
  - `implemented`: `OperationControlStateCoordinator` exists in
    [operation_control_state.py](../../src/agent_operator/application/commands/operation_control_state.py)
    and owns control/checkpoint synchronization concerns such as checkpoint refresh and legacy
    command-effect persistence
  - `implemented`: `OperationRuntimeContext` exists in
    [operation_runtime_context.py](../../src/agent_operator/application/runtime/operation_runtime_context.py)
    and owns runtime gating/runtime capability projection concerns
  - `implemented`: `OperationLifecycleCoordinator` exists in
    [operation_lifecycle.py](../../src/agent_operator/application/operation_lifecycle.py) and owns
    terminal lifecycle closure and cancellation sequencing
  - `implemented`: `OperatorService` remains a shell in
    [service.py](../../src/agent_operator/application/service.py), delegating public entrypoints to
    entrypoint/drive/cancellation collaborators and keeping only `_drive_state` and
    `_merge_runtime_flags` as private methods beyond `__init__`
  - `verified`: [tests/test_operator_service_shell.py](../../tests/test_operator_service_shell.py)
    asserts that `OperatorService` exposes only `run`, `resume`, `recover`, `tick`, `cancel`, and
    `answer_question` as public methods and only `_drive_state` and `_merge_runtime_flags` as
    private methods
  - `verified`: [tests/test_operation_control_state.py](../../tests/test_operation_control_state.py)
    exercises canonical control-state persistence through `OperationControlStateCoordinator`
  - `verified`: [tests/test_operation_lifecycle.py](../../tests/test_operation_lifecycle.py)
    exercises terminal outcome persistence and event-sourced cancellation through
    `OperationLifecycleCoordinator`

Skim-safe current truth on 2026-04-12:

- `implemented`: `OperatorService` remains a thin shell with 6 public methods and 2 private
  methods beyond `__init__`; public entrypoints delegate to entrypoint, drive, cancellation, and
  brain collaborators
- `implemented`: `OperationLifecycleCoordinator`, `OperationControlStateCoordinator`, and
  `OperationRuntimeContext` are all present as explicit application boundaries
- `verified`: focused tests cover the shell boundary, lifecycle persistence, and control-state
  coordination; `Verified` remains gated on a green full `uv run pytest` run
