# ADR 0203 Phase 1 Design Artifact: Canonical v2 Persistence Authority

Date: 2026-04-25

## Phase Boundary

This is Phase 1 only. It grounds ADR 0203 in current repository code and defines the required
implementation changes, tests, verification steps, risks, and next working point. It does not mark
ADR 0203 Accepted, Implemented, or Verified.

Out of scope:

- production code changes,
- ADR status promotion,
- changes to ADRs outside ADR 0203,
- removal of legacy snapshot support for explicitly legacy operation paths.

## Swarm Phase 1 Problem Definition

- Core problem: ADR 0203 needs a code-grounded implementation brief for making
  `operation_events` the canonical v2 persistence authority without overclaiming current
  implementation state.
- Scope: repository-local design artifact and ADR-context grounding for ADR 0203.
- Out of scope: implementation, ADR acceptance, status promotion, and broad legacy-store removal.
- Success criteria: every current-state claim below is tied to `rg`, `sed`, or `nl` evidence; all
  required code changes, tests, verification steps, risks, and the next reachable working point are
  named.
- Missing information / uncertainty: no user-owned ambiguity remains for Phase 1. The remaining
  unknowns are implementation findings for the next wave, especially whether checkpoint projection
  already contains every field needed by delivery/forensic read models after snapshot precedence is
  removed.

Swarm configuration snapshot:

- preset: Research / Discovery
- overrides: high grounding need; narrow route branching; high closure strictness
- rationale: the task is not to invent architecture, but to discriminate ADR claims against current
  code and stop at a bounded implementation plan.

## Evidence Commands

- `sed -n '1,260p' design/adr/0203-canonical-v2-persistence-authority.md`
- `rg -n "class OperatorServiceV2|FileOperationStore|save_operation\(|load_operation\(|list_operations\(|OperationEventStore|OperationCheckpointStore|EventSourcedReplayService|DriveService|CanonicalPersistenceMode|operation_events|operation_checkpoints" src tests -g '*.py'`
- `nl -ba src/agent_operator/application/operator_service_v2.py | sed -n '30,175p'`
- `nl -ba src/agent_operator/application/drive/drive_service.py | sed -n '58,245p'`
- `nl -ba src/agent_operator/application/drive/drive_service.py | sed -n '245,430p'`
- `nl -ba src/agent_operator/application/event_sourcing/event_sourced_replay.py | sed -n '40,125p'`
- `nl -ba src/agent_operator/application/event_sourcing/event_sourced_commands.py | sed -n '35,105p'`
- `nl -ba src/agent_operator/application/queries/operation_resolution.py | sed -n '24,105p'`
- `nl -ba src/agent_operator/application/queries/operation_status_queries.py | sed -n '70,143p'`
- `nl -ba src/agent_operator/mcp/service.py | sed -n '88,115p'`
- `nl -ba src/agent_operator/cli/workflows/views.py | sed -n '442,468p'`
- `nl -ba src/agent_operator/cli/workflows/views.py | sed -n '648,666p'`
- `rg -n "event-sourced|event sourced|operation_events|operation_checkpoints|v2.*absent|runs.*absent|load_event_sourced|list_canonical_operation_states|FileOperationStore\.save_operation|save_operation\(\)" tests/test_cli.py tests/test_operator_service_v2.py tests/test_drive_service_v2.py tests/test_event_sourced_replay.py tests/test_application_structure.py tests/test_client.py tests/test_operation_entrypoints.py`
- `nl -ba tests/test_application_structure.py | sed -n '80,125p'`
- `nl -ba tests/test_event_sourced_replay.py | sed -n '120,200p'`
- `nl -ba tests/test_operator_service_v2.py | sed -n '195,235p'`

## Current Repository Evidence

- `implemented`: `OperatorServiceV2` is an event-sourced facade. Its constructor depends on
  `DriveService` and `OperationEventStore`, not `FileOperationStore`
  (`src/agent_operator/application/operator_service_v2.py:40`,
  `src/agent_operator/application/operator_service_v2.py:46`,
  `src/agent_operator/application/operator_service_v2.py:49`,
  `src/agent_operator/application/operator_service_v2.py:50`).
- `implemented`: v2 creation appends `operation.created` and optional `operation.ticket_linked`
  domain events at expected sequence `0`, then drives the operation
  (`src/agent_operator/application/operator_service_v2.py:90`,
  `src/agent_operator/application/operator_service_v2.py:114`,
  `src/agent_operator/application/operator_service_v2.py:121`,
  `src/agent_operator/application/operator_service_v2.py:130`,
  `src/agent_operator/application/operator_service_v2.py:132`).
