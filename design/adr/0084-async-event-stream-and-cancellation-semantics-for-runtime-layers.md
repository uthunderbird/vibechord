# ADR 0084: Async event-stream and cancellation semantics for runtime layers

## Status

Accepted

## Context

[`RFC 0010`](../rfc/0010-async-runtime-lifecycles-and-session-ownership.md)
already chooses the broad public shape of runtime layers:

- explicit async lifecycle
- command ingress
- async event egress
- explicit cancellation

What remains underdefined is the event-stream contract itself. Without a narrower decision here,
runtime implementations can diverge in invisible but important ways:

- single-consumer vs multi-consumer semantics
- buffering and backpressure expectations
- terminal behavior after cancellation or exit
- re-subscription expectations

Those choices materially affect correctness and resource behavior even if the higher-level runtime
layer names are already chosen.

### Current truth

The repository uses async and polling patterns in different places, but it does not yet expose one
explicit runtime-wide event-stream contract for adapter/session layers.

## Decision

Runtime event streams for `AdapterRuntime` and `AgentSessionRuntime` are explicit async streams with
single-consumer semantics and explicit terminal behavior.

### Single-consumer rule

`events()` or an equivalent event-egress surface is single-consumer.

The architecture must not assume that multiple concurrent consumers can safely subscribe to the same
live stream instance without an explicit fan-out layer.

### Buffering rule

Runtime layers may buffer events internally, but buffering is bounded implementation detail rather
than implicit durable replay.

The stream contract must not imply infinite in-memory retention or hidden replay on late
consumption.

### No implicit replay

Live runtime event streams are for live consumption, not historical replay.

If replay is needed, it must come from persisted facts or events through separate repository
mechanisms, not from re-subscribing to a live runtime stream and expecting old items to reappear.

### Terminal behavior

When a runtime is cancelled or exits, its event stream must become terminal in a well-defined way.

It must not:

- hang indefinitely after terminal runtime shutdown
- silently restart as a new stream of a new session without explicit discontinuity handling

### Cancellation semantics

Cancellation is explicit control intent, not implicit consumer abandonment.

Dropping the event iterator without cancellation or lifecycle exit is not sufficient architectural
cleanup.

Runtime owners must ensure that cancellation and context exit produce resource cleanup and a terminal
stream boundary.

## Consequences

- Runtime implementations get a narrow behavioral target for event egress without freezing every
  mechanism-level detail.
- Consumer code can assume one clear ownership model for live event streams.
- Replay responsibilities stay where the repository already wants them: persisted facts/events and
  canonical checkpoints, not hidden stream caches.
- Cancellation bugs become easier to reason about because shutdown and terminality are architectural
  requirements.

## Closure Notes

- The first runtime-layer implementations now enforce explicit single-consumer stream semantics:
  - `AcpAdapterRuntime.events()` may be claimed only once
  - `AcpAgentSessionRuntime.events()` may be claimed only once
- Runtime cancellation and context exit now lead to terminal streams through the existing runtime
  shutdown paths, rather than silently allowing implicit replay via repeated subscription.
- The repository does not treat repeated `events()` calls as replay or fan-out; callers must add an
  explicit fan-out layer if they need multiple consumers.
- This ADR is accepted as the protocol-semantics foundation slice. It intentionally does not freeze
  queue sizes, sentinel style, or future `OperationRuntime` stream behavior.
- Verification:
  - dedicated adapter-runtime and agent-session-runtime stream tests pass
  - full repository test suite passes (`302 passed, 11 skipped`)

## This ADR does not decide

- exact queue sizes or buffering algorithms
- the exact exception vs sentinel behavior used to signal terminality
- whether `OperationRuntime` also exposes a peer event stream
- transport-specific retry policy

Those remain narrower implementation or protocol details.

## Alternatives Considered

### Multi-consumer live streams by default

Rejected. That introduces hidden fan-out and ownership complexity into the base contract.

### Implicit replay on new subscriptions

Rejected. That blurs live runtime behavior with persisted event/fact replay responsibilities.

### Treat iterator abandonment as sufficient cancellation

Rejected. That makes cleanup and shutdown semantics too implicit for long-lived async runtimes.
