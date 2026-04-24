# ADR 0204: v2 Operation Identity, Resolution, and Lifecycle Entrypoints

- Date: 2026-04-23

## Decision Status

Accepted

## Implementation Status

Partial

Implementation grounding on 2026-04-24:

- `implemented`: a shared `OperationResolutionService` now lives under
  `src/agent_operator/application/queries/operation_resolution.py` and resolves exact ids,
  unique prefixes, `last`, and v2 event-sourced operations without requiring `.operator/runs`
- `implemented`: CLI resolution delegates to that shared service through
  `src/agent_operator/cli/helpers/resolution.py`
- `implemented`: Python SDK and MCP now use the same shared resolver through
  `src/agent_operator/client.py` and `src/agent_operator/mcp/service.py`
- `verified`: cross-surface regression coverage exists in `tests/test_cli.py`,
  `tests/test_client.py`, and `tests/test_mcp_server.py`
- `partial`: lifecycle entrypoint semantics (`run` create-only vs `resume`/`recover`/`tick`
  continue-only across all public surfaces) are not yet unified under one shared application
  contract

## Context

Operation references are accepted by CLI, TUI, MCP, SDK, and internal services. Today those
surfaces do not share one canonical v2 resolver. Some paths know about event-sourced operations,
while others still resolve only legacy summaries. The observed failure mode is severe: passing an
existing operation id to the wrong entrypoint can create a new operation instead of resuming the old
one.

## Decision

Introduce one canonical v2 operation resolver and one lifecycle entrypoint contract.

Resolution supports:

- exact operation id
- unique prefix
- `last`
- future project-scoped filters only when explicitly requested

Lifecycle semantics are:

- `run` creates a new operation only
- `resume`, `recover`, and `tick` continue an existing operation only
- `cancel`, `answer`, `pause`, `unpause`, `interrupt`, and patch/message commands address an
  existing operation only
- no command may silently reinterpret an operation id as an objective

## Required Properties

- CLI, MCP, SDK, and TUI use the same resolver or a shared application resolver contract.
- Ambiguous prefixes fail with the same structured error shape across surfaces.
- `last` is derived from v2 event/checkpoint metadata, not only `.operator/runs` mtimes.
- terminal operation handling is explicit and consistent.

## Verification Plan

- exact/prefix/ambiguous/last resolver tests for CLI, MCP, and SDK.
- regression: `operator run <existing-operation-id>` does not resume or mutate that operation.
- regression: `operator resume <v2-id>` cannot create a new operation.
- v2-only fixture with no `.operator/runs` resolves from all public surfaces.

## Related

- ADR 0203
- ADR 0205
- ADR 0207