- `implemented`: `OperatorServiceV2.cancel()` requires `EventSourcedCommandApplicationService` and
  delegates command application to it
  (`src/agent_operator/application/operator_service_v2.py:152`,
  `src/agent_operator/application/operator_service_v2.py:160`,
  `src/agent_operator/application/operator_service_v2.py:175`).
- `implemented`: `DriveService.drive()` loads aggregate state through replay and appends domain
  events for timeout, live events, reconciliation, deferred executor events, pause materialization,
  and budget exhaustion
  (`src/agent_operator/application/drive/drive_service.py:109`,
  `src/agent_operator/application/drive/drive_service.py:136`,
  `src/agent_operator/application/drive/drive_service.py:153`,
  `src/agent_operator/application/drive/drive_service.py:166`,
  `src/agent_operator/application/drive/drive_service.py:175`,
  `src/agent_operator/application/drive/drive_service.py:200`,
  `src/agent_operator/application/drive/drive_service.py:235`).
- `partial`: `DriveService` checkpoints after terminal or iteration events through
  `OperationCheckpointStore`, and `_save_checkpoint()` records the last applied sequence, but the
  current checkpoint payload contains only `status` and `operation_id`; full replay/checkpoint
  read-model parity still depends on event replay and projector coverage
  (`src/agent_operator/application/drive/drive_service.py:140`,
  `src/agent_operator/application/drive/drive_service.py:217`,
  `src/agent_operator/application/drive/drive_service.py:239`,
  `src/agent_operator/application/drive/drive_service.py:399`,
  `src/agent_operator/application/drive/drive_service.py:403`,
  `src/agent_operator/application/drive/drive_service.py:406`,
  `src/agent_operator/application/drive/drive_service.py:410`).
- `implemented`: `DriveService._load_aggregate()` uses replay state and suffix events to rebuild
  aggregate state from checkpoint/event truth
  (`src/agent_operator/application/drive/drive_service.py:252`,
  `src/agent_operator/application/drive/drive_service.py:260`,
  `src/agent_operator/application/drive/drive_service.py:267`,
  `src/agent_operator/application/drive/drive_service.py:269`,
  `src/agent_operator/application/drive/drive_service.py:270`).
- `implemented`: `EventSourcedReplayService.load()` reads the latest checkpoint, compares its
  sequence against the event stream tail, rejects checkpoint-ahead-of-stream, loads suffix events,
  and projects the checkpoint
  (`src/agent_operator/application/event_sourcing/event_sourced_replay.py:67`,
  `src/agent_operator/application/event_sourcing/event_sourced_replay.py:69`,
  `src/agent_operator/application/event_sourcing/event_sourced_replay.py:71`,
  `src/agent_operator/application/event_sourcing/event_sourced_replay.py:73`,
  `src/agent_operator/application/event_sourcing/event_sourced_replay.py:79`,
  `src/agent_operator/application/event_sourcing/event_sourced_replay.py:83`).
- `implemented`: `EventSourcedCommandApplicationService.apply()` loads replay state, appends
  command outcome events at the replayed sequence, advances replay state, and materializes a
  checkpoint
  (`src/agent_operator/application/event_sourcing/event_sourced_commands.py:46`,
  `src/agent_operator/application/event_sourcing/event_sourced_commands.py:86`,
  `src/agent_operator/application/event_sourcing/event_sourced_commands.py:88`,
  `src/agent_operator/application/event_sourcing/event_sourced_commands.py:93`,
  `src/agent_operator/application/event_sourcing/event_sourced_commands.py:94`).
- `partial`: operation resolution can include event streams, but legacy snapshots take precedence.
  `load_canonical_operation_state()` returns `store.load_operation()` before event-sourced state;
  `list_canonical_operation_states()` enumerates `store.list_operations()` first, then adds unseen
  event streams
  (`src/agent_operator/application/queries/operation_resolution.py:72`,
  `src/agent_operator/application/queries/operation_resolution.py:73`,
  `src/agent_operator/application/queries/operation_resolution.py:76`,
  `src/agent_operator/application/queries/operation_resolution.py:78`,
  `src/agent_operator/application/queries/operation_resolution.py:81`,
  `src/agent_operator/application/queries/operation_resolution.py:87`).
