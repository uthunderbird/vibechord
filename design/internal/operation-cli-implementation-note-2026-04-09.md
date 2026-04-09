# Operation CLI Implementation Note

## Status

Internal implementation note.

This note translates:

- [0115-fleet-workbench-projection-and-cli-tui-parity.md](/Users/thunderbird/Projects/operator/design/adr/0115-fleet-workbench-projection-and-cli-tui-parity.md)
- [0116-cli-parity-gaps-for-fleet-operation-and-session-surfaces.md](/Users/thunderbird/Projects/operator/design/adr/0116-cli-parity-gaps-for-fleet-operation-and-session-surfaces.md)
- [operation-view-ui-contract-2026-04-09.md](/Users/thunderbird/Projects/operator/design/internal/operation-view-ui-contract-2026-04-09.md)

into a narrower implementation-oriented sketch for the `Operation View` parity tranche.

## Goal

Make the shared one-operation payload carry a normalized `operation_brief` contract so that:

- TUI `Operation View`
- richer CLI operation surfaces

can render the same operation-scoped meaning without each assembling it ad hoc.

This note does **not** require inventing a brand-new public command in the first tranche. It is
about strengthening the shared operation display contract.

## Current substrate

The existing one-operation payload already exposes most deeper truth:

- tasks
- attention
- decision memos
- memory entries
- sessions
- recent events
- timeline events

The main gap is not missing raw data. The main gap is missing normalized operation-scoped summary
semantics.

## Proposed `operation_brief` block

Recommended display-facing shape:

```json
{
  "operation_brief": {
    "now": "implementing session drill-down",
    "wait": "current agent turn running",
    "progress": {
      "done": "fleet, operation",
      "doing": "session",
      "next": "forensic, docs"
    },
    "attention": "2 blocking",
    "recent": [
      "slice landed",
      "resumed session",
      "next turn started"
    ]
  }
}
```

This block should be distinct from:

- raw `summary`
- final report prose
- task board rows
- full event history

## Field semantics

### `now`

Short normalized statement of the operation's current work.

Preferred sources:

- latest turn work summary
- active task focus
- active session summary

### `wait`

Short normalized statement of the main blocking or waiting condition.

Preferred sources:

- active session waiting reason
- operation pause/drain state
- blocking attention

### `progress.done`

Short summary of completed major slices or completed task grouping.

### `progress.doing`

Short summary of the slice or task cluster currently in flight.

### `progress.next`

Short summary of the next visible work front.

### `attention`

Compact operation-scoped attention summary.

This is not a full attention list. It should stay brief enough for:

- right-pane operation brief
- CLI rich snapshot

### `recent`

Short list of recent operator-meaningful changes.

This should stay bounded and should not become a raw timeline dump.

## Relationship to existing payload blocks

The normalized `operation_brief` should sit alongside existing deeper data, not replace it.

Likely shape:

```json
{
  "operation_id": "op-...",
  "status": "running",
  "operation_brief": { ... },
  "tasks": [ ... ],
  "attention": [ ... ],
  "decision_memos": [ ... ],
  "memory_entries": [ ... ],
  "sessions": [ ... ],
  "recent_events": [ ... ],
  "timeline_events": [ ... ]
}
```

The operation brief is the compact interpretation layer.

The other blocks remain the deeper structured evidence.

## Renderer expectations

### TUI `Operation View`

Use `operation_brief` for the compact top-right section:

- `Now`
- `Wait`
- `Progress`
- `Attention`
- `Recent`

Do not reconstruct this block from a loose mix of:

- `brief_summary`
- `active_session`
- `attention`
- `recent_events`

inside the TUI renderer.

### CLI richer operation surface

Whether the richer surface remains `dashboard` or later gains a more refined public shape, the
renderer should use the same `operation_brief` block.

This preserves parity even if the exact public command lineup evolves later.

## Reuse guidance

Prefer reuse from the current one-operation query path:

- [operation_dashboard_queries.py](/Users/thunderbird/Projects/operator/src/agent_operator/application/operation_dashboard_queries.py)
- [operation_projections.py](/Users/thunderbird/Projects/operator/src/agent_operator/application/operation_projections.py)

Do not:

- create a second operation truth in the CLI layer
- encode operation-brief meaning only in TUI-local render helpers

## Suggested first file touch set

- [operation_projections.py](/Users/thunderbird/Projects/operator/src/agent_operator/application/operation_projections.py)
- [operation_dashboard_queries.py](/Users/thunderbird/Projects/operator/src/agent_operator/application/operation_dashboard_queries.py)
- [tui.py](/Users/thunderbird/Projects/operator/src/agent_operator/cli/tui.py)
- [test_operation_projections.py](/Users/thunderbird/Projects/operator/tests/test_operation_projections.py)
- [test_tui.py](/Users/thunderbird/Projects/operator/tests/test_tui.py)

## Test targets

Minimum test targets for the first tranche:

1. emits normalized `operation_brief`
2. preserves deeper blocks (`tasks`, `attention`, `sessions`, `recent_events`)
3. renders compact operation brief in TUI right pane
4. keeps selected-task detail separate from the operation brief
5. does not regress task board ordering or task selection behavior

## Deliberate deferrals

The first tranche can defer:

- a brand-new public operation command
- alternate operation modes
- more sophisticated progress grammar
- extraction of a separate operation query service if the shared dashboard path remains clean
