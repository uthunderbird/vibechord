# ADR 0203: Canonical v2 Persistence Authority

- Date: 2026-04-23

## Decision Status

Accepted

## Implementation Status

Verified

Implementation status on 2026-04-25:

- `implemented`: `OperatorServiceV2` creates operations by appending `operation.created` domain
  events through `OperationEventStore` and drives through `DriveService`.
- `implemented`: `OperatorServiceV2.cancel()` delegates cancellation to
  `EventSourcedCommandApplicationService` when that service is wired.
- `implemented`: `DriveService` reloads aggregate state from replay, appends new domain events, and
  saves derived checkpoints through `OperationCheckpointStore`.
- `implemented`: `EventSourcedReplayService` rejects checkpoints whose sequence is ahead of the
  event stream.
- `implemented`: canonical resolution now checks v2 event-sourced state before legacy snapshots for
  exact loads and merged operation lists.
- `implemented`: status payload construction now prefers v2 replay over stale legacy snapshots for
  the same operation id.
- `implemented`: MCP list and SDK list use the canonical merged v2-plus-legacy operation state
  service.
- `implemented`: converse operation prompts, converse fleet prompts, TUI converse operation/fleet
  prompts, detail projections, transcript/session detail lookups, and control-runtime operation
  metadata restoration now load operation state through canonical resolution helpers rather than
  direct legacy snapshot reads.
- `implemented`: canonical operation reference resolution preserves profile-name matching through
  the merged v2-plus-legacy state list.
- `verified`: targeted ADR 0203 regression tests and the full `uv run pytest` suite passed on
  2026-04-25; this was reconfirmed in the current ADR 0203 work wave with `250 passed` targeted
  tests and `978 passed, 11 skipped` for the full suite.
- `verified`: the 2026-04-25 current-session ADR 0203 work wave produced
  `../internal/adr-0203-session-design-artifact-2026-04-25.md`, reran the targeted ADR 0203
  regression set with `250 passed`, and reran the full suite with `978 passed, 11 skipped`.
- `verified`: the remaining CLI smoke gap is now covered by
  `tests/test_cli.py::test_v2_cli_smoke_creates_observes_and_cancels_without_runs_dir`, which
  drives `operator run --v2 --json`, `operator status --json`, and `operator cancel --yes --json`
  against canonical `operation_events`/`operation_checkpoints` state while asserting that no
  legacy `runs/<operation_id>.operation.json` or `.outcome.json` snapshot becomes authoritative.
- `verified`: the current 2026-04-26 verification wave passed the focused ADR 0203 CLI slice with
  `uv run pytest tests/test_cli.py -k "v2_cli_smoke_creates_observes_and_cancels_without_runs_dir or resolution_last_accepts_event_sourced_operation_without_runs_dir or attention_command_reads_event_sourced_operation_without_runs_dir or list_json_emits_event_sourced_objects_without_runs_dir" -q`
  (`4 passed`) and passed the full repository suite with `uv run pytest`
  (`1004 passed, 11 skipped`).

## ADR 0203 Closure Iteration Brief

Phase 1 produced the grounded completion artifact
`../internal/adr-0203-completion-design-artifact-2026-04-25.md`, which scoped completion to the
remaining converse/detail/control read-authority leaks and explicitly selected `Implemented`, not
`Verified`, unless full smoke evidence existed.

The current ADR 0203-only work wave also produced
`../internal/adr-0203-current-grounded-design-2026-04-25.md`, which rechecked the current
repository state before execution and found no new ADR 0203 production-code change required beyond
verification and preserving the read-time status overlay immutability guard needed for the full
suite.

The current session also produced
`../internal/adr-0203-session-design-artifact-2026-04-25.md`, which reran the DESIGN phase using
swarm-mode, scoped required production and test changes to none under current repository evidence,
and made the IMPLEMENT & VERIFY phase verification-gated.

Grep/read citations for `Decision Status: Accepted`:

