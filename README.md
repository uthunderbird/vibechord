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

## Where to go next

- [Quickstart](docs/quickstart.md)
- [CLI reference](docs/reference/cli.md)
- [Configuration reference](docs/reference/config.md)
- [Integrations](docs/integrations.md)
- [Contributing](CONTRIBUTING.md)
- [Design corpus](design/README.md)
