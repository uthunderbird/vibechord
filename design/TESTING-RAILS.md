# Testing Rails

Status: `verified`

This document defines the verification rails `vibechord` uses before and during
runtime implementation. Current implemented evidence is tracked in
[`docs/verification-matrix.md`](../docs/verification-matrix.md).

[VERIFICATION-SCENARIOS.md](VERIFICATION-SCENARIOS.md) is the concrete scenario
catalog for these rails.

## Purpose

`vibechord` must be testable end to end by local development tools. The test
system should prove both:

- behavior is correct; and
- development is still moving in the intended architectural direction.

The rails therefore include ordinary behavioral tests and architecture fitness
checks.

## Core Testing Thesis

The system should be built around fakeable boundaries and replayable evidence.

Every major runtime dependency should have a deterministic test double:

- fake clock;
- fake operator brain;
- fake agent adapter;
- fake event sink/store;
- tempdir-backed persistence;
- scripted command source;
- scripted live-feed consumer;
- renderable TUI projection.

If a feature cannot be exercised with those local fakes, the design is not yet
testable enough.

## Test Mesh

### 1. Unit Tests

Purpose: prove local behavior cheaply and deterministically.

Targets:

- domain model invariants;
- stop-policy evaluation;
- budget accounting;
- command validation;
- event construction;
- read-model projection functions;
- prompt/context assembly;
- small formatting and rendering functions.

Rules:

- no network;
- no real terminal;
- no real agent process;
- no wall-clock sleeps unless guarded by fake time;
- regression tests for bug fixes at the lowest useful level.

### 2. Protocol Contract Tests

Purpose: prove implementations satisfy shared contracts.

Every implementation of a core protocol should run the same conformance suite.

Candidate contract suites:

- `OperatorBrain` contract;
- `AgentAdapter` contract;
- `EventStore` contract;
- `CommandApplication` contract;
- `ProjectionService` contract;
- `LiveFeed` contract;
- `DeliverySurface` contract.
- `RestApiSurface` contract when REST is implemented separately from generic
  delivery adapters.

The contract suite should test required behavior, not implementation details.

Contract suites should be reusable behavior specifications. Each suite should
accept implementation factories or fixtures rather than copy-pasting assertions
per implementation. Adding a new implementation should mean registering it with
the relevant suite and satisfying the same behavioral cases as existing
implementations.

Examples:

- an `AgentAdapter` can start a session, accept an input, return progress, and
  report terminal result or explicit failure;
- an `EventStore` preserves append order, rejects sequence conflicts, and can
  replay from a cursor;
- a `DeliverySurface` resolves the same operation id and command result shape
  across CLI, TUI, REST, SDK, and future MCP bindings.

### 3. Event Replay and State Authority Tests

Purpose: prove canonical state can be rebuilt and does not split from live
surfaces.

Required scenarios:

- event append and replay reconstruct the same operation state;
- duplicate command ids are idempotent;
- sequence gaps are detected and surfaced;
- stale projections are labeled, not silently trusted;
- checkpoints/read models never outrank canonical replay;
- forensic upstream logs are treated as evidence, not canonical operation truth.

These tests should inspect persisted artifacts directly when file-backed storage
exists.

### 4. Operation Loop Tests

Purpose: prove the central loop works under deterministic fakes.

Required scenarios:

- operation completes when fake brain emits a valid completion decision;
- iteration limit stops the run deterministically;
- budget limit stops the run deterministically;
- adapter failure becomes an explicit failed state and event;
- human attention gates forward progress when blocking;
- answering attention resumes progress through the command path;
- live operator message enters planning context and later expires with an event;
- cancellation wins over in-flight work.

These should run without real LLMs or external agents.

### 5. Delivery Parity Tests

Purpose: prevent CLI, TUI, REST, SDK, and future MCP from creating separate
business authority.

Required parity checks:

