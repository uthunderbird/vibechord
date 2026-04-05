# ADR 0070: Fact store and fact translator contracts

## Status

Accepted

## Context

[`RFC 0009`](../rfc/0009-operation-event-sourced-state-model-and-runtime-architecture.md)
chooses a layered write pipeline:

1. `Command`
2. `AdapterFact`
3. `TechnicalFact`
4. `DomainEvent`
5. `OperationCheckpoint`

[`ADR 0069`](./0069-operation-event-store-and-checkpoint-store-contracts.md) fixes the storage
contract for domain events and checkpoints. The next unresolved executable boundary is the
non-canonical fact layer:

- what `FactStore` persists
- what `FactTranslator` is allowed to do
- how adapter facts become technical facts
- how technical facts become domain events
- what ordering and idempotency guarantees are required

Without this ADR, at least four failure modes remain likely:

1. adapters leak vendor-specific payload semantics directly into domain events
2. reducers start depending on technical facts, violating canonical replay boundaries
3. translators become ad hoc state mutators rather than deterministic mappers
4. duplicate or out-of-order runtime observations produce duplicate domain consequences

## Decision

### `FactStore` is non-canonical

`FactStore` is a persisted non-canonical store for:

- adapter facts
- technical facts

It exists for:

- deterministic translation
- recovery and reconciliation
- forensic inspection
- read models that need technical/runtime detail

It is **not** part of canonical business replay.

If `FactStore` is lost but `OperationEventStore` and `OperationCheckpointStore` remain intact:

- canonical business state remains recoverable
- some technical reconciliation and forensic detail may be lost

That is acceptable by design.

### Two fact families

#### Adapter facts

`AdapterFact` is raw vendor-facing or runtime-facing input.

Examples:

- raw ACP notifications
- raw disconnect payloads
- raw completion payloads
- raw progress payloads

`AdapterFact` payloads may be adapter-specific.

#### Technical facts

`TechnicalFact` is the normalized operator-runtime interpretation of one or more adapter facts.

Examples:

- `ExecutionStartObserved`
- `ExecutionHeartbeatObserved`
- `ExecutionDisconnectObserved`
- `ExecutionCompletionObserved`
- `WakeupEnqueued`
- `WakeupClaimed`
- `WakeupAcked`
- `CooldownExpiredObserved`

Technical facts are operator-shaped and adapter-agnostic enough to support deterministic business
translation.

### Translation pipeline

The allowed translation path is:

1. adapter emits `AdapterFact`
2. agent session runtime normalizes adapter facts into `TechnicalFact`
3. `FactTranslator` derives zero or more `DomainEvent` values from one or more technical facts
4. domain events are appended to `OperationEventStore`

The following shortcuts are forbidden:

- adapter fact -> domain event without passing through the technical-fact layer
- adapter fact -> checkpoint mutation
- technical fact -> checkpoint mutation
- translator directly mutating `OperationCheckpoint`

### Translator role

`FactTranslator` is a deterministic mapper, not a business-state owner.

It may:

- derive domain-event proposals from technical facts
- attach causation references from facts to emitted domain events
- suppress duplicates when the same observation was already translated

It may not:

- inspect or mutate read models as a source of truth
- mutate canonical checkpoint state directly
- bypass the event store
- embed adapter-specific payload structure into domain-event contracts

The runtime-side normalization boundary is therefore:

- `AdapterRuntime` emits `AdapterFact`
- `AgentSessionRuntime` emits session-scoped `TechnicalFact`
- `FactTranslator` emits business `DomainEvent`

This ADR treats `AgentSessionRuntime` as the owner of session continuity semantics and of the
adapter-fact to technical-fact normalization boundary.

### Relationship to checkpoint state

Translating technical facts into domain events may require current canonical checkpoint context.

Example:

- `ExecutionDisconnectObserved` only yields a new domain event if the checkpoint currently shows the
  execution or session in a state where "disconnect" changes business truth

