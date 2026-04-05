# ADR 0083: OperationRuntime coordination boundary and relationship to OperatorService

## Status

Accepted

## Context

[`RFC 0010`](../rfc/0010-async-runtime-lifecycles-and-session-ownership.md)
introduces operation-scoped coordination ownership distinct from both transport and session
ownership. [`RFC 0009`](../rfc/0009-operation-event-sourced-state-model-and-runtime-architecture.md)
and `ADR 0080` simultaneously require `OperatorService` to shrink into an orchestration shell.

The remaining open question is the operation-scoped runtime boundary itself:

- what operation-level runtime coordination owns
- how it relates to `OperatorService`
- how it hands lower-layer observations into translation and canonical event append

Without this decision, `OperatorService` risks remaining the effective operation runtime under a new
name.

### Current truth

Operation-level coordination still lives mostly in `OperatorService` and its helper methods. The
repository does not yet expose a stable operation-runtime boundary distinct from the top-level
application service.

## Decision

`OperationRuntime` is the operation-scoped coordination boundary beneath `OperatorService` and above
adapter/session runtimes.

### Owned responsibilities

`OperationRuntime` owns:

- per-operation concurrency scope
- operation-scoped background tasks and subscriptions
- dispatch of operation-level work into one or more agent session runtimes
- collection of technical facts for translation and follow-up processing
- operation-scoped cancellation boundaries

### Relationship to `OperatorService`

`OperatorService` remains the public application entrypoint and composition root.

`OperationRuntime` is the per-operation coordination owner that `OperatorService` creates,
delegates to, supervises, and tears down.

`OperatorService` must not remain the hidden implementation of all operation-runtime behavior after
this boundary is adopted.

### Relationship to canonical event flow

`OperationRuntime` coordinates runtime work that produces facts and commands, but it is not itself
granted blanket permission to mutate canonical business truth arbitrarily.

It must hand business-affecting consequences into the narrower boundaries already chosen for:

- fact translation
- command application
- domain-event append
- checkpoint projection/materialization

### Publicness

This ADR prefers `OperationRuntime` to become a first-class repository architectural concept even if
its first implementation begins as an internal application runtime rather than a broadly reusable
plugin-facing protocol.

## Consequences

- Operation coordination gets a concrete home separate from both `OperatorService` and
  session-level runtime logic.
- The repository can reduce service-level helper sprawl without flattening everything into one new
  god object.
- Concurrency, subscriptions, and cancellation gain a per-operation owner.
- Later implementation can stage public protocol exposure without losing the architectural
  separation.

## Closure Notes

- The repository now exposes an explicit public `OperationRuntime` protocol for operation-scoped
  coordination.
- The repository now contains a first implementation:
  - `SupervisorBackedOperationRuntime` owns background-turn dispatch, polling, collection,
    finalization, and grouped cancellation against the background supervisor
- `OperatorService` now delegates background coordination through `OperationRuntime` instead of
  owning background-supervisor interactions directly across those paths.
- This ADR is accepted as a foundation boundary. `OperatorService` still contains substantial
  attached-mode and recovery orchestration, so the repository has not yet reached the final minimal
  shell end state from RFC 0010. The operation-scoped coordination boundary is now explicit and
  materially used in production code.
- Verification:
  - dedicated operation-runtime tests pass
  - service regression tests pass
  - full repository test suite passes (`300 passed, 11 skipped`)

## This ADR does not decide

- the final Python method surface of `OperationRuntime`
- whether it must expose the same event-stream shape as lower runtime layers
- the exact orchestration of command application versus fact translation
- whether it is immediately public API or first an internal architectural boundary

Those are intentionally left to narrower implementation ADRs or code rollout.

## Alternatives Considered

### Keep all operation coordination inside `OperatorService`

Rejected. That directly conflicts with the shell-extraction goal of RFC 0009.

### Collapse operation coordination into `AgentSessionRuntime`

Rejected. Session ownership is narrower than operation ownership and must not absorb multi-agent or
operation-scoped concurrency.

### Introduce `OperationRuntime` only as an implementation detail with no documented boundary

Rejected. That would leave the architectural split implicit and easy to regress.
