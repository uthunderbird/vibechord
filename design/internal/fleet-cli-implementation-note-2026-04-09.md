# Fleet CLI Implementation Note

## Status

Internal implementation note.

This note translates:

- [0115-fleet-workbench-projection-and-cli-tui-parity.md](/Users/thunderbird/Projects/operator/design/adr/0115-fleet-workbench-projection-and-cli-tui-parity.md)
- [fleet-ui-contract-2026-04-09.md](/Users/thunderbird/Projects/operator/design/internal/fleet-ui-contract-2026-04-09.md)

into a narrower implementation-oriented sketch for the `Fleet` parity tranche.

## Goal

Replace the old agenda/dashboard-oriented fleet payload with a normalized fleet workbench projection
that can feed both:

- the TUI `Fleet` workbench
- textual CLI fleet snapshots

without creating a TUI-local truth model.

## Current substrate

The existing fleet path still relies on runtime-oriented agenda data:

- `objective_brief`
- `focus_brief`
- `latest_outcome_brief`
- `blocker_brief`
- `runtime_alert`
- `runnable_task_count`
- `reusable_session_count`

This is useful raw material, but it is not yet the same thing as the display contract required by
the current `Fleet` UI.

## Proposed fleet workbench payload

Recommended top-level shape:

```json
{
  "project": "operator",
  "header": {
    "active_count": 7,
    "needs_human_count": 2,
    "running_count": 4,
    "paused_count": 1,
    "operator_load": null
  },
  "rows": [
    {
      "operation_id": "op-...",
      "display_name": "checkout-redesign",
      "attention_badge": "[!!2]",
      "state_label": "RUNNING",
      "agent_cue": "codex_acp",
      "recency_brief": "8s",
      "row_hint": "now: session drill-down",
      "sort_bucket": "needs_attention"
    }
  ],
  "selected_brief": {
    "goal": "Finish TUI UX, then docs",
    "now": "Implementing session drill-down",
    "wait": "Agent turn running",
    "progress": {
      "done": "fleet, operation",
      "doing": "session",
      "next": "forensic, docs"
    },
    "attention": "2 blocking",
    "recent": [
      "previous slice landed",
      "session resumed",
      "next turn started"
    ]
  },
  "actions": [ ... ]
}
```

## Header summary sketch

The `header` block should stay compact and human-facing.

Required fields:

- `active_count`
- `needs_human_count`
- `running_count`
- `paused_count`

Optional field:

- `operator_load`

`operator_load` should remain `null` or absent until the model is strongly grounded. It must not be
fabricated from weak heuristics just to make the header look richer.

## Fleet row sketch

Each row should be display-oriented rather than runtime-oriented.

Required fields:

- `operation_id`
- `display_name`
- `attention_badge`
- `state_label`
- `agent_cue`
- `recency_brief`
- `row_hint`
- `sort_bucket`

### `display_name`

Human-facing short operation label. Prefer a stable user-friendly identifier over a raw UUID.

### `attention_badge`

Compact badge string such as:

- `[ ]`
- `[!1]`
- `[!!2]`

### `state_label`

Human-facing operation state suitable for the second row line.

### `agent_cue`

Compact agent or adapter cue.

The first tranche does not need full multi-agent grammar. One short cue is sufficient.

### `recency_brief`

Compact relative time or activity recency, suitable for the second row line.

### `row_hint`

Normalized third-line hint.

Preferred priority:

1. `waiting: ...`
2. `now: ...`
3. `paused: ...`
4. `failed: ...`
5. fallback from focus/outcome summary

### `sort_bucket`

Normalized bucket for display ordering:

- `needs_attention`
- `active`
- `recent`

## Selected brief sketch

This block powers the right pane in `Fleet` and any textual fleet snapshot equivalent.

Required fields:

- `goal`
- `now`
- `wait`
- `progress.done`
- `progress.doing`
- `progress.next`
- `attention`
- `recent`

This block is intentionally narrower than a full operation dashboard payload.

It should not absorb:

- full task board
- full event timeline
- transcript excerpts
- forensic payloads

## Renderer expectations

### TUI `Fleet`

Use the normalized row and selected-brief blocks directly.

Do not keep reconstructing the screen from:

- `needs_attention`
- `active`
- `recent`
- and ad hoc dashboard detail reads

inside the TUI layer.

### CLI fleet snapshot

The CLI snapshot should render the same semantics in textual form:

- compact header counts
- selected operation list
- concise selected-operation brief

The CLI does not need to mimic the TUI layout exactly, but it should tell the same story.

### `--json`

`--json` should emit the normalized fleet workbench payload directly.

## Reuse guidance

Use the existing agenda/runtime data as input, but not as the final display contract.

Likely reuse sources:

- [agenda.py](/Users/thunderbird/Projects/operator/src/agent_operator/runtime/agenda.py)
- [operation_projections.py](/Users/thunderbird/Projects/operator/src/agent_operator/application/operation_projections.py)
- current one-operation payload for selected-brief enrichment where needed

Do not:

- make fleet semantics TUI-local
- keep the old bucket payload as the primary public fleet contract

## Suggested first file touch set

- [agenda.py](/Users/thunderbird/Projects/operator/src/agent_operator/runtime/agenda.py)
- [operation_projections.py](/Users/thunderbird/Projects/operator/src/agent_operator/application/operation_projections.py)
- new or adjacent fleet query module near [operation_dashboard_queries.py](/Users/thunderbird/Projects/operator/src/agent_operator/application/operation_dashboard_queries.py)
- [main.py](/Users/thunderbird/Projects/operator/src/agent_operator/cli/main.py)
- [tui.py](/Users/thunderbird/Projects/operator/src/agent_operator/cli/tui.py)
- [test_operation_projections.py](/Users/thunderbird/Projects/operator/tests/test_operation_projections.py)
- [test_cli.py](/Users/thunderbird/Projects/operator/tests/test_cli.py)
- [test_tui.py](/Users/thunderbird/Projects/operator/tests/test_tui.py)

## Test targets

Minimum test targets for the first tranche:

1. emits normalized fleet rows
2. emits normalized selected brief
3. preserves intended row ordering by bucket and urgency
4. renders 3-line row semantics in TUI
5. renders the same core meaning in CLI snapshot mode
6. emits machine-readable normalized payload in `fleet --json`

## Deliberate deferrals

The first tranche can defer:

- strong operator-load modeling
- full multi-agent grammar
- alternate fleet modes such as `dense` or `attention`
- richer project/fleet drill-in semantics beyond the selected brief
