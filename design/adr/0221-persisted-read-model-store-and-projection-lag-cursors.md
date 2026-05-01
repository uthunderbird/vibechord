# ADR 0221: Persisted Read-Model Store And Projection Lag Cursors

- Date: 2026-05-02

## Decision Status

Proposed

## Implementation Status

Planned

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

This ADR is proposed and planned. No standalone persisted read-model store is implemented by this
ADR.
