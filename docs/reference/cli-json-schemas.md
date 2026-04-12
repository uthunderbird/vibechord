# CLI JSON Schemas

This document is the stability reference for the agent-facing CLI payloads covered by ADR 0145.

## Stability Rules

- Published field names are stable.
- Adding new optional fields is non-breaking.
- Removing a field, renaming a field, or changing a field's type is breaking and requires a
  deprecation cycle.
- The deprecation cycle is: ship the new field alongside the old field in one release, then remove
  the old field in the next release with a changelog note.

## Covered Commands

### `operator run --json`

Without `--wait`, `run --json` emits JSON objects over stdout as a JSONL stream:

- `{"type":"operation","operation_id":"..."}`
- `{"type":"event","event":{...}}`
- `{"type":"snapshot","snapshot":{...}}` when live follow surfaces emit snapshots
- `{"type":"outcome","outcome":{...}}`

With `--wait`, the command emits one final JSON object:

- `operation_id`: string
- `status`: `completed|failed|needs_human|cancelled`
- `summary`: string
- `metadata`: object

### `operator status --json`

- `operation_id`: string
- `status`: string
- `summary`: object
- `action_hint`: string or null
- `durable_truth`: object

### `operator ask --json`

- `question`: string
- `answer`: string

### `operator fleet --once --json`

Fleet snapshot object as emitted by `cli_projection_payload(...)`.

### `operator list --json`

One JSON object per line. Each object is the operation brief payload for one operation, optionally
with `runtime_alert`.

### `operator tasks --json`

- `operation_id`: string
- `tasks`: array

### `operator attention --json`

- `operation_id`: string
- `attention_requests`: array

### `operator answer --json`

- `operation_id`: string
- `answer_command`: object
- `policy_command`: object or null
- `outcome`: object or null

### `operator ask --json`

- `operation_id`: string
- `question`: string
- `answer`: string

### `operator cancel --json`

- `operation_id`: string
- `status`: `cancelled|failed|needs_human|completed`
- `summary`: string
- `metadata`: object

### `operator watch --once --json`

Single snapshot object as emitted by `build_live_snapshot(...)`.
