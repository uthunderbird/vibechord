# RFC 0010: Async runtime lifecycles and session ownership

## Status

Accepted

## Implementation Status

Current repository truth:

- `implemented`: the repository exposes `AdapterRuntime`, `AgentSessionRuntime`, and
  `OperationRuntime` as the public runtime architecture
- `implemented`: adapter and agent-session lifecycles are expressed through explicit async
  enter/exit boundaries in the public contract
- `implemented`: the public runtime interface is command ingress plus async event egress, with
  stream/cancellation semantics defined by accepted ADRs
- `implemented`: session continuity ownership and the one-live-session invariant are enforced at
  the agent-session runtime boundary
- `implemented`: the repository retains `operator-profile` naming for operation-scoped project
  configuration, as fixed by `ADR 0085`
- `implemented`: the runtime-boundary decision batch beneath this RFC is now recorded and accepted
  through `ADR 0081` through `ADR 0085`
- `implemented`: repository-truth closure work for runtime contracts and hosting is accepted
  through `ADR 0089` through `ADR 0091`
- `verified`: runtime cleanup removed `AgentAdapter` as public truth and removed worker-hosted
  execution from the active runtime path

This RFC is now `Accepted`. It describes the current public runtime model of the repository.

## Context

[`RFC 0009`](./0009-operation-event-sourced-state-model-and-runtime-architecture.md)
defines the event-sourced business architecture of an operation:

- one canonical domain event stream per operation
- `AdapterFact -> TechnicalFact -> DomainEvent -> OperationCheckpoint`
- a thin `OperatorService`

That RFC intentionally leaves one lower runtime boundary underspecified:

- what an adapter runtime object is
- what an agent runtime object is
- where subprocess or vendor events stop being transport facts and start being operator-shaped
  runtime facts
- which runtime entities own lifecycle resources and should therefore expose explicit async
  enter/exit boundaries

The current system already treats adapters as wrappers around long-lived subprocess-backed or
session-backed runtimes. At the same time, the operation model already distinguishes reusable
session state from individual execution state. That makes it important not to collapse:

- transport lifecycle
- agent session lifecycle
- operation lifecycle
- business-domain translation

Without a clearer runtime model, at least five failure modes remain likely:

1. adapters silently absorb session semantics that should belong to the agent layer
2. agents degrade into thin renames for adapter processes with no real ownership boundary
3. raw vendor/runtime events leak into business translation without a stable normalization layer
4. lifecycle cleanup and cancellation stay implicit rather than tied to resource ownership
5. per-operation configuration is mislabeled as operator-global configuration, obscuring scope

## Decision

### 1. Distinct runtime layers

This RFC distinguishes three runtime layers:

- `AdapterRuntime`
- `AgentSessionRuntime`
- `OperationRuntime`

These are distinct layers with different ownership and event responsibilities.

They are not synonyms for one another.

### 2. `AdapterRuntime` owns transport and subprocess lifecycle

`AdapterRuntime` is the narrow boundary around transport- or subprocess-level mechanics.

It owns:

- starting and stopping adapter-managed subprocess or transport resources
- sending adapter-shaped commands
- receiving raw adapter-facing or vendor-facing runtime notifications
- cancellation and cleanup of those resources

It does **not** own:

- logical session continuity semantics
- detection of unexpected session reset at the agent layer
- business-domain translation

Its outward event surface is `AdapterFact`.

### 3. `AgentSessionRuntime` owns exactly one live session at a time

`AgentSessionRuntime` is the runtime layer that owns one logical agent session.

Normative invariant:

- one `AgentSessionRuntime` may have at most one live session at a time

For this RFC, a session is `live` while it may still:

- accept commands through the runtime boundary
- emit runtime events through the runtime boundary
- or both

It may:

- continue an existing session
- recover a session after a recoverable interruption
- terminate a session
- start a new session intentionally

If it starts a new session instead of continuing the prior one, that discontinuity must become
explicitly observable to the operator through technical facts. Silent reset is forbidden.

Additional normative guardrails:

- one `AgentSessionRuntime` must not expose two live session handles concurrently
- a replacement session must not become live until the prior session is terminal or explicitly
  abandoned through a discontinuity technical fact
- recoverable interruption handling must preserve the same no-overlap rule; recovery probing must
  not surface a second live session silently

`AgentSessionRuntime` owns:

- session identity and continuity semantics
- mapping adapter facts into session-scoped technical facts
- detection of session restart, replacement, reset, or unexpected discontinuity
- session-scoped command ingress

It does **not** own:

- canonical business translation into domain events
- operation-wide orchestration across multiple agents

Its outward event surface is `TechnicalFact`.

