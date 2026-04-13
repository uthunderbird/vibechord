# Quickstart

This quickstart gets you from a fresh checkout to a first useful `operator` run.

## Prerequisites

- Python 3.13
- `uv`
- an available agent backend such as `codex_acp`

## Install

```sh
uv sync --extra dev
```

## Initialize the project

```sh
UV_CACHE_DIR=/tmp/uv-cache uv run operator init
```

This creates local operator state under `.operator/`.

## Run your first operation

For `codex_acp`, use the explicit command override:

```sh
env OPERATOR_CODEX_ACP__COMMAND='npx @zed-industries/codex-acp --' \
    OPERATOR_CODEX_ACP__MODEL='gpt-5.4' \
    OPERATOR_CODEX_ACP__EFFORT='low' \
    UV_CACHE_DIR=/tmp/uv-cache \
    uv run operator run --mode attached --agent codex_acp --max-iterations 100 \
    "Inspect this repository and summarize the main architectural boundaries."
```

## Inspect the result

```sh
UV_CACHE_DIR=/tmp/uv-cache uv run operator list
UV_CACHE_DIR=/tmp/uv-cache uv run operator status last
UV_CACHE_DIR=/tmp/uv-cache uv run operator report last
```

## Common next steps

- [Run your first operation](how-to/run-first-operation.md)
- [Resume and inspect operations](how-to/resume-and-inspect.md)
- [CLI reference](reference/cli.md)
- [Configuration reference](reference/config.md)
