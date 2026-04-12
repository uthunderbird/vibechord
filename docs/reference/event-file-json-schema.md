# Event File JSON Schema

This document is the stability reference for the file-based event streaming surface covered by
ADR 0147.

## Stability Rules

- Published top-level field names are stable.
- Adding new optional top-level fields is non-breaking.
- Removing a top-level field, renaming a top-level field, or changing a top-level field's type is
  breaking and requires a deprecation cycle.
- The deprecation cycle is: ship the new field alongside the old field in one release, then remove
  the old field in the next release with a changelog note.
- Stable event routing uses `event_type`. Consumers must ignore unknown `event_type` values for
  forward compatibility.

## File Contract

- Path: `<data_dir>/events/<operation_id>.jsonl`
- Encoding: UTF-8
- Format: one JSON object per line
- Current `schema_version`: `1`

## Stable Top-Level Fields

Every event-file line contains:

- `schema_version`: integer
- `event_id`: string
- `event_type`: string
- `kind`: `trace | wakeup`
- `category`: `domain | trace | null`
- `operation_id`: string
- `iteration`: integer
- `task_id`: string or null
- `session_id`: string or null
- `dedupe_key`: string or null
- `timestamp`: ISO 8601 datetime string
- `not_before`: ISO 8601 datetime string or null
- `payload`: object

## Stable Event Types

The following event types are the stable agent-facing routing set currently implemented:

- `operation.started`
- `brain.decision.made`
- `agent.invocation.started`
- `agent.invocation.background_started`
- `agent.invocation.completed`
- `evaluation.completed`
- `operation.cycle_finished`

Other event types currently written to the file are implementation detail unless and until they
are explicitly added to this reference.
