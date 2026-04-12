# ADR 0127: Cross-level filtering, search, and focus persistence

- Date: 2026-04-10

## Status

Accepted

## Implementation Status

Implemented

Skim-safe current truth on 2026-04-12:

- `implemented`: each supervisory level owns its own filter slot — `filter_query` (fleet),
  `task_filter_query` (operation), `session_filter_query` (session), `forensic_filter_query`
  (forensic); filters are reset when zooming between levels (`_clear_task_filter`,
  `_clear_session_filter`, `_clear_forensic_filter`)
- `implemented`: escape cancels a pending filter edit and restores the previous query without
  erasing user intent
- `implemented`: background refresh updates data but does not reset active filters or current
  selection
- `implemented`: focus restoration falls to nearest stable neighbour when filtered rows change
- `verified`: `test_fleet_filter_escape_restores_previous_query`,
  `test_operation_filter_escape_restores_previous_query`,
  `test_session_filter_escape_restores_previous_query`,
  `test_forensic_filter_escape_restores_previous_query` in `tests/test_tui.py`
- `verified`: `test_fleet_filter_does_not_carry_into_operation_level_on_zoom` explicitly asserts
  level-local filter locality — fleet filter not carried into operation task_filter_query

## Context

Filtering has already appeared as a real TUI feature wave:

- session filtering
- forensic filtering
- navigation behavior tied to selection changes

At the same time, the product now spans multiple linked supervision levels:

- `fleet`
- `operation`
- `session`
- `forensic`

Without an explicit ADR, filter and focus behavior can drift into inconsistent local rules:

- one level may persist filters across zoom while another resets them
- selection restoration may feel arbitrary after a filter change
- search and filter may blur together without a stable semantic difference

This would make the TUI feel locally polished but globally ad hoc.

## Decision

The repository should define one cross-level contract for:

- filtering
- search
- focus/selection persistence
- restoration after zoom or refresh changes

The contract should be shared across supervisory levels rather than implemented as unrelated
per-view behavior.

## Core Rules

### 1. Locality by default

Filters are level-local by default.

That means:

- a `fleet` filter does not automatically become a session filter
- a forensic search does not implicitly rewrite the parent operation view

Cross-level persistence must be explicit rather than accidental.

### 2. Explicit inherited context only

Some context may be carried across zoom as an explicit narrowing anchor, for example:

- selected operation when entering operation view
- selected session when entering session view

But inherited selection is not the same thing as inherited filter state.

### 3. Search and filter are not identical

The product should distinguish:

- filter: persistent narrowing of the currently visible set
- search: directed find behavior within the current level or current data slice

If the implementation temporarily shares UI affordances, the semantic distinction should still
remain explicit in the design contract.

### 4. Focus restoration must be deterministic

When filters or refreshes change visible rows:

- preserve the current selection if still visible
- otherwise restore to the nearest stable neighbor or a documented default target
- never leave focus restoration to incidental list ordering side effects

### 5. Refresh must not silently reset user intent

Background refresh may update data, but it should not casually erase:

- an active filter
- the user's current selection
- the user's current search context

unless the current target truly disappears from the visible data.

## Persistence Rule

Allowed persistent state:

- per-level active filter text or filter predicate
- current selection target
- current zoom anchor

Disallowed implicit persistence:

- carrying forensic search terms upward into fleet or operation
- carrying a fleet triage filter into all deeper levels as hidden state

If future product work wants deliberate cross-level search propagation, that should be explicit and
documented rather than emergent.

## Consequences

Positive:

- navigation becomes more predictable across the supervision stack
- future filtering features can compose without inventing new focus rules every time
- testing can assert deterministic restoration behavior

Tradeoffs:

- some ad hoc convenience behaviors become disallowed
- implementation needs explicit state ownership for filters and focus
- documentation must explain locality vs persistence clearly

## Verification

When implemented, the repository should preserve these conditions:

- filter behavior is deterministic and level-aware
- selection restoration after filter/refresh changes follows documented rules
- refresh does not reset user intent without cause
- tests cover focus preservation and fallback selection behavior

## Related

- [ADR 0110](./0110-tui-view-hierarchy-and-zoom-contract.md)
- [ADR 0113](./0113-tui-data-substrate-and-refresh-model.md)
- [ADR 0118](./0118-supervisory-surface-implementation-tranche.md)
- [ADR 0126](./0126-supervisory-activity-summary-contract.md)
