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
screen with `Now`, `Wait`, `Attention`, `Latest output`, and selected-event detail; use `r` to
switch to raw transcript, and use `a` from fleet, operation, or session to answer the oldest
blocking attention in scope. For the current keymap, supported actions, and known limitations, see
[TUI Workbench](docs/tui-workbench.md).

## Where to go next

- [Quickstart](docs/quickstart.md)
- [TUI Workbench](docs/tui-workbench.md)
- [CLI reference](docs/reference/cli.md)
- [Configuration reference](docs/reference/config.md)
- [Integrations](docs/integrations.md)
- [Contributing](CONTRIBUTING.md)
- [Design corpus](design/README.md)
