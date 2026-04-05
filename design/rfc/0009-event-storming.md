# Event Storming For RFC 0009

## Status

Working design artifact

## Purpose

This document performs a concrete event-storming pass for
[`RFC 0009`](./0009-operation-event-sourced-state-model-and-runtime-architecture.md).

Its goal is to make the proposed architecture operational by identifying:

- event initiators
- event consumers
- canonical and non-canonical state ownership
- checkpoint and state-collapse cadence

This document is narrower than RFC 0009. RFC 0009 defines the architectural decision. This file
turns that decision into an explicit event flow and ownership model.

## Scope

In scope:

- operation-scoped event storming
- command, fact, and domain-event flow
- state ownership
- checkpoint cadence
- read-model and technical-fact consumption

Out of scope:

- final wire-format event names
- CLI redesign
- cross-operation session reuse
- distributed multi-stream architecture

## Event Storming Summary

### Core rule

The canonical write path is:

1. `Command`
2. `AdapterFact`
3. `TechnicalFact`
4. `DomainEvent`
5. `OperationCheckpoint`
6. read models

Only domain events mutate canonical business state.

### Core ownership rule

There is one canonical operation stream, but not one state machine.

Canonical business state is divided into:

- operation-owned state
- task child state
- session child state
- execution child state
- attention child state
- scheduler child state

Non-canonical state is divided into:

- adapter facts
- technical facts
- read models and trace artifacts

`RFC 0010` later refines the lower runtime ownership of those non-canonical fact families:

- `AdapterRuntime` emits `AdapterFact`
- `AgentSessionRuntime` emits session-scoped `TechnicalFact`
- `FactTranslator` derives `DomainEvent`

## Actors

### Initiators

- user / CLI
- operator brain
- process managers
- agent adapters
- agent session runtimes
- background worker / runtime supervisor
- timer / clock / cooldown expiry

### Consumers

- `OperationEventStore`
- `FactStore`
- `OperationProjector`
- reducer slices
- process managers
- CLI read models
- trace/report surfaces
- runtime recovery logic

## State Inventory

### Canonical business state machines

If counting only canonical business state machines, there are **6**:

1. `Operation`
2. `Task`
3. `Session`
4. `Execution`
5. `Attention`
6. `Scheduler`

### Operation-owned canonical substates

These are canonical, but not promoted to independent child state machines in RFC 0009:

- operator-message context state
- policy applicability state

### Non-canonical persisted state surfaces

These remain persisted, but are not part of canonical replay:

1. adapter-fact log
2. technical-fact log
3. wakeup delivery state
4. runtime progress / partial output state
5. trace briefs and narrative reports

If counting all persisted state surfaces that the system materially cares about, the effective
design space is closer to **11 logical state surfaces**:

- 6 canonical business state machines
- 2 canonical operation-owned substates
- 3 major non-canonical state strata:
  - facts
  - wakeup/runtime delivery
  - read models / trace

The important distinction is not the raw count. It is whether a surface belongs to canonical
replay, technical reconciliation, or human-facing projections.

## State Ownership

| State surface | Canonical | Owner | Notes |
|---|---|---|---|
| Operation lifecycle | yes | `OperationCheckpoint` / operation reducer slice | run status, terminality, summary-bearing status |
| Task graph | yes | operation aggregate / task reducer slice | dependencies, readiness, assignment intent |
| Session lifecycle | yes | session reducer slice | desired/observed/terminal state, cooldown, recovery, bindings |
| Execution lifecycle | yes | execution reducer slice | registration, observed state, binding to task/session |
| Attention lifecycle | yes | attention reducer slice | open, answered, resolved, blocking semantics |
| Scheduler lifecycle | yes | scheduler reducer slice | active, pause requested, paused |
| Operator message context window | yes | operation-owned substate | because it changes planning context |
| Policy applicability summary | yes | operation-owned substate | because it affects planning and permission behavior |
| Adapter payload history | no | `FactStore` | forensic and translation input only |
| Technical runtime observations | no | `FactStore` | translation input and technical read models |
| Wakeup delivery bookkeeping | no | wakeup inbox / technical fact layer | delivery mechanics only |
| Progress / partial output | no | technical fact layer + read models | product-visible if desired, but not canonical replay |
| Briefs / report / timeline | no | `TraceStore` / read models | traceability layer only |

## Event Families

### Commands

Commands are intent carriers. They do not mutate state directly.

Primary command families:

- `StartOperation`
- `ResumeOperation`
- `ApplyBrainDecision`
- `RequestAgentTurn`
- `ContinueAgentTurn`
- `CancelAgentTurn`
- `ReconcileTechnicalFacts`
- `OpenAttentionRequest`
- `AnswerAttentionRequest`
- `ResolveAttentionRequest`
- `PauseScheduler`
- `ResumeScheduler`
- `RefreshPolicyContext`
- `InjectOperatorMessage`

### Adapter facts

