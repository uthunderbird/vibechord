# ADR 0089: Runtime factory composition root and AgentAdapter retirement

## Status

Accepted

## Context

`RFC 0010` cannot be closed while repository truth still presents `AgentAdapter` as the public
runtime contract and composition root surface.

Today:

- bootstrap builds `AgentAdapter` instances
- ACP-backed implementations still present the legacy `start/send/poll/collect/cancel/close`
  lifecycle
- runtime composition is centered on adapter objects rather than runtime factories and runtime
  protocols

### Current truth

The repository already contains `AdapterRuntime`, `AgentSessionRuntime`, and `OperationRuntime`
protocols, but the composition root still assembles `AgentAdapter`-era truth.

## Decision

The composition root must retire `AgentAdapter` as public runtime truth and assemble the system
around runtime factories or runtime registries that produce:

- `AdapterRuntime`
- `AgentSessionRuntime`
- `OperationRuntime`

### Composition rule

`build_service` and adjacent bootstrap wiring must no longer depend on `dict[str, AgentAdapter]` as
the central runtime dependency surface.

Instead, the composition root must provide runtime-oriented factories or providers keyed by agent
identity.

### ACP implementation rule

ACP-backed implementations remain valid, but they must be expressed as implementations of the new
runtime contracts rather than as primary `AgentAdapter` objects.

### Retirement rule

`AgentAdapter` is retired from:

- public architecture docs
- composition-root authority
- core protocol exports used as repository truth

## Consequences

- `RFC 0010` can be satisfied by repository truth rather than by parallel experimental contracts.
- ACP adapter code can align with transport/session boundaries without legacy facade layering.
- Bootstrap wiring becomes explicit about runtime ownership.

## This ADR does not decide

- whether the runtime host is single-process or multi-process
- the exact in-process orchestration loop for one operation
- business-domain append ownership

## Alternatives Considered

### Keep `AgentAdapter` as a stable outer facade above the new runtime contracts

Rejected. That would preserve the old public truth and keep `RFC 0010` only partially implemented.

### Retire `AgentAdapter` only in docs while preserving it in bootstrap and core wiring

Rejected. That would produce another paper cutover instead of a real one.

## Verification

- `verified`: bootstrap now assembles agent integrations through runtime-oriented bindings rather
  than directly through `build_agent_adapters()`.
- `verified`: `OperatorService` now accepts runtime bindings as a first-class constructor surface;
  direct `adapters=` injection remains only as an internal compatibility path for legacy tests and
  in-memory doubles rather than as canonical runtime truth.
- `verified`: live runtime modules no longer import the public `AgentAdapter` protocol directly;
  attached execution and supervisor compatibility paths now depend on internal compatibility
  protocols instead of treating `AgentAdapter` as active repository truth.
- `verified`: `agent_operator.protocols` no longer exports `AgentAdapter`; the package-level public
  runtime surface now exposes runtime contracts rather than the legacy adapter protocol.
- `verified`: active ACP adapter/session-runner code now types requests through `AgentRunRequest`
  rather than through the legacy `AgentRequest` protocol exported from `agent_operator.protocols`.
- `verified`: the legacy module `src/agent_operator/protocols/agents.py` has been removed; the
  retired adapter protocol no longer exists as active repository code.
- `verified`: the repository now contains `AgentRuntimeBinding` and
  `build_agent_runtime_bindings()` as the composition-root surface for ACP-backed agents.
- `verified`: focused tests cover adapter-runtime factory creation, session-runtime factory
  creation, runtime-backed attached-session execution, and service construction from runtime
  bindings.
- `verified`: canonical attached execution now runs through `AttachedSessionRuntimeRegistry`, which
  owns live `AgentSessionRuntime` instances instead of raw adapter maps or public `AgentAdapter`
  facades.
- `verified`: `build_agent_adapters()` no longer exists in the active public `adapters` package
  surface.
- `verified`: canonical in-process background hosting now consumes runtime bindings rather than
  public legacy adapter helpers.

## Implementation notes

What is implemented:

- composition root is no longer centered on `dict[str, AgentAdapter]` as its primary assembly
  concept
- runtime-oriented bindings can produce `AdapterRuntime` and `AgentSessionRuntime` from one place
- the public service-construction path is now binding-oriented rather than adapter-oriented
- active runtime modules no longer treat `AgentAdapter` as a required public dependency surface
- the package-level protocol export surface no longer presents `AgentAdapter` as public runtime
  truth
- active adapter/runtime code no longer depends on `AgentRequest` as a public protocol-typing
  surface
- the retired adapter protocol module no longer exists in active repository code
- attached execution now uses session-runtime-backed registry ownership instead of the removed
  `attached_registry.py` compatibility layer
- older ADRs and RFCs that still mention `AgentAdapter` as current truth are now explicitly marked
  as historical or superseded
