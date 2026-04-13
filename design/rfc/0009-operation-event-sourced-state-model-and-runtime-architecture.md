# RFC 0009: Operation Event-Sourced State Model and Runtime Architecture

## Status

Accepted

## Implementation Status

- `implemented`: executable foundation boundaries beneath this RFC exist via accepted ADRs
  `0069` through `0074`
- `implemented`: closure foundations beneath this RFC exist via accepted ADRs `0077` through
  `0080`
- `implemented`: the repository contains an operation event store, checkpoint store, fact store,
  projector protocol, and default projector implementation
- `verified`: those foundation slices are covered by focused tests
- `implemented`: runtime-contract closure work from `ADR 0089` through `ADR 0091` is complete
- `implemented`: `ADR 0092` has split durable policy, execution budget, and runtime hints in the
  repository data model
- `implemented`: `ADR 0086` and `ADR 0088` have completed the main entrypoint cutover
- `verified`: `ADR 0144` now closes the remaining live write-path retirement work:
  cancellation, `STOP_OPERATION`, and attached-turn polling no longer rely on snapshot-era
  business persistence
- `implemented`: the three concrete resume/reconcile failure modes (session_id lost,
  cooldown_until not cleared, active_session stale) are resolved via events
  `execution.session_linked`, `session.cooldown_cleared`, and `operation.active_session_updated`
  with corresponding projector slices
- `implemented`: `OperationCheckpoint` is the canonical replay target for live operation truth
- `verified`: repository verification currently passes after the final `ADR 0144` closure wave:
  `608 passed, 11 skipped`

The repository has accepted and now verified the domain-event-plus-checkpoint architecture
described here, including the live write-path retirement required by `ADR 0144`.

## Context

`operator` currently keeps its canonical persisted truth in a mutable operation snapshot:
`OperationState` is serialized as `<operation-id>.operation.json` by `FileOperationStore`.

That snapshot already contains multiple distinct state surfaces:

- operation lifecycle
- task graph state
- session state
- execution state
- attention state
- scheduler state
- operator message state
- policy applicability state
- convenience brief and report fields

At the same time, runtime truth is also persisted outside the operation snapshot:

- `events/<operation-id>.jsonl`
- `wakeups/`
- `background/jobs/`
- `background/runs/`
- `background/results/`
- trace timeline and report files

This split has two concrete consequences:

1. canonicality is ambiguous
2. business transitions are applied procedurally inside `OperatorService`

The current `OperatorService` is correspondingly too large. At the time of writing it is
approximately 3650 lines with more than
100 private helper methods. That is not just a style problem. It indicates that:

- multiple state machines are being coordinated implicitly rather than modeled explicitly
- transition invariants are distributed across helper call ordering
- persistence, runtime reconciliation, and business mutation are too tightly coupled

RFC 0006 established the event model vocabulary and event taxonomy, but it did not change the
canonical source of truth. Events are currently `implemented` as observability and wakeup plumbing;
they are not yet the authoritative business state transition log.

This RFC proposes the next step: make operation state event-sourced, clarify the child state
machines that live inside an operation, and shrink `OperatorService` to an orchestration shell.

## Decision

### 1. One canonical domain event stream per operation

Each operation has exactly one canonical domain event stream.

This RFC does **not** choose one global state machine. It chooses one canonical stream containing
typed event families for multiple child entities.

The canonical stream is authoritative for business truth. A persisted checkpoint may be used for
replay acceleration, but the checkpoint is derived from the domain event stream and is not a second
independent source of truth.

### 2. Child-entity state machines inside the operation stream

The canonical operation stream contains domain events for these child state machines:

- `Operation`
- `Task`
- `Session`
- `Execution`
- `Attention`
- `Scheduler`

Interpretation:

- `Task` remains part of the operation aggregate rather than becoming its own top-level canonical
  stream.
- `Session` and `Execution` remain distinct child entities. They are not collapsed into one
  lifecycle because the current runtime already demonstrates separate semantics for reusable
  sessions and individual executions.
- Policy applicability remains operation-owned substate in this RFC rather than becoming a separate
  child state machine. It still belongs in canonical replay whenever it affects planning or
  permission behavior.

### 3. Layered write pipeline

The runtime pipeline is:

1. `Command`
2. `AdapterFact`
3. `TechnicalFact`
4. `DomainEvent`
5. `OperationCheckpoint`
6. read models

