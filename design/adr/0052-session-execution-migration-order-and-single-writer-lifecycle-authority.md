# ADR 0052: Session/Execution Migration Order And Single-Writer Lifecycle Authority

## Status

Accepted

## Context

[`RFC 0005`](/Users/thunderbird/Projects/operator/design/rfc/0005-session-execution-data-model.md)
introduced the `Operation` / `Session` / `Execution` direction before the newer event-sourced
architecture was defined.

That direction remains useful, but the architectural frame has since become sharper:

- [`RFC 0009`](/Users/thunderbird/Projects/operator/design/rfc/0009-operation-event-sourced-state-model-and-runtime-architecture.md)
  defines canonical truth as operation-scoped domain events plus derived checkpoint state
- [`RFC 0010`](/Users/thunderbird/Projects/operator/design/rfc/0010-async-runtime-lifecycles-and-session-ownership.md)
  defines lower runtime ownership for adapters, agent-session runtime, and operation coordination

Within that newer architecture, the repository still needed one migration-specific rule:

- how `Session` / `Execution` compatibility work should proceed without creating competing
  lifecycle authorities

The older ambiguity was real. Runtime truth had been spread across overlapping structures such as:

- `OperationState.status`
- `SessionRecord.status`
- `BackgroundRunHandle.status`
- runtime supervisor run files
- wakeups and events
- `current_focus`
- scheduler state

This overlap has already produced failure-prone cancel, recovery, and stale-running behavior.

The repository therefore needed a narrower migration ADR beneath RFC 0009 / RFC 0010:

- preserve one lifecycle authority during transition
- allow compatibility bridges
- reject schema-first rewrite as the migration order

## Decision

`operator` adopts the `Session` / `Execution` direction through a staged compatibility path.

It does not use schema-first rewrite as the migration order.

The migration is governed by one primary rule:

**canonical lifecycle truth must have a single writer.**

In practice this means:

- runtime infrastructure may produce evidence
- adapters may produce turn and session observations
- but canonical lifecycle state for operations, sessions, and executions changes only through the
  canonical aggregate path

Runtime stores, supervisor files, events, wakeups, and process inspection are therefore evidence
inputs, not peer lifecycle authorities.

## Migration Rules

### 1. Single-writer lifecycle authority

Canonical lifecycle state for:

- operation lifecycle
- session lifecycle
- execution lifecycle

must not be committed independently by runtime stores or supervisor artifacts.

Lower layers may persist:

- logs
- job specs
- heartbeats
- runtime handles
- result artifacts
- wakeup signals

But those artifacts must be reconciled into aggregate truth rather than treated as equal
authorities.

### 2. No old/new peer truth during migration

The system must not expose both:

- the old session/background lifecycle model
- and the new session/execution lifecycle model

as parallel peer authorities in production state.

During migration, one side may temporarily be derived from the other, but they must not both be
authoritative.

### 3. Compatibility bridge before schema replacement

The first migration slices should:

- introduce `Execution` as a new canonical runtime unit
- derive existing surfaces from it where practical
- and keep old read/write paths only as compatibility shims

Persistence format replacement must come after lifecycle ownership is already clear in code.

### 4. Reducer migration before projection migration

Canonical lifecycle derivation should move first.

CLI projections such as:

- `inspect`
- `list`
- scheduler summaries
- focus summaries

should migrate only after canonical lifecycle state is already being derived from the
session/execution model.

### 5. Runtime files are evidence, not truth

Supervisor run files and worker result files remain important.

They are the durable evidence used for:

- reconciliation
- crash recovery
- observability

They are not the canonical lifecycle state of the operation aggregate or of the future
operation-scoped checkpoint model.

### 6. Attached vs background is execution mode

Attached and background must migrate as execution mode on the new `Execution` entity.

They must not survive migration as separate session ontologies or separate peer lifecycle records.

### 7. Focus and scheduler state are projections

`current_focus`, scheduler state, and blocking summaries may remain persisted for transparency and
crash recovery, but they must be treated as derived control projection.

They must not be used as the canonical source of truth for whether a session or execution is still
active.

## Explicitly Rejected Route

The following route is rejected:

- replace the persistence schema first
- delete the current session-management model wholesale
- rewrite operator logic from scratch against the new schema

This route is rejected because:

- current reducers, runtime stores, supervisor logic, and CLI projections are deeply coupled to the
  existing state shape
- schema-first replacement would maximize the number of simultaneously moving parts
- and it would likely create a long transition period in which cancellation, recovery, and inspect
  semantics are all unstable at once

The target model from RFC 0005 is still the right target.

The rejected part is the implementation order, not the destination.

## Consequences

### Positive

- Migration risk is localized.
- Cancel and recovery semantics can be proven slice by slice.
- Runtime evidence remains available without competing with aggregate truth.
- The repository keeps a clear claim boundary between:
  - implemented compatibility shims
  - and accepted canonical lifecycle ownership

### Negative

- Migration will take longer than a burn-it-down rewrite.
- Temporary compatibility code is required.
- Some old structures will remain in the codebase longer than ideal while they are being narrowed
  into derived or compatibility-only roles.

### Follow-Up Implications

- This ADR now serves mainly as a compatibility and authority rule beneath `RFC 0009` and
  `RFC 0010`, not as the primary source of forward architecture.
- Remaining follow-up work should focus on narrowing old compatibility surfaces and projections,
  not on reopening single-writer lifecycle authority.
- Exact persistence schema transition, event-sourced checkpoint migration, and lower runtime
  protocol shape are owned by newer RFC/ADR work rather than by this ADR alone.
