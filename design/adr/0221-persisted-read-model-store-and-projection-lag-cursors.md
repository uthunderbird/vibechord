# ADR 0221: Persisted Read-Model Store And Projection Lag Cursors

- Date: 2026-05-02

## Decision Status

Proposed

## Implementation Status

Partial

Implementation grounding on 2026-05-02:

- `implemented`: foundation record `PersistedReadModelProjection` carries `operation_id`,
  `projection_type`, `source_event_sequence`, opaque projection payload, and projection timestamp.
  Evidence: `src/agent_operator/domain/read_model.py`.
- `implemented`: `FileReadModelProjectionStore` can save/load standalone projection snapshots,
  isolate projection types, expose `source_event_sequence`, and compute projection lag relative to
  canonical event sequence. Evidence: `src/agent_operator/runtime/read_models.py`.
- `implemented`: status sync-health can consume the persisted read-model projection store as a
  separate lag source and exposes `persisted_read_model_projection_*` fields without making that
  projection authoritative over canonical replay. Evidence:
  `src/agent_operator/application/queries/operation_status_queries.py`.
- `implemented`: `OperationReadModelProjectionWriter` rebuilds persisted status projections from
  canonical operation events and is wired into event-sourced birth, command append, and technical
  fact ingestion paths. Evidence:
  `src/agent_operator/application/queries/operation_read_model_projector.py`,
  `src/agent_operator/application/event_sourcing/event_sourced_birth.py`,
  `src/agent_operator/application/event_sourcing/event_sourced_commands.py`, and
  `src/agent_operator/application/event_sourcing/event_sourced_operation_loop.py`.
- `verified`: focused tests cover cursor persistence, per-projection isolation, lag calculation,
  and invalid cursor rejection. Evidence: `tests/test_read_model_projection_store.py`.
- `verified`: status JSON reports stale persisted read-model projection lag even when the replay
  checkpoint is current. Evidence: `tests/test_operation_status_queries.py`.
- `verified`: focused tests cover writer cursor/payload persistence and refreshes from
  event-sourced birth, command append, and technical-fact append paths. Evidence:
  `tests/test_operation_read_model_projector.py`, `tests/test_event_sourced_birth.py`,
  `tests/test_event_sourced_command_application.py`, and
  `tests/test_event_sourced_operation_loop.py`.
- `implemented`: dashboard payloads expose shared `sync_health` in `runtime_overlay`, so stale
  persisted read-model projection labels reach dashboard consumers instead of being hidden by the
  dashboard read shape. Evidence:
  `src/agent_operator/application/queries/operation_dashboard_queries.py`.
- `verified`: dashboard tests assert stale persisted projection lag is surfaced through the
  dashboard payload. Evidence: `tests/test_operation_dashboard_queries.py`.
- `planned`: TUI/MCP/fleet caches still need store-specific freshness policies before they can
  read persisted projections as cached delivery data.

## Context

ADR 0220 establishes synchronizable operation state for the current event-sourced runtime:
canonical events remain business truth, runtime facts are durable inputs, checkpoints are derived
replay acceleration, and `status --json` reports fact, translation, checkpoint, and projection lag.

Today the status/read projections are checkpoint-backed and rebuildable at read time. For those
surfaces, `projection_sequence` intentionally equals the replay checkpoint sequence. That is enough
for the current v2 sync-health contract, but it is not a durable standalone read-model store.

If the operator later introduces persisted read-model stores for dashboards, fleet views, MCP
indexes, TUI caches, or project-level aggregates, those stores need their own projection cursor and
lag semantics. Otherwise a persisted read model can become a new hidden authority and recreate the
same split-brain failure class that ADR 0220 removed for runtime facts.

## Decision

Any future persisted read-model store must expose an explicit projection cursor.

The minimum contract for a persisted read-model store is:

- name the canonical event sequence represented by each stored projection;
- reject or clearly label reads when the projection is stale relative to canonical events;
- be rebuildable from canonical operation events;
- never outrank canonical replay for business truth;
- surface lag through shared sync-health payloads instead of silently serving stale state.

This ADR is intentionally scoped to future standalone persisted read models. It does not require a
new store for current checkpoint-backed status projections.

## Consequences

### Positive

- Future dashboard or fleet caches cannot become implicit business authority.
- Projection freshness can be debugged without comparing files manually.
- ADR 0220 can remain focused on current runtime fact reconciliation rather than carrying future
  read-model-store design work.

### Negative

- Future persisted read models must carry more metadata.
- Cached read surfaces will need freshness handling in tests and payload contracts.

## Implementation Notes

Planned implementation should introduce:

- a persisted projection record shape with `operation_id`, projection type, and
  `source_event_sequence`;
- projection writer semantics for full rebuild and incremental update;
- sync-health fields that distinguish checkpoint lag from standalone projection lag;
- regression tests where canonical events advance while a persisted projection remains stale.

## Current Status

This ADR is proposed and partially implemented. The standalone projection store foundation exists,
status sync-health can report its cursor lag, and event-sourced write paths refresh the persisted
status projection. Dashboard surfaces shared sync-health labels; TUI/MCP/fleet cached read-surface
freshness policies remain planned.
