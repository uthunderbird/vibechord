# Quickstart

Status: `verified`

This guide covers the local first implementation slice.

## Install For Development

```sh
uv sync
```

## Start And Inspect An Operation

```sh
uv run vibechord --json init
uv run vibechord --json run "write a short plan"
uv run vibechord --json fleet --once
```

Use the returned `operation_id` for focused inspection:

```sh
uv run vibechord --json status OPERATION_ID
uv run vibechord --json watch OPERATION_ID --once
uv run vibechord --json show report OPERATION_ID
```

## Local REST

```sh
uv run vibechord serve --host 127.0.0.1 --port 8765
```

REST is local-first. Non-loopback binding requires configured bearer-token auth
or the explicit unsafe development flag. Use `--token` for an admin token,
`--read-token` for read-only access, or `--control-token` for read/write
control access. For production non-loopback use `--production` with auth and
`--tls-cert`.

## Local Verification

```sh
uv run vibechord verify full
```

This runs lint, strict typing, and tests.