Only `DomainEvent` objects may mutate canonical business state.

This RFC fixes the canonical layering, but leaves the lower runtime ownership boundary abstract.
[`RFC 0010`](./0010-async-runtime-lifecycles-and-session-ownership.md) refines that lower layer by
assigning:

- `AdapterRuntime` as the producer of `AdapterFact`
- `AgentSessionRuntime` as the producer of session-scoped `TechnicalFact`
- `FactTranslator` as the producer of business `DomainEvent`

The remaining RFC 0009 rollout boundaries beneath this decision are now explicitly split into:

- [`ADR 0077`](../adr/0077-event-sourced-operation-cutover-and-legacy-coexistence-policy.md)
- [`ADR 0078`](../adr/0078-command-application-and-single-writer-domain-event-append-boundary.md)
- [`ADR 0079`](../adr/0079-live-replay-and-checkpoint-materialization-authority.md)
- [`ADR 0080`](../adr/0080-operator-service-shell-extraction-and-runtime-ownership-after-event-sourced-cutover.md)

The remaining RFC 0009 closure boundaries after those accepted foundations are:

- [`ADR 0086`](../adr/0086-event-sourced-operation-birth-and-snapshot-legacy-retirement-policy.md)
- [`ADR 0087`](../adr/0087-canonical-operation-loop-and-fact-to-domain-append-authority.md)
- [`ADR 0088`](../adr/0088-main-entrypoint-cutover-and-final-operator-service-shell-boundary.md)
- [`ADR 0092`](../adr/0092-split-operationconstraints-into-policy-budget-and-runtime-hints.md)
- [`ADR 0091`](../adr/0091-legacy-runtime-cleanup-and-document-supersession-after-cutover.md)

`OperationCheckpoint` is derived only from domain events. Read models may be derived from domain
events alone or from domain events joined with technical facts and trace material, depending on the
surface. That does not make those joined inputs canonical.

### 4. `OperationCheckpoint` is the canonical replay target

The replay target for an operation is `OperationCheckpoint`: a fold of domain events only.

If reconstructing a field requires technical facts, raw adapter payloads, or trace records, that
field does not belong in the canonical checkpoint.

### 5. `OperatorService` becomes an orchestration shell

`OperatorService` remains the application entrypoint and runtime coordinator, but it no longer owns
business transition semantics directly.

Its responsibilities become:

- public entrypoints such as `run`, `resume`, and command handling
- dependency composition
- transaction and runtime coordination boundaries
- delegating command handling, projection, and follow-up actions to dedicated components

This RFC does not propose splitting the current service into many classes without changing the
truth model. That would preserve the core ambiguity instead of resolving it.

## Criteria To Close

This RFC can move beyond `Proposed` only when all of the following are true:

1. New operation business truth is persisted canonically through `OperationEventStore`, not through
   mutable `OperationState` snapshot mutation as the primary source of truth. This cutover must be
   governed by [`ADR 0077`](../adr/0077-event-sourced-operation-cutover-and-legacy-coexistence-policy.md)
   and [`ADR 0078`](../adr/0078-command-application-and-single-writer-domain-event-append-boundary.md).
2. `OperationCheckpoint` is the canonical replay target for operation recovery, per
   [`ADR 0079`](../adr/0079-live-replay-and-checkpoint-materialization-authority.md).
3. The main runtime path (`run`, `resume`, command handling, recovery) projects business state from
   domain events rather than procedurally mutating canonical operation state in `OperatorService`.
4. `OperatorService` has become an orchestration shell by repository truth, not just by intended
   architecture, per
   [`ADR 0080`](../adr/0080-operator-service-shell-extraction-and-runtime-ownership-after-event-sourced-cutover.md).
5. Repository tests verify the event-sourced path as the canonical runtime, not merely the
   existence of foundation components.
6. The repository no longer treats `OperationConstraints` as one canonical aggregate. Durable
   operation policy, execution budget, and runtime hints must be separated per
   [`ADR 0092`](../adr/0092-split-operationconstraints-into-policy-budget-and-runtime-hints.md).

## State Model

The canonical business state of an operation is represented by `OperationCheckpoint`.

`OperationCheckpoint` includes only replay-required business truth:

- operation lifecycle state
- task graph state
- session state
- execution state
- attention state
- scheduler state
- durable operation policy state such as `involvement_level`
- durable operation agent-governance state such as `allowed_agents`
- operator-message state only insofar as it affects planning windows or blocking semantics
- policy applicability state only insofar as it affects planning or permission decisions
- references needed for control-plane continuity

`OperationCheckpoint` excludes:

- execution-budget settings such as `max_iterations` and `timeout_seconds`
- runtime hints such as prompt-window knobs and metadata glue
- raw adapter payloads
- technical fact logs
- wakeup bookkeeping
- heartbeat/progress chatter
- partial output snapshots
- trace briefs and narrative reports

## Event Taxonomy

Unless stated otherwise, event names in this section are conceptual family names, not mandated
serialized `event_type` strings. RFC 0006 remains the source of truth for the lower-level event-log
taxonomy and wire-format conventions.

### Adapter facts

`AdapterFact` is raw vendor-facing or runtime-facing input.

Examples:

- raw ACP notification payloads
- raw subprocess disconnect/error payloads
- raw adapter progress notifications

Adapter facts are retained for forensic or debugging purposes. Reducers never inspect them
directly.

### Technical facts

`TechnicalFact` is a normalized operator-runtime observation.

At the level of this RFC, the concrete producer of `TechnicalFact` is left abstract. The lower
runtime boundary is specified by [`RFC 0010`](./0010-async-runtime-lifecycles-and-session-ownership.md),
which assigns session-scoped technical-fact normalization to `AgentSessionRuntime`.

Examples:

- `ExecutionStartObserved`
- `ExecutionHeartbeatObserved`
- `ExecutionDisconnectObserved`
- `WakeupEnqueued`
- `WakeupClaimed`
- `WakeupAcked`
- `ExecutionPartialOutputObserved`

Technical facts may justify future domain events, but they are not canonical business truth.

### Domain events

`DomainEvent` is a business-meaningful state transition in the operation or one of its child
entities.

Examples:

- `OperationStarted`
- `OperationStatusChanged`
- `TaskCreated`
- `TaskStatusChanged`
- `SessionCreated`
- `SessionObservedStateChanged`
- `ExecutionRegistered`
- `ExecutionObservedStateChanged`
- `AttentionRequestCreated`
- `AttentionRequestAnswered`
- `AttentionRequestResolved`
- `SchedulerStateChanged`
- `OperatorMessageReceived`
- `OperatorMessageDroppedFromContext`
- `PolicyEvaluated`
- `CommandAccepted`
- `CommandRejected`

Only domain events are folded into `OperationCheckpoint`.

`ExecutionRegistered` and `ExecutionStartObserved` are intentionally different:

- `ExecutionRegistered` is the business decision to create or track an execution child entity
- `ExecutionStartObserved` is a technical fact that the runtime actually observed the execution
  starting

### Trace records

Trace records remain non-canonical narrative or forensic material.

Examples:

- `BrainDecisionMade`
- evaluation summaries
- reconciliation commentary
- iteration and report briefs

### Classification rules

The following classification rules are normative:

- `BrainDecisionMade` is trace, not a domain event
- wakeup enqueue/claim/ack is technical, not a domain event
- heartbeat, progress, and partial output are technical by default
- operator-message aging-out events are domain events when they change the active planning context
- policy applicability changes are domain events when they change planning or permission behavior
- disconnects and errors become domain truth only after translation into business consequences such
  as `ExecutionObservedStateChanged(... -> lost)` or a session recovery event

## Runtime Architecture

### Persisted stores

This RFC introduces these persisted stores:

- `OperationEventStore` as the canonical domain-truth store
- `OperationCheckpointStore` as a derived replay-acceleration store

This RFC also introduces a separate non-canonical fact surface:

- `FactStore` for adapter facts and technical facts

The lower runtime ownership of those fact families is specified separately by
[`RFC 0010`](./0010-async-runtime-lifecycles-and-session-ownership.md).

### Projector and reducer slices

The canonical projector is `OperationProjector`.

`OperationProjector` folds the operation stream into `OperationCheckpoint` using reducer slices for:

- operation
- task
- session
- execution
- attention
- scheduler

This RFC intentionally chooses one projector with reducer slices rather than many separate
canonical projectors. The goal is to make child-entity boundaries explicit without introducing a
new multi-stream coordination problem.