- all delivery surfaces use the same operation resolver;
- all state-changing actions use the same command application path;
- status/fleet reads use `ProjectionService` through shared delivery contracts;
- machine-facing error codes are stable and documented;
- surface-specific rendering does not change underlying command/query meaning.

When a new delivery surface is added, parity tests must fail until it is wired
through the shared contracts.

### 6. Fleet Tests

Purpose: make fleet supervision a tested read model, not a TUI-local table.

Required scenarios:

- fleet includes running, blocked, terminal, and stale operations;
- fleet marks operations with blocking attention;
- fleet marks operations with live chat waiting or recently received;
- fleet reports active agent/session facts from live overlays with provenance;
- fleet labels stale projection data;
- fleet drill-down references the same operation ids as status and trace
  surfaces.

### 7. Live Chat Tests

Purpose: prove operator chat is a first-class input channel.

Required scenarios:

- operator message appends through shared command authority;
- message appears in the next fake brain planning context;
- message expiry is explicit and evented;
- chat messages are distinct from typed commands and attention answers;
- TUI chat input and CLI/REST message commands converge on the same persisted
  truth.

### 8. TUI Projection Tests

Purpose: keep TUI behavior testable without requiring a GUI.

The TUI should separate:

- domain/query payloads;
- TUI view models;
- pure text/cell rendering;
- terminal event handling.

Codex-friendly verification should be able to run:

- view-model tests;
- text snapshot tests;
- keyboard event reducer tests;
- live-feed projection tests;
- stale-data warning rendering tests.

Manual terminal verification may still be useful, but it must not be the only
way to test TUI behavior.

### 9. REST API Tests

Purpose: prove REST is a delivery adapter, not a second runtime or unsafe
remote control plane.

Required scenarios:

- endpoints live under `/v1`;
- mutating endpoints require idempotency keys;
- mutating endpoints route through shared command application;
- read endpoints reuse shared operation/fleet query payloads;
- event listing supports sequence-derived cursor resume;
- REST error payloads expose stable application error codes;
- live transport emits `LiveFeedEnvelope` payloads without schema drift;
- default binding is loopback;
- non-loopback exposure requires explicit unsafe-development flag or real auth
  configuration;
- CORS is disabled by default;
- mutating REST calls emit audit events.

### 10. CLI Contract Tests

Purpose: prove the scriptable surface is stable enough for automation.

Required scenarios:

- `run` returns a resolvable operation id;
- `status --json` exposes shared status DTO fields;
- `fleet --once --json` exposes shared fleet row DTO fields;
- `message` and `answer` return stable command responses;
- `watch --once --json` exposes event sequence and live-feed provenance;
- exit codes match [CLI-VISION.md](CLI-VISION.md).

### 11. Release And Documentation Claim Tests

Purpose: prevent public docs from outrunning implemented and verified behavior.

Required scenarios:

- public docs do not claim implemented runtime behavior without tests or
  runtime artifacts;
- CLI reference matches implemented commands and exit codes;
- REST reference matches implemented schemas and safety behavior;
- TUI guide claims only behavior covered by automated checks or manual notes;
- ADR implementation statuses match evidence;
- known limitations are documented before release.

### 12. End-to-End Local Harness

Purpose: prove the whole system works with deterministic local fakes.

The top-level harness should run an operation using:

- tempdir persistence;
- fake clock;
- scripted fake brain;
- scripted fake agent adapter;
- local event store;
- CLI or application command entrypoints;
- inspectable output artifacts.

Minimum workflows:

- happy path completion;
- blocking attention and answer;
- live chat injection;
- adapter failure;
- cancellation;
- resume after persisted events;
- fleet view over multiple operations.

The harness should be runnable by the same local tools used by coding agents.

The harness must produce inspectable evidence:

- stdout/stderr suitable for local agent review;
- persisted event/log artifacts in a temp directory;
- a machine-readable summary file for high-level workflows;
- stable failure messages that identify the failed rail.

## Architecture Fitness Functions

