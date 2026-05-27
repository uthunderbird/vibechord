# ADR 0003: Adapter And Brain Protocol Boundaries

- Date: 2026-05-23

## Decision Status

Accepted

## Implementation Status

Partial

Scope: fake brain, fake agent, local process-agent adapter, local process-brain
adapter, and OpenAI Responses brain adapter verified.

## Context

`vibechord` must supervise heterogeneous agents and use an internal operator
brain without coupling the core loop to one vendor or invocation mechanism.

## Decision

The operation loop depends on protocol contracts for:

- operator brain;
- external agent adapter;
- clock;
- event store;
- command inbox/source;
- live-feed sink;
- console/output where needed.

Vendor-specific behavior lives in integration adapters.

## Required Properties

- Core/domain/application modules do not import vendor adapters.
- Protocols have conformance tests.
- Fake implementations exist for E2E harnesses.
- Provider DTOs are mapped into domain decisions/results at boundaries.

## Consequences

### Positive

- The operation loop can be tested without network or real agents.
- New agent providers can be added without changing core semantics.

### Negative

- Protocols and mappers require discipline before provider code exists.

## Verification Plan

- Scenario coverage: VS-002, VS-011, and VS-012 in
  [VERIFICATION-SCENARIOS.md](../VERIFICATION-SCENARIOS.md).
- Import-boundary architecture tests.
- Protocol conformance suites.
- Fake brain/adapter operation-loop tests.
- Provider DTO mapping tests once real providers are added.
