# TUI Forensic Workflow

This note covers the current interactive forensic drill-down inside the `operator fleet` workbench.

## Entry

From the Level 2 `session` view, press `Enter` on the selected timeline event to open the Level 3
forensic view.

From the Level 1 `operation` view, press `l` on a task with a linked session to take the direct
transcript/log escalation path into the same Level 3 forensic view without stopping in the live
session screen first.

The forensic view opens even if the session has no raw transcript payload. In that case, the right
pane still shows the selected event context and an explicit `No raw transcript available for the
selected session.` message.

## Current actions

- `a`: answer the oldest blocking attention for the current task without backing out of forensic
- `n`: answer the oldest non-blocking attention for the current task
- `A`: open the current-scope attention picker for the current task
- `/`: filter the current raw transcript/detail text
- `?`: show the forensic help overlay
- `Esc`: return to the session timeline
- `q`: return to the session timeline

## Scope rule

The forensic view keeps the current task and session scope from Level 2. That means the inline
answer action uses the same current-task attention routing as the session view rather than changing
the selected scope.
