# ADR 0006: REST API Delivery Surface

- Date: 2026-05-23

## Decision Status

Accepted

## Implementation Status

Verified

Scope: local REST first slice with scoped bearer-token auth, binding guard,
production-mode guardrails, optional TLS wrapping, idempotent mutations, audit
events, and shared query DTOs.

## Context

`vibechord` needs a new REST API surface for programmatic and remote
supervision. REST is useful only if it exposes the same operation semantics as
CLI and TUI. If it grows separate state, command behavior, or error semantics,
the project recreates the delivery-surface drift this rewrite is meant to
avoid.

## Decision

REST is a versioned delivery adapter over shared application command/query
contracts.

Required properties:

- endpoints live under `/v1` for the first public API shape;
- mutating endpoints submit typed commands to `CommandApplication`;
- mutating endpoints require command idempotency keys;
- read endpoints use shared operation and fleet query DTOs;
- event listing uses sequence-derived cursors;
- live streaming emits `LiveFeedEnvelope` payloads;
- HTTP status codes do not replace stable application error codes;
- first implementation binds to loopback by default;
- non-loopback binding requires configured bearer-token auth or an explicit
  unsafe development flag;
- configured bearer tokens are scoped as read-only, read/write control, or
  admin;
- production non-loopback binding rejects unsafe exposure and requires auth plus
  a TLS certificate;
- REST responses include conservative cache/content-type security headers.

REST is not a separate runtime, scheduler, event authority, or persistence
layer.

## Consequences

Positive:

- CLI/TUI/REST parity is directly testable.
- Remote clients can automate supervision without bypassing application
  guardrails.
- API versioning is explicit before any public contract exists.

Negative:

- Delivery DTOs must stabilize earlier.
- REST implementation cannot shortcut through store internals.
- TLS certificate lifecycle is deployment-owned.

## Verification Plan

- Scenario coverage: VS-005, VS-008, and VS-009 in
  [VERIFICATION-SCENARIOS.md](../VERIFICATION-SCENARIOS.md).
- Endpoint-to-command routing tests.
- Endpoint-to-query routing tests.
- Idempotency tests for mutating calls.
- Cursor resume tests for event listing.
- Live-feed schema tests.
- Local binding/configuration tests.
- Parity tests comparing covered REST, CLI JSON, and TUI view-model payloads.
