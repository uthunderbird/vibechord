# ADR 0214: Canonical Live Session And Event Streaming Contract

- Date: 2026-04-24

## Decision Status

Accepted

## Implementation Status

Partial

Implementation grounding on 2026-04-26:

- `implemented`: shared status/read payload authority already exists at
  `src/agent_operator/application/delivery_surface.py` and
  `src/agent_operator/application/queries/operation_status_queries.py`. Delivery surfaces resolve
  one operation id through `DeliverySurfaceService.build_read_payload()`, then consume one
  `OperationReadPayload` carrying canonical operation truth plus explicit runtime-overlay
  authorities and staleness metadata.
- `implemented`: CLI `watch` and Python SDK `OperatorClient.stream_events()` already prefer the
  canonical `.operator/operation_events/<operation_id>.jsonl` event stream and fall back to
  legacy `.operator/events/<operation_id>.jsonl` only when no canonical stream exists. Evidence:
  `src/agent_operator/cli/workflows/control_runtime.py`,
  `src/agent_operator/client.py`,
  `tests/test_cli.py::test_watch_prefers_canonical_v2_events_over_legacy_event_file`,
  `tests/test_client.py::test_operator_client_stream_events_prefers_canonical_v2_stream_over_legacy`.
- `implemented`: canonical event-stream records are normalized into shared `RunEvent` objects for
  live CLI/SDK consumption instead of each surface inventing a separate ad hoc parser. Evidence:
  `src/agent_operator/cli/workflows/control_runtime.py`,
  `src/agent_operator/client.py`,
  `tests/test_cli.py::test_watch_reads_canonical_v2_events_without_legacy_event_file`,
  `tests/test_client.py::test_operator_client_stream_events_reads_canonical_v2_operation_events`.
- `implemented`: CLI `watch` and SDK event-stream parsing now share one typed
  `LiveFeedEnvelope` family under `src/agent_operator/application/live_feed.py`, so canonical live
  events and synthetic warning records use one cross-surface shape instead of each reader
  improvising its own parser state. Evidence:
  `src/agent_operator/application/live_feed.py`,
  `src/agent_operator/cli/workflows/control_runtime.py`,
  `src/agent_operator/client.py`,
  `tests/test_live_feed.py::test_iter_live_feed_emits_sequence_gap_warning_for_canonical_stream`.
- `implemented`: CLI `watch` now surfaces explicit sequence-gap warnings for canonical event
  streams and explicit stale-attention overlay warnings when an answered attention still appears
  open in replay-derived status. Evidence:
  `src/agent_operator/application/live_feed.py`,
  `src/agent_operator/cli/workflows/control_runtime.py`,
  `tests/test_cli.py::test_watch_surfaces_canonical_sequence_gap_warning`,
  `tests/test_live_feed.py::test_build_attention_stale_warning_reports_answered_attention_still_open`.
- `implemented`: Python SDK streaming now exposes warning-capable
  `OperatorClient.stream_live_feed()` envelopes while keeping backward-compatible
  `OperatorClient.stream_events()` event-only semantics by skipping warning records. Evidence:
  `src/agent_operator/client.py`,
  `tests/test_client.py::test_operator_client_stream_live_feed_surfaces_sequence_gap_warning`,
  `tests/test_client.py::test_operator_client_stream_events_skips_live_feed_warnings`.
- `implemented`: TUI session timelines now render shared live-feed warning records with explicit
  human-facing labels for canonical sequence gaps and stale answered-attention overlays instead of
  collapsing them into a generic warning bucket. Evidence:
  `src/agent_operator/cli/tui/model_display.py`,
  `src/agent_operator/cli/tui/model_text.py`.
- `implemented`: JSON status-like surfaces already expose overlay provenance and staleness
  explicitly through `runtime_overlay.authorities` and `runtime_overlay.staleness`. Evidence:
  `src/agent_operator/application/queries/operation_status_queries.py`,
  `src/agent_operator/mcp/service.py`,
  `tests/test_operation_status_queries.py::test_status_json_uses_shared_read_payload_overlay_metadata`.
- `partial`: the new typed live-feed family currently closes CLI `watch` plus shared SDK/CLI
  parsing, but TUI and other future supervisory consumers do not yet consume the same envelope
  contract directly.
- `partial`: explicit gap warnings now exist for CLI `watch`, SDK `stream_live_feed()`, and TUI
  session timelines for the currently covered session-detail path, but broader TUI/live-supervisory
  parity remains open because other supervisory consumers still do not consume the shared envelope
  contract directly.
- `verified`: focused TUI regression coverage now proves shared live-feed warning records survive
  TUI session timeline projection and render with explicit warning labels. Evidence:
  `tests/test_tui.py::test_tui_session_timeline_includes_live_feed_warning_records`,
  `tests/test_tui.py::test_session_timeline_renders_human_warning_labels`.
- `verified`: the live verification prerequisite named by this ADR is now satisfied by the fresh
  end-to-end evidence recorded under ADR 0211. That closes the earlier external-verification block
  for this ADR, but it does not change the overall `Partial` implementation status because broader
  TUI/live-supervisory parity still remains open.

Acceptance grounding on 2026-04-26:

- The repository already depends on this direction in code: canonical event files are preferred for
  live watch/SDK streaming, shared read payloads carry overlay provenance, and status-like delivery
  surfaces consume that shared authority today.
- Acceptance records that architectural direction in git now. It does not claim that all required
  properties below are fully delivered; implementation truth remains `Partial`.

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