- Read citation: this ADR's Required Properties define the accepted authority contract: v2 mutation,
  control, list/status/inspect, checkpoint sequence, and read-model authority rules in this file's
  `Required Properties` section.
- Current-session read citation:
  `nl -ba src/agent_operator/application/operator_service_v2.py | sed -n '40,175p'` showed
  `OperatorServiceV2` is constructed with `DriveService` and `OperationEventStore`, appends
  `operation.created` through `_event_store.append(...)`, and requires
  `EventSourcedCommandApplicationService` for cancellation at
  `src/agent_operator/application/operator_service_v2.py:46`,
  `src/agent_operator/application/operator_service_v2.py:130`, and
  `src/agent_operator/application/operator_service_v2.py:160`.
- Current-session read citation:
  `nl -ba src/agent_operator/application/event_sourcing/event_sourced_replay.py | sed -n '45,120p'`
  showed `EventSourcedReplayService.load()` compares checkpoint sequence to event-stream sequence
  and rejects ahead-of-stream checkpoints at
  `src/agent_operator/application/event_sourcing/event_sourced_replay.py:67` and
  `src/agent_operator/application/event_sourcing/event_sourced_replay.py:73`.
- Grep citation: `rg -n "load_required_canonical_operation_state_async|load_canonical_operation_state_async|list_canonical_operation_states_async|resolve_operation_id_async|profile_matches" src/agent_operator/application/queries/operation_resolution.py src/agent_operator/cli/helpers/resolution.py src/agent_operator/cli/workflows/converse.py src/agent_operator/cli/workflows/views.py src/agent_operator/cli/commands/operation_detail.py src/agent_operator/cli/workflows/control_runtime.py`
  showed canonical helper use in:
  `src/agent_operator/cli/helpers/resolution.py:41`,
  `src/agent_operator/cli/helpers/resolution.py:47`,
  `src/agent_operator/cli/helpers/resolution.py:54`,
  `src/agent_operator/cli/workflows/converse.py:401`,
  `src/agent_operator/cli/workflows/converse.py:419`,
  `src/agent_operator/cli/workflows/converse.py:426`,
  `src/agent_operator/cli/workflows/views.py:443`,
  `src/agent_operator/cli/workflows/views.py:649`,
  `src/agent_operator/cli/workflows/views.py:749`,
  `src/agent_operator/cli/commands/operation_detail.py:248`,
  `src/agent_operator/cli/commands/operation_detail.py:296`,
  `src/agent_operator/cli/commands/operation_detail.py:353`,
  `src/agent_operator/cli/commands/operation_detail.py:398`,
  `src/agent_operator/cli/commands/operation_detail.py:444`,
  `src/agent_operator/cli/commands/operation_detail.py:564`,
  `src/agent_operator/cli/commands/operation_detail.py:698`, and
  `src/agent_operator/cli/workflows/control_runtime.py:444`.
- Grep citation: `rg -n "build_store\\(settings\\)\\.load_operation|store\\.list_operations\\(|store\\.load_operation\\(" src/agent_operator/cli/workflows/converse.py src/agent_operator/cli/workflows/views.py src/agent_operator/cli/commands/operation_detail.py src/agent_operator/cli/workflows/control_runtime.py`
  returned no matches for the named ADR 0203 converse/detail/control files after implementation.

Grep/read citations for `Implementation Status: Implemented`:

- Read citation: `src/agent_operator/application/queries/operation_resolution.py` exposes
  `OperationResolutionService.load_canonical_operation_state()` and
  `list_canonical_operation_states()` as the merged event-sourced-plus-legacy read authority.
- Current-session read citation:
  `nl -ba src/agent_operator/application/queries/operation_resolution.py | sed -n '95,140p'`
  showed event-sourced state is attempted before `store.load_operation()` at
  `src/agent_operator/application/queries/operation_resolution.py:105`, and event-sourced
  operation ids are enumerated before legacy store summaries at
  `src/agent_operator/application/queries/operation_resolution.py:114`.
