# ADR 0203 Session Design Artifact — 2026-04-25

## Phase Boundary

This is the DESIGN phase artifact for the current ADR 0203-only work wave. It records the
swarm-mode route, repository-grounded evidence, required changes, verification plan, and risks.
It does not mark ADR 0203 newly Accepted or Implemented during this design phase.

## Swarm Phase 1 — Problem Definition

- Core problem: determine whether ADR 0203's canonical v2 persistence authority is complete in the
  current repository state and define the smallest safe implementation/verification wave.
- Scope: ADR 0203, local source/tests, local grep/read evidence, and local pytest evidence.
- Out of scope: ADRs outside 0203, broad legacy removal, unrelated dirty worktree changes, and live
  external agent runs unless explicitly needed for ADR 0203 verification.
- Success criteria: concrete required changes are stated, required tests are named, verification
  commands are explicit, closure risks are bounded, and ADR status is not strengthened beyond the
  evidence.
- Uncertainties: the worktree has unrelated uncommitted changes, so full-suite evidence may be
  affected by changes outside this ADR 0203 wave.

Swarm configuration snapshot:

- preset: Diagnosis / Engineering
- overrides: high grounding need, narrow branching, high closure strictness
- evidence boundary: local repository files, grep/read citations, and local test output only

## Swarm Phase 2 — Expert Assembly

- Barbara Liskov (Critic): checks operation-state contracts and authority boundaries.
- Leslie Lamport (Critic): checks event ordering, replay, and checkpoint sequence safety.
- Martin Fowler (Balanced · Synthesizer): keeps the service shape small and migration-aware.
- Kelsey Hightower (Evangelist · Implementer): keeps the delivery-surface path practical.
- Nancy Leveson (Critic · Completer-Finisher): checks closure evidence and overclaiming risk.

## Swarm Phase 3 — Iteration Brief

### Iteration 1 — Option A Round-Robin

Open items scan: no aged or blocked user-owned item. The active uncertainty is whether this work
wave needs code/test changes or only refreshed evidence and ADR 0203 documentation.

Moderator reasoning: the unresolved gap is status truth. Round-robin is appropriate because ADR
0203 combines event-sourced mutation authority, canonical read authority, checkpoint safety, and
closure discipline.

- Liskov: public reads must enter through a canonical operation-state contract. Direct legacy reads
  are acceptable only behind that contract as fallback.
- Lamport: replay must reject checkpoints that are ahead of event streams; otherwise checkpoints
  become an unsound authority.
- Fowler: if `OperationResolutionService` already handles event-first merged reads, adding another
  persistence authority would create needless duplicate concepts.
- Hightower: delivery surfaces matter because users notice list/status/detail failures before they
  notice storage design purity.
- Leveson: `Verified` is not justified unless the full live CLI smoke in ADR 0203's verification
  plan is actually run and cited.

Route update:

- Route: preserve the existing event-first resolution/service design and verify it.
- Prior state: open.
- New state: selected.
- Justification: local reads show the repository already has the intended authority boundary.

### Iteration 2 — Option E Executor Grounding

Executor questions:

- Do v2 mutation paths avoid legacy snapshot writes?
- Do canonical read paths prefer event-sourced state before legacy snapshots?
- Are checkpoint sequence constraints implemented?
- Do tests guard the contract?

Scope: `OperatorServiceV2`, `EventSourcedReplayService`, `OperationResolutionService`, ADR 0203
static guards, and the named targeted pytest modules.

Tool-backed findings:

- `OperatorServiceV2.run()` appends `operation.created` through `_event_store.append(...)` and then
  drives the operation, with no `FileOperationStore` dependency in the constructor
  (`src/agent_operator/application/operator_service_v2.py:46`, `src/agent_operator/application/operator_service_v2.py:130`).
- `OperatorServiceV2.cancel()` requires `EventSourcedCommandApplicationService`, so cancel is not a
  legacy snapshot mutation path (`src/agent_operator/application/operator_service_v2.py:152`,
  `src/agent_operator/application/operator_service_v2.py:160`).
- `EventSourcedReplayService.load()` compares checkpoint sequence with the event stream sequence and
  rejects ahead-of-stream checkpoints (`src/agent_operator/application/event_sourcing/event_sourced_replay.py:67`,
  `src/agent_operator/application/event_sourcing/event_sourced_replay.py:73`).
- `OperationResolutionService.load_canonical_operation_state()` attempts event-sourced state before
  `store.load_operation()` (`src/agent_operator/application/queries/operation_resolution.py:105`).
- `OperationResolutionService.list_canonical_operation_states()` enumerates event-sourced operation
  ids first and only then adds unseen legacy states (`src/agent_operator/application/queries/operation_resolution.py:114`).
- Static ADR 0203 guards reject `save_operation()` in v2 mutation paths and assert event-first read
  references (`tests/test_application_structure.py:113`, `tests/test_application_structure.py:131`).

Route update:

- Route: implementation wave.
- Prior state: selected.
- New state: verification-gated.
- Justification: current evidence does not require production-code changes; the remaining work is
  verification and ADR 0203 evidence refresh.

### Iteration 3 — Option H Finalization

Pre-mortem:

- Liskov: wrong if a public read surface still bypasses canonical resolution; mitigate with grep
  citations in the ADR update.
- Lamport: wrong if replay tests do not cover checkpoint-ahead failure; mitigate with targeted
  `tests/test_event_sourced_replay.py`.
- Fowler: wrong if this wave creates another abstraction; mitigation is no production-code change.
- Hightower: wrong if delivery regressions are not run; mitigate with targeted CLI/control tests.
- Leveson: wrong if `Verified` is claimed without live smoke; mitigation is keep status at
  `Implemented` unless the smoke runs.

Readiness check: enough local evidence exists to execute the implementation/verification phase.
The stable route is to make no production/test changes, run targeted and full pytest, then update
ADR 0203 evidence only if verification supports the current status.

## Required Code Changes

No production code changes are required by the current repository evidence.

## Required Test Changes

No test changes are required by the current repository evidence. Existing required tests are:

- `tests/test_application_structure.py`: static v2 mutation and read-authority guards.
- `tests/test_event_sourced_replay.py`: checkpoint/replay safety.
- `tests/test_operation_status_queries.py`: event-sourced status precedence.
- `tests/test_cli.py`: event-sourced-only CLI read-surface regressions.
- `tests/test_control_workflows.py`: canonical control-runtime read seam.

## Verification Steps

1. Re-run ADR 0203 grep/read citations for status evidence.
2. Run targeted tests:
   `uv run pytest tests/test_application_structure.py tests/test_event_sourced_replay.py tests/test_operation_status_queries.py tests/test_cli.py tests/test_control_workflows.py -q`.
3. Run full suite: `uv run pytest`.
4. Update only ADR 0203 with current evidence.
5. Keep Implementation Status at `Implemented`, not `Verified`, unless the full live CLI smoke is
   run and cited.
6. Commit the ADR 0203 work wave immediately after preserving or updating Accepted status evidence.

## Risks

- The worktree contains unrelated dirty files. Staging must be path-specific.
- Full-suite failures may come from unrelated dirty changes; that would block stronger closure.
- ADR 0203 remains below `Verified` without live create/observe/terminate smoke evidence.
