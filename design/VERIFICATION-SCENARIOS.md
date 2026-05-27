# Verification Scenarios

Status: `verified`

This document is the scenario catalog for `vibechord` verification. It expands
[TESTING-RAILS.md](TESTING-RAILS.md) into concrete scenarios that implementation
plans can reference.

Implemented evidence is summarized in
[`docs/verification-matrix.md`](../docs/verification-matrix.md).

## Scenario Status Labels

- `required`: must exist before a claim can be marked implemented.
- `release-blocking`: must pass before a public pre-release can claim the
  related behavior.
- `optional-integration`: may require external binaries, credentials, or manual
  setup and is not part of the default local fake suite.

## Scenario Catalog

### VS-001 Domain And Guardrail Unit Scenarios

Status: `required`

Proves:

- operation status transitions reject invalid local states;
- stop policies fire deterministically;
- budget accounting is deterministic under fake time;
- command validators reject malformed or unsafe inputs;
- event constructors produce required event metadata.

Evidence:

- unit test output;
- failing-case assertions with stable error codes.

### VS-002 Protocol Conformance Scenarios

Status: `required`

Proves every implementation of a core protocol satisfies the same behavioral
contract.

Initial protocol suites:

- `OperatorBrain`;
- `AgentAdapter`;
- `EventStore`;
- `CommandApplication`;
- `ProjectionService`;
- `LiveFeed`;
- `DeliverySurface`;
- `RestApiSurface` when REST needs a surface-specific contract in addition to
  the generic delivery contract.

Evidence:

- shared conformance suite results for fake and real implementations;
- implementation registration list for each protocol suite.

### VS-003 Event Store And Replay Scenarios

Status: `required`

Proves:

- append order is preserved;
- sequence conflicts are rejected;
- duplicate command ids are idempotent;
- sequence gaps and corrupt events fail loudly;
- replay rebuilds canonical operation state;
- checkpoints and read models never outrank replay.

Evidence:

- event-store contract tests;
- persisted tempdir artifacts inspected by tests;
- replay state snapshots.

### VS-004 Operation Loop Fake-Harness Scenarios

Status: `required`

Proves the central operation loop works under deterministic fakes.

Workflows:

- happy path completion;
- iteration-limit stop;
- budget-limit stop;
- blocking attention and answer;
- live operator message affects next planning context;
- live operator message expiry;
- adapter failure;
- cancellation during active work;
- resume after persisted events.

Evidence:

- E2E fake harness summary;
- persisted events;
- stdout/stderr with rail-specific failure messages.

### VS-005 Delivery Parity Scenarios

Status: `required`

Proves CLI, TUI, REST, and future SDK/MCP surfaces do not create separate
business authority.

Checks:

- all surfaces resolve operation ids through the shared resolver;
- all mutating actions use `CommandApplication`;
- status and fleet reads use shared query DTOs;
- command response and error DTOs match across surfaces;
- live-feed envelopes have the same payload semantics across transports.

Evidence:

- parity tests comparing CLI JSON, TUI view models, and REST responses for the
  covered fields.

### VS-006 CLI Contract Scenarios

Status: `required`

Proves:

- `run` returns a resolvable operation id;
- `status --json` exposes shared status DTO fields;
- `fleet --once --json` exposes shared fleet row DTO fields;
- `message` and `answer` produce stable command responses;
- `watch --once --json` exposes canonical event sequence and live-feed
  provenance;
- exit codes match [CLI-VISION.md](CLI-VISION.md).

Evidence:

- CLI smoke tests;
- JSON schema or DTO assertions;
- exit-code tests.

### VS-007 TUI Projection And Reducer Scenarios

Status: `required`

Proves TUI behavior is testable without a real terminal.

Checks:

- fleet and operation views render from shared query payloads;
- stale/partial labels render when present;
- keyboard reducers dispatch typed commands without mutating canonical state;
- attention answer and live message actions use shared commands;
- destructive actions require confirmation;
- live-feed projection updates view models without becoming canonical truth.

Evidence:

- view-model tests;
- snapshot tests;
- keyboard reducer tests;
- command-dispatch tests.

### VS-008 REST API Contract Scenarios

Status: `required`

Proves REST is a delivery adapter, not a second runtime.

Checks:

- endpoints live under `/v1`;
- mutating endpoints require idempotency keys;
- mutating endpoints route through `CommandApplication`;
- read endpoints reuse shared operation and fleet query DTOs;
- event listing supports sequence-derived cursor resume;
- HTTP status codes do not replace stable application error codes;
- live transport emits `LiveFeedEnvelope` payloads without schema drift.

Evidence:

- endpoint tests;
- idempotency tests;
- cursor tests;
- REST/CLI/TUI parity tests.

### VS-009 REST Safety And Exposure Scenarios

