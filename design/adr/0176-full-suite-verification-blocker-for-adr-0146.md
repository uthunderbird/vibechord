# ADR 0176: Full-suite verification blocker for ADR 0146

- Date: 2026-04-14

## Decision Status

Proposed

## Implementation Status

Planned

## Context

ADR 0146 (`design/adr/0146-mcp-server-surface-and-tool-contract.md`) can only move from
`Implementation Status: Implemented` to `Implementation Status: Verified` when both:

- the ADR-relevant MCP verification slice passes, and
- the full repository verification gate required by policy passes.

The ADR-relevant MCP slice currently passes:

- `uv run pytest tests/test_mcp_server.py`

The full repository gate currently fails on an unrelated regression outside the MCP surface:

- `uv run pytest`
- failing test:
  `tests/test_service.py::test_busy_follow_up_for_claude_in_turn_continuation_keeps_waiting_on_live_turn[asyncio]`

Observed failure during the verification wave for ADR 0146:

- expected: task status remains `running` while the live Claude turn is still in progress
- actual: task status becomes `blocked`

## Decision

Do not promote ADR 0146 to `Verified` until the repository-wide verification gate is green again.

Track the blocker as explicit design debt so ADR closure reporting remains truthful and does not
infer global verification from MCP-slice success alone.

## Consequences

- ADR 0146 remains `Accepted` and `Implemented` until the failing service-path regression is fixed
  and `uv run pytest` passes again.
- MCP-specific evidence remains valid, but it is insufficient for repository-wide verified closure
  under current verification policy.

## Verification

Recorded from local verification on 2026-04-15:

- `uv run pytest tests/test_mcp_server.py` -> passed
- `uv run pytest` -> failed at
  `tests/test_service.py::test_busy_follow_up_for_claude_in_turn_continuation_keeps_waiting_on_live_turn[asyncio]`

## Related

- [ADR 0146](./0146-mcp-server-surface-and-tool-contract.md)
