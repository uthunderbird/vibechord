# ADR 0207: Delivery Surface Parity Contract

- Date: 2026-04-23

## Decision Status

Accepted

## Implementation Status

Partial

Phase 1 grounding on 2026-04-25:

- `implemented`: a shared `OperationResolutionService` exists and resolves exact ids, unique
  prefixes, `last`, and event-sourced operation ids from canonical state/event files. Evidence:
  `src/agent_operator/application/queries/operation_resolution.py:61-103`,
  `src/agent_operator/application/queries/operation_resolution.py:114-151`.
- `implemented`: CLI operation reference resolution delegates to that shared resolver for the main
  operation-scoped commands. Evidence:
  `src/agent_operator/cli/helpers/resolution.py:32-41`,
  `src/agent_operator/cli/commands/operation_control.py:43-90`,
  `src/agent_operator/cli/commands/operation_detail.py:239-340`.
- `implemented`: MCP and the Python SDK already construct and use `OperationResolutionService`.
  Evidence: `src/agent_operator/mcp/service.py:96-114`,
  `src/agent_operator/mcp/service.py:198-287`,
  `src/agent_operator/mcp/service.py:309-321`,
  `src/agent_operator/client.py:108-136`, `src/agent_operator/client.py:155-205`,
  `src/agent_operator/client.py:535-545`.
- `implemented`: status-like read paths already have a typed `OperationReadPayload` with runtime
  overlay metadata, and CLI/MCP status consume it. Evidence:
  `src/agent_operator/application/queries/operation_status_queries.py:61-85`,
  `src/agent_operator/application/queries/operation_status_queries.py:154-230`,
  `src/agent_operator/application/queries/operation_status_queries.py:248-294`,
  `src/agent_operator/mcp/service.py:198-238`.
- `partial`: the delivery command facade exists for CLI/TUI/MCP command paths, but SDK command
  methods still enqueue or invoke service paths directly instead of consuming that facade. Evidence:
  `src/agent_operator/application/commands/operation_delivery_commands.py:61-213`,
  `src/agent_operator/mcp/service.py:240-287`,
  `src/agent_operator/client.py:330-430`.
- `partial`: TUI is wired through injected load/control callbacks and uses shared payloads and
  delivery actions indirectly, but that callback contract is not yet a named cross-surface parity
  contract. Evidence: `src/agent_operator/cli/tui/controller.py:39-62`,
  `src/agent_operator/cli/tui/controller.py:538-617`,
  `src/agent_operator/cli/tui/controller.py:775-821`,
  `src/agent_operator/cli/tui/controller.py:823-843`.
- `planned`: parity needs a small application-facing delivery contract layer that names the covered
  resolver, command, query, and event-stream capabilities, plus tests that assert CLI, TUI, MCP, and
  SDK consume those capabilities instead of parallel authority paths.

The Phase 1 grounded design artifact is
[`../internal/adr-0207-phase-1-grounded-design.md`](../internal/adr-0207-phase-1-grounded-design.md).

Phase 2 implementation on 2026-04-25:

- `implemented`: a named `DeliverySurfaceService` now composes the shared operation resolver,
  status query service, and delivery command facade without taking over their business semantics.
  Evidence: `src/agent_operator/application/delivery_surface.py:16-41`,
  `src/agent_operator/application/delivery_surface.py:57-113`.
- `implemented`: the SDK constructs the delivery surface and routes status, answer, cancel, and
  interrupt through it while preserving SDK return styles. Evidence:
  `src/agent_operator/client.py:145-177`, `src/agent_operator/client.py:317-349`,
  `src/agent_operator/client.py:391-436`,
  `tests/test_client.py:223-270`.
- `implemented`: MCP list, status, answer, cancel, interrupt, and resolver/error mapping paths
  now build or consume the delivery surface instead of independently assembling those authorities.
  Evidence: `src/agent_operator/mcp/service.py:97-109`,
  `src/agent_operator/mcp/service.py:198-235`,
  `src/agent_operator/mcp/service.py:237-277`,
  `src/agent_operator/mcp/service.py:299-342`.
- `implemented`: production TUI control callbacks are backed by the delivery surface while the TUI
  controller keeps callback injection for UI tests. Evidence:
  `src/agent_operator/cli/helpers/services.py:93-103`,
  `src/agent_operator/cli/workflows/views.py:562-584`.
- `implemented`: parity contract tests assert that reads and commands resolve through the shared
  surface before reaching status/query or command authorities. Evidence:
  `tests/test_delivery_surface_parity.py:123-161`.
- `implemented`: public reference documentation lists the covered shared authorities, surface-local
  output shapes, machine-facing error mapping, and intentional gaps. Evidence:
  `docs/reference/delivery-surface-parity.md:7-33`.
- `implemented`: stream/watch parity now uses the shared `LiveFeedEnvelope` contract and shared
  canonical/legacy parser family for CLI `watch`, SDK `stream_live_feed()`, and SDK
  `stream_events()`. These paths prefer canonical
  `.operator/operation_events/<operation_id>.jsonl` and fall back to legacy
  `.operator/events/<operation_id>.jsonl` only when no canonical stream exists. Evidence:
  `src/agent_operator/application/live_feed.py`,
  `src/agent_operator/client.py`,
  `src/agent_operator/cli/workflows/control_runtime.py`,
  `tests/test_delivery_surface_parity.py::test_cli_and_sdk_live_streams_use_shared_live_feed_contract`,
  `tests/test_client.py::test_operator_client_stream_events_prefers_canonical_v2_stream_over_legacy`,
  `tests/test_cli.py::test_watch_prefers_canonical_v2_events_over_legacy_event_file`.
- `partial`: TUI parity for explicit sequence-gap and stale-stream warnings still trails CLI
  `watch` and SDK `stream_live_feed()`. The shared live-feed parsing path exists, but TUI warning
  rendering parity remains incomplete across every supervisory surface.
- `partial`: full typing verification is not complete. `uv run mypy` on the touched delivery
  modules still traverses existing repository-wide typing debt outside this ADR slice; full pytest
  completed with `975 passed, 11 skipped`.

## Context

`operator` exposes overlapping capabilities through CLI, TUI, MCP, and Python SDK. Without a
delivery parity contract, each surface can implement its own resolver, command path, error shape,
and read projection. That creates drift and hides v2 bugs in one surface while another works.

## Decision

CLI, TUI, MCP, and Python SDK are delivery adapters over shared application command/query
contracts.

The parity matrix covers:

- run
- status
- list
- answer
- cancel
- interrupt
- stream/watch
- session/log
- attention/task inspection

## Required Properties

- One operation resolver contract.
- One command application contract.
- One query/read-model contract.
- Surface-specific rendering is allowed; surface-specific authority is not.
- Error codes and JSON schema fields are stable and documented for machine-facing surfaces.

## Verification Plan

- cross-surface contract tests for operation id resolution.
- cross-surface command tests for answer/cancel/interrupt.
- MCP and SDK tests use v2-only operation fixtures.
- CLI/TUI/MCP/SDK status outputs agree on status, attention, session, and permission facts.
- public docs list parity guarantees and intentional gaps.
- import/structure tests fail if public delivery surfaces bypass the shared resolver, command
  facade, or read-model service for covered capabilities.

## Related

- ADR 0145
- ADR 0146
- ADR 0161
- ADR 0204
- ADR 0205
- ADR 0206
