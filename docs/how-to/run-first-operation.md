# Run Your First Operation

## 1. Initialize the repository

```sh
UV_CACHE_DIR=/tmp/uv-cache uv run operator init
```

## 2. Start an attached run

```sh
env OPERATOR_CODEX_ACP__COMMAND='npx @zed-industries/codex-acp --' \
    OPERATOR_CODEX_ACP__MODEL='gpt-5.4' \
    OPERATOR_CODEX_ACP__EFFORT='low' \
    UV_CACHE_DIR=/tmp/uv-cache \
    uv run operator run --mode attached --allowed-agent codex_acp --max-iterations 100 \
    "Inspect this repository and summarize the main architectural boundaries."
```

## 3. Observe the operation

```sh
UV_CACHE_DIR=/tmp/uv-cache uv run operator status last
UV_CACHE_DIR=/tmp/uv-cache uv run operator tasks last
UV_CACHE_DIR=/tmp/uv-cache uv run operator attention last
```

## 4. Read the final output

```sh
UV_CACHE_DIR=/tmp/uv-cache uv run operator report last
```
