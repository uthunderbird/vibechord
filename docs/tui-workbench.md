# TUI Workbench

The fleet workbench is the interactive terminal UI behind `operator fleet` when you run it in a
real terminal.

It gives you a four-level drill-down over persisted runtime truth:

1. `fleet`
2. `operation`
3. `session`
4. `forensic`

## Launch

Run the fleet dashboard in a terminal with interactive stdin and stdout:

```sh
UV_CACHE_DIR=/tmp/uv-cache uv run operator fleet
```

The interactive workbench is used when `operator fleet` is attached to TTY input and output.
`--once` renders one snapshot and exits. `--json` emits machine-readable output instead of the TUI.

## Navigation Model

The workbench keeps a left pane for selection and a right pane for detail:

- `fleet`: operations list on the left, operation detail on the right
- `operation`: task board on the left, task-scoped detail on the right
- `session`: selected task's session timeline on the left, selected event detail on the right
- `forensic`: selected event context on the left, focused raw transcript/detail on the right

The header shows the current breadcrumb and operation count. The footer shows either the active key
help, the latest action result, or a cancel confirmation prompt.

## Fleet Level

`fleet` is the default entry view. It lists actionable operations across the current project scope.

Available keys:

- `j` / `k` or arrow keys: move the selected operation
- `Enter`: open the selected operation in the Level 1 operation view
- `Tab`: jump to the next operation with an alert or open attention
- `n`: answer the oldest non-blocking attention in the selected operation
- `A`: open the current-scope attention picker for the selected operation
- `/`: start fleet filter input; match by operation id, objective, status, agent cue, project, or attention text
- `p`: enqueue pause for the selected operation
- `u`: enqueue unpause/resume for the selected operation
- `s`: enqueue an operation-scoped stop-turn interrupt
- `c`: start cancel confirmation for the selected operation
- `?`: show the current view help overlay
- `r`: refresh the fleet snapshot immediately
- `q`: quit the workbench

Cancel confirmation:

- `y`: confirm cancellation
- any other key: abort cancellation

Filter input:

- type to update the fleet rows live
- `Enter`: apply the current filter text
- `Esc`: abort the edit and restore the previous filter
- submit an empty filter to clear it

## Operation Level

`Enter` from fleet opens the Level 1 operation view. The left pane is a task board. The right pane
switches between task-focused detail modes for the selected task. The task board is grouped into
status lanes in this order: `RUNNING`, `READY`, `BLOCKED`, `COMPLETED`, `FAILED`, `CANCELLED`.
`BLOCKED` is a display alias for `pending` tasks that still have unresolved dependencies.

Available keys:

- `j` / `k` or arrow keys: move the selected task
- `Enter`: open the Level 2 session view for the selected task if it has a linked session
- `n`: answer the oldest non-blocking attention for the selected task
- `A`: open the current-scope attention picker for the selected task
- `/`: start task filter input; match by task id, short id, title, status, agent, goal, or notes
- `i`: show task detail
- `d`: show decision memos for the selected task scope
- `t`: show recent operation events
- `m`: show memory entries for the selected task scope
- `Esc`: return to fleet
- `p`: enqueue pause for the parent operation
- `u`: enqueue unpause/resume for the parent operation
- `s`: enqueue a task-scoped stop-turn interrupt when the selected task has a linked session; otherwise fall back to an operation-scoped interrupt
- `c`: start cancel confirmation for the parent operation
- `?`: show the current view help overlay
- `r`: refresh the current fleet and operation payloads immediately
- `q`: quit the workbench

If the selected task has no linked session, `Enter` stays in the operation view and shows a status
message instead of opening Level 2.

Task filter input:

- type to update the task rows live
- `Enter`: apply the current filter text
- `Esc`: abort the edit and restore the previous filter
- submit an empty filter to clear it

## Session Level

`Enter` on a task with a linked session opens the Level 2 session view. The left pane shows the
selected task's session timeline. The right pane defaults to a split session screen:

- a compact session brief with `Now`, `Wait`, `Attention`, and `Latest output`
- a selected-event detail block for the currently highlighted timeline item

