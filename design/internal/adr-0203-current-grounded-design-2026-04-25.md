# ADR 0203 Current Grounded Design Artifact — 2026-04-25

## Phase Boundary

This artifact is Phase 1 for ADR 0203 only. It records the current repository evidence, required
code/test closure items, verification steps, and risks. It does not promote ADR decision or
implementation status in this phase.

## Swarm Phase 1 — Problem Definition

- Core problem: verify whether ADR 0203's canonical v2 persistence authority is actually represented
  in current code and tests, and identify any remaining implementation work before status closure is
  claimed.
- Scope: ADR 0203, local repository code, focused tests, and verification evidence.
- Out of scope: ADRs outside 0203, the next ADR in sequence, broad legacy snapshot removal, and
  unrelated dirty worktree changes.
- Success criteria: current-state claims cite grep/read evidence; all required code changes, tests,
  verification commands, and risks are explicit; Phase 2 has a bounded working point.
- Uncertainties: the worktree contains unrelated modified files, so Phase 2 must avoid staging or
  relying on those changes unless they are already part of the current repository state under test.

Swarm configuration snapshot:

- preset: Diagnosis / Engineering
- overrides: high grounding need, narrow route branching, high closure strictness
- evidence boundary: local files, grep/read citations, and local test output only

## Swarm Phase 2 — Expert Assembly

- Barbara Liskov (Critic): contract boundaries for canonical read services.
- Martin Fowler (Balanced · Synthesizer): application service and migration shape.
- Leslie Lamport (Critic): event ordering, replay, and checkpoint authority.
- Kelsey Hightower (Evangelist · Implementer): practical CLI and user-facing completion.
- Nancy Leveson (Critic · Completer-Finisher): closure risk and verification adequacy.

## Swarm Phase 3 — Iteration Brief

### Iteration 1 — Option A Round-Robin

Open items scan: no aged or blocked user-owned item. The active uncertainty is whether ADR 0203
still needs code changes or only renewed verification evidence.

Moderator reasoning: the unresolved gap is authority, not architecture invention. A round-robin
separates event-sourced mutation authority, public read authority, and closure evidence.

- Liskov: public operation-state projections must use one canonical query contract. Legacy store
  reads are acceptable inside that contract as fallback, not as independent public authority.
- Fowler: avoid adding another service if `OperationResolutionService` already provides merged
  v2-plus-legacy state.
- Lamport: status closure needs event-first replay evidence and tests where `.operator/runs` is
  absent; snapshot-backed tests are insufficient.
- Hightower: keep Phase 2 to the ADR-sized slice; do not rewrite CLI or forensic transcript flows.
- Leveson: do not claim `Verified` unless the live smoke in the ADR verification plan is also run
  and evidenced.

Route update:

- Route: complete or verify event-first canonical persistence authority using existing resolution
  and status services.
- Prior state: open.
- New state: selected.
- Justification: this route directly matches ADR 0203's required properties and avoids new
  abstractions.

### Iteration 2 — Option E Executor Grounding

Questions: which current code paths prove or violate the ADR 0203 authority contract?

Scope: `operation_resolution`, status queries, CLI converse/detail/control read paths, MCP/client
list paths, and ADR 0203 regression tests.

Findings:

- `OperationResolutionService.load_canonical_operation_state()` loads event-sourced state before
  legacy snapshots (`src/agent_operator/application/queries/operation_resolution.py:105` through
  `src/agent_operator/application/queries/operation_resolution.py:112`).
- `OperationResolutionService.list_canonical_operation_states()` enumerates event streams first and
  only adds legacy operations not already seen (`src/agent_operator/application/queries/operation_resolution.py:114`
  through `src/agent_operator/application/queries/operation_resolution.py:131`).
- Status read payload construction loads event-sourced operation state before `store.load_operation`
  and marks the source as `event_sourced` when replay succeeds
  (`src/agent_operator/application/queries/operation_status_queries.py:210` through
  `src/agent_operator/application/queries/operation_status_queries.py:214`).