These tests protect direction, not just behavior.

Planned checks:

- core/domain modules do not import vendor adapters;
- delivery modules do not bypass application command/query contracts;
- TUI modules do not own canonical business state;
- adapters do not write canonical events directly except through approved
  application boundaries;
- public docs do not claim implemented runtime behavior without code/test
  evidence;
- ADRs include both `Decision Status` and `Implementation Status`;
- no hidden fallback path is introduced without an explicit migration note;
- new core moving parts update `MOVING-PARTS.md`, architecture, and an ADR.

Fitness checks are required whenever work adds:

- a new top-level package;
- a new delivery surface;
- a new adapter family;
- a new persistence authority;
- a new event schema family;
- a new public API.

## Agent-Executable Gates

The default full local verification command should eventually run:

```sh
uv run ruff check .
uv run mypy .
uv run pytest
```

Before a full implementation exists, agents should verify design changes by:

- checking links and artifact placement;
- searching for status overclaims;
- confirming substantial artifacts have red-team coverage;
- confirming backlog items exist for unresolved implementation-critical gaps.

Future implementation should add narrower commands for fast feedback:

- unit-only tests;
- contract-only tests;
- replay/persistence tests;
- delivery parity tests;
- TUI projection tests;
- end-to-end fake harness tests.

Gate tiers:

- `fast`: lint, type-check changed code, unit tests, architecture fitness tests;
- `focused`: relevant contract/replay/delivery/TUI tests for the touched area;
- `full`: all checks plus end-to-end fake harness workflows.

Local agents should prefer `fast` while iterating, then run `focused` and `full`
before claiming completion for behavior-affecting work.

## Product Coverage Matrix

Every product goal should eventually map to more than one test layer.

| Product area | Unit | Contract | Replay/state | Delivery parity | E2E fake harness |
| --- | --- | --- | --- | --- | --- |
| Operation loop | stop policy, budgets | brain/adapter contracts | operation event replay | status command/read parity | happy path, stop limits |
| Human attention | validation | command application | attention events replay | CLI/TUI/REST answer parity | block and resume |
| Live chat | retention rules | command/message contract | message and expiry events | CLI/TUI/REST message parity | chat affects next plan |
| Fleet | row derivation | read-model contract | projection lag labels | CLI/TUI/REST fleet parity | multi-operation fleet |
| Agent adapters | result mapping | adapter conformance | invocation/result events | session/log surfaces | fake adapter failure |
| TUI workbench | reducers/renderers | live-feed contract | stale warning payloads | shared query payloads | scripted TUI projection |
| CLI surface | formatting/errors | delivery contract | command events | CLI/REST/TUI DTO parity | CLI fake workflow |
| REST API | errors/config | REST surface contract | command/audit events | REST/CLI/TUI DTO parity | REST fake workflow |
| Release/docs | claim labels | ADR/status checks | artifact references | reference/schema parity | release claim audit |

## Coverage Expectations

Coverage is not only line coverage.

Each substantial feature should identify:

- lowest-level unit tests;
- relevant protocol contract tests;
- event/replay evidence if state changes;
- delivery parity coverage if exposed to users;
- top-level fake-harness coverage if it affects operation behavior.
- matching entries in [VERIFICATION-SCENARIOS.md](VERIFICATION-SCENARIOS.md).

## Definition of Testable

A design is testable enough to implement when:

- every external dependency has a fake or local deterministic substitute;
- canonical state transitions are observable in persisted events;
- delivery behavior can be checked without a real terminal or real LLM;
- replay can rebuild state;
- stale or partial data has a user-visible label;
- a coding agent can run the verification commands locally and inspect the
  resulting artifacts.

## Open Questions

- Which test runner mode should own async tests: `pytest-asyncio`, `anyio`, or
  both?
- Should the first event store be JSONL, SQLite, or a protocol with both fakes
  and file-backed implementation?
- What is the exact golden/snapshot strategy for TUI text rendering?
