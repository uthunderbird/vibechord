# ADR 0048: Operator-owned ACP substrate and per-adapter SDK migration

## Status

Accepted

## Historical note

This ADR still correctly describes the ACP substrate seam, but its references to `AgentAdapter`
as the operator-facing runtime contract are historical. Current repository truth uses
`AdapterRuntime`, `AgentSessionRuntime`, and `OperationRuntime` per ADR 0081, ADR 0082, ADR 0083,
ADR 0089, and ADR 0091.

## Context

`operator` had bespoke ACP connection logic embedded directly in `claude_acp` and `codex_acp`
adapter construction. That made it hard to:

- migrate one ACP adapter at a time,
- keep foreground and background-worker wiring aligned,
- and adopt the ACP Python SDK without changing the operator-facing `AgentAdapter` lifecycle.

RFC 0001 established the desired boundary: `operator` should own the session-oriented
`AgentAdapter` contract, while ACP wire/session mechanics should live below it in an injected ACP
substrate.

## Decision

Introduce an operator-owned ACP substrate seam beneath ACP-backed adapters.

The substrate contract is the existing `AcpConnection` interface used by adapters. It is now an
explicit injection seam with multiple implementations:

- `AcpSubprocessConnection` for the bespoke ACP path
- `AcpSdkConnection` for the ACP Python SDK-backed path

Per-adapter selection happens through adapter settings:

- `claude_acp.substrate_backend`
- `codex_acp.substrate_backend`

Bootstrap and background-worker composition must both build ACP adapters through the same shared
adapter factory so the per-adapter substrate choice is consistent in attached and background paths.

The operator-facing `AgentAdapter` lifecycle remains unchanged:

- `start`
- `send`
- `poll`
- `collect`
- `cancel`
- `close`

## Alternatives Considered

- Keep ACP backend choice hard-coded inside each adapter.
- Add one global ACP backend switch for the whole runtime.
- Move ACP SDK concepts directly into `AgentAdapter`.

## Consequences

- Positive:
  - ACP backend choice is now injectable per adapter.
  - `codex_acp` and `claude_acp` can migrate independently.
  - foreground and background-worker ACP wiring share one construction path.
- Negative:
  - the ACP seam still exposes raw ACP-shaped payloads to adapters for now.
  - mixed-mode migration adds configuration and test surface.
- Follow-up implication:
  - bespoke ACP code must not be removed until both adapters have direct runtime evidence on the
    SDK-backed path and mixed-mode operation is verified.
  - direct `claude_code` removal is a separate follow-up decision; see ADR 0049.