- `partial`: status can replay v2 state only when both legacy operation and legacy outcome are
  absent, so stale snapshots can still dominate status for the same id
  (`src/agent_operator/application/queries/operation_status_queries.py:97`,
  `src/agent_operator/application/queries/operation_status_queries.py:101`,
  `src/agent_operator/application/queries/operation_status_queries.py:102`,
  `src/agent_operator/application/queries/operation_status_queries.py:103`,
  `src/agent_operator/application/queries/operation_status_queries.py:104`,
  `src/agent_operator/application/queries/operation_status_queries.py:123`,
  `src/agent_operator/application/queries/operation_status_queries.py:127`,
  `src/agent_operator/application/queries/operation_status_queries.py:137`).
- `planned`: MCP list is snapshot-only because it enumerates `store.list_operations()` and then
  loads each operation from that same store
  (`src/agent_operator/mcp/service.py:94`,
  `src/agent_operator/mcp/service.py:99`,
  `src/agent_operator/mcp/service.py:100`,
  `src/agent_operator/mcp/service.py:102`,
  `src/agent_operator/mcp/service.py:103`).
- `planned`: some delivery interactions still require snapshot state. `ask_async()` loads directly
  from `build_store(settings).load_operation()` and exits if absent; the TUI converse path does the
  same before building an operation prompt
  (`src/agent_operator/cli/workflows/views.py:442`,
  `src/agent_operator/cli/workflows/views.py:443`,
  `src/agent_operator/cli/workflows/views.py:444`,
  `src/agent_operator/cli/workflows/views.py:648`,
  `src/agent_operator/cli/workflows/views.py:649`,
  `src/agent_operator/cli/workflows/views.py:650`).
- `partial`: current static structure tests are ADR 0144-oriented and guard legacy
  `operation_drive.py` save boundaries; they do not yet encode the full ADR 0203 v2 persistence
  authority contract
  (`tests/test_application_structure.py:84`,
  `tests/test_application_structure.py:90`,
  `tests/test_application_structure.py:102`,
  `tests/test_application_structure.py:113`,
  `tests/test_application_structure.py:115`).
- `verified-by-test`: existing tests cover selected v2 event-sourced behavior. `OperatorServiceV2`
  birth events are asserted in `tests/test_operator_service_v2.py:195` through
  `tests/test_operator_service_v2.py:205`, and checkpoint-ahead-of-stream rejection is asserted in
  `tests/test_event_sourced_replay.py:120` through `tests/test_event_sourced_replay.py:144`.

## Required Implementation Changes

1. Introduce an event-first operation read authority for v2.
   - Centralize stream existence, replay loading, checkpoint projection, and legacy fallback in one
     application query service.
   - Authority rule: if `operation_events/<id>.jsonl` exists and replay has any canonical content,
     v2 replay wins over `.operator/runs/<id>.operation.json`.
   - Legacy fallback remains only for ids with no v2 stream.

2. Repair checkpoint materialization so derived checkpoints are useful replay accelerators, not
   lossy status crumbs.
   - `DriveService._save_checkpoint()` should persist a checkpoint payload that can round-trip the
     fields needed by v2 drive/query/read-model consumers, or delegate checkpoint materialization to
     the existing replay/projector authority.
   - The checkpoint must remain derived; deleting it must not change canonical status/list/inspect
     output when the event stream is intact.

3. Convert public read surfaces to the event-first service.
   - Update `OperationResolutionService.load_canonical_operation_state()` and
     `list_canonical_operation_states()` so v2 streams are not second-class when a stale snapshot
     exists.
   - Update `OperationStatusQueryService.build_status_payload()` so v2 state wins over legacy
     operation/outcome for the same id.
   - Update list/agenda/inspect/detail call sites that currently treat `list_operations()` as the
     complete candidate set.
   - Update `OperatorMcpService.list_operations()` to enumerate the merged v2-plus-legacy set.

4. Repair or explicitly bound snapshot-only delivery paths.
   - Convert `ask_async()` and TUI converse operation prompt loading to the event-first read
     service.
   - Audit forensic/session/log/detail paths that still call `build_store(settings).load_operation()`
     directly. Convert paths that only need operation read-model fields; mark truly legacy-only
     paths with explicit error text and tests.