- Current-session read citation:
  `nl -ba tests/test_application_structure.py | sed -n '105,165p'` showed static ADR 0203 guards
  for v2 mutation paths and canonical read surfaces at
  `tests/test_application_structure.py:113` and `tests/test_application_structure.py:131`.
- Grep citation: `rg -n "event_sourced_operation_without_runs_dir|fleet_includes_event_sourced|attention_command_reads_event_sourced|_seed_event_sourced_checkpoint|load_canonical_operation_state_async" tests/test_cli.py tests/test_control_workflows.py`
  showed event-sourced-only regressions in `tests/test_cli.py:850`, `tests/test_cli.py:885`,
  `tests/test_cli.py:916`, `tests/test_cli.py:955`, and the control-runtime canonical-loader test
  seam in `tests/test_control_workflows.py:201`.
- Verification citation: `uv run pytest tests/test_cli.py tests/test_control_workflows.py -q`
  passed with `211 passed`.
- Verification citation: targeted `uv run ruff check` on the changed Python modules and tests passed
  with `All checks passed!`.
- Verification citation: `uv run pytest` passed with `959 passed, 11 skipped`.
- Current verification citation: `uv run pytest tests/test_application_structure.py tests/test_event_sourced_replay.py tests/test_operation_status_queries.py tests/test_cli.py tests/test_control_workflows.py -q`
  passed with `250 passed`.
- Current verification citation: `uv run pytest` passed with `978 passed, 11 skipped`.
- Current-session verification citation:
  `uv run pytest tests/test_application_structure.py tests/test_event_sourced_replay.py tests/test_operation_status_queries.py tests/test_cli.py tests/test_control_workflows.py -q`
  passed with `250 passed`.
- Current-session verification citation: `uv run pytest` passed with `978 passed, 11 skipped`.
- Status-bound citation: `tests/test_cli.py::test_v2_cli_smoke_creates_observes_and_cancels_without_runs_dir`
  now closes the previously named create/observe/terminate CLI smoke gap, and the current
  repository-wide `uv run pytest` pass (`1004 passed, 11 skipped`) supports
  `Implementation Status: Verified`.

## Context

The v2 architecture intends `operation_events` to be the canonical operation truth and
`operation_checkpoints` to be a derived replay accelerator. The repository still has many paths
where `FileOperationStore` and `.operator/runs` remain authoritative for reads, mutation, history,
or delivery behavior.

This creates split truth:

- v2 operations can exist only in `operation_events`
- legacy commands can fail because they look only in `.operator/runs`
- status/inspect may need event-sourced fallback logic
- tests can pass while public surfaces still depend on snapshots

The operator cannot be fully canonical v2 until persistence authority is singular and explicit.

## Decision

For new v2 operations, canonical operation truth is:

1. `.operator/operation_events/<operation_id>.jsonl`
2. `.operator/operation_checkpoints/<operation_id>.json` as derived replay cache
3. explicit read models projected from the event stream

`.operator/runs` and `FileOperationStore` are not authoritative for v2 operation state. They may
exist only as legacy migration input, forensic artifacts, or compatibility fixtures until removed.

## Required Properties

- No v2 mutation path calls `FileOperationStore.save_operation()`.
- No v2 control path requires `FileOperationStore.load_operation()`.
- No v2 list/status/inspect path treats `FileOperationStore.list_operations()` as complete.
- Checkpoints are always behind or equal to event stream sequence, never ahead.
- Read models identify their authority and refresh path.

## Verification Plan

- Static tests reject new v2 mutation callers of `save_operation()`.
- v2 status/list/inspect work when `.operator/runs` is absent.
- replay from `operation_events` alone reconstructs canonical state.
- checkpoint deletion followed by replay yields the same status/read-model output.
- full CLI smoke creates, observes, and terminates a v2 operation without `.operator/runs`.

## Related

- ADR 0069
- ADR 0144
- ADR 0193
- ADR 0194
