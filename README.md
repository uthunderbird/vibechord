# operator

`operator` is a Python CLI and library for supervising other agents from a single operator loop.

It is aimed at developers and platform engineers who want one control surface for running agents,
tracking progress, and surfacing decisions that need human input.

## What problem it solves

Most agent tools are optimized for one agent in one surface. `operator` targets a different shape:
goal-directed orchestration across heterogeneous agents, with deterministic guardrails around an
LLM-driven control loop.

## Install

For local development:

```sh
uv sync --extra dev
```

Run the CLI:

```sh
UV_CACHE_DIR=/tmp/uv-cache uv run operator
```

## First useful path

1. Initialize the current project:

```sh
UV_CACHE_DIR=/tmp/uv-cache uv run operator init
```

2. Run one attached operation:

```sh
env OPERATOR_CODEX_ACP__COMMAND='npx @zed-industries/codex-acp --' \
    OPERATOR_CODEX_ACP__MODEL='gpt-5.4' \
    OPERATOR_CODEX_ACP__EFFORT='low' \
    UV_CACHE_DIR=/tmp/uv-cache \
    uv run operator run --mode attached --allowed-agent codex_acp --max-iterations 100 \
    "Inspect this repository and summarize the main architectural boundaries."
```

3. Inspect the operation:

```sh
UV_CACHE_DIR=/tmp/uv-cache uv run operator list
UV_CACHE_DIR=/tmp/uv-cache uv run operator status last
```

Runtime state is stored under `.operator/` in the project root.

## TUI Workbench

Launch the interactive fleet workbench from a real terminal:

```sh
UV_CACHE_DIR=/tmp/uv-cache uv run operator fleet
```

The implemented navigation path is `fleet -> operation -> session -> forensic`. Use `Enter` to
drill down, `Esc` to go back, and the level-specific bindings to inspect tasks, timeline items, raw
transcript/detail, and operation controls. The session level now defaults to a compact live session
screen with `Now`, `Wait`, `Attention`, `Latest output`, and selected-event detail; use `r` from
session level as a direct shortcut into the forensic/raw-transcript drill-down, and use `a` from
fleet, operation, or session to answer the oldest
blocking attention in scope, chaining directly to the next oldest blocking attention in the same
scope when one remains. The session timeline now renders newest-first. Fleet view also supports
`/` for a live filter over operation id,
objective, status, agent cue, project, and attention text, and operation view supports `/` for a
live task filter over task id, title, status, agent, goal, and notes. Session view also supports
`/` for a live timeline filter over event type, summary, task id, session id, and iteration.
Forensic view now supports `/` for a live raw-transcript/detail filter, `?` opens a compact help
overlay for the current workbench level, `n` answers the oldest non-blocking attention in the
current scope with the same inline flow used for blocking attention, and `A` opens a compact
current-scope attention picker so you can choose a specific attention item before answering.
Operation view now renders the task board in grouped status lanes, including a `BLOCKED` display
lane for dependency-blocked pending tasks, plus compact dependency and linked-session cue lines
under task rows when that context is available, with a status glyph on each task row.
Fleet view now uses a compact multi-line row layout in the left pane so each operation shows its
attention badge, display label, state/agent/recency line, and normalized hint without requiring a
drill-down.
`Enter` still drills into forensic even when a session has no raw transcript payload, falling back
to event context plus an explicit empty-state message, and forensic `q` now behaves like back-navigation
to session level instead of quitting the whole workbench. The forensic context pane now also shows
richer session metadata when that context is available. For the
current keymap, supported actions, and known limitations, see
[TUI Workbench](docs/tui-workbench.md). For the current forensic drill-down behavior, see
[TUI Forensic Workflow](docs/tui-forensic-workflow.md).

## Where to go next

- [Quickstart](docs/quickstart.md)
- [TUI Workbench](docs/tui-workbench.md)
- [CLI reference](docs/reference/cli.md)
- [Configuration reference](docs/reference/config.md)
- [Integrations](docs/integrations.md)
- [Contributing](CONTRIBUTING.md)
- [Design corpus](design/README.md)
