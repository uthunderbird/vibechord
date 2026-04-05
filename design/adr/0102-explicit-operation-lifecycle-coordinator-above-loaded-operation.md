# ADR 0102: Explicit operation lifecycle coordinator above LoadedOperation

## Status

Accepted

## Context

`ADR 0100` established a stable loaded-operation runtime boundary together with a pluggable
operator-policy layer.

`ADR 0101` then clarified the ideal top application-layer organization:

- `OperatorService` as the system shell and composition root
- `LoadedOperation` as the one-operation runtime boundary for operation-local mechanics
- workflow-authority services as the enduring application capabilities

After those decisions, one lifecycle question remains easy to rediscover:

- when an operation folds, stops, suspends, or terminates for any reason, which one application
  boundary owns the full lifecycle transition sequence?

That question is not hypothetical.

The repository already has partial lifecycle handling in code:

- `OperationCancellationService` handles explicit cancellation paths and can cancel background
  executions through the supervisor/runtime boundary
- `OperationRuntimeReconciliationService` handles stale/orphaned/disconnected external execution
  reconciliation and can finalize background runs
- `OperationDriveService` persists operation progress and writes terminal outcome/history on some
  terminal exits
- `DecisionExecutionService` can set some terminal or blocking operation statuses

But this is still only a composition of partial lifecycle behaviors.

The repository does **not** currently have one explicit application boundary that means:

- "this operation is now folding / suspending / terminating"
- "I own the sequencing of notifications, external finalization, state mutation, persistence,
  outcome projection, and history append"

`LoadedOperation` is also not that boundary today.

It already has a clear and useful role:

- task/session/background/result-slot bookkeeping
- continuation and attachment mechanics
- working-directory and restart-instruction synthesis
- operation-local lookups and mutations

That is an operation-local runtime/mechanics boundary, not a cross-service lifecycle authority.

Promoting `LoadedOperation` directly into a full lifecycle owner would mix:

- one-operation local mechanics
- and cross-service lifecycle choreography involving supervisor/runtime finalization,
  notifications, persistence, and outcome/history closure

That would weaken a boundary that is currently becoming clearer.

The missing decision is therefore not "should current composition be considered good enough" and
not "should `LoadedOperation` absorb everything".

The missing decision is:

- whether to introduce an explicit one-operation lifecycle authority above `LoadedOperation`

and what that authority should own.

## Decision

`operator` should introduce an explicit `OperationLifecycleCoordinator` above `LoadedOperation`.

`OperationLifecycleService` is an acceptable implementation name if the repository prefers
consistency with existing service naming, but the architectural role is:

- one-operation lifecycle authority

not generic context management.

### What the lifecycle coordinator owns

The lifecycle coordinator owns the sequencing of operation-wide lifecycle transitions for one
loaded operation.

That includes:

- full operation cancellation sequencing
- terminal completion/failure closure sequencing
- suspension/blocking closure paths when notification and persistence matter
- external execution finalization/reconciliation when it causes an operation-level transition
- lifecycle-significant notifications
- persistence, outcome, and history sequencing for those transitions

This means the lifecycle coordinator becomes the explicit answer to questions such as:

- who owns shutting down or finalizing the active participants of one operation
- who owns folding those results into operation state
- who owns making the resulting operation transition durable

### What remains in `LoadedOperation`

`LoadedOperation` remains the owner of one-operation local runtime mechanics.

It continues to own:

- task/session/background/result-slot state access and mutation
- continuation/focus/attachment rules
- operation-local derived lookups
- working-directory and restart-instruction helpers

It does **not** become the owner of:

- lifecycle choreography across multiple workflow authorities
- process-wide notification/finalization sequencing
- outcome/history closure
- or top-level lifecycle transition authority

### What remains outside the lifecycle coordinator

The lifecycle coordinator does not replace the rest of the application architecture.

The following remain outside it:

- `OperatorService`
  - public entrypoints
  - top-level graph assembly
  - shell/composition concerns
- `OperatorPolicy`
  - internal operator decision/evaluation policy
- workflow-authority services
  - decision execution
  - command application
  - result handling
  - runtime reconciliation
  - traceability
- process-wide infrastructure boundaries
  - stores
  - history ledger
  - event relay
  - wakeup signaling
  - supervisor/runtime host

The lifecycle coordinator composes these collaborators where needed for one lifecycle transition.

It does not replace them as independent authorities.

In particular, lower runtime-side terminal-finalization mechanics remain outside the lifecycle
coordinator:

- `OperationRuntimeReconciliationService` may still call `finalize_background_turn(...)` on the
  operation runtime / supervisor boundary
- that work is treated as runtime-reconciliation mechanics, not as operation-level lifecycle
  authority

The lifecycle coordinator owns the operation-facing transition sequence around those terminal
results, but it does not absorb the lower supervisor cleanup protocol itself.

### API shape guidance

The lifecycle coordinator should expose a small public surface organized around transition
families, not helper verbs.

Representative operations may include:

- `cancel_operation(...)`
- `suspend_operation(...)`
- `finalize_terminal_outcome(...)`
- `reconcile_external_terminal_signal(...)`

The exact method names are implementation details.

The important architectural rule is that the public surface should describe lifecycle transitions,
not degenerate into another bag of helper methods.

## Alternatives Considered

### Treat the current composition as already sufficient lifecycle authority

Rejected.

The repository currently has partial lifecycle logic spread across drive, cancellation,
reconciliation, and decision execution paths.

That means lifecycle handling exists, but the lifecycle authority is still implicit rather than
explicit.

This is not a stable architectural answer for future contributors.

### Promote `LoadedOperation` into the lifecycle authority

Rejected.

`LoadedOperation` already has a useful, narrower meaning as the owner of one-operation local
mechanics.

Expanding it into the owner of:

- external execution finalization
- notifications
- persistence/outcome/history closure
- and cross-service lifecycle sequencing

would mix two different concerns and risk creating a new blob where a cleaner boundary already
exists.

### Introduce a generic operation-wide context manager

Rejected.

The repository does not need a passive context bag or a vaguely named "manager" that merely
collects dependencies.

The missing abstraction is a lifecycle authority with a narrow sequencing contract, not a generic
context object.

## Consequences

- The repository gains an explicit architectural home for operation-wide lifecycle closure instead
  of relying on implicit composition across several services.
- `LoadedOperation` can remain a focused one-operation mechanics boundary instead of absorbing
  cross-service lifecycle choreography.
- `OperatorService` can continue shrinking toward a true shell because lifecycle sequencing no
  longer needs to remain spread across shell-adjacent glue.
- The implementation wave that follows must be careful not to turn the lifecycle coordinator into a
  second shell or a new bag-of-collaborators object.
- Current repository truth now materially matches this ADR:
  - `implemented`: `OperationLifecycleCoordinator` exists in code
  - `implemented`: durable terminal closure (`save_operation` / `save_outcome` / history append)
    is centralized there
  - `implemented`: most explicit top-level status transitions now route through the coordinator,
    including `RUNNING`, `COMPLETED`, `FAILED`, `CANCELLED`, and `NEEDS_HUMAN` paths in drive,
    decision, command, result, and snapshot-command flows
  - `implemented`: whole-operation and scoped session/run cancellation sequencing now route through
    lifecycle coordination
  - `implemented`: repeated post-reconciliation terminal fold logic now routes through lifecycle
    coordination
  - `implemented`: supervisor/runtime-side terminal-finalization mechanics remain in
    reconciliation/runtime layers by design rather than as an unresolved lifecycle-coordinator gap
