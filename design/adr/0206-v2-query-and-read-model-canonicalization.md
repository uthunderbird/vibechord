# ADR 0206: v2 Query and Read-Model Canonicalization

- Date: 2026-04-23

## Decision Status

Accepted

## Implementation Status

Verified

Phase 2 implementation on 2026-04-25:

- `implemented`: status-like surfaces now use an explicit typed `OperationReadPayload` with a
  runtime overlay that names wakeup, background, and trace authorities and staleness bounds.
  Evidence: `src/agent_operator/application/queries/operation_status_queries.py:31`,
  `src/agent_operator/application/queries/operation_status_queries.py:61`,
  `src/agent_operator/application/queries/operation_status_queries.py:154`.
- `implemented`: status JSON/text rendering, dashboard payloads, and MCP status consume the shared
  read payload instead of independently assembling state from `OperationState` and side inputs.
  Evidence: `src/agent_operator/application/queries/operation_status_queries.py:255`,
  `src/agent_operator/application/queries/operation_dashboard_queries.py:32`,
  `src/agent_operator/mcp/service.py:202`.
- `implemented`: agenda/fleet-style enumeration can use canonical operation-state listing and the
  CLI service builder wires that boundary through `OperationResolutionService`.
  Evidence: `src/agent_operator/application/queries/operation_agenda_queries.py:17`,
  `src/agent_operator/application/queries/operation_agenda_queries.py:55`,
  `src/agent_operator/cli/helpers/services.py:96`.
- `implemented`: replay projection and the trace read-model projector accept canonical
  `operation.created` event shapes without feeding event-level metadata into `ObjectiveState`.
  Evidence: `src/agent_operator/projectors/operation.py:117`,
  `src/agent_operator/projectors/operation.py:484`,
  `src/agent_operator/application/queries/operation_read_model_projector.py:40`.
- `verified`: regression coverage now catches whole-event objective validation, status JSON
  recomputation drift, canonical agenda enumeration regressions, and MCP status payload contract
  drift. Evidence: `tests/test_event_sourced_replay.py:120`,
  `tests/test_operation_status_queries.py:264`,
  `tests/test_operation_agenda_queries.py:138`,
  `tests/test_mcp_server.py:309`.
- `verified`: local verification completed with targeted read-surface suites and the full suite:
  `UV_CACHE_DIR=/tmp/uv-cache uv run pytest ...` targeted ADR 0206 modules: 38 passed;
  `UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/test_cli.py -k "status or inspect or dashboard or report or fleet or project"`:
  57 passed, 148 deselected; `UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/test_tui.py`:
  77 passed; `UV_CACHE_DIR=/tmp/uv-cache uv run pytest`: 972 passed, 11 skipped.

Phase 1 grounding on 2026-04-25:

- `implemented`: status queries already prefer event-sourced replay over legacy snapshots when a
  replay service is available.
- `implemented`: dashboard queries already route through the status query service before adding
  dashboard-specific trace, command, event, and transcript overlays.
- `implemented`: MCP operation listing already uses canonical operation-state enumeration through
  the shared resolution service.
- `partial`: status JSON/text, MCP status, dashboard, and TUI-facing payloads still assemble
  surface-specific dictionaries from `OperationState` and side inputs rather than consuming one
  explicit typed read payload.
- `partial`: agenda/fleet-style enumeration still starts from legacy store summaries and can miss
  event-sourced-only operations unless those operations are also represented through the legacy
  listing path.
- `planned`: projector and read-model projector handling for `operation.created` needs explicit
  regression coverage against the canonical event shape written by v2 birth, including event-level
  metadata that is not part of `ObjectiveState`.
- `planned`: the next implementation wave should introduce a typed read payload, route covered
  read surfaces through it, and label runtime/trace/background data as overlays with explicit
  authority and staleness.

The Phase 1 grounded design artifact is
[`../internal/adr-0206-phase-1-grounded-design.md`](../internal/adr-0206-phase-1-grounded-design.md).

## Context

v2 writes canonical domain events, but public read surfaces still mix replay, checkpoint views,
legacy snapshots, trace stores, event files, and background inspection stores. Some of those are
valid derived inputs; others are obsolete authority leaks.

Recent repository failures also showed a stricter requirement: canonical replay must be
schema-stable across the event stream actually written by v2. A read surface is not canonical if it
can crash on valid persisted events because projector or payload validation expects an older shape.

The observed failure mode is severe:

- `status`, `answer`, and operation resolution can fail before doing useful work
- replay can raise `ValidationError` while materializing `operation.created`
- a v2 operation can be valid in the event stream but unreadable through public surfaces

That is a read-model failure, not only an entrypoint failure. Public v2 read surfaces cannot depend
on "happy-path" payload shapes that differ from the canonical stream already persisted by the
repository.

Phase 1 grounding found that the current repository already has pieces of the target shape, but not
the full ADR 0206 contract. `OperationStatusQueryService` is the current practical read gateway for
status-like surfaces, and it prefers replay before legacy snapshots. `OperationDashboardQueryService`
builds on that gateway, and MCP listing uses canonical resolution. However, several consumers still
assemble their own surface payloads, agenda/fleet enumeration still begins from legacy store
summaries, and canonical event-shape handling needs direct tests at the replay projector and
read-model projector boundaries.

## Decision

All v2 read surfaces consume explicit read models derived from canonical replay plus documented
non-canonical overlays for runtime facts.

Covered surfaces:

- status
- inspect
- dashboard
- fleet
- project dashboard
- session
- report
- attention
- tasks
- memory
- artifacts
- history where operation state is included

## Required Properties

- Canonical operation state comes from event replay/checkpoint.
- Replay and projector payload validation accept the canonical event shapes written by the current
  v2 write paths.
- Schema drift between stored domain events and projector expectations is treated as a canonical
  read-model bug, not as an acceptable per-surface edge case.
- Runtime overlays identify their authority and staleness bound.
- JSON output and text output are different renderings of the same read model.
- TUI payloads consume the same query services as CLI/MCP/SDK where practical.
- Missing legacy snapshot is not an error for v2 operations.

## Verification Plan

- v2-only fixtures for every read surface.
- replay/projector regressions cover canonical `operation.created` payload materialization and other
  known shape-sensitive event slices
- text and JSON outputs derive from one read payload.
- checkpoint deletion does not change read model after replay.
- stale runtime overlays produce explicit alerts, not hidden state mutation.
- TUI model tests cover v2 replay-derived permission/session events.

## Related

- ADR 0173
- ADR 0180
- ADR 0193
- ADR 0203
