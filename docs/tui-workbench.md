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

The header is a compact workbench summary band. It keeps the current breadcrumb on the first line
and adds human-readable scope or situation lines beneath it:

- `fleet`: scope plus the shared fleet counts (`Active / Running / Needs human / Paused`) and a short `Selected / Working on / Waiting on` summary for the current row
- `operation`: scope plus compact task counts (`Tasks / Running / Ready / Blocked / Done`) and a `Now / Waiting on / Needs input` summary for the current operation
- `session`: scope, session identity, and a compact `Now / Waiting on / Needs input` summary for the current task session
- `forensic`: session identity plus the currently focused event summary

The footer is the action band for the current state. It shows either:

- the primary actions for the current level in compact human-first language
- the active filter or answer prompt while editing
- the latest action result
- a cancel confirmation prompt

The live session footer now uses the shorter human-first action phrasing documented here:

- `session`: `Enter open transcript  r raw transcript  / filter  a/n answer  A pick  i live detail  o report  Esc back  ? help`

At fleet level, each selected operation row is rendered as a compact multi-line summary:

- line 1: attention badge plus display label
- line 2: state, agent cue, and recency brief
- line 3: normalized row hint such as `now: ...` or `waiting: ...`

## Fleet Level

`fleet` is the default entry view. It lists actionable operations across the current project scope.
The left pane uses the normalized fleet workbench row projection instead of a flat one-line table,
so the selected operation stays scannable without opening the right pane.

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
Blocked tasks show a compact dependency continuation line, and tasks with linked session runtime
state can show a compact session continuation line under the task row.
Task rows now include a compact status glyph before the task short id.

Available keys:

- `j` / `k` or arrow keys: move the selected task
- `Enter`: open the Level 2 session view for the selected task if it has a linked session
- `l`: open the selected task's transcript/log escalation path directly in the Level 3 forensic view
- `n`: answer the oldest non-blocking attention for the selected task
- `A`: open the current-scope attention picker for the selected task
- `/`: start task filter input; match by task id, short id, title, status, agent, goal, or notes
- `i`: show task detail
- `d`: show decision memos for the selected task scope
- `t`: show recent operation events
- `m`: show memory entries for the selected task scope
- `o`: show the operation retrospective report when one has been recorded
- `Esc`: return to fleet
- `p`: enqueue pause for the parent operation
- `u`: enqueue unpause/resume for the parent operation
- `s`: enqueue a task-scoped stop-turn interrupt when the selected task has a linked session; otherwise fall back to an operation-scoped interrupt
- `c`: start cancel confirmation for the parent operation
- `?`: show the current view help overlay
- `r`: refresh the current fleet and operation payloads immediately
- `q`: quit the workbench

If the selected task has no linked session, `Enter` stays in the operation view and shows a status
message instead of opening Level 2. `l` follows the same linked-session guardrail before opening
the direct transcript/log escalation path.

Task filter input:

- type to update the task rows live
- `Enter`: apply the current filter text
- `Esc`: abort the edit and restore the previous filter
- submit an empty filter to clear it

## Session Level

`Enter` on a task with a linked session opens the Level 2 session view. The left pane shows the
selected task's session timeline, ordered newest-first. The right pane defaults to a split session
screen:

- a compact session brief with explicit session identity plus `Now`, `Wait`, `Attention`, and `Latest output`
- a compact `Open` cue separating forensic drill-down (`Enter` / `r`), live detail (`i`), and retrospective report (`o`)
- a selected-event detail block for the currently highlighted timeline item

The session header also carries a compact live summary line so you can orient before reading the
right pane in detail. The session footer stays human-first, but it now includes the direct
intervention controls as well: `interrupt`, `pause`, `resume`, and `cancel` remain visible without
reverting to the older raw key-dump style.

Use `Enter` or `r` on the selected timeline item to drill into the Level 3 forensic/raw-transcript
view. `r` is the direct raw-transcript shortcut from session level. Use `o` to switch the session
right pane to the operation retrospective report, and `i` to return to the live session detail
panel.

Available keys:

- `j` / `k` or arrow keys: move the selected timeline item
- `/`: start session filter input; match by event type, summary, task id, session id, or iteration
- `n`: answer the oldest non-blocking attention for the current task
- `A`: open the current-scope attention picker for the current task
- `a`: answer the oldest blocking attention for the current task
- `Enter`: open the selected timeline item in the Level 3 forensic view
- `r`: open the selected timeline item in the Level 3 forensic/raw-transcript view
- `i`: show the live session detail panel
- `o`: show the operation retrospective report in the session right pane
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
- `q`: return to the session timeline from forensic/raw-transcript view
- `Ctrl+C`: quit the workbench

Forensic filter input:

- type to update the transcript/detail lines live
- `Enter`: apply the current filter text
- `Esc`: abort the edit and restore the previous filter
- submit an empty filter to clear it

The forensic view currently shows:

- task context for the selected event when available
- session adapter, status, waiting reason, and bound-task context when available
- event type and iteration
- task id and session id when present in the timeline payload
- the selected event summary
- the raw transcript/detail text currently available for the selected session payload, or an
  explicit empty-state message when none is available

## Supported Actions

Current interactive actions implemented in the workbench:

- inspect fleet, operation, session, and forensic views
- show the retained operation retrospective report from operation level
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
