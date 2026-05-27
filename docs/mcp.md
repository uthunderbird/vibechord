# MCP

Status: `verified`

`vibechord` exposes an MCP-style stdio surface over the same local SDK
contracts as CLI, TUI, and REST. It uses JSON-RPC request/response messages for
initialization, tool discovery, resource reads, prompt templates, and tool
calls.

## Command

```sh
uv run vibechord mcp
```

The stdio loop accepts one JSON-RPC message per line.

HTTP JSON-RPC POST transport is also available:

```sh
uv run vibechord mcp-http --host 127.0.0.1 --port 8766
```

The HTTP endpoint accepts `POST /mcp` for JSON-RPC requests and `GET /mcp` for
Server-Sent Events replay. When `--token TOKEN` is configured, requests must
include `Authorization: Bearer TOKEN`. The configured token is hashed in memory
and compared through the shared REST auth path.

## Tools

- `vibechord_run`: start and drive an operation.
- `vibechord_status`: read operation status.
- `vibechord_fleet`: list fleet rows.
- `vibechord_live`: read live-feed envelopes.
- `vibechord_message`: post a live operator message.

## Scope

Implemented:

- `initialize`;
- `ping`;
- `tools/list`;
- `tools/call`;
- `resources/list`;
- `resources/read`;
- `resources/subscribe`;
- `resources/unsubscribe`;
- `prompts/list`;
- `prompts/get`;
- `notifications/progress` for tool calls that include
  `params._meta.progressToken`;
- newline-delimited stdio transport for local clients.
- HTTP JSON-RPC POST transport at `/mcp`;
- HTTP GET SSE event replay with `Last-Event-ID` resume;
- durable JSONL-backed MCP transport events across process restarts;
- bounded `GET /mcp?wait=N` waits for future events.

Not implemented:

- unbounded long-lived streams.

Resource subscription methods maintain session-local subscription state and
acknowledge subscribe/unsubscribe requests. They do not yet emit asynchronous
`notifications/resources/updated` messages.

## Verification

MCP behavior is covered by `tests/test_mcp.py` and the full local gate:

```sh
uv run vibechord verify full
```
