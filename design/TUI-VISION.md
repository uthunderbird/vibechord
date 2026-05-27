# TUI Vision

Status: `verified`

The TUI is the interactive supervisory workbench for live agent operations.

## Role

The TUI should let an operator:

- see the whole fleet;
- drill into one operation;
- inspect session/activity detail;
- answer attention;
- send live chat messages;
- pause, resume, interrupt, or cancel work;
- see stale or partial data labels.

The TUI is not the canonical state owner. It renders shared query payloads and
submits shared commands.

## Navigation Model

Initial levels:

1. `fleet` — cross-operation supervision.
2. `operation` — one operation, tasks/sessions/attention.
3. `session` — one agent/session timeline.
4. `forensic` — raw evidence/detail for selected event or session.

The TUI should preserve breadcrumb context and make the current scope visible.

Initial key model:

- arrow keys or `j`/`k` move selection;
- `enter` opens the selected item;
- `esc` moves up one level;
- `r` refreshes;
- `a` answers selected attention;
- `m` posts a live operator message;
- `p` pauses or resumes according to current status;
- `i` interrupts the current agent turn;
- `c` cancels with confirmation;
- `/` filters the current list.

## Fleet Level

Fleet rows should show:

- operation id/display label;
- status;
- active agent/session cue;
- current wait/attention state;
- live chat cue;
- freshness/staleness label.

Fleet actions:

- open operation;
- jump to next attention;
- answer attention;
- send chat message;
- pause/resume;
- interrupt;
- cancel with confirmation;
- filter;
- refresh.

## Operation Level

Operation view should show:

- goal summary;
- current status and stop reason if terminal;
- task/session board if tasks exist;
- attention queue;
- recent events;
- live chat history/cue;
- next useful actions.

## Session and Forensic Levels

Session view should show:

- adapter/session identity;
- current activity;
- latest output;
- waiting reason;
- selected timeline item.

Forensic view should show:

- event context;
- raw transcript/log reference if available;
- explicit empty state when forensic data is absent.

## Live Chat

The TUI should provide a visible live chat input for the selected operation.

Chat messages must use the shared operator-message command. They must not be
stored only in TUI state.

## Testability

TUI implementation must separate:

- query payloads;
- view models;
- render functions;
- keyboard event reducers;
- terminal runtime.

Most TUI behavior should be testable without a real terminal through view-model,
snapshot, reducer, and live-feed projection tests.

## First Implementation Slice

The first TUI slice should cover:

1. fleet view over shared fleet query payloads;
2. operation detail view over shared operation query payloads;
3. attention answer command;
4. live operator message command;
5. pause/resume/interrupt/cancel command dispatch with confirmation where
   destructive;
6. live-feed rendering from `LiveFeedEnvelope` inputs.

Acceptance gates:

- TUI reducers never mutate canonical state directly.
- View snapshots show stale/partial labels when query payloads include them.
- Command dispatch tests prove the TUI submits the same typed commands as CLI
  and REST.
- The first manual terminal check records viewport, command, and observed
  behavior in a verification note or release checklist.
