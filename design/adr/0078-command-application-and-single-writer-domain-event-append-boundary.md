# ADR 0078: Command application and single-writer domain-event append boundary

## Status

Accepted

## Context

[`RFC 0009`](../rfc/0009-operation-event-sourced-state-model-and-runtime-architecture.md)
requires canonical business mutation to happen through domain events rather than procedural
mutation of `OperationState` inside `OperatorService`.

[`ADR 0069`](./0069-operation-event-store-and-checkpoint-store-contracts.md) already fixes event
store sequencing and checkpoint derivation. [`ADR 0073`](./0073-command-bus-and-planning-trigger-semantics.md)
already fixes how durable control intents enter the system. The missing boundary is the command
application step between them:

- who validates a command against current canonical business truth
- where acceptance or rejection is materialized
- where the only authoritative append happens

Without this decision, event-sourced rollout risks retaining procedural business mutation behind a
new persistence facade.

### Current truth

Today the main runtime still applies business effects procedurally inside `OperatorService`.
Commands may be durable and visible, but the repository does not yet route canonical command
handling through one single-writer event-append boundary.

## Decision

For `event_sourced` operations, command handling must pass through one single-writer application
boundary that is solely responsible for producing canonical domain-event appends.

### One command-application authority per operation

There is exactly one application boundary per operation responsible for:

- loading canonical replay state for validation
- deciding whether a command is accepted or rejected
- appending the resulting domain events in sequence order

No other runtime component may append business domain events opportunistically for the same command.

### Validation input

Command validation is performed against canonical checkpoint state plus any required replay suffix
from the operation event stream.

Validation must not depend on mutable snapshot state as source of truth for `event_sourced`
operations.

### Acceptance and rejection are domain-event outcomes

For canonical command processing, acceptance or rejection is not an implicit side effect.

The command-application boundary must materialize the outcome through appended domain events,
including explicit rejection when a command fails business validation.

This makes command handling inspectable, replayable, and consistent with event-sourced truth.

### Single-writer rule

Per operation, the command-application boundary is the only component allowed to append business
domain events that represent command consequences.

Other components may:

- emit control intents
- persist adapter facts or technical facts
- request planning or reconciliation

They may not bypass the command-application boundary to write business consequences directly.

### Checkpoint refresh relation

Checkpoint refresh is downstream from successful domain-event append, not a prerequisite write.

This ADR permits:

- append, then project and refresh checkpoint in the same application service
- append, then project and refresh checkpoint asynchronously through a guaranteed follow-up path

It forbids:

- mutating checkpoint first and treating event append as secondary bookkeeping
- accepting a command by mutating canonical replay state without appending domain events

## Consequences

- Event-sourced command handling gains one inspectable write authority instead of many procedural
  mutation sites.
- Explicit rejection events become part of canonical business history rather than hidden branching.
- `OperatorService` can delegate command application without remaining the business mutation owner.
- Later runtime work can separate control-intent durability from command consequence durability
  without ambiguity.

## Closure Notes

- The repository now contains a dedicated `EventSourcedCommandApplicationService` that:
  - loads canonical checkpoint state plus event suffix
  - validates one command against replayed canonical state
  - appends explicit `command.accepted` or `command.rejected` domain events through one writer
  - appends supported business mutation events in the same batch
  - projects and persists the derived checkpoint after append
- The first supported event-sourced command slice covers:
  - `PATCH_OBJECTIVE`
  - `PATCH_HARNESS`
  - `PATCH_SUCCESS_CRITERIA`
  - `INJECT_OPERATOR_MESSAGE`
- Unsupported event-sourced command types are rejected through explicit `command.rejected`
  domain events rather than hidden in-memory return values.
- `DefaultOperationProjector` now folds `objective.updated` so checkpoint mutation remains derived
  from domain events only.
- This ADR is accepted as a foundation boundary. The main runtime is still not fully cut over to
  use this service as the live command path for all operations; that remains follow-up work under
  `ADR 0079` and `ADR 0080`.
- Verification:
  - dedicated event-sourced command-application tests pass
  - projector tests pass
  - full repository test suite passes (`281 passed, 11 skipped`)

## This ADR does not decide

- the exact class or module name of the command-application component
- whether translation from technical facts into domain events shares implementation machinery with
  command application
- the final checkpoint refresh scheduling strategy
- the coexistence policy for snapshot-legacy operations

Those are constrained by adjacent ADRs, especially `ADR 0077` and `ADR 0079`.

## Alternatives Considered

### Let multiple services append business events directly

Rejected. That would create hidden write authority, weaken sequencing guarantees, and reintroduce
distributed mutation semantics.

### Treat command rejection as an in-memory return value only

Rejected. That would make rejected business attempts invisible to replay and audit.

### Keep command validation in `OperatorService` while only persistence moves to the event store

Rejected. That preserves the core god-object problem under a new storage backend.