Therefore the translator may read:

- the latest canonical checkpoint
- the relevant untranslated facts

But it may not write checkpoint state.

### Idempotency

Translation must be idempotent.

Required guarantees:

- reprocessing the same adapter fact must not emit duplicate technical facts with new semantic
  identity
- reprocessing the same technical fact set must not emit duplicate domain events for the same
  business consequence

Minimum mechanism:

- each persisted fact has a stable `fact_id`
- each domain event derived from facts records causation metadata referencing the source fact ids
- translation can detect that a given fact or fact-set has already produced a business consequence

This ADR does not force one exact deduplication algorithm. It requires the property.

### Ordering

Facts are ordered per operation by their persisted arrival sequence within `FactStore`.

Translation must preserve this rule:

- a domain event may depend only on facts that are already durably recorded in `FactStore`

The translator may batch multiple facts into one translation step, but it must not emit domain
events based on unpersisted in-memory observations.

### Partial failure semantics

If facts are persisted but translation fails:

- canonical state is unchanged
- translation may be retried later

If translation emits domain-event proposals but event append fails:

- no checkpoint update may occur
- translation may be retried, subject to idempotency rules

This makes fact persistence ahead of domain append acceptable, just as stale checkpoints are
acceptable under ADR 0069.

### Consumer model

`FactStore` has these primary consumers:

- `FactTranslator`
- technical recovery and reconciliation logic
- technical read models
- forensic inspection surfaces

Reducers and canonical replay do not consume `FactStore`.

### Minimal persistence fields

Every persisted fact needs at least:

- `fact_id`
- `operation_id`
- fact family (`adapter` or `technical`)
- subtype / kind
- payload
- persisted timestamp
- optional session / execution / task linkage
- optional source-fact references

This ADR does not require a specific file layout or database schema.

The repository now includes a foundation implementation for this boundary:

- typed adapter-fact and technical-fact models
- a file-backed `FileFactStore`
- stable fact identifiers and per-operation arrival sequencing
- a `FactTranslator` protocol for deterministic technical-fact to domain-event mapping

This establishes the contract without yet wiring end-to-end translation into the current
application loop.

## Consequences

- adapters are forced to emit raw facts rather than business events
- the translator becomes the explicit seam where operator semantics are imposed
- canonical replay remains isolated from adapter/runtime noise
- recovery can retry translation after crashes without corrupting canonical state
- technical read models can use rich runtime detail without polluting business truth

## Verification

Current repository truth:

- `implemented`: typed fact models exist for adapter facts, technical facts, and persisted facts
- `implemented`: `FactStore` and `FactTranslator` protocols define the executable contract
- `implemented`: `FileFactStore` persists ordered non-canonical facts with optimistic append checks
- `verified`: `tests/test_fact_store.py` covers shared per-operation sequencing, family filtering,
  fact-id lookup, stale-sequence conflict handling, batch-write failure semantics, per-operation
  isolation, and same-operation append serialization
- `partial`: end-to-end wiring from runtime observation -> fact translation -> canonical domain
  event append is intentionally not yet integrated into the current application loop

`Accepted` here means the contract boundary and foundation implementation are settled. It does not
claim that the full RFC 0009 pipeline is already wired end-to-end.

## Alternatives Considered

### Let adapters emit domain events directly

Rejected. This leaks vendor/runtime structure into business language and collapses the distinction
between observation and business consequence.

### Skip technical facts and translate raw adapter facts directly into domain events

Rejected. This makes the business layer depend on adapter-specific payload shapes and weakens
cross-adapter normalization.

### Treat technical facts as canonical replay material

Rejected. This would reintroduce runtime chatter into canonical business recovery and undermine RFC
0009's checkpoint boundary.

### Allow translators to mutate checkpoint state directly

Rejected. This recreates the same procedural-state-update ambiguity that RFC 0009 is intended to
eliminate.