### Process managers

This RFC introduces process managers as command-emitting reactors.

The minimum set is:

- `PlanningProcessManager`
- `ExecutionProcessManager`
- `AttentionProcessManager`

Process managers:

- observe domain events and current checkpoint state
- decide whether a follow-up command should be issued
- do not mutate canonical state directly

### Command handling

Commands remain the intent boundary for state transitions.

Illustrative commands include:

- start or resume operation
- apply brain decision
- request or continue an agent turn
- reconcile an execution fact
- answer or resolve attention
- pause or resume the scheduler

The exact command catalog is left to implementation, but the architectural rule is fixed:
commands request transitions; reducers apply only domain events.

## Checkpoints And Replay

### Replay contract

Replaying from:

- the latest checkpoint
- plus subsequent domain events

must be sufficient to reconstruct canonical business state.

Replaying from technical facts or trace records must not be required for canonical state recovery.

### Constraints split

This RFC no longer treats `OperationConstraints` as one cohesive canonical state slice.

For RFC-closure purposes, the old aggregate must be split into:

- durable `OperationPolicy`
- non-canonical `ExecutionBudget`
- non-canonical `RuntimeHints`

Specifically:

- `involvement_level` and `allowed_agents` belong to durable operation policy
- `max_iterations` and `timeout_seconds` belong to execution budget
- `operator_message_window` and metadata-like runtime glue belong to runtime hints

The exact replacement types and migration details are constrained by
[`ADR 0092`](../adr/0092-split-operationconstraints-into-policy-budget-and-runtime-hints.md).

### Checkpoint cadence

The runtime should persist checkpoints:

- at iteration boundaries
- at terminal boundaries
- after sufficiently large domain-event batches

This RFC does not require a checkpoint after every individual domain event.

### Read models

Read models are derived, non-canonical projections for CLI and forensic surfaces.

Examples include:

- inspect summaries
- dashboard views
- brief bundles
- progress displays
- timeline and report material

Read models may incorporate technical facts or trace records as needed. That does not make those
facts canonical.

## Migration

### Chosen migration route

This RFC chooses a versioned cutover, not dual-write canonicality.

New operations use:

- operation event stream
- operation checkpoint
- fact store

Legacy operations remain readable and resumable through the current snapshot path until that path is
retired.

### Legacy import policy

If migration tooling is introduced, it may import a legacy snapshot into a bootstrap checkpoint or
emit a coarse event such as `OperationImportedFromLegacySnapshot`.

It must **not** fabricate fine-grained historical event streams from snapshots and present them as
true historical causality.

### Rejected migration route

This RFC rejects a dual-write period in which mutable snapshot truth and canonical event truth are
both treated as authoritative. That would recreate the split-truth problem this RFC is intended to
eliminate.

## Alternatives Considered

### Keep snapshot truth and only improve event logging

Rejected. This preserves the current ambiguity:

- snapshot remains authoritative
- events remain observational
- transition semantics remain procedural

### Split `OperatorService` into smaller classes without changing truth model

Rejected. This addresses file size but not canonicality or transition ownership.

### Multiple canonical streams (`Operation`, `Session`, `Execution`, ...)

Deferred. This may become appropriate if sessions must become reusable across operations or if
child-entity retention and replay requirements diverge materially. At current system maturity it
would increase coordination complexity too early.

### Dual-write migration

Rejected. It introduces a temporary but highly risky period of ambiguous canonicality.

## Non-Goals

This RFC does not:

- redesign the CLI surface
- canonicalize heartbeat, wakeup, or progress chatter
- reconstruct fake detailed event history from legacy snapshots
- introduce cross-operation session reuse as a product capability
- require separate canonical streams per child entity
- treat trace output as source of truth
- accept a purely cosmetic “split the service into more classes” refactor

## Consequences

If accepted and implemented, this RFC will:

- replace mutable operation snapshot truth with domain-event truth for new operations
- require a new canonical checkpoint model
- force a clearer boundary between runtime observations and business state transitions
- reduce the semantic load currently concentrated inside `OperatorService`
- align state mutation semantics with the event model introduced by RFC 0006

It will also impose new discipline:

- translators must not leak adapter-specific payloads into domain semantics
- reducers must remain pure
- process managers must not mutate checkpoint state directly
- read models must not silently become canonical truth
