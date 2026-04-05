# ADR 0081: AdapterRuntime public protocol and transport ownership

## Status

Accepted

## Context

[`RFC 0010`](../rfc/0010-async-runtime-lifecycles-and-session-ownership.md)
introduces `AdapterRuntime` as the transport-focused runtime boundary beneath operation-level
coordination and above vendor/subprocess mechanics.

The repository still exposes an `AgentAdapter`-shaped contract and some ACP-specific helpers, but
the public transport/runtime boundary is not yet frozen.

The open question is narrow:

- what public responsibilities belong to `AdapterRuntime`
- which lifecycle contract expresses transport ownership
- what kind of events leave this layer

This must be decided before session/runtime layers can be made explicit without adapter/session
semantic bleed.

### Current truth

The repository already separates some transport concerns in practice, but not through an adopted
public `AdapterRuntime` protocol. Some lifecycle and transport details are still expressed through
legacy adapter methods rather than an explicit async runtime boundary.

## Decision

`AdapterRuntime` is the public transport-ownership protocol for adapter-managed subprocess or
vendor connections.

### Owned responsibilities

`AdapterRuntime` owns:

- acquisition and cleanup of transport/subprocess resources
- adapter-shaped command ingress
- observation of raw adapter/vendor runtime notifications
- transport-scoped cancellation

### Lifecycle contract

`AdapterRuntime` must expose an explicit asynchronous enter/exit lifecycle boundary, whether by
`__aenter__` / `__aexit__` directly or by a public equivalent with the same semantics.

Transport cleanup must be attached to that lifecycle boundary, not hidden in best-effort finalizer
behavior.

### Event egress

The outward event surface of `AdapterRuntime` is `AdapterFact`.

`AdapterRuntime` must not emit:

- `TechnicalFact`
- `DomainEvent`

It may normalize vendor noise into adapter-shaped facts, but it must stop at the transport/runtime
boundary.

### Cancellation responsibility

`AdapterRuntime.cancel(...)` or an equivalent public operation is responsible for transport-level
cancellation and teardown intent.

It is not responsible for declaring business-level consequences of that cancellation.

### Relation to current adapters

Existing adapter implementations and ACP connection helpers may evolve toward this contract
incrementally, but once the public boundary is adopted they must be judged by transport ownership,
not by legacy poll/collect naming.

## Consequences

- Transport concerns get an explicit home that does not pretend to own session continuity or
  business translation.
- Adapters become easier to compare across vendors because their public contract is transport-first.
- Session-layer ADRs can build on a stable source of `AdapterFact` without adapter/session drift.
- Cleanup semantics become explicit architectural behavior instead of incidental implementation.

## Closure Notes

- The repository now exposes an explicit public `AdapterRuntime` protocol with:
  - async lifecycle (`__aenter__` / `__aexit__`)
  - transport command ingress
  - async adapter-fact egress
  - explicit cancellation
- The repository now contains a first transport-focused implementation:
  - `AcpAdapterRuntime` owns ACP connection start/close, command dispatch, and live
    `AdapterFactDraft` emission from raw ACP notifications
- Adapter-runtime commands are now represented through explicit typed `AdapterCommand` payloads
  rather than implicit direct calls to ACP connection methods.
- This ADR is accepted as a foundation boundary. Existing top-level adapters still primarily expose
  the legacy `AgentAdapter` contract; full repository-wide cutover to `AdapterRuntime` remains
  follow-up work under later RFC 0010 ADRs.
- Verification:
  - dedicated adapter-runtime tests pass
  - full repository test suite passes (`293 passed, 11 skipped`)

## This ADR does not decide

- the final Python method names for the protocol
- buffering or backpressure semantics for the event stream
- how `AgentSessionRuntime` consumes adapter facts
- the operation-level coordination boundary

Those are covered by later ADRs in this RFC 0010 batch.

## Alternatives Considered

### Keep the current adapter contract as the long-term public runtime boundary

Rejected. It under-specifies lifecycle ownership and blends transport mechanics with higher-level
runtime semantics.

### Let adapters emit technical facts directly

Rejected. That would collapse the adapter/session normalization seam chosen by RFC 0010.

### Model adapter lifecycle only through internal helpers

Rejected. The lifecycle boundary is part of the architecture, not an implementation detail.
