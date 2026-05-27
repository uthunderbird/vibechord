# TUI Guide

Status: `verified`

The implementation includes a full-screen curses TUI runtime, a line-oriented
terminal fallback for injected streams, and a pure view/reducer model.

Run a one-shot fleet view:

```sh
uv run vibechord tui --once
```

Interactive `vibechord tui` uses curses by default. The reusable view/reducer
layer and curses runtime are tested without a real terminal through a fake
screen protocol.

Full-screen keys:

- `j` / `k`: move selection;
- `enter`: open selected operation;
- `esc`: return to fleet;
- `r`: refresh;
- `m`: post a live operator message to the selected operation;
- `a`: answer open attention;
- `p`: pause or resume selected operation;
- `i`: interrupt selected operation;
- `c`: request/confirm cancellation;
- `q`: quit.

Line-oriented mode remains available when tests or callers provide explicit
input/output streams.

The TUI never owns canonical operation state. It renders `ProjectionService`
payloads and submits commands through `CommandApplication`.