Status: `release-blocking`

Proves REST cannot be accidentally exposed as a remote unauthenticated control
plane.

Checks:

- default bind address is loopback;
- non-loopback bind fails without explicit unsafe-development flag or real auth
  configuration;
- CORS is disabled by default;
- mutating REST calls emit audit events;
- non-local exposure requires documented auth behavior.

Evidence:

- configuration tests;
- audit-event tests;
- release claim audit.

### VS-010 Fleet And Live Chat Scenarios

Status: `required`

Proves fleet and live chat are first-class application concepts.

Checks:

- fleet includes running, blocked, terminal, and stale operations;
- fleet marks attention and live-chat cues;
- fleet overlays active agent/session facts with provenance;
- operator messages append through shared command authority;
- messages are distinct from typed commands and attention answers;
- message expiry is explicit and evented.

Evidence:

- fleet projection tests;
- live chat command/replay tests;
- multi-operation E2E fake harness workflow.

### VS-011 Adapter Integration Scenarios

Status: `required` for fake adapters, `optional-integration` for real adapters

Proves adapters do not leak vendor behavior into the core loop.

Checks:

- fake brain and fake agent satisfy conformance suites;
- real adapter DTO mapping is tested separately from core logic;
- adapter failures surface as explicit events;
- no hidden fallback path is introduced;
- external forensic logs are evidence, not canonical operation state.

Evidence:

- protocol conformance tests;
- mapping tests;
- fallback-free failure tests;
- optional integration test reports.

### VS-012 Architecture Fitness Scenarios

Status: `required`

Proves implementation is still moving in the intended architectural direction.

Checks:

- core/domain modules do not import vendor adapters;
- delivery modules do not bypass application command/query contracts;
- TUI modules do not own canonical business state;
- adapters do not write canonical events directly except through approved
  application boundaries;
- public docs do not claim implemented runtime behavior without evidence;
- ADRs include `Decision Status` and `Implementation Status`;
- hidden fallback paths require an explicit migration note;
- new core moving parts require updates to `MOVING-PARTS.md`, architecture, and
  an ADR.

Evidence:

- import-boundary tests;
- static checks;
- docs claim audit output;
- ADR lint/check output.

### VS-013 Release Verification Scenarios

Status: `release-blocking`

Proves public release claims are backed by current evidence.

Checks:

- verification matrix maps every release claim to tests, E2E artifacts, or
  manual verification notes;
- CLI reference matches implemented commands and exit codes;
- REST reference matches implemented schemas and safety behavior;
- TUI guide claims only behavior covered by automated checks or manual notes;
- known limitations and unsupported behavior are documented.

Evidence:

- release verification matrix;
- docs claim audit;
- E2E fake harness artifacts;
- manual terminal verification note for TUI behavior that cannot yet be
  automated.

## Requirement Coverage Matrix

| Requirement area | Scenario coverage |
| --- | --- |
| Operation loop and deterministic guardrails | VS-001, VS-003, VS-004 |
| Event authority and replay | VS-003, VS-004, VS-012 |
| Protocol-oriented adapters | VS-002, VS-011, VS-012 |
| CLI vision | VS-005, VS-006, VS-012 |
| TUI vision | VS-005, VS-007, VS-013 |
| REST API vision | VS-005, VS-008, VS-009, VS-013 |
| Fleet supervision | VS-005, VS-010 |
| Live operator chat | VS-004, VS-010 |
| Delivery-surface parity | VS-005, VS-006, VS-007, VS-008 |
| External proactive projection safety | VS-003, VS-005, VS-009, VS-012 |
| Testing rails architecture | VS-001 through VS-013 |
| Release readiness | VS-012, VS-013 |
| Minimum moving parts | VS-005, VS-012 |

## Planned Command Families

Exact command names may change when the package skeleton exists, but the first
implementation should provide these local gate families:

- `verify fast`: lint, type-check changed code, unit tests, and architecture
  fitness checks;
- `verify focused AREA`: relevant contract, replay, delivery, TUI, REST, or
  adapter scenarios for the touched area;
- `verify full`: all checks plus E2E fake harness workflows and docs claim
  audit.

Until a package command exists, implementation plans should state the underlying
`uv run ruff`, `uv run mypy`, and `uv run pytest` commands that satisfy each
gate.

## E2E Fake Harness Summary Shape

The E2E fake harness should produce a machine-readable summary with:

- `schema_version`;
- `run_id`;
- `workflow`;
- `status`;
- `operation_ids`;
- `event_artifact_paths`;
- `last_event_sequence_by_operation`;
- `rails_exercised`;
- `failed_rail` when applicable;
- `failure_message` when applicable;
- `started_at` and `finished_at`.

The summary should be stable enough for coding agents to inspect without
parsing free-form logs.