### 4. `OperationRuntime` owns per-operation concurrency and coordination scope

`OperationRuntime` is the operation-scoped coordination owner.

It coordinates:

- concurrent agent session runtimes participating in one operation
- command dispatch into those runtimes
- collection of technical facts and subsequent translation workflow
- per-operation background tasks, subscriptions, and cancellation boundaries

`OperationRuntime` is operation-scoped. It is not the same thing as the top-level `OperatorService`.

This RFC does **not** require `OperationRuntime` to be a peer protocol with the same event-surface
shape as `AdapterRuntime` or `AgentSessionRuntime`. It only fixes the coordination ownership
boundary.

### 5. Async context managers are the architectural lifecycle contract

`AdapterRuntime` and `AgentSessionRuntime` must be modeled as asynchronous context managers.

`OperationRuntime` is also an acceptable and preferred asynchronous context manager when it owns
operation-scoped background tasks or subscriptions.

Rationale:

- resource ownership is explicit
- cleanup and cancellation are attached to the same lifecycle object that acquired the resources
- multiple agents can run concurrently without blocking the operator loop

This RFC does **not** require `OperatorService` itself to be a context manager.

### 6. Public runtime contract is command ingress plus async event egress

The architectural contract for adapter and agent runtimes is:

- explicit async lifecycle
- explicit command ingress
- explicit async event stream egress
- explicit cancellation

Generators may be used internally as an implementation technique, but generator protocol methods
such as `send`, `throw`, and `close` are not the architectural contract.

The system should be described in terms of:

- runtime objects
- commands
- event streams
- cancellation and exit semantics

not in terms of generator mechanics.

This RFC fixes the existence of an async event-stream boundary, but does not yet freeze the full
stream contract.

Concrete adapter and agent implementations must still define, in their narrower contracts:

- whether `events()` is single-consumer
- what buffering or backpressure semantics apply
- whether any replay or re-subscription behavior exists

### 7. Event translation happens at two different runtime boundaries

The event path is:

1. external subprocess or vendor runtime emits raw observations
2. `AdapterRuntime` surfaces those as `AdapterFact`
3. `AgentSessionRuntime` converts adapter facts into session-scoped `TechnicalFact`
4. `FactTranslator` converts technical facts plus canonical checkpoint context into `DomainEvent`

This RFC therefore chooses two distinct translation seams:

- transport/vendor -> operator runtime normalization happens at the adapter-to-agent boundary
- operator runtime -> business-domain consequence happens at the fact-translator boundary

`AgentSessionRuntime` must not emit `DomainEvent` directly.

The rollout boundaries beneath this specification were split into:

- [`ADR 0081`](../adr/0081-adapter-runtime-public-protocol-and-transport-ownership.md)
- [`ADR 0082`](../adr/0082-agent-session-runtime-public-protocol-and-single-live-session-invariant.md)
- [`ADR 0083`](../adr/0083-operation-runtime-coordination-boundary-and-relationship-to-operator-service.md)
- [`ADR 0084`](../adr/0084-async-event-stream-and-cancellation-semantics-for-runtime-layers.md)
- [`ADR 0085`](../adr/0085-retain-operator-profile-naming-for-operation-scoped-project-configuration.md)

The closure boundaries that completed repository-truth adoption were:

- [`ADR 0089`](../adr/0089-runtime-factory-composition-root-and-agentadapter-retirement.md)
- [`ADR 0090`](../adr/0090-single-process-async-runtime-hosting-and-background-worker-removal.md)
- [`ADR 0091`](../adr/0091-legacy-runtime-cleanup-and-document-supersession-after-cutover.md)

### 8. `operator-profile` is retained for operation-scoped project configuration

Configuration or policy that shapes one operation's planning or runtime behavior should be modeled
through operation-scoped project configuration even though the retained repository filename is
`operator-profile`.

The retained name is a repository surface decision, not a statement that the configuration is
process-global.

`ADR 0085` fixes this naming boundary for the current architecture wave: `operator-profile` remains
the canonical filename and term in repository truth, while its semantics remain operation-scoped.

## Architectural consequences

### Runtime ownership summary

`AdapterRuntime`
- resource scope: subprocess / transport
- input: adapter commands
- output: `AdapterFact`

`AgentSessionRuntime`
- resource scope: one live logical session
- input: agent-session commands
- output: `TechnicalFact`

`OperationRuntime`
- resource scope: one operation
- input: operation commands
- output: coordinated runtime work leading to translation and canonical event append

### Concurrency model

The runtime model is explicitly asynchronous.

`operator` must be able to:

- host multiple live agent session runtimes within one operation
- supervise multiple operations over time
- consume event streams without blocking on one agent while others continue to make progress