`r` switches that right pane to the raw transcript view for the current session payload.

Available keys:

- `j` / `k` or arrow keys: move the selected timeline item
- `/`: start session filter input; match by event type, summary, task id, session id, or iteration
- `n`: answer the oldest non-blocking attention for the current task
- `A`: open the current-scope attention picker for the current task
- `a`: answer the oldest blocking attention for the current task
- `Enter`: open the selected timeline item in the Level 3 forensic view
- `r`: toggle the right pane between timeline detail and raw transcript
- `Esc`: return to the operation view
- `s`: enqueue a task-scoped stop-turn interrupt when the task has a linked session; otherwise fall back to an operation-scoped interrupt
- `p`: enqueue pause for the parent operation
- `u`: enqueue unpause/resume for the parent operation
- `c`: start cancel confirmation for the parent operation
- `?`: show the current view help overlay
- `q`: quit the workbench

Session filter input:

- type to update the timeline rows live
- `Enter`: apply the current filter text
- `Esc`: abort the edit and restore the previous filter
- submit an empty filter to clear it

## Forensic Level

`Enter` on a selected session timeline item opens the Level 3 forensic view. This is a focused
read-only drill-down over the selected timeline event. It opens even when the session has no raw
transcript payload; in that case the forensic view still shows event context and an explicit `no
raw transcript` message.

Available keys:

- `/`: start forensic filter input; match by raw transcript/detail text
- `n`: answer the oldest non-blocking attention for the current task
- `A`: open the current-scope attention picker for the current task
- `?`: show the current view help overlay
- `Esc`: return to the session timeline
- `q`: quit the workbench

Forensic filter input:

- type to update the transcript/detail lines live
- `Enter`: apply the current filter text
- `Esc`: abort the edit and restore the previous filter
- submit an empty filter to clear it

The forensic view currently shows:

- task context for the selected event when available
- event type and iteration
- task id and session id when present in the timeline payload
- the selected event summary
- the raw transcript/detail text currently available for the selected session payload, or an
  explicit empty-state message when none is available

## Supported Actions

Current interactive actions implemented in the workbench:

- inspect fleet, operation, session, and forensic views
- show a compact keybinding help overlay for the current view without hiding the left pane
- answer the oldest blocking attention in scope from fleet, operation, or session, then continue
  directly to the next oldest blocking attention in the same scope when one remains
- answer the oldest non-blocking attention in scope with `n`, using the same inline answer flow
  and same-scope chaining behavior
- open a mixed current-scope attention picker with `A`, choose an exact attention item with
  `j`/`k`, and then reuse the same inline answer flow
- jump to the next attention-bearing operation from fleet
- refresh fleet and operation views
- pause an operation
- unpause/resume an operation
- enqueue stop-turn interrupts at operation scope
- enqueue stop-turn interrupts at task scope when the selected task has a linked session
- cancel an operation with explicit confirmation

These actions operate over persisted runtime truth and command delivery services already used by the
CLI.

When you answer a blocking attention with `a`, the workbench now keeps the interaction scoped and
oldest-first: after a successful answer, it auto-selects the next oldest blocking attention in the
same fleet or task scope when one remains and stays in answer mode so you can continue triage
without re-triggering `a`.

## Current Limitations

Current limitations of the implemented UI:

- The workbench is only available when `operator fleet` runs with interactive terminal input and output.
- The session brief and timeline now read from the shared normalized session payload used by
  `operator session`. They do not yet provide adapter-specific forensic formatting or rich
  per-event timestamps.
- The forensic view is read-only. It does not add deeper per-event actions beyond back-navigation.
- Inline attention answering now supports oldest-first blocking (`a`), oldest-first non-blocking
  (`n`), and a compact mixed attention picker (`A`), but it is still not a richer multi-pane
  attention management surface.
- Session drill-down depends on task-linked session data being present in the operation dashboard
  payload. Tasks without a linked session cannot open Level 2.
- Filtering is now available at fleet, operation, session, and forensic levels.
