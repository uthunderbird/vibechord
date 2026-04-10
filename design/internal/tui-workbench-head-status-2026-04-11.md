# TUI Workbench HEAD Status 2026-04-11

## Purpose

This note records the current-HEAD status of the interactive TUI workbench against the current
design corpus. It is evidence-based and limited to what is visible in current source, tests, and
user-facing docs on `HEAD`.

## Scope

Compared sources:

- `README.md`
- `docs/tui-workbench.md`
- `design/ARCHITECTURE.md`
- `design/VISION.md`
- `design/adr/0109-cli-authority-and-tui-workbench-v2.md`
- `design/adr/0110-tui-view-hierarchy-and-zoom-contract.md`
- `design/adr/0115-fleet-workbench-projection-and-cli-tui-parity.md`
- `design/adr/0126-supervisory-activity-summary-contract.md`

Implementation and verification evidence was taken from:

- `src/agent_operator/cli/tui/rendering.py`
- `tests/test_tui.py`
- `tests/test_tui_session_view.py`
- `tests/test_tui_session_summary_jump_to.py`

## Current HEAD Summary

The current TUI workbench is materially aligned with the active delivery-surface ADR chain.

Implemented and evidenced on `HEAD`:

- fixed four-level navigation: `fleet -> operation -> session -> forensic`
- breadcrumbed header summaries for fleet, operation, session, and forensic scopes
- compact human-first footers with level-specific actions and visible `Help ?` affordance
- fleet left-pane normalized multi-line rows
- operation task board with grouped status lanes, dependency continuation lines, and linked-session
  continuation lines
- session brief panel with `Now`, `Wait`, `Attention`, `Latest output`, timeline summary, and
  a direct forensic next-step cue
- forensic drill-down that still opens when no raw transcript payload exists, with explicit empty
  messaging
- focused TUI coverage for the session summary slice, fleet row rendering, empty states, headers,
  footers, and current forensic/session transitions

## ADR Comparison

### ADR 0109: CLI authority, TUI as supervisory workbench

Current HEAD matches the core contract:

- TUI is used as the interactive supervision surface, not as an authority that invents separate
  control semantics.
- Rendered controls remain mapped to existing control verbs such as pause, resume, interrupt,
  cancel, and answer.
- Read-only navigation remains workbench-local.

Evidence:

- `src/agent_operator/cli/tui/rendering.py` renders only mapped action strips for fleet,
  operation, session, and forensic footers.
- `tests/test_tui.py` covers the compact footer language and action-oriented controller behavior.

### ADR 0110: fixed zoom hierarchy and explicit empty states

Current HEAD matches the implemented hierarchy:

- fleet, operation, session, and forensic levels are all present
- breadcrumb text is rendered in headers
- empty fleet, empty session timeline, and no-raw-transcript cases all render explicit messages

Current HEAD exceeds the older transcript-empty behavior described in this ADR by opening forensic
with an explicit empty-state panel rather than refusing the drill-down.

This is not treated as a mismatch because repository truth now documents the newer behavior in
`README.md` and `docs/tui-workbench.md`, and tests cover it directly.

### ADR 0115: shared fleet workbench projection and normalized fleet rows

Current HEAD matches the visible fleet-shape requirements:

- fleet header shows `Operations / Running / Needs human / Paused`
- fleet rows render as normalized compact multi-line summaries
- fleet selection shows a separate right-pane detail brief

The implementation evidence available in this audit is primarily delivery-side rendering and TUI
tests. This note does not re-verify the full application/query-layer projection path beyond the
existing repository tests already cited by ADR 0126.

### ADR 0126: shared supervisory activity summary contract

Current HEAD appears aligned with the currently documented partial implementation status:

- fleet, operation, and session surfaces all render normalized summary fields such as `now`,
  `wait`, `attention`, and recent/live cues
- session surfaces now include the `Latest output` cue in both the session brief and session header
- the presentation remains compact and human-readable instead of inventing new delivery-local
  semantics

The remaining unclosed area stays the one already admitted by ADR 0126:

- broader parity verification for every future CLI/TUI supervisory surface is still not fully closed

## User-Facing Doc Alignment

Current user-facing docs appear aligned with the implementation slice on `HEAD`:

- `README.md` describes the implemented navigation path, session `Latest output` cue, help overlay,
  multi-line fleet rows, grouped operation task board, and forensic empty-state behavior
- `docs/tui-workbench.md` describes the same header/footer language, fleet row shape, session brief
  rows, and forensic behavior reflected in rendering code and focused tests

No immediate doc contradiction was found in the audited TUI sections.

## Verified Boundaries

Verified during this audit from current source and tests:

- visible TUI header text exists and includes summary bands
- footer/help text exists and keeps `Help ?` visible in human-first action strips
- session summary area exists in both header and right-pane brief
- fleet row summary rendering exists in compact multi-line form
- focused tests exist for fleet header/footer, fleet row rendering, session summary/detail, and
  session header latest-output wording
- TUI user-facing docs and README TUI manual text describe the current implemented slices rather
  than an older aspirational design

## Partial / Open

Still partial by current design corpus, not newly discovered in this audit:

- ADR 0126 explicitly keeps broader future CLI/TUI parity verification partial
- stronger plurality cues and richer operator-state signals remain conditional on stronger runtime
  evidence rather than guaranteed product truth

No additional bounded TUI UX slice was selected from this audit because the current HEAD already
shows the recently documented header, footer/help, session summary, fleet-row, and forensic-empty
state slices as implemented with focused coverage.