Adapter facts are raw vendor-facing observations.

Examples:

- ACP notification payload received
- raw disconnect payload observed
- adapter progress callback received
- adapter completion payload received

### Technical facts

Technical facts are normalized runtime observations.

In the more concrete lower-runtime model from `RFC 0010`, these are emitted by
`AgentSessionRuntime` after session-scoped normalization of adapter facts.

Examples:

- `ExecutionStartObserved`
- `ExecutionHeartbeatObserved`
- `ExecutionDisconnectObserved`
- `ExecutionCompletionObserved`
- `ExecutionFailureObserved`
- `WakeupEnqueued`
- `WakeupClaimed`
- `WakeupAcked`
- `CooldownExpiredObserved`
- `ExecutionPartialOutputObserved`
- `PolicyRefreshObserved`

### Domain events

Domain events are business-meaningful state transitions folded into canonical state.

Examples:

- `OperationStarted`
- `OperationStatusChanged`
- `TaskCreated`
- `TaskStatusChanged`
- `SessionCreated`
- `SessionObservedStateChanged`
- `SessionCooldownStarted`
- `SessionCooldownExpired`
- `SessionRecoveryRequested`
- `ExecutionRegistered`
- `ExecutionObservedStateChanged`
- `ExecutionResultAttached`
- `AttentionRequestCreated`
- `AttentionRequestAnswered`
- `AttentionRequestResolved`
- `SchedulerStateChanged`
- `OperatorMessageReceived`
- `OperatorMessageDroppedFromContext`
- `PolicyEvaluated`
- `CommandAccepted`
- `CommandRejected`

### Trace-only records

These do not affect canonical replay:

- `BrainDecisionMade`
- evaluation summaries
- reconciliation commentary
- iteration briefs
- reports

## Initiator Matrix

| Initiator | Emits directly | Typical result |
|---|---|---|
| user / CLI | command | command accepted or rejected, then business transitions |
| operator brain | decision trace, decision-shaped command proposal | later becomes command(s), not direct domain mutation |
| process managers | command | follow-up transitions after prior domain events |
| agent adapter | adapter fact | later normalized into technical facts |
| background worker / supervisor | technical fact | execution/session transitions after translation |
| timer / clock | technical fact or command | cooldown expiry, timeout checks, scheduled wakeups |

Important rule:

- the operator brain does not directly emit domain events
- adapters do not directly emit domain events
- process managers do not directly mutate canonical state

## Consumer Matrix

| Event/fact type | Primary consumers | Non-consumers by rule |
|---|---|---|
| command | command handler, process managers | reducers |
| adapter fact | fact recorder, translator | reducers, projector |
| technical fact | translator, technical read models, recovery logic | reducers, canonical projector |
| domain event | canonical event store, projector, process managers, read models | raw adapter layers |
| trace record | trace store, forensic UI | reducers, process managers |

## Stormed Flows

### Flow 1: User command to operation state change

1. user submits `OperationCommand`
2. command handler validates target and payload
3. command is accepted or rejected
4. accepted command emits domain event such as `CommandAccepted`
5. process manager or command handler emits follow-up domain event(s)
6. projector folds events into checkpoint
7. read models update from checkpoint and trace

Initiator:
- user / CLI

Primary consumers:
- command inbox
- command handler
- projector
- process managers
- inspect/dashboard read models

### Flow 2: Agent execution lifecycle

1. process manager emits `RequestAgentTurn`
2. runtime starts background or attached turn
3. adapter emits raw start/progress/completion/disconnect payloads
4. raw payloads are recorded as adapter facts
5. runtime translator emits technical facts such as `ExecutionStartObserved`
6. technical facts produce domain events such as:
   - `ExecutionRegistered`
   - `ExecutionObservedStateChanged`
   - `SessionObservedStateChanged`
7. projector updates session/execution child state
8. process managers may request recovery, replanning, or result evaluation

Initiators:
- process managers
- adapters
- runtime supervisor

Primary consumers:
- fact store
- translator
- projector
- execution and planning process managers

### Flow 3: Wakeup and reconciliation

1. background worker enqueues wakeup
2. wakeup inbox records delivery mechanics
3. attached/resumable runtime claims and acks wakeup
4. runtime polls background result and/or run state
5. translator emits technical facts for observed execution state
6. technical facts emit domain events for business consequences
7. projector updates canonical checkpoint

Important rule:

- wakeup events themselves are never canonical business truth
- only their translated business consequences may become domain events

### Flow 4: Attention lifecycle

1. brain or deterministic guardrail identifies blocking ambiguity
2. command/process manager emits `OpenAttentionRequest`
3. domain event `AttentionRequestCreated`
4. projector marks attention open and possibly blocks task/operation progression
5. user answers via command
6. domain events:
   - `AttentionRequestAnswered`
   - `AttentionRequestResolved`
7. projector unblocks the relevant state
8. process manager may enqueue replanning