5. Add ADR 0203 static guardrails.
   - AST guard: v2 mutation paths must not call `save_operation()`.
   - AST guard: v2 read/control/list/status/inspect/MCP-list paths must not rely only on
     `FileOperationStore.list_operations()` or `load_operation()` when an event stream may exist.
   - Guard target modules should include `operator_service_v2.py`, `drive_service.py`,
     `event_sourced_commands.py`, `operation_resolution.py`, `operation_status_queries.py`, MCP
     service, and CLI view/detail/workflow modules touched by this wave.

6. Tighten read-model authority metadata.
   - Ensure v2-derived status/list/inspect JSON identifies event replay/checkpoint projection as
     its source, not `.operator/runs`.
   - Keep `OperationStateViewService` outputs as read models, not persisted source of truth.

## Required Tests

- Unit: `OperatorServiceV2.run()` appends birth events and creates no `.operator/runs` snapshot.
  Mutation caught: replacing event append with snapshot save.
- Unit: `OperatorServiceV2.cancel()` appends command/cancel events through
  `EventSourcedCommandApplicationService` and materializes a checkpoint. Mutation caught: direct
  legacy status mutation.
- Unit: `DriveService.drive()` replay-loads, appends, applies, and checkpoints without calling
  `FileOperationStore.save_operation()`. Mutation caught: restoring snapshot writes in v2 drive.
- Unit: replay rejects checkpoint-ahead-of-stream. Mutation caught: removing the sequence guard.
- Unit: deleting `operation_checkpoints/<id>.json` and replaying from `operation_events/<id>.jsonl`
  yields the same status/read model. Mutation caught: treating checkpoint as canonical truth.
- Query: when both event stream and stale snapshot exist for one id, resolution/status/inspect/list
  use v2 replay. Mutation caught: snapshot-first precedence.
- Query: when `.operator/runs` is absent, list/status/inspect still find event-only v2 operations.
  Mutation caught: treating `list_operations()` as complete.
- MCP: `list_operations()` includes event-only v2 operations. Mutation caught: snapshot-only MCP
  enumeration.
- Delivery: `ask_async()` and TUI converse can load an event-only v2 operation or produce an
  explicit legacy-only limitation where conversion is intentionally deferred.
- Static: no v2 mutation path calls `save_operation()`.
- Static: no ADR 0203 read surface relies only on `list_operations()` as the operation universe.

## Verification Steps

1. Run focused unit/query tests for event sourcing, v2 service, drive service, operation resolution,
   status queries, MCP service, and CLI view/detail workflows.
2. Run ADR 0203 static guardrail tests.
3. Run `uv run pytest -q`.
4. Run a local CLI smoke with temporary `OPERATOR_DATA_DIR`:
   - create or seed a v2 operation that writes only `operation_events` and
     `operation_checkpoints`,
   - avoid or remove `.operator/runs`,
   - run list/status/inspect,
   - delete the checkpoint and confirm replay from events reproduces the same status.
5. Inspect generated `.operator/operation_events/<id>.jsonl` and
   `.operator/operation_checkpoints/<id>.json` to confirm checkpoint sequence is behind or equal to
   event stream sequence.

## Risks

- Stale snapshot precedence can preserve split-brain public behavior even after v2 write paths are
  event-sourced.
- Centralizing event-first reads incorrectly could create a second authority if the service stores
  independent state instead of projecting replay/checkpoint truth.
- Some delivery/forensic views may depend on fields not yet represented by domain events or
  checkpoint projection.
- The current drive checkpoint payload is intentionally small but too lossy to serve as a complete
  replay accelerator for every v2 read-model surface; relying on it without suffix replay/projector
  coverage would overclaim checkpoint authority.
- Broad replacement of store reads can break legacy operations unless stream-existence gating is
  explicit.
- Static AST tests can miss dynamic calls; pair them with event-only integration tests.
- Checkpoint deletion tests may expose projector gaps that require adding missing event projection
  support before status/list parity can be claimed.

## Bounded Implementation Plan For Next Wave

Blast radius: L0 local reversible code/test changes until commit/push. Contract impact is internal
application/query behavior plus CLI/MCP observable behavior; downstream consumers are CLI commands,
TUI workflows, MCP service methods, SDK/client list/status helpers, and tests.

Next working point: a green repository where v2 create/cancel/drive, list, status, inspect, and MCP
list are canonical-event-first; legacy snapshot-only operations still work; and new ADR 0203 static
guardrails plus focused query/CLI/MCP tests pass.

Sequence:

1. Add a small event-first operation read service around event stream existence, replay load, and
   `OperationStateViewService` projection.
