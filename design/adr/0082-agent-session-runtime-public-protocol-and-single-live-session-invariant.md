# ADR 0082: AgentSessionRuntime public protocol and single-live-session invariant

## Status

Accepted

## Context

[`RFC 0010`](../rfc/0010-async-runtime-lifecycles-and-session-ownership.md)
distinguishes session ownership from transport ownership and imposes a strong invariant: one agent
session runtime must not expose two live sessions concurrently.

The repository already has session-oriented behavior in practice, including reusable sessions and
session-runner code, but it does not yet expose a public architectural contract for
`AgentSessionRuntime`.

This boundary must be made explicit before operation-level runtime coordination can rely on it.

### Current truth

Session continuity and execution behavior exist in the repository, but they are not yet governed by
a public `AgentSessionRuntime` contract with an explicit one-live-session invariant.

## Decision

`AgentSessionRuntime` is the public runtime boundary that owns exactly one logical live session at
a time.

### Owned responsibilities

`AgentSessionRuntime` owns:

- session identity and continuity
- session-scoped command ingress
- conversion from `AdapterFact` to session-scoped `TechnicalFact`
- detection of session replacement, reset, discontinuity, and recoverable interruption
- explicit lifecycle for one live session boundary

### One-live-session invariant

At any point in time, one `AgentSessionRuntime` may have at most one live session.

Forbidden:

- two concurrently live session handles from the same runtime
- silent replacement of a live session with a new one
- recovery probing that creates a second observable live session before the first becomes terminal
  or explicitly abandoned

### Discontinuity observability

If a new session replaces an old one rather than continuing it, that discontinuity must become
observable as `TechnicalFact`.

Silent session reset is forbidden.

### Event egress

`AgentSessionRuntime` emits `TechnicalFact`, not `DomainEvent`.

It may use adapter facts, checkpoint context, or internal continuity state to classify technical
observations, but it must not skip directly to canonical business consequences.

### Lifecycle contract

`AgentSessionRuntime` must expose an explicit async lifecycle boundary, whether through async
context-manager methods or a public equivalent with the same semantics.

## Consequences

- The agent layer gains a concrete non-pass-through responsibility.
- Session discontinuity becomes inspectable instead of being hidden inside adapter behavior.
- Operation-level coordination can reason about one stable session-ownership boundary per runtime.
- Technical-fact production gains a clear home between adapter observations and business
  translation.

## Closure Notes

- The repository now exposes an explicit public `AgentSessionRuntime` protocol with:
  - async lifecycle
  - session-scoped command ingress
  - technical-fact event egress
  - explicit cancellation
- The repository now contains a first ACP-backed implementation:
  - `AcpAgentSessionRuntime` owns one live ACP session at a time over `AdapterRuntime`
  - it rejects a second concurrent `START_SESSION`
  - it emits explicit `session.discontinuity_observed` technical facts on intentional replacement
  - it translates adapter-layer ACP notifications into session-scoped `TechnicalFactDraft`
- This ADR is accepted as a foundation boundary. Existing top-level adapters and `AcpSessionRunner`
  still remain part of current repository truth; full migration of runtime orchestration onto
  `AgentSessionRuntime` remains follow-up work under later RFC 0010 ADRs.
- Verification:
  - dedicated agent-session-runtime tests pass
  - full repository test suite passes (`297 passed, 11 skipped`)

## This ADR does not decide

- the exact Python signatures of `send`, `events`, or `cancel`
- the full stream-consumption semantics for runtime events
- whether current ACP session helpers will be wrapped or replaced
- how operation-level coordination orchestrates multiple session runtimes

Those are covered by adjacent ADRs.

## Alternatives Considered

### Keep session continuity inside adapters

Rejected. That collapses transport and session semantics into one layer and makes normalization less
portable.

### Allow one runtime to multiplex multiple live sessions

Rejected. That weakens the core ownership boundary and makes continuity bugs harder to detect.

### Let the agent session layer emit domain events directly

Rejected. That bypasses the fact-to-domain boundary chosen in RFC 0009 and RFC 0010.
