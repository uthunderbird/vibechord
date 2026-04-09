# ADR 0110: TUI View Hierarchy and Zoom Contract

## Status

Implemented

## Context

TUI design defines a multi-level supervisory structure:

- Fleet level overview.
- One-operation detail and task drill-down.
- Session-level event lineage.
- Raw transcript mode for forensic inspection.

Current implementation risk is not feature completeness; it is semantic drift:

- missing left-pane continuity during navigation,
- different mental models for selection and zoom state,
- ambiguity in empty/no-data behavior,
- inconsistent return paths between levels.

`TUI-UX-VISION.md` already defines explicit level names and layouts, but these are currently
functional-level specifications. We need a binding contract.

## Decision

The TUI must use a fixed zoom contract with an anchored navigation model:

1. **Level 0: Fleet View** — operation-level list with right-side operation brief.
2. **Level 1: Operation View** — task board and operation/task-specific details.
3. **Level 2: Session View** — timeline of recent session events.
4. **Level 3: Raw Transcript** — full-screen transcript for one session.

At any non-root level:
- `Esc` returns to immediate parent level.
- Breadcrumb always includes the full path from root.
- Left pane remains visible at all zoom levels.

## Navigation and State Invariants

1. The selected item is always visible in the left pane.
2. Selection and scroll context are local to level and may reset predictably when returning to a parent.
3. `Enter` performs one-level zoom only; there is no multi-level teleport jump.
4. `Esc` is disabled at root except for explicit exit (`q`).
5. When no operation is renderable at the current depth, the app shows an explicit empty state instead of a crash.

## Empty and Degenerate States

- **Empty fleet:** Fleet View shows a minimal guidance card in the left pane:
  `No active operations. Run 'operator run [goal]' to start.`
- **No events in selected session:** session timeline shows "No session timeline events."
- **Raw transcript unavailable:** entering Level 3 shows a terminal message in place and returns
  to Level 2 with an inline hint.

## Keyboard Contract Alignment

- `Enter` is always zoom-in.
- `Esc` is always zoom-out by one level (except Level 0).
- Arrow keys (`↑`/`↓`) always move selection within left pane context of the current level.
- `q` remains global quit and must terminate the interface regardless of level.

## Depth and future nesting

Any nested sub-operator structure (including `operator_acp`) is represented in the same zoom chain.
At nesting depth >3, the left pane shows only immediate children of the current zoom level, while the
breadcrumb remains full-depth.

## Alternatives Considered

### Option A: Freeform full-screen panes per view with ephemeral selection

Rejected.

This model increases cognitive churn, breaks fast return behavior, and violates the core principle that
navigation remains continuous.

### Option B: Separate task/session/operation shells without shared zoom model

Rejected.

It would force duplicated navigation semantics and create inconsistent escape behavior between
surfaces.

### Option C: Fixed level contract with persistent left pane and one-step zoom

Accepted.

This model gives predictable supervision, minimal action cost for attention-heavy workflows, and stable
mental state.

## Consequences

- New UI implementations for TUI must expose a consistent hierarchical zoom path.
- The interface cannot use a hidden modal stack that removes the left navigation surface.
- Empty-state behavior is now specified and testable.
- `operator_acp` nesting can be integrated without inventing a separate navigation paradigm.

## Verification

- For each level, there is exactly one zoom-in and one zoom-out path.
- Any session with no events does not crash and displays explicit state.
- Root quit exits deterministically in all modes and contexts.

## Implementation

- Implemented via:
  - `src/agent_operator/cli/tui_controller.py` (session-level `Enter` guards against absent raw transcript and stays on timeline).
  - `src/agent_operator/cli/tui_rendering.py` (empty-fleet guidance row in operation list).
- Verified by `tests/test_tui.py`:
  - `test_session_enter_stays_in_session_if_transcript_is_unavailable`
  - `test_empty_fleet_shows_guidance_message`