### Flow 5: Operator-message context window

1. user injects free-form operator message
2. command handler emits `OperatorMessageReceived`
3. projector adds message to active planning context state
4. each planning cycle increments active-age accounting
5. when message ages out of the planning window, domain event `OperatorMessageDroppedFromContext`
6. projector removes it from active context while retaining historical auditability elsewhere

Important rule:

- message aging-out is canonical because it changes planning context
- message text history beyond the active window may live in read models or trace, but active-window
  membership belongs to canonical state

### Flow 6: Policy refresh

1. runtime or command requests policy refresh
2. policy store is read
3. runtime records technical observation that refresh was attempted
4. domain event `PolicyEvaluated` is emitted only when the effective applicability result changes
5. projector updates operation-owned policy applicability state

Important rule:

- repeated refresh with no effective change should not emit redundant canonical domain events

## Ownership By Event Family

| Domain event family | Initiator | Canonical owner after fold | Typical consumers |
|---|---|---|---|
| operation | command handler / process manager | operation reducer slice | scheduler and planning process managers |
| task | brain decision application / process manager | task reducer slice | planning and execution process managers |
| session | execution translator / recovery logic | session reducer slice | execution and planning process managers |
| execution | execution translator / command handler | execution reducer slice | execution and planning process managers |
| attention | command handler / guardrail | attention reducer slice | attention and planning process managers |
| scheduler | command handler / guardrail | scheduler reducer slice | planning process manager |
| operator message | command handler / planning-window logic | operation-owned substate | planning process manager, prompt builder |
| policy applicability | policy refresh logic | operation-owned substate | planning logic, permission evaluation |

## Recommended Checkpoint Cadence

### Baseline rule

Checkpointing should be cheap enough that resumable recovery does not depend on replaying a long
operation stream, but not so frequent that every technical twitch becomes a write amplification
problem.

### Mandatory checkpoint triggers

Persist `OperationCheckpoint` immediately when any of the following occurs:

- end of an operator iteration
- operation terminal transition
- scheduler transition
- attention request created, answered, or resolved
- session or execution transition into a terminal or lost state
- operator-message drop from active context
- policy applicability change

### Batched checkpoint triggers

While a long reconciliation burst is in progress, checkpoint when either threshold is reached:

- **20 domain events** since the last checkpoint
- **5 seconds** since the last checkpoint

These are recommended initial defaults, not immutable protocol constants.

### Explicit non-triggers

Do **not** checkpoint solely because of:

- heartbeat facts
- wakeup claim/ack events
- partial output/progress chatter
- trace-only records
- raw adapter notifications

### Why this cadence

This gives three properties:

1. operation recovery remains bounded
2. execution/session terminal transitions are durably reflected quickly
3. noisy runtime observations do not force canonical writes

## State Collapse Guidance

“State collapse” in this design means folding new domain events into `OperationCheckpoint`.

Recommended collapse frequency by layer:

| Layer | Collapse frequency |
|---|---|
| adapter facts | never into canonical checkpoint |
| technical facts | never directly into canonical checkpoint |
| domain events | immediate append; checkpoint at mandatory or batched triggers |
| read models | update opportunistically from checkpoint and supporting technical/trace material |

## Implementation Guidance

### Components that should own the stormed behavior

- `OperationCommandService`
  - validates and applies commands into domain-event proposals
- `FactRecorder`
  - persists adapter and technical facts
- `FactTranslator`
  - maps adapter facts to technical facts and technical facts to domain events
- `OperationEventStore`
  - appends domain events
- `OperationProjector`
  - folds domain events into `OperationCheckpoint`
- `PlanningProcessManager`
  - reacts to planning-relevant domain events
- `ExecutionProcessManager`
  - reacts to execution/session domain events
- `AttentionProcessManager`
  - reacts to blocking attention lifecycle
- `TraceStore`
  - records non-canonical narrative surfaces

### What `OperatorService` should still do

- invoke the command service
- invoke the brain when a planning process manager calls for it
- coordinate runtime waiting and wakeup handling
- commit the event-store / checkpoint-store / read-model transaction boundary
- expose public API and CLI entrypoints

### What `OperatorService` should stop doing

- mutating canonical business state directly
- embedding reducer semantics in helper call ordering
- treating technical fact reconciliation as ad hoc snapshot patching

## Open Questions

These do not block the architecture, but they still need implementation decisions:

- exact serialized event names and payload schemas
- whether `ExecutionResultAttached` should be canonical or a read-model reference only
- whether policy applicability should be recomputed on replay or fully stored in domain-event form
- whether 20 events / 5 seconds is the right initial checkpoint threshold in production

## Recommended Next Step

Use this document as the implementation bridge between RFC 0009 and the first code-slice RFC or
ADR set:

1. event-store and checkpoint-store contracts
2. projector and reducer slices
3. fact recorder and translator seams
4. `OperatorService` reduction plan