- CLI resolution helpers expose canonical list/load helpers backed by
  `OperationResolutionService` (`src/agent_operator/cli/helpers/resolution.py:44` through
  `src/agent_operator/cli/helpers/resolution.py:64`).
- Grep evidence shows converse, TUI views, operation detail, and control-runtime operation metadata
  use canonical helpers rather than direct `build_store(settings).load_operation()` in the ADR 0203
  read-authority files.
- Static guardrails cover v2 mutation paths for `save_operation()` and canonical read-surface
  references (`tests/test_application_structure.py:113` through
  `tests/test_application_structure.py:154`).
- Regression tests seed event-sourced checkpoints without `.operator/runs` and cover resolution,
  converse operation prompt, converse fleet prompt, and attention detail output
  (`tests/test_cli.py:808`, `tests/test_cli.py:902`, `tests/test_cli.py:933`, and
  `tests/test_cli.py:972`).
- Status regression coverage includes stale snapshot precedence, asserting event-sourced replay wins
  over a legacy snapshot for the same operation id (`tests/test_operation_status_queries.py:239`
  through `tests/test_operation_status_queries.py:274`).

Route update:

- Route: verify current ADR 0203 implementation rather than introduce new code.
- Prior state: selected.
- New state: implementation-ready, verification-gated.
- Justification: current code already satisfies the known remaining read-authority changes; Phase 2
  should run targeted and full verification before touching ADR status or committing.

### Iteration 3 — Option H Finalization

Pre-mortem:

- Liskov: the answer is wrong if a public state projection still bypasses the canonical service.
  Mitigation: grep the named ADR 0203 surface files before closure.
- Fowler: the answer is wrong if a new abstraction is added unnecessarily. Mitigation: use the
  existing service.
- Lamport: the answer is wrong if checkpoints are treated as canonical without replay sequence
  checks. Mitigation: include replay sequence tests in targeted verification.
- Hightower: the answer is wrong if Phase 2 expands into unrelated ADRs or CLI redesign. Mitigation:
  keep file and test scope fixed.
- Leveson: the answer is wrong if `Verified` is claimed without the live smoke. Mitigation: use
  `Implemented` unless every ADR verification-plan item is evidenced.

Readiness check: enough repository evidence exists to execute Phase 2. The active route is stable:
run focused ADR 0203 tests, run the full suite, then update ADR 0203 only if evidence changes the
status truth. Another design iteration is unlikely to change the practical plan.

## Required Code Changes

No new production code changes are currently required by the evidence above. If Phase 2 verification
reveals a failure, the required code changes are limited to the failing ADR 0203 authority path.

## Tests That Must Exist

- Static guard: v2 mutation paths do not call `save_operation()`.
- Static guard: canonical read surfaces retain event-first resolution/service references.
- Resolution: event-sourced operation ids resolve when `.operator/runs` is absent.
- Converse: operation prompt and fleet prompt include event-sourced-only operations.
- Detail: attention/detail projection can read event-sourced-only operation state.
- Status: event-sourced replay wins over stale legacy snapshots.
- Replay: checkpoint-ahead-of-stream is rejected.

## Phase 2 Verification Steps

1. Re-run grep/read evidence for ADR 0203 status-flip citations.
2. Run targeted tests:
   `uv run pytest tests/test_application_structure.py tests/test_event_sourced_replay.py tests/test_operation_status_queries.py tests/test_cli.py tests/test_control_workflows.py -q`.
3. Run full suite: `uv run pytest`.
4. If targeted and full verification pass but no live CLI smoke is run, ADR 0203 may remain
   `Implemented` but must not be promoted to `Verified`.
5. If any closure item lacks evidence, leave or downgrade implementation status truthfully and write
   a new debt ADR instead of overclaiming.

## Risks

- The worktree is already dirty with unrelated ADR and runtime/query files; staging must be
  path-specific.
- Full `uv run pytest` can fail because of unrelated pre-existing changes; such a failure blocks any
  stronger ADR closure claim.
- Empty event streams plus checkpoints are used in regression tests as event-sourced-only fixtures;
  that proves read authority over `.operator/runs`, but not a full live create/observe/terminate
  smoke.
