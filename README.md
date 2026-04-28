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
    uv run operator run --mode attached --agent codex_acp --max-iterations 100 \
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
drill down and `Esc` to go back. Fleet, operation, session, and forensic levels provide live
filters, attention actions, and direct supervision controls, with session level focused on compact
live state and forensic level focused on raw transcript/detail drill-down. For the current keymap,
supported actions, and known limitations, see [TUI Workbench](docs/tui-workbench.md). For the
current forensic drill-down behavior, see
[TUI Forensic Workflow](docs/tui-forensic-workflow.md).

## Where to go next

- [Quickstart](docs/quickstart.md)
- [Public release reference](docs/reference/public-release.md)
- [TUI Workbench](docs/tui-workbench.md)
- [CLI reference](docs/reference/cli.md)
- [Configuration reference](docs/reference/config.md)
- [Integrations](docs/integrations.md)
- [Contributing](CONTRIBUTING.md)
- [Design corpus](design/README.md)

## MCP Server

`operator` exposes an inbound MCP server for Claude Code and Codex.

Start the server on stdio:

```sh
UV_CACHE_DIR=/tmp/uv-cache uv run operator mcp
```

Claude Code configuration:

```json
{
  "mcpServers": {
    "operator": {
      "command": "operator",
      "args": ["mcp"],
      "env": {
        "OPERATOR_DATA_DIR": "/path/to/project/.operator"
      }
    }
  }
}
```

The committed MCP tool contract lives in
[design/reference/mcp-tool-schemas.md](design/reference/mcp-tool-schemas.md).
