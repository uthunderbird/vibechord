# MCP Tool Schemas

This document is the committed contract reference for the inbound MCP server exposed by
`operator mcp`.

## Entry Point

```bash
operator mcp
```

Recommended Claude Code configuration:

```json
{
  "mcpServers": {
    "operator": {
      "command": "operator",
      "args": ["mcp"]
    }
  }
}
```

## Tool Surface

The initial published tool set contains exactly six tools:

- `list_operations`
- `run_operation`
- `get_status`
- `answer_attention`
- `cancel_operation`
- `interrupt_operation`

All tool input schemas are strict. Unknown fields are rejected.

### `list_operations`

Input:

```json
{
  "status_filter": "running | needs_human | completed | failed | cancelled | null"
}
```

Return:

```json
[
  {
    "operation_id": "op-abc123",
    "status": "needs_human",
    "goal": "Inspect MCP status",
    "started_at": "2026-04-12T10:00:00+00:00",
    "attention_count": 1
  }
]
```

### `run_operation`

Input:

```json
{
  "goal": "Inspect this repository and summarize the MCP surface.",
  "agent": "codex_acp",
  "wait": false,
  "timeout_seconds": null
}
```

Return without wait:

```json
{
  "operation_id": "op-abc123",
  "status": "running"
}
```

Return with `wait=true`:

```json
{
  "operation_id": "op-abc123",
  "status": "completed",
  "outcome": {
    "status": "completed",
    "summary": "Finished."
  }
}
```

Notes:

- `agent` is optional. If omitted, the active project profile's default agent set is used.
- `wait=true` polls persisted operation state until a terminal outcome is available.
- `timeout_seconds` applies only when `wait=true`. On timeout, the server returns a structured
  MCP error with `data.code = "timeout"`.
- `run_operation` requires a local `operator-profile.yaml` so the server can resolve the project
  profile and default agent configuration.

### `get_status`

Input:

```json
{
  "operation_id": "op-abc123"
}
```

Return:

```json
{
  "operation_id": "op-abc123",
  "status": "needs_human",
  "goal": "Inspect MCP status",
  "iteration": 0,
  "task_summary": "1 blocked",
  "attention_requests": [
    {
      "id": "att-1",
      "question": "Which environment should I deploy to?",
      "created_at": "2026-04-12T10:01:00+00:00"
    }
  ],
  "started_at": "2026-04-12T10:00:00+00:00",
  "ended_at": "2026-04-12T10:05:00+00:00",
  "outcome_summary": "Waiting for user input."
}
```

Notes:

- `operation_id` also accepts `last` and an unambiguous operation-id prefix.
- `attention_requests` includes only open blocking attention items.
- `task_summary` is the compact human-facing summary already used by the CLI status surfaces.

### `answer_attention`

Input:

```json
{
  "operation_id": "op-abc123",
  "attention_id": null,
  "answer": "Deploy to staging first."
}
```

Return:

```json
{
  "attention_id": "att-1",
  "status": "answered"
}
```

Notes:

- If `attention_id` is omitted or `null`, the oldest blocking attention request is answered.

### `cancel_operation`

Input:

```json
{
  "operation_id": "op-abc123",
  "reason": "No longer needed"
}
```

Return:

```json
{
  "operation_id": "op-abc123",
  "status": "cancelled"
}
```

### `interrupt_operation`

Input:

```json
{
  "operation_id": "op-abc123"
}
```

Return:

```json
{
  "operation_id": "op-abc123",
  "acknowledged": true
}
```

## Error Contract

Tool failures are returned through the MCP/JSON-RPC `error` response shape. `error.data` contains
the stable operator-specific fields:

```json
{
  "code": "not_found | invalid_state | timeout | internal_error",
  "operation_id": "op-abc123"
}
```

Meaning:

- `not_found`: the requested operation or attention target does not exist
- `invalid_state`: the request conflicts with current runtime state or violates the published tool
  schema
- `timeout`: a waited operation did not reach a terminal outcome before the requested timeout
- `internal_error`: an unexpected server-side failure occurred

The `operation_id` field is included when the failure is scoped to a specific operation.
