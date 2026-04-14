# ADR 0173: Immutable Truth And Query Boundaries

## Decision Status

Proposed

## Implementation Status

Partial

Implementation grounding on 2026-04-14:

- `implemented`: the canonical event/checkpoint path already exists and is conceptually the
  repository source of truth
- `implemented`: application services and query helpers still mutate `OperationState`,
  `TaskState`, `SessionRecord`, and related models in place across many code paths
- `implemented`: stale-status bugs have shown that read-time mutation of operation/session models
  is currently possible and can create hybrid false state
- `implemented`: `OperationStatusQueryService.build_status_payload()` no longer overlays runtime
  background progress onto a copied `OperationState` for status/inspect query assembly; it now
  derives runtime alerts from inspection data while leaving stored session truth untouched
- `implemented`: the hidden debug-session inspection path now builds explicit derived session
  payloads from stored session truth plus background-run progress facts instead of patching copied
  `SessionRecord` models through `overlay_live_background_progress()`
- `implemented`: the stale `overlay_live_background_progress()` helper and the unused
  `OperationStatusQueryService` overlay hook are now removed from this tranche's read/query
  boundary instead of lingering as an alternate mutation path
- `verified`: regression coverage for the status-query immutability tranche now exists in
  `tests/test_operation_status_query_immutability.py`
- `verified`: CLI regression coverage now asserts that debug-session inspection derives live
  progress fields without routing through the mutation-style overlay helper
- `planned`: immutable boundaries are not yet enforced repository-wide across all query DTOs,
  projection helpers, and forensic/read surfaces

## Context

The repository has repeatedly hit bugs where short status surfaces drift away from current
repository truth. Investigation around `status`, `inspect`, pending wakeups, and background
inspection showed a recurring structural problem:

- canonical truth exists in the event/checkpoint path
- runtime truth exists in background inspection and live session state
- query/status layers can still mutate copied operation/session models and present the mixed
  result as if it were authoritative

ADR 0172 addresses one concrete symptom by requiring live status to be derived instead of stored.
That still leaves a broader architectural question:

> should some layers become strictly immutable so these bugs become structurally harder to write?

The answer is yes, but not uniformly across the entire runtime.

`operator` currently has three distinct state roles:

1. **canonical truth** — event/checkpoint derived durable state
2. **query/read truth** — DTOs and payloads used for status, inspect, dashboards, and TUI
3. **runtime workspace** — mutable orchestration state used inside the operator loop while driving
   a live operation

The stale/hybrid-state failures are strongest at the boundary between (1) and (2), and between
runtime inspection and (2). They do not by themselves prove that the entire runtime workspace must
be made immutable immediately.

## Decision

Adopt immutability as a boundary rule for truth-carrying layers, not as an immediate global rule
for every application object.

Specifically:

- canonical durable truth layers should be strictly immutable in practice and by construction
- query/read-model payloads should be built as immutable derived objects and must not mutate
  `OperationState`, `SessionRecord`, or sibling truth-carrying models during read-time assembly
- mutable orchestration state may remain inside the operator application loop for now, but it is
  treated as an internal runtime workspace rather than an authoritative truth surface

This yields the following architectural rule:

> the earlier the truth layer, the stronger the immutability requirement

and:

> read/query layers must behave as pure derivation from authoritative inputs, not as patch-up
> phases over mutable state objects

## Consequences

### Positive

- false-state bugs become structurally harder to introduce in status/query paths
- canonical truth and read truth become easier to reason about and test
- query services can be validated as pure derivations rather than semi-runtime mutation helpers
- later migration from mutable runtime workspace to stricter state transitions remains possible
  without blocking current progress

### Negative

- some existing helpers will need refactoring from in-place mutation to DTO construction
- more explicit copy/build steps will appear in query and projection code
- a full transition of mutable runtime orchestration to immutable transitions is deferred rather
  than completed by this ADR

### Neutral / Follow-on

- this ADR does not require immediate freezing of every `BaseModel` in the domain layer
- this ADR is compatible with keeping `OperationState` mutable as an internal loop workspace for
  now
- a later tranche may choose to make larger portions of the runtime state machine immutable if the
  benefits justify the migration cost

## Alternatives Considered

### 1. Make the whole application state machine immutable immediately

Rejected for now.

This would be architecturally clean but too wide as an immediate migration. The repository still
relies heavily on in-place mutation across decision execution, lifecycle, control-state syncing,
and runtime reconciliation. A full rewrite now would create high churn and slow delivery.

### 2. Keep everything mutable and rely on code review plus targeted bug fixes

Rejected.

Recent status bugs already show that this is insufficient. The architecture needs a preventive
boundary, not just more vigilance.

### 3. Make only the canonical event/checkpoint layer immutable and leave query/read layers mutable

Rejected.

This would protect durable truth but still allow read-time hybrid-state bugs in the surfaces users
actually rely on.

## Implementation Notes

The intended migration order is:

1. enforce pure derivation discipline in status/query/projection helpers
2. introduce immutable query/read DTOs where mutation currently happens during rendering/status
   assembly
3. tighten canonical truth objects so they are not casually repurposed as mutable workspace state
4. evaluate later whether the runtime workspace itself should move toward immutable state
   transitions

The first bounded tranche under this ADR should focus on:

- removing read-time mutation from status/projection helpers
- preventing query helpers from rewriting session summary fields
- adding regression tests for stale-status and hybrid-state failure modes

Current tranche closure on 2026-04-14:

- `partial`: the status-query path now avoids patching runtime progress timestamps onto copied
  `OperationState` session records during read assembly
- `partial`: the debug-session inspection path now emits explicit derived live-progress fields in
  its session payloads instead of mutating copied session models
- `partial`: a regression test now asserts that status-query assembly leaves stored session truth
  untouched even when runtime background progress exists
- `remaining`: other read surfaces still derive output by mutating copied truth models, especially
  broader projection/dashboard assembly paths that still operate directly on mutable truth objects

## Related

- [ADR 0172: Derived Live Status Over Stored Session Summary](./0172-derived-live-status-over-stored-session-summary.md)
