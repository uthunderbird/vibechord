# Moving Parts

Status: `verified`

This document defines the minimum set of moving parts for `vibechord`.
Implemented evidence is tracked in
[`../docs/verification-matrix.md`](../docs/verification-matrix.md).

## Purpose

`vibechord` should cover the required product behavior with the fewest
independent authority boundaries.

Minimizing moving parts does not mean hiding behavior inside one large object.
It means every independently replaceable part must have a reason to vary.

## Functional Requirements Covered

The minimum architecture must cover:

- operation lifecycle and resumable work;
- deterministic stop policies and guardrails;
- event-backed canonical state and replay;
- human attention and answers;
- live operator messages;
- fleet supervision;
- external agent invocation;
- CLI, TUI, and REST delivery surfaces;
- future SDK/MCP delivery surfaces;
- local fake verification harness;
- external proactive projection safety.

## Minimal Core Set

The first implementation should have exactly these core moving parts.

### 1. Domain Model

Owns the vocabulary and invariants:

- operation ids, goals, status, budgets, stop reasons;
- commands;
- events;
- attention requests;
- operator messages;
- agent invocation/result values;
- projection and live-feed DTO shapes.

Reason to vary: product semantics change.

Must not own:

- persistence;
- provider-specific DTOs;
- CLI/TUI/REST rendering.

### 2. CommandApplication

Owns command validation, idempotency, and canonical event append decisions.

Reason to vary: command semantics change.

Must be the only application path for mutating operation state. Delivery
surfaces, adapters, and proactive systems must not write canonical operation
events directly.

### 3. OperationDriver

Owns the iteration loop:

1. replay operation state;
2. drain accepted commands;
3. enforce deterministic guardrails;
4. ask the brain when needed;
5. invoke external agents when selected;
6. append resulting events through the same authority;
7. request projection refresh and live-feed emission.

Reason to vary: loop policy changes.

Must not contain provider-specific behavior or surface-specific rendering.

### 4. EventStore

Owns durable append/replay mechanics.

Reason to vary: persistence backend changes.

Initial implementation should be local and inspectable. Backend replacement is
allowed only behind the same append/replay/idempotency contract.

### 5. ProjectionService

Owns all derived read models and live-feed envelopes:

- operation status/detail;
- fleet snapshot;
- live-feed envelopes;
- staleness and provenance labels.

Reason to vary: read-model shape changes.

This intentionally replaces separate first-tranche services such as
`OperationQueries`, `FleetQueries`, and `LiveFeedService`. Those names may
appear as internal modules or functions, but they should not become independent
authority boundaries without a documented reason.

### 6. AdapterGateway

Owns calls through external-facing protocols:

- operator brain;
- external agent adapter;
- clock/time provider;
- process/terminal adapter when required;
- output/event sink when required.

Reason to vary: integration boundary changes.

Vendor-specific implementations live behind this gateway. The gateway reports
results back as domain-level values and does not write canonical events by
itself.

## Thin Delivery Surfaces

CLI, TUI, REST, future SDK, and future MCP are delivery surfaces, not core
moving parts.

Each delivery surface may own:

- request parsing;
- authentication or local exposure checks where relevant;
- rendering;
- transport mechanics;
- surface-local input handling.

Each delivery surface must reuse:

- shared operation resolution;
- `CommandApplication` for mutation;
- `ProjectionService` for reads;
- shared command/error DTOs;
- shared live-feed envelope shape.

Adding a new delivery surface must not add a new business authority.

## Extension Rules

New moving parts are allowed only when at least one condition is true:

- a new dependency varies independently and cannot be hidden behind
  `AdapterGateway`;
- a new persistence or projection backend must satisfy the existing contract;
- a new delivery surface cannot be expressed as thin command/query rendering;
- a feature would otherwise force core modules to import vendor-specific code;
- a verification scenario cannot be tested without a separate boundary.

Before adding a new core moving part, implementation must update:

- this document;
- [ARCHITECTURE.md](ARCHITECTURE.md);
- the relevant ADR or a new ADR;
- [VERIFICATION-SCENARIOS.md](VERIFICATION-SCENARIOS.md) if coverage changes.

## Forbidden Splits

The first implementation must not introduce:

- per-surface command handlers;
- REST-only operation state;
- TUI-owned canonical state;
- adapter-owned canonical event writes;
- separate fleet authority outside projections;
- separate live-chat authority outside commands/events/projections;
- hidden fallback adapters without an explicit migration note;
- plugin framework abstractions before a concrete second implementation needs
  them.

## Requirement Coverage Matrix

| Requirement | Core part(s) | Extension surface |
| --- | --- | --- |
| Operation lifecycle | Domain, CommandApplication, OperationDriver, EventStore | CLI, TUI, REST |
| Resumable work | EventStore, OperationDriver, ProjectionService | CLI, TUI, REST |
| Stop policies and budgets | Domain, OperationDriver | none |
| Event-backed truth | Domain, CommandApplication, EventStore | all surfaces read projections |
| Human attention | Domain, CommandApplication, ProjectionService | CLI, TUI, REST |
| Live operator chat | Domain, CommandApplication, ProjectionService | CLI, TUI, REST |
| Fleet supervision | ProjectionService, EventStore | CLI, TUI, REST |
| External agent invocation | OperationDriver, AdapterGateway | adapter implementations |
| CLI | CommandApplication, ProjectionService | CLI delivery |
| TUI | CommandApplication, ProjectionService | TUI delivery |
| REST API | CommandApplication, ProjectionService | REST delivery |
| Future SDK/MCP | CommandApplication, ProjectionService | SDK/MCP delivery |
| Proactive external projection | CommandApplication, ProjectionService | external projection adapter |
| Verification harness | all six core parts with fakes | fake delivery/adapter entrypoints |

## Implementation Guidance

The first tranche should resist turning every noun into a service.

Preferred first-tranche shape:

- one domain package;
- one application command module/service;
- one operation driver;
- one event store interface plus local implementation;
- one projection module/service;
- one adapter gateway plus fake implementations;
- delivery packages that only parse, render, and call application contracts.

If implementation pressure suggests adding another core service, treat that as
an architecture decision, not a local refactor.