2. Repair or delegate v2 checkpoint materialization so checkpoint payloads remain derived but are
   not lossy for consumers that reload from checkpoint-plus-suffix.
3. Convert resolution/status/list/inspect and MCP list to use that service, preserving legacy
   fallback only when no v2 stream exists.
4. Convert `ask_async()` and TUI converse operation prompt loading, or add explicit tested
   legacy-only limitation text for any path deferred.
5. Add static ADR 0203 guardrails with named mutations in test docstrings.
6. Add event-only and stale-snapshot-precedence integration tests.
7. Run focused tests, then `uv run pytest -q`, then the temporary-data-dir CLI smoke.

Reachability statement: this is reachable without parallel untested changes because the first slice
can be limited to a read-service addition plus query/MCP/list/status consumers, with legacy fallback
preserved and no persisted format migration.

## Phase 2 Implementation Brief

Status: `Partial`. This implementation wave closes the event-first read precedence slice for
resolution, status, MCP list, SDK list, and ADR 0203 static guardrails. It does not close the full
ADR because converse/detail/control paths still have direct legacy snapshot reads.

Implemented evidence:

- `OperationResolutionService.load_canonical_operation_state()` now attempts event-sourced replay
  before `store.load_operation()`, and `list_canonical_operation_states()` enumerates event streams
  before legacy summaries (`src/agent_operator/application/queries/operation_resolution.py:72`,
  `src/agent_operator/application/queries/operation_resolution.py:73`,
  `src/agent_operator/application/queries/operation_resolution.py:76`,
  `src/agent_operator/application/queries/operation_resolution.py:84`,
  `src/agent_operator/application/queries/operation_resolution.py:90`).
- `OperationStatusQueryService.build_status_payload()` now loads event-sourced state before legacy
  operation snapshots (`src/agent_operator/application/queries/operation_status_queries.py:101`,
  `src/agent_operator/application/queries/operation_status_queries.py:103`,
  `src/agent_operator/application/queries/operation_status_queries.py:104`).
- `OperatorMcpService.list_operations()` now lists through `OperationResolutionService` with
  `build_replay_service()` and the `operation_events` root instead of treating
  `store.list_operations()` as complete (`src/agent_operator/mcp/service.py:101`,
  `src/agent_operator/mcp/service.py:103`,
  `src/agent_operator/mcp/service.py:104`,
  `src/agent_operator/mcp/service.py:108`).
- `OperatorClient.list_operations()` now builds summaries from
  `list_canonical_operation_states()` rather than direct store summaries
  (`src/agent_operator/client.py:175`, `src/agent_operator/client.py:177`,
  `src/agent_operator/client.py:199`).
- Static guardrails now reject `save_operation()` in v2 mutation paths and check the converted read
  surfaces for event-first resolution references (`tests/test_application_structure.py:115`,
  `tests/test_application_structure.py:132`).
- Regression coverage now includes stale-snapshot status precedence, event-only MCP listing, and
  event-only SDK listing (`tests/test_operation_status_queries.py:236`,
  `tests/test_mcp_server.py:469`, `tests/test_client.py:227`).

Verification evidence:

- `UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/test_operation_status_queries.py tests/test_mcp_server.py tests/test_client.py tests/test_application_structure.py -q`
  passed: 45 passed.
- `UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/test_cli.py::test_resolution_accepts_event_sourced_operation_id tests/test_cli.py::test_resolution_last_accepts_event_sourced_operation_without_runs_dir tests/test_client.py::test_operator_client_lists_event_only_v2_operation tests/test_mcp_server.py::test_operator_mcp_service_lists_event_only_v2_operation tests/test_operation_status_queries.py::test_status_payload_prefers_event_sourced_replay_over_stale_snapshot tests/test_application_structure.py::test_adr_0203_v2_mutation_paths_do_not_save_legacy_snapshots tests/test_application_structure.py::test_adr_0203_canonical_read_surfaces_use_event_first_resolution -q`
  passed: 7 passed.
- `UV_CACHE_DIR=/tmp/uv-cache uv run pytest` passed: 956 passed, 11 skipped.

Remaining evidence gaps:

- `src/agent_operator/cli/workflows/converse.py` still has snapshot-only operation loading and
  operation reference resolution paths.
- Some detail/control/report paths still call legacy `load_operation()` directly after resolving an
  operation id.
- The checkpoint-deletion parity smoke and full temporary-data-dir CLI smoke from the phase-1 plan
  were not run in this wave.
