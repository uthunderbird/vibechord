# REST API Vision

Status: `verified`

The REST API is a new first-class delivery surface for remote and programmatic
supervision of `vibechord`.

## Role

REST should expose the same operation, fleet, command, and live-feed semantics
as CLI and TUI.

REST is not a separate runtime, database authority, or workflow engine. It is a
delivery adapter over shared application command/query contracts.

## API Shape

Initial resource families:

- `/v1/health`
- `/v1/operations`
- `/v1/operations/{operation_id}`
- `/v1/operations/{operation_id}/commands`
- `/v1/operations/{operation_id}/messages`
- `/v1/operations/{operation_id}/attention`
- `/v1/operations/{operation_id}/events`
- `/v1/operations/{operation_id}/live`
- `/v1/fleet`
- `/v1/agents`

Initial operations:

- create operation;
- get operation status/detail;
- list fleet;
- cancel/pause/resume/interrupt operation;
- answer attention;
- post operator message;
- stream or poll live feed;
- list events with cursor.

## Command Semantics

Mutating endpoints should submit typed commands through the shared command
application path.

Required properties:

- idempotency keys for command submission;
- stable command accepted/rejected responses;
- stable error code taxonomy;
- no direct mutation of read models;
- no REST-only command semantics.

Initial command responses should include:

- `command_id`;
- `accepted`;
- `code`;
- `message`;
- `operation_id` when applicable;
- `resulting_event_ids` when events were appended;
- `retryable` when known.

## Read Semantics

Read endpoints should expose:

- canonical status fields;
- derived projection fields;
- runtime overlay provenance;
- staleness/freshness labels;
- operation id and sequence cursor information where relevant.

List endpoints should use cursor pagination. Offset pagination is not a first
implementation target because event streams and fleet projections need stable
resume points.

Event cursors should be derived from operation event sequence, not wall-clock
timestamps.

## Error Model

REST errors should map from shared application errors.

Initial fields:

- `code`;
- `message`;
- `details`;
- `operation_id` when known;
- `retryable`;
- `correlation_id`.

HTTP status codes are transport metadata. They must not replace stable
application error codes.

## Live Feed

REST should support live observation through an implementation-appropriate
transport, initially one of:

- Server-Sent Events;
- WebSocket;
- long polling.

The live payload shape should be `LiveFeedEnvelope` from the application layer.
Transport choice must not change payload semantics.

## Safety and Access

Authentication and authorization are required before REST is exposed beyond
localhost.

Initial implementation may be local-only, but the API design should keep room
for:

- bearer token or local auth;
- project/workspace scoping;
- audit events for mutating calls;
- CORS disabled by default.

Local-only means bind to loopback by default and reject non-loopback exposure
unless an explicit unsafe-development flag or real auth configuration is
present.

## Testability

REST tests should cover:

- endpoint-to-command routing;
- endpoint-to-query routing;
- idempotency;
- error codes;
- live-feed payload shape;
- parity with CLI/TUI payloads for covered operations.

First implementation acceptance gates:

- all mutating endpoints require an idempotency key;
- all mutating endpoints route through `CommandApplication`;
- operation detail and fleet endpoints reuse shared query DTOs;
- event listing supports cursor resume;
- live-feed transport emits `LiveFeedEnvelope` payloads without transport-only
  schema changes;
- local-only binding behavior is covered by configuration tests.
