# Resume And Inspect Operations

## Inspect persisted operations

```sh
UV_CACHE_DIR=/tmp/uv-cache uv run operator list
UV_CACHE_DIR=/tmp/uv-cache uv run operator status last
```

## Resume a previous operation

Use the operation ID shown by `operator list`, or `last` when the current project has a recent run.
The current manual resume surface is a debug/repair command rather than part of the default stable
day-to-day CLI story.

```sh
UV_CACHE_DIR=/tmp/uv-cache uv run operator debug resume last
```

## Inspect details

```sh
UV_CACHE_DIR=/tmp/uv-cache uv run operator report last
UV_CACHE_DIR=/tmp/uv-cache uv run operator tasks last
UV_CACHE_DIR=/tmp/uv-cache uv run operator memory last
UV_CACHE_DIR=/tmp/uv-cache uv run operator artifacts last
```

## Interrupt, pause, or cancel

```sh
UV_CACHE_DIR=/tmp/uv-cache uv run operator interrupt last
UV_CACHE_DIR=/tmp/uv-cache uv run operator pause last
UV_CACHE_DIR=/tmp/uv-cache uv run operator unpause last
UV_CACHE_DIR=/tmp/uv-cache uv run operator cancel last
```
