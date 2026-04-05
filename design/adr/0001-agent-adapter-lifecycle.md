# ADR 0001: Agent Adapter Lifecycle Is Session-Oriented

## Status

Superseded by ADR 0081, ADR 0082, ADR 0083, and ADR 0089

## Historical note

This ADR captured the pre-runtime-contract architecture where `AgentAdapter` was the active public
runtime boundary. Repository truth has since moved to `AdapterRuntime`, `AgentSessionRuntime`, and
`OperationRuntime`. Keep this ADR for historical context only.

## Context

`operator` needs a stable way to drive heterogeneous external agents through one operator loop.

That loop must support more than a single request-response exchange. The operator may need to:

- start an agent,
- observe intermediate progress,
- continue the same session with follow-up instructions,
- collect results only after completion,
- and stop or cancel work when constraints require it.

This requirement comes from the nature of the product, not from one specific integration.

Examples:

- Claude Code can often be invoked in a headless request-oriented way, but the operator may still want lifecycle consistency across iterations.
- Codex via ACP is naturally session-based and cannot be cleanly represented as a single blocking call.
- Future hosted agents may expose polling-oriented APIs with asynchronous completion.

If the adapter contract is too narrow, vendor-specific lifecycle details will leak into the operator loop.

## Decision

The `AgentAdapter` contract will be session-oriented.

The core lifecycle shape is:

1. describe adapter capabilities
2. start a session from an operator request
3. optionally send follow-up input to that session
4. poll or inspect session progress
5. collect the current or final result
6. cancel the session if supported or required

The contract should therefore revolve around concepts such as:

- `AgentDescriptor`
- `AgentRequest`
- `AgentSessionHandle`
- `AgentProgress`
- `AgentResult`

Illustrative protocol shape:

```python
class AgentAdapter(Protocol):
    async def describe(self) -> AgentDescriptor: ...
    async def start(self, request: AgentRequest) -> AgentSessionHandle: ...
    async def send(self, handle: AgentSessionHandle, message: AgentMessage) -> None: ...
    async def poll(self, handle: AgentSessionHandle) -> AgentProgress: ...
    async def collect(self, handle: AgentSessionHandle) -> AgentResult: ...
    async def cancel(self, handle: AgentSessionHandle) -> None: ...
```

Not every implementation must have equally rich semantics for every method, but the lifecycle shape is the architectural source of truth.

## Alternatives Considered

### Option A: Single call contract

Example shape:

```python
async def run(request: AgentRequest) -> AgentResult
```

Pros:

- very small API surface
- trivial for simple headless integrations

Cons:

- poorly fits ACP-backed or polling-based agents
- makes follow-up interaction awkward
- forces the operator loop to treat long-running work as a black box
- encourages vendor-specific escape hatches outside the protocol

### Option B: Session-oriented contract

Pros:

- fits both request/response and stateful agents
- supports multi-iteration operator control naturally
- keeps vendor lifecycle details inside adapters
- better supports progress reporting, cancellation, and inspection

Cons:

- larger protocol surface
- slightly heavier implementation burden for simple adapters

## Consequences

- The operator loop can treat Claude Code, Codex via ACP, and future hosted agents through one lifecycle model.
- Simple adapters may internally complete immediately after `start`, but they should still project into the session model.
- Codex via ACP is no longer an architectural exception. It is only a more stateful adapter implementation.
- The domain model now needs explicit session-related types.
- Contract tests should verify lifecycle behavior consistently across adapters.
- The next likely ADR should define how much structure `AgentProgress` and `AgentResult` must contain.