This RFC therefore assumes async coordination as the default rather than as an optional adapter
optimization.

### Alignment with RFC 0009

This RFC refines, but does not replace, the event pipeline chosen by `RFC 0009`.

It makes the lower layers concrete:

- `AdapterRuntime` is the producer of `AdapterFact`
- `AgentSessionRuntime` is the producer of session-scoped `TechnicalFact`
- `FactTranslator` remains the only layer that emits business `DomainEvent`

### Recommended protocol shape

This RFC intentionally does not freeze final Python signatures, but the intended protocol shape is:

```python
class AdapterRuntime(Protocol):
    async def __aenter__(self) -> "AdapterRuntime": ...
    async def __aexit__(self, exc_type, exc, tb) -> None: ...
    async def send(self, command: AdapterCommand) -> None: ...
    def events(self) -> AsyncIterator[AdapterFact]: ...
    async def cancel(self, reason: str | None = None) -> None: ...
```

```python
class AgentSessionRuntime(Protocol):
    async def __aenter__(self) -> "AgentSessionRuntime": ...
    async def __aexit__(self, exc_type, exc, tb) -> None: ...
    async def send(self, command: AgentCommand) -> None: ...
    def events(self) -> AsyncIterator[TechnicalFact]: ...
    async def cancel(self, reason: str | None = None) -> None: ...
```

```python
class OperationRuntime(Protocol):
    async def __aenter__(self) -> "OperationRuntime": ...
    async def __aexit__(self, exc_type, exc, tb) -> None: ...
    async def dispatch(self, command: OperationCommand) -> None: ...
```

The method names are illustrative rather than canonical. The lifecycle and event-boundary shape is
the actual decision.

Unlike the adapter and agent protocol sketches above, this `OperationRuntime` sketch is
intentionally minimal. It illustrates operation-scoped coordination ownership, not a finalized
peer event-runtime contract.

## Criteria To Close

This RFC can move beyond `Proposed` only when all of the following are true:

1. The repository exposes explicit runtime-layer contracts equivalent to `AdapterRuntime`,
   `AgentSessionRuntime`, and operation-scoped coordination ownership, per `ADR 0081`,
   `ADR 0082`, and `ADR 0083`.
2. Adapter and agent runtime lifecycles are expressed through explicit async enter/exit boundaries
   in the public architectural contract, not just internal helpers.
3. The public runtime interface is command ingress plus async event egress, rather than the current
   poll/collect adapter contract, with stream/cancellation semantics consistent with `ADR 0084`.
4. Session continuity ownership and the one-live-session invariant are enforced at the agent-session
   runtime boundary by architecture, not only by incidental implementation behavior.
5. The per-operation naming boundary described here remains aligned with repository truth,
   including retained `operator-profile` naming as described by `ADR 0085`.

## Anti-patterns

The following are explicit anti-patterns under this RFC:

- `AdapterRuntime` that emits `DomainEvent` directly
- `AgentSessionRuntime` that is only a thin rename for transport or subprocess handling
- agent runtime that can silently replace one live session with another
- public architecture that requires generator protocol mechanics as the primary runtime interface
- top-level `operator` object that conflates process-wide service lifetime with one operation's
  runtime ownership
- per-operation configuration treated as process-global merely because the retained filename uses
  `operator-profile`

## Alternatives considered

### Make the adapter own both transport and session semantics

Rejected.

This collapses vendor transport lifecycle and logical session lifecycle into one boundary and makes
cross-adapter normalization harder.

### Let the agent emit domain events directly

Rejected.

This bypasses the fact/domain seam already chosen in `RFC 0009` and `ADR 0070`.

### Make generator protocol the primary public runtime contract

Rejected.

That is a mechanism-level choice that unnecessarily couples architecture to Python generator
semantics and obscures the clearer model of lifecycle + command ingress + async event egress.

### Keep `operator-profile` as the retained repository surface for per-operation semantics

Accepted later by `ADR 0085`.

The repository had already standardized on `operator-profile` across code, CLI behavior, tests,
and docs. The architecture wave therefore retained the established filename and corrected the RFC
instead of forcing rename churn with little architectural payoff.

## Consequences

- adapter contracts become simpler and more transport-focused
- the agent layer gains a concrete reason to exist beyond pass-through wrapping
- session discontinuity becomes explicit and inspectable
- async resource cleanup becomes part of the architecture rather than an implementation accident
- the lower runtime layers align cleanly with the fact taxonomy from `RFC 0009` and `ADR 0070`
- future implementation work can define adapter, agent, and operation runtime protocols without
  reopening the question of where business translation happens
