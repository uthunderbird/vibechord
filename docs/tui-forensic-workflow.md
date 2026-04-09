# TUI Forensic Workflow

This note covers the current interactive forensic drill-down inside the `operator fleet` workbench.

## Entry

From the Level 2 `session` view, press `Enter` on the selected timeline event to open the Level 3
forensic view.

The forensic view opens even if the session has no raw transcript payload. In that case, the right
pane still shows the selected event context and an explicit `No raw transcript available for the
selected session.` message.

## Current actions

- `a`: answer the oldest blocking attention for the current task without backing out of forensic
- `Esc`: return to the session timeline
- `q`: quit the workbench

## Scope rule

The forensic view keeps the current task and session scope from Level 2. That means the inline
answer action uses the same current-task attention routing as the session view rather than changing
the selected scope.
