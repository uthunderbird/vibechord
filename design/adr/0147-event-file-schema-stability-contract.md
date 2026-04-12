# ADR 0147: Event file schema stability contract

- Date: 2026-04-12

## Decision Status

Accepted

## Implementation Status

Implemented

## Context

`operator` writes a per-operation JSONL event file at `.operator/events/<operation_id>.jsonl`.
That surface is already consumed by live-watch style flows and is called out in
`AGENT-INTEGRATION-VISION.md` as an agent-facing integration point.

Before this closure wave, the repository truth and the draft ADR text were misaligned:

- the file path and JSONL write path already existed
- the serialized payload was the incidental `RunEvent.model_dump_json()` shape
- no explicit wire-record model anchored the event-file contract in code
- no committed schema reference documented the stable top-level fields
- the draft ADR overclaimed an alternate event shape (`kind` as event name, `ts`, `seq`,
  `iteration_started`, `operation_completed`, etc.) that the runtime does not emit

Per repository policy, the event-file contract has to be grounded in the implemented codebase
rather than in an aspirational alternate schema.

## Decision

The stable event-file contract is the current per-operation JSONL surface backed by an explicit
wire-record model and schema reference.

### File contract

- Path: `<data_dir>/events/<operation_id>.jsonl`
- Default project-local path: `.operator/events/<operation_id>.jsonl`
- Encoding: UTF-8
- Format: one JSON object per line
- Schema version field: `schema_version`

### Stable top-level fields

Every event-file line contains these stable top-level fields:

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

Stable routing is by `event_type`. Consumers must not treat `kind` as the event name; `kind`
remains the runtime bucket (`trace` or `wakeup`).

### Stable event-type catalog

The stable agent-facing routing set currently implemented is:

- `operation.started`
- `brain.decision.made`
- `agent.invocation.started`
- `agent.invocation.background_started`
- `agent.invocation.completed`
- `evaluation.completed`
- `operation.cycle_finished`

Other `event_type` values currently written to the file are implementation detail unless and until
they are explicitly added to the committed schema reference.

### Breaking change policy

A breaking change is any of:

- removing a stable top-level field
- renaming a stable top-level field
- changing the type or semantics of a stable top-level field
- removing a stable event type from the catalog
- changing the semantics of a stable event type

The deprecation cycle is:

1. release N: emit old and new fields or event types side by side
2. release N+1: remove the old field or event type with changelog note

Adding new optional top-level fields is non-breaking.

Adding new event types outside the stable catalog is non-breaking.

### Consumption guidance

Agents consuming the file should:

1. open `<data_dir>/events/<operation_id>.jsonl`
2. parse one JSON object per line
3. route by `event_type`
4. ignore unknown `event_type` values
5. treat `operation.cycle_finished` as the stable terminal event for a completed run invocation

## Consequences

- The event file is now anchored by code (`EventFileRecord`) rather than by incidental raw model
  serialization.
- Agents have a committed schema reference for the file surface.
- The stable contract now matches the runtime that actually exists.
- Legacy event-file lines remain readable through the parser compatibility path.

## Grounding Evidence

- Wire model: `src/agent_operator/domain/events.py` (`EventFileRecord`,
  `EVENT_FILE_SCHEMA_VERSION`, `RunEvent.to_event_file_record`)
- Writer and parser: `src/agent_operator/runtime/events.py` (`JsonlEventSink.emit`,
  `JsonlEventSink.read_events`, `JsonlEventSink.iter_events`, `parse_event_file_line`)
- Schema reference: `docs/reference/event-file-json-schema.md`
- Agent-facing design reference: `design/AGENT-INTEGRATION-VISION.md`
- Stable event emitters:
  - `src/agent_operator/application/service.py` (`OperatorService.run`)
  - `src/agent_operator/application/drive/operation_drive.py` (`OperationDriveService.drive`)
  - `src/agent_operator/application/attached_turns.py` (`AttachedTurnService.start_turn`,
    `AttachedTurnService.continue_turn`)
  - `src/agent_operator/application/operation_turn_execution.py`
    (`OperationTurnExecutionService.start_background_agent_turn`,
    `OperationTurnExecutionService.continue_background_agent_turn`)
  - `src/agent_operator/application/agent_results.py`
    (`AgentResultService.handle_agent_result`)
- Verification:
  - `tests/test_runtime.py`
  - `tests/test_cli.py`

## Closure Evidence Matrix

| ADR clause | Repository evidence | Closure |
|---|---|---|
| per-operation JSONL file path is the contract surface | `src/agent_operator/runtime/events.py` `JsonlEventSink.__init__`; `docs/reference/event-file-json-schema.md` | closed |
| UTF-8 one-object-per-line persistence is explicit | `src/agent_operator/runtime/events.py` `JsonlEventSink.emit` | closed |
| stable wire schema is code-owned, not incidental | `src/agent_operator/domain/events.py` `EventFileRecord`; `RunEvent.to_event_file_record` | closed |
| stable top-level fields are documented | `docs/reference/event-file-json-schema.md` | closed |
| stable routing uses `event_type` | `docs/reference/event-file-json-schema.md`; `design/AGENT-INTEGRATION-VISION.md` | closed |
| `operation.started` is implemented | `src/agent_operator/application/service.py` `OperatorService.run` | closed |
| `brain.decision.made` and `evaluation.completed` are implemented | `src/agent_operator/application/drive/operation_drive.py` `OperationDriveService.drive` | closed |
| `agent.invocation.started` is implemented | `src/agent_operator/application/attached_turns.py` `AttachedTurnService.start_turn` and `continue_turn` | closed |
| `agent.invocation.background_started` is implemented | `src/agent_operator/application/operation_turn_execution.py` `OperationTurnExecutionService.start_background_agent_turn` and `continue_background_agent_turn` | closed |
| `agent.invocation.completed` is implemented | `src/agent_operator/application/agent_results.py` `AgentResultService.handle_agent_result` | closed |
| `operation.cycle_finished` is the stable terminal run event | `src/agent_operator/application/drive/operation_drive.py` `OperationDriveService.drive` | closed |
| event-file parser tolerates historical pre-contract lines | `src/agent_operator/runtime/events.py` `parse_event_file_line`; `tests/test_runtime.py::test_parse_event_file_line_accepts_legacy_run_event_payload` | closed |
| schema contract is regression tested | `tests/test_runtime.py::test_jsonl_event_sink_reads_written_events`; `tests/test_runtime.py::test_event_file_record_round_trips_run_event` | closed |
| CLI event-file consumers still work on the stabilized schema | `tests/test_cli.py::test_watch_follows_live_attached_events_and_state`; `tests/test_cli.py::test_watch_resolves_last_operation_reference` | closed |

## Related

- [AGENT-INTEGRATION-VISION.md](../AGENT-INTEGRATION-VISION.md)
- [docs/reference/event-file-json-schema.md](../../docs/reference/event-file-json-schema.md)
- [ADR 0145](./0145-cli-output-format-and-agent-integration-stability-contract.md)
- [ADR 0086](./0086-event-sourced-command-application-service.md)
- [ADR 0144](./0144-event-sourcing-write-path-contract-and-rfc-0009-closure.md)
