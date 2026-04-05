# ADR 0069: Operation event store and checkpoint store contracts

## Status

Accepted

## Context

[`RFC 0009`](../rfc/0009-operation-event-sourced-state-model-and-runtime-architecture.md)
proposes replacing mutable operation snapshot truth with:

- one canonical domain event stream per operation
- one derived replay target: `OperationCheckpoint`

That RFC intentionally stays at the architecture level. The first implementation boundary that
needs a narrower decision is storage: what exactly `OperationEventStore` and
`OperationCheckpointStore` guarantee, which of them is authoritative, and how they behave under
partial failure.

Without this ADR, the implementation could drift into at least three incompatible interpretations:

1. both stores are treated as authoritative, recreating split truth
2. checkpoint writes are allowed to run ahead of event persistence, making replay unsound
3. the checkpoint store quietly inherits the semantics of the current snapshot store, preserving
   the same ambiguity under new names

The contract needs to be explicit before code is written.

## Decision

### `OperationEventStore` is canonical

`OperationEventStore` is the only canonical persistence surface for business state transitions.

It stores append-only domain events scoped to one operation stream.

Each persisted event has:

- `operation_id`
- an operation-local monotonically increasing sequence number
- an event family / type
- payload
- timestamp
- optional causation / correlation metadata

This ADR does not standardize the concrete payload schema for each event family. It standardizes
the storage contract.

The repository now includes a file-backed foundation slice for this boundary:

- `FileOperationEventStore`
- `FileOperationCheckpointStore`
- optimistic append conflict handling
- replay-oriented load APIs

Those implementations establish the contract without yet replacing the current mutable
`FileOperationStore` application path.

### `OperationCheckpointStore` is derived

`OperationCheckpointStore` is not canonical. It is a replay-acceleration store only.

Each persisted checkpoint contains:

- `operation_id`
- the serialized `OperationCheckpoint`
- `last_applied_sequence`
- checkpoint format version
- creation timestamp

`last_applied_sequence` means: "this checkpoint is the fold of all domain events for this
operation whose sequence number is less than or equal to this value."

### Write ordering

The write order is:

1. append domain events to `OperationEventStore`
2. fold those events into a new `OperationCheckpoint`
3. persist the new checkpoint to `OperationCheckpointStore`

The reverse order is forbidden.

If a crash happens after step 1 but before step 3:

- the event store remains correct
- the checkpoint is stale
- replay recovers by loading the latest checkpoint and folding the suffix of events after
  `last_applied_sequence`

If a crash happens before step 1 completes:

- no later checkpoint may be written

### Atomicity model

The required atomicity boundary is the event append batch, not the event-plus-checkpoint pair.

This ADR does **not** require a distributed transaction spanning both stores.

Required guarantees:

- appending an event batch to `OperationEventStore` is atomic for that batch
- a checkpoint must never claim to include events that were not durably appended
- a stale checkpoint is acceptable
- a checkpoint ahead of the event stream is invalid

### Read model

The canonical read path for business state is:

1. load latest checkpoint for the operation, if any
2. load all domain events with `sequence > last_applied_sequence`
3. fold the suffix onto the checkpoint

If no checkpoint exists:

- replay starts from the empty initial state and folds the full event stream

### Concurrency model

Appends are serialized per operation stream.

The minimum contract is optimistic append with expected stream position:

- caller provides the expected last sequence number
- append succeeds only if the stream is still at that position

This is sufficient for single-writer-by-default operation semantics while still protecting against
future accidental concurrent appenders.

This ADR does not require multi-writer coordination beyond optimistic position checks.

### Relationship to technical facts and trace

`OperationEventStore` stores domain events only.

It does not store:

- adapter facts
- technical facts
- wakeup bookkeeping
- trace records
- narrative reports

Those belong to separate non-canonical stores and must not be required for canonical replay.

### Initial empty state

Each operation stream has a well-defined empty initial state. A checkpoint is optional.

There is no required synthetic "stream created" event just to make the storage contract work.
If the product later wants an explicit `OperationStarted` domain event, that is a business decision,
not a storage requirement.

### Legacy import policy

If legacy snapshot import is implemented, the imported checkpoint remains derived state.

Two acceptable bootstrap patterns are:

- write one coarse import domain event and derive the checkpoint from it
- write an imported checkpoint tagged with `last_applied_sequence = 0` plus explicit metadata that
  it was bootstrapped from legacy state

What is not allowed:

- fabricating a detailed historical sequence of domain events from snapshot fields and presenting it
  as true causal history

## Consequences

- `OperationEventStore` becomes the only canonical business-truth store
- `OperationCheckpointStore` becomes an explicitly derived cache/replay surface
- replay logic is simple: checkpoint + suffix
- failure handling tolerates stale checkpoints but not checkpoints ahead of the stream
- store implementations must expose operation-local sequencing and optimistic append semantics
- the current `FileOperationStore` shape cannot be reused unchanged as the canonical store under new
  names

## Alternatives Considered

### Make both stores authoritative

Rejected. This recreates split truth.

### Make checkpoint writes atomic with event appends in one joint transaction

Rejected for the baseline contract. It is stronger than needed and would over-constrain file-based
and lightweight implementations. The design only needs event append atomicity plus the invariant
"checkpoint never ahead of stream."

### Keep a mutable snapshot store and treat the event store as an audit log

Rejected. This would fail the core architectural goal of RFC 0009.

### Separate canonical stores per child entity

Rejected for now. RFC 0009 already chose one canonical operation stream with child-entity event
families.
