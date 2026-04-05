# ADR 0087: Canonical operation loop and fact-to-domain append authority

## Status

Accepted

## Context

Accepted foundation ADRs already define:

- canonical command append rules (`ADR 0078`)
- canonical replay and checkpoint materialization rules (`ADR 0079`)
- lower runtime ownership boundaries (`ADR 0081` through `ADR 0084`)

What remains open is the live authority that ties these pieces together during one operation run.

Without that authority, business mutation remains structurally diffuse:

- technical facts can be observed in one place
- translation can happen in another
- canonical append can happen in yet another
- `OperatorService` can still drift back into procedural business mutation

### Current truth

The repository contains the required building blocks, but it does not yet expose one named
operation-loop authority that owns:

- technical fact persistence
- fact translation
- canonical domain-event append
- derived checkpoint materialization
- process-manager follow-up generation

## Decision

The repository must introduce one canonical event-sourced operation-loop authority per operation.

Recommended name:

- `EventSourcedOperationService`

An equivalent name is acceptable only if the ownership boundary remains identical.

### Owned responsibilities

This authority is the only live component allowed to perform the full canonical loop for one
operation:

1. load canonical operation state through replay
2. accept session-scoped `TechnicalFact`
3. persist facts through the non-canonical fact store
4. translate facts into business `DomainEvent`
5. append canonical domain events through one single-writer boundary
6. materialize the derived checkpoint
7. emit process-manager follow-up signals and planning triggers

### Single-writer rule

For one operation, canonical domain-event append authority must remain singular even if multiple
agent sessions are active concurrently.

Concurrency may exist at the runtime-event level, but canonical business append must still funnel
through one serialized per-operation write authority.

### Forbidden authority leakage

`OperatorService`, adapters, session runtimes, and process managers must not directly own
business-state mutation for event-sourced operations.

## Consequences

- The event-sourced runtime gets one real business authority rather than a collection of helper
  slices.
- Fact persistence, translation, append, and checkpoint refresh become testable as one coherent
  loop.
- The repository gains a concrete component that can replace procedural mutation in the main
  runtime path.

## This ADR does not decide

- the public facade responsibilities of `OperatorService`
- the composition root and factory surface used to assemble runtimes
- whether runtime hosting is single-process or multi-process

Those are fixed by adjacent ADRs in this wave.

## Alternatives Considered

### Keep the loop split across multiple services with `OperatorService` coordinating them ad hoc

Rejected. That preserves the current ambiguity about who truly owns canonical mutation.

### Let session runtimes emit `DomainEvent` directly

Rejected. That violates `RFC 0010` and collapses the technical-fact to domain-event seam.

## Verification

- `verified`: the repository now contains one named loop authority,
  `EventSourcedOperationLoopService`, that owns replay, technical-fact persistence,
  translator-mediated domain-event append, checkpoint materialization, and process-manager
  follow-up emission for one operation.
- `verified`: focused tests cover technical-fact persistence, translated event append, checkpoint
  refresh, and planning-trigger emission through the same loop authority.

## Closure notes

This ADR is accepted as a foundation slice.

What is established by repository truth now:

- one canonical event-sourced loop authority exists
- fact persistence, translation, append, checkpoint refresh, and planning-trigger emission can be
  exercised through one coherent service boundary

What remains for adjacent ADRs:

- the main live runtime path still does not delegate to this authority end-to-end
- `OperatorService` shell cutover remains the scope of `ADR 0088`
