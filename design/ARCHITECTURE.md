# Architecture

Status: `verified`

This document is the implementation architecture authority for `vibechord`.
Implemented evidence is tracked in
[`../docs/verification-matrix.md`](../docs/verification-matrix.md).

## System Shape

`vibechord` has four architectural parts:

1. domain model;
2. operation application loop;
3. integration adapters;
4. delivery surfaces.

The operation loop is the center. Everything else either informs its decisions,
executes its decisions, persists its truth, or exposes its state.

[MOVING-PARTS.md](MOVING-PARTS.md) defines the minimum set of core
moving parts and extension rules. This architecture should not grow new
authority boundaries without satisfying that document.

## Authority Rules

- Canonical operation truth is event-sourced.
- Application command handlers are the only writers of canonical operation
  events.
- Read models, checkpoints, fleet rows, and live feeds are derived.
- Runtime liveness facts are overlays with provenance.
- Forensic upstream logs are evidence, not canonical business truth.
- CLI, TUI, REST, and future SDK/MCP surfaces use the same application
  command/query contracts.

## Layers

### Domain

The domain layer defines the language of the system.

Initial domain concepts:

- `Operation`
- `OperationId`
- `OperationGoal`
- `OperationStatus`
- `ExecutionBudget`
- `StopPolicy`
- `StopReason`
- `AgentDescriptor`
- `AgentInvocation`
- `AgentResult`
- `AttentionRequest`
- `OperatorMessage`
- `RunEvent`
- `FleetSnapshot`
- `LiveFeedEnvelope`

Domain objects should be small and explicit. If Pydantic is adopted, it should
serve schema clarity rather than blur domain objects with provider payloads.

### Application

The application layer owns the operation loop and command/query contracts.

Initial application moving parts:

- `OperationDriver` — runs one operation iteration loop under deterministic
  guardrails.
- `CommandApplication` — validates and applies operation commands as canonical
  events.
- `ProjectionService` — builds one-operation status/detail payloads, fleet
  projections, and live-feed envelopes from replay, projections, and overlays.
- `AdapterGateway` — invokes operator brain and external agent adapters through
  protocol contracts.

Service-minimalism gate: create a named service only when it owns a real
authority boundary, has a concrete caller, or removes meaningful coupling.
Do not create service families just because `operator` eventually grew them.

The first tranche should not split `ProjectionService` into independent
`OperationQueries`, `FleetQueries`, or `LiveFeedService` authorities. Those may
exist as internal functions or modules only.

### Integration

Integration adapters hide external specifics.

Initial adapter families:

- operator-brain LLM provider;
- external agent runtime adapters;
- process/terminal adapters;
- file-backed event/read-model stores;
- event sinks;
- clock/time providers.

Vendor-specific behavior must remain here.

### Delivery

Delivery surfaces drive the application layer.

Initial delivery surfaces:

- CLI;
- TUI workbench;
- REST API.

Planned later surfaces:

- Python SDK;
- MCP server.

Delivery may render differently, but it must not create its own business
authority. Delivery actions use the same command application path. Delivery
reads use `ProjectionService` through shared delivery contracts.

## Event Store

Initial implementation should use an append-only file-backed event store before
introducing a database.

Required event-store semantics:

- each event has `operation_id`, monotonically increasing `sequence`, `event_id`,
  `kind`, `timestamp`, and payload;
- append rejects sequence conflicts;
- replay by operation id is deterministic;
- command ids are idempotency keys for command-caused events;
- sequence gaps are explicit errors or live-feed warnings, never silent;
- corrupted events fail loudly with file path and sequence context.

The first store may be JSONL if it satisfies the contract and has direct tests.
SQLite may be introduced later behind the same `EventStore` contract.

## Operation Loop

The operation loop executes under fakeable dependencies:

1. load replayed operation state;
2. drain and apply pending commands;
3. enforce stop policy;
4. assemble planning context;
5. ask the operator brain for the next decision when needed;
6. invoke agent adapters when selected;
7. ingest results and append events;
8. refresh read projections;
9. emit live-feed envelopes;
10. repeat until terminal or blocked.

The brain may recommend completion or failure, but the runtime owns whether the
recommendation is accepted.

## Commands

Operation commands are typed inputs to the application layer.

Initial command families:

- start operation;
- cancel operation;
- pause/resume operation;
- answer attention;
- post operator message;
- interrupt current agent turn;
- patch goal/constraints;
- adjust allowed agents or execution profile.

Every accepted command produces `command.accepted` plus any resulting domain
events. Every rejected command produces `command.rejected` with a stable reason.

## Read Models and Live Feed

Read models are derived from canonical events.

Required projection metadata:

- source operation id;
- projection type;
- source event sequence;
- generated timestamp;
- stale/fresh/partial label.

Live feed envelopes identify whether payloads are:

- canonical event;
- derived projection;
- runtime overlay;
- warning;
- forensic reference.

## Fleet

Fleet is a first-class read model.

Fleet rows include:

- operation id and display label;
- status;
- objective summary;
- active agent/session cue;
- attention summary;
- live chat cue;
- terminal/stop reason when present;
- projection freshness labels.

Fleet is consumed by CLI, TUI, and REST through shared query contracts.

## Live Operator Chat

Live chat is a first-class operation input channel.

Rules:

- operator chat messages are distinct from typed commands and attention answers;
- posting a message uses the shared command authority;
- messages enter the brain context for a bounded number of planning cycles;
- expiry is explicit and evented;
- delivery surfaces may render chat differently, but message authority is
  shared.

## REST API

REST is a delivery surface over the same command/query contracts as CLI and
TUI.

REST must not introduce separate operation state, command semantics, or error
taxonomy. It exposes remote programmatic access to operations, fleet, live
feeds, and operator chat.

## Testability

Architecture choices must preserve [TESTING-RAILS.md](TESTING-RAILS.md).

Implementation must provide:

- fake clock;
- fake operator brain;
- fake agent adapter;
- tempdir-backed event store;
- scripted command source;
- inspectable E2E harness summary.

Fitness checks should fail if implementation adds a new core authority boundary
without updating [MOVING-PARTS.md](MOVING-PARTS.md) and an ADR.

## promptstrings and agent-dashboard

Applicability remains deferred until prompt assembly and projection surfaces
exist.

Working hypotheses:

- `promptstrings` may be useful for prompt assembly if it reduces prompt drift
  without hiding control-plane decisions.
- `agent-dashboard` may be useful for agent-facing or TUI-facing screen
  projection if it remains a projection boundary rather than a runtime.

They are not initial dependencies.
