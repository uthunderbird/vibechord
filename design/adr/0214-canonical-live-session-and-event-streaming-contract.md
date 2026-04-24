# ADR 0214: Canonical Live Session And Event Streaming Contract

- Date: 2026-04-24

## Decision Status

Proposed

## Implementation Status

Planned

## Context

The v2 ADR tranche already defines canonical persistence, query/read-model behavior, cross-surface
parity, runtime facts, and end-to-end verification. In practice, live supervisory behavior still
depends on how session updates, permission events, wakeups, background progress, and streamed
snapshots are emitted and consumed.

Recent repository work exposed that this is not a cosmetic concern:

- session events can be visible in one place and absent or delayed in another
- TUI or watch consumers can lag and drop events
- a run can be canonically unblocked while the live surface still renders stale attention state
- restart/resume behavior depends on whether wakeups and live session facts are surfaced promptly

These are architecture questions, not just renderer questions. Without a canonical streaming
contract, CLI `watch`, TUI workbench, SDK streaming, session/log views, and verification tooling can
all appear to work while disagreeing about the live state of the same operation.

## Decision

The repository adopts one canonical live session and event streaming contract for v2 supervisory
surfaces.

The contract distinguishes four layers:

1. **Canonical operation event authority**
   - operation domain events and accepted control-plane events
   - authoritative for operation truth

2. **Canonical runtime fact overlays**
   - replayable or projector-backed runtime facts that materially affect operator behavior
   - includes session state, permission state, wakeup reconciliation state, and supervisor
     observations when those facts influence behavior

3. **Streaming delivery feed**
   - ordered live payloads emitted to CLI watch, TUI, SDK streaming, and other supervisory
     consumers
   - derived from canonical event authority plus documented runtime overlays

4. **Forensic upstream logs**
   - adapter-native logs such as Codex ACP or Claude session logs
   - valuable evidence, but not themselves the canonical cross-surface supervisory contract

## Required Properties

- Live delivery surfaces identify whether each payload is canonical, overlay-derived, or forensic.
- Event drops, lag, replay catch-up, and stale overlays are surfaced explicitly, not hidden.
- CLI `watch`, TUI, and SDK streaming do not invent distinct control semantics.
- Session state transitions, permission transitions, and wakeup resolution are visible through the
  shared streaming contract quickly enough for supervision and operator follow-up.
- A resolved attention request cannot remain silently open in the live contract without an explicit
  stale-data warning.
- Streaming consumers may render differently, but they must agree on the underlying event/status
  facts for the same operation.

## Covered Surfaces

- CLI `watch`
- CLI `session`
- CLI `log` when used as a supervisory live surface
- TUI workbench and session views
- Python SDK event streaming
- any future MCP or web supervisory stream that claims parity with the main operator surfaces

## Explicit Non-Goals

- guaranteeing lossless transport through every UI rendering layer
- replacing detailed upstream adapter logs
- requiring every live surface to emit byte-identical payloads

The contract is about authority, staleness signaling, and shared semantics, not identical
presentation.

## Verification Plan

- contract tests showing CLI, TUI-facing projection code, and SDK streaming agree on session,
  permission, attention, and terminal facts for v2-only fixtures
- regression tests for answered-attention, resumed-session, and wakeup-reconciled flows
- explicit lag/drop tests showing user-visible stale-data signaling rather than silent divergence
- one live verification run tied to ADR 0211 evidence proving that session and permission events are
  observable in the approved supervisory surfaces

## Related

- ADR 0206
- ADR 0207
- ADR 0208
- ADR 0210
- ADR 0211
