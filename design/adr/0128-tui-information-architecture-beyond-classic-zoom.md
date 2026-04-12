# ADR 0128: TUI information architecture beyond classic zoom

- Date: 2026-04-10

## Decision Status

Accepted

## Implementation Status

Implemented

Skim-safe current truth on 2026-04-12:

- `implemented`: primary navigation remains zoom-based: fleet → operation → session → forensic;
  each level entered via `enter`/`r`, exited via `esc`/`q`
- `implemented`: cross-cutting briefing elements (header summary band, Now/Wait/Attention cues,
  selected-operation brief in fleet) are supportive and do not replace zoom
- `implemented`: higher-level panes summarize deeper levels without absorbing them — fleet shows
  compact operation brief, not full task board or session detail
- `implemented`: layout documented per-level in `docs/tui-workbench.md` (Navigation Model section)
- `verified`: `test_enter_opens_operation_view_and_escape_returns_to_fleet`,
  `test_operation_view_enter_opens_session_view_and_escape_returns`,
  `test_session_timeline_enter_opens_forensic_view_and_escape_returns` in `tests/test_tui.py`
  confirm zoom is the sole primary navigation path

## Context

The current TUI already has a stable supervisory backbone:

- `fleet`
- `operation`
- `session`
- `forensic`

That zoom model remains correct and should not be reopened casually.

At the same time, recent product work and review exposed a next-wave tension:

- strict zoom-only navigation is coherent
- but a richer supervisory cockpit wants compact cross-cutting information such as
  "what matters now", running summaries, recent intervention cues, and active waiting state

If these cross-cutting elements are added without an ADR, the TUI can quietly mutate into an
unclear hybrid:

- partly zoom navigator
- partly operator dashboard
- without explicit authority for what is primary and what is merely supportive

## Decision

The TUI should remain fundamentally zoom-structured, but it may add operator-centric,
cross-cutting briefing surfaces that support rather than replace the zoom model.

That means:

- `fleet -> operation -> session -> forensic` remains the primary navigation grammar
- compact cross-level briefing elements are allowed
- those briefing elements must not become a second undocumented navigation system

## Architecture Rule

The TUI has one primary information architecture:

- zoom is primary
- cross-cutting summaries are secondary

Allowed supporting structures include:

- persistent or repeated summary bands
- "what matters now" cues
- compact running/waiting/operator summaries
- local explanatory briefs in side panes

Disallowed direction:

- replacing zoom with an unbounded dashboard model
- creating hidden alternate navigation anchors with different truth semantics
- duplicating a deeper view in a higher-level pane until the higher level effectively becomes the
  deeper level

## Non-Duplication Rule

Higher-level views may summarize deeper levels, but they may not absorb them wholesale.

Examples:

- `fleet` may show a compact "Now" summary for a selected operation
- `fleet` may not become a full operation board
- `operation` may summarize one active session
- `operation` may not become a transcript-heavy forensic surface

If a higher-level pane starts reading like the next zoom level, the design has crossed the
boundary.

## Cross-Cutting Surface Rule

Cross-cutting elements must answer one of these questions:

- what is happening now
- what is waiting
- what needs intervention
- what changed recently

They should not become a dumping ground for:

- task-board detail
- transcript body
- large memory views
- raw forensic/debug payloads

## Consequences

Positive:

- the product can become more operator-centric without losing its clean zoom mental model
- future pane design work has a clear authority boundary
- review can distinguish healthy summaries from accidental duplication

Tradeoffs:

- some attractive dashboard ideas are intentionally ruled out
- implementation must keep summary surfaces compact and subordinate
- design reviews must police duplication more actively

## Verification

When implemented, the repository should preserve these conditions:

- the primary navigation model remains zoom-based
- cross-cutting surfaces stay supportive rather than replacing zoom
- higher-level panes do not silently become deeper-level views
- docs and tests describe the distinction explicitly

## Related

- [ADR 0109](./0109-cli-authority-and-tui-workbench-v2.md)
- [ADR 0110](./0110-tui-view-hierarchy-and-zoom-contract.md)
- [ADR 0115](./0115-fleet-workbench-projection-and-cli-tui-parity.md)
- [ADR 0126](./0126-supervisory-activity-summary-contract.md)
