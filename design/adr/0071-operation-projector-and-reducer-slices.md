# ADR 0071: Operation projector and reducer slices

## Status

Accepted

## Context

[`RFC 0009`](../rfc/0009-operation-event-sourced-state-model-and-runtime-architecture.md)
chooses:

- one canonical domain event stream per operation
- one derived replay target: `OperationCheckpoint`
- one projector with reducer slices rather than many canonical mini-projectors

[`ADR 0069`](./0069-operation-event-store-and-checkpoint-store-contracts.md) defines the event and
checkpoint storage contract. [`ADR 0070`](./0070-fact-store-and-fact-translator-contracts.md)
defines how runtime observations become domain events. The next unresolved executable boundary is
the projector itself:

- what `OperationProjector` is responsible for
- what counts as a reducer slice
- how slices interact
- what purity guarantees apply
- where side effects and follow-up actions are allowed to live

Without this ADR, the implementation can still regress into the same core failure mode under a new
shape:

- a large projector with hidden side effects and procedural transition ordering

The reducer boundary must therefore be explicit.

## Decision

### One canonical projector per operation stream

Each operation stream is folded by exactly one canonical projector: `OperationProjector`.

`OperationProjector` is responsible for:

- loading an initial checkpoint or empty initial state
- applying a sequence of domain events in order
- producing a new `OperationCheckpoint`

It is not responsible for:

- reading adapter facts directly
- translating technical facts into domain events
- issuing commands
- mutating stores other than writing the derived checkpoint result

### Reducer slices are pure functions

`OperationProjector` is composed from reducer slices. Each reducer slice is a pure function over:

- prior checkpoint substate
- one domain event

and returns:

- updated checkpoint substate

Minimum reducer slices:

- operation reducer slice
- task reducer slice
- session reducer slice
- execution reducer slice
- attention reducer slice
- scheduler reducer slice

Operation-owned canonical substates may be handled as additional slices or sub-slices:

- operator-message context slice
- policy applicability slice

This ADR fixes the semantic boundary, not the final Python module layout.

### Input and output contract

The projector contract is:

```text
(OperationCheckpoint, DomainEvent[]) -> OperationCheckpoint
```

At the per-event step:

```text
(OperationCheckpoint, DomainEvent) -> OperationCheckpoint
```

The projector must be deterministic:

- same input checkpoint
- same ordered event suffix
- same output checkpoint

### Cross-slice coordination rule

Reducer slices may update different checkpoint regions in response to the same domain event.

Example:

- an attention-related domain event may update both attention state and operation status
- an execution-related domain event may update both execution state and session state

But that coordination must still happen inside the pure fold of the event. It must not require:

- hidden service calls
- runtime polling
- process-manager callbacks
- read-model lookups

If an event has business consequences across multiple substates, the projector applies them in one
deterministic fold step.

### Reducers do not emit side effects

Reducer slices and the projector may not:

- emit commands
- read or write facts
- mutate read models
- append new domain events
- perform I/O beyond the derived checkpoint write that occurs after the fold completes

Follow-up actions belong to process managers, not reducers.

### Process manager boundary

If a domain event implies further work, the projector does not perform it. Instead:

- projector folds the event into canonical state
- process managers observe the new domain event and/or updated checkpoint
- process managers decide whether to issue commands

Examples:

- `ExecutionObservedStateChanged(... -> lost)` may cause `ExecutionProcessManager` to issue a
  recovery-related command
- `AttentionRequestResolved` may cause `PlanningProcessManager` to issue a replanning command

The projector records consequences in state; process managers decide follow-up actions.

### Replay boundary

Canonical replay uses:

- empty initial state or latest checkpoint
- ordered suffix of domain events

No projector logic may depend on:

- technical facts
- trace records
- read models
- wall-clock side effects
- adapter-specific payload shape

If a fold would require any of those inputs, the missing business consequence belongs in domain
translation before the projector stage.

### Invariant ownership

Business invariants about canonical state belong in reducer slices and projector tests.

Examples:

- task state transitions must be valid with respect to dependencies
- session and execution state must remain mutually consistent
- operation status and blocking attention state must remain mutually consistent
- scheduler state transitions must be valid

Runtime and orchestration invariants do not belong here.

Examples:

- when to poll the background supervisor
- when to retry translation
- when to call the brain

Those belong to runtime coordination and process managers.

### Checkpoint shape rule

`OperationProjector` produces `OperationCheckpoint`, not a convenience snapshot with embedded
trace and runtime detail.

Specifically, the projector must not silently accumulate:

- raw runtime progress strings
- wakeup bookkeeping
- trace brief bundles
- forensic report content

The repository now includes a foundation implementation for this boundary:

- a typed `OperationCheckpoint`
- a pure `OperationProjector` protocol
- a `DefaultOperationProjector` composed from reducer-slice methods
- focused projector tests covering deterministic replay and cross-slice coordination

This establishes the fold contract without yet replacing the current `OperatorService`
mutation path.

Those belong to separate read-model or technical surfaces even if they are currently co-located in
`OperationState`.

## Consequences

- business mutation semantics move out of `OperatorService` helper ordering and into explicit pure
  reducer slices
- replay behavior becomes testable as pure fold logic
- process managers become the only place where event-driven follow-up actions are chosen
- state and side effects get a hard boundary
- current `OperationState` fields that are not replay-safe become pressure points for extraction

## Verification

Current repository truth:

- `implemented`: `OperationProjector` protocol defines the pure fold contract
- `implemented`: `DefaultOperationProjector` provides deterministic reducer-slice-based folding for
  operation, task, session, execution, attention, scheduler, operator-message, and policy slices
- `verified`: `tests/test_operation_projector.py` covers deterministic replay, cross-slice
  execution/session coordination, and attention/scheduler/operator-message/policy folding
- `partial`: the current `OperatorService` still uses the legacy mutation path as the main runtime
  write model; projector-based canonical replay is established as a foundation boundary but is not
  yet the repository-wide execution path

`Accepted` here means the projector contract and foundation fold implementation are settled. It
does not claim that the entire operator runtime has already been switched to projector-first
canonical mutation.

## Alternatives Considered

### Many canonical projectors, one per child entity

Rejected for now. This would reopen coordination complexity that RFC 0009 explicitly deferred.

### Single monolithic reducer function with no slice boundaries

Rejected. It would preserve the same maintainability problem under a smaller file count.

### Allow reducers to emit follow-up commands

Rejected. This mixes state folding with orchestration and recreates hidden side effects.

### Let projector depend on technical facts during replay

Rejected. This violates the checkpoint and canonical replay contract defined by RFC 0009 and ADR
0069.
