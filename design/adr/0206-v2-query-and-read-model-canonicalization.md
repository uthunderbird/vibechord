# ADR 0206: v2 Query and Read-Model Canonicalization

- Date: 2026-04-23

## Decision Status

Proposed

## Implementation Status

Planned

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
