# ADR 0203 Completion Design Artifact — 2026-04-25

## Swarm Configuration Snapshot

- preset: Diagnosis / Engineering
- overrides: rigor = high, grounding need = high, route branching budget = narrow, closure strictness = high
- evidence boundary: local repository files, grep/read citations, and local test output only

## Phase 1 — Problem Definition

Core problem: ADR 0203 says canonical v2 operation truth must come from
`operation_events` plus derived checkpoints, but its status remains `Proposed` / `Partial` because
some converse, operation-detail, and control surfaces still load operation state directly from
legacy `.operator/runs` snapshots.

Scope:

- In scope: complete ADR 0203's remaining read-authority slice for operation detail/converse/control
  surfaces, add focused regression tests, run targeted and full verification, and update ADR 0203
  only if evidence supports the status change.
- Out of scope: removal of legacy `.operator/runs`, changes to ADRs outside `0203..0212`, unrelated
  shell thinning, and adapter transcript discovery that requires legacy session metadata by design.

Success criteria:

- Operation detail commands that project canonical operation fields load through
  `OperationResolutionService.load_canonical_operation_state()`.
- Converse operation and fleet prompts use canonical merged v2-plus-legacy operation state.
- TUI converse operation and fleet prompts use canonical merged state.
- Static grep/read evidence shows the replaced paths no longer use direct `build_store(...).load_operation`
  or `store.list_operations()` for those state projections.
- Regression tests fail if event-sourced operations are invisible when `.operator/runs` is absent.
- Targeted pytest and full `uv run pytest` pass before ADR 0203 is flipped.

Uncertainties:

- Some detail commands such as `log` and session transcript views may still need legacy session metadata
  and external log-file resolution; these are forensic compatibility paths, not canonical state
  projections. They should not block ADR 0203 unless tests show they are status/list/inspect authority.

## Phase 2 — Expert Assembly

- Barbara Liskov (Critic): contract boundaries and substitutability of canonical read services.
- Martin Fowler (Balanced · Synthesizer): application service/read-model boundaries and migration shape.
- Leslie Lamport (Critic): event stream authority, ordering, and replay evidence discipline.
- Kelsey Hightower (Evangelist · Implementer): practical CLI/user workflow completion without overdesign.
- Nancy Leveson (Critic · Completer-Finisher): closure risk, status overclaiming, and verification gaps.

## Phase 3 — Iteration Brief

### Iteration 1 — Option A Round-Robin

Open items scan: no aged swarm items; all ADR 0203 closure questions are current.

Moderator reasoning: the unresolved gap is not whether v2 persistence exists, but whether remaining
public read surfaces still treat snapshots as authoritative. Round-robin is useful to separate
canonical state projection from legacy forensic lookup.

Expert outputs:

- Liskov: require a single canonical operation-state query contract for public state projections.
  Direct `FileOperationStore` access can remain in legacy implementation internals only when the
  caller is explicitly a migration/forensic path.
- Fowler: introduce no new abstraction if `OperationResolutionService` already exists. Route detail
  and converse reads through it, preserving delivery formatting.
- Lamport: status flip needs grep/read evidence and replay-backed tests where no `.operator/runs`
  file exists. A green unit test using snapshots alone does not prove ADR 0203.
- Hightower: keep the slice feature-sized. Do not rewrite CLI command layout; replace load/list call
  sites that shape user-visible operation state.
- Leveson: do not mark `Verified` unless the full ADR verification plan, including CLI smoke without
  `.operator/runs`, is actually evidenced. `Implemented` is the safer closure target if tests cover
  the remaining authority leaks.

Route update:

- Route: complete remaining canonical read authority through existing resolution service.
- Prior state: plausible but ungrounded.
- New state: selected.
- Justification: ADR 0203 explicitly names remaining converse/detail/control direct snapshot reads,
  and `OperationResolutionService` already merges event-sourced and legacy states.

### Iteration 2 — Option E Executor Grounding

Open items scan: no blocked user-owned items.

Executor questions:

- Which exact files still load operation state directly for remaining ADR 0203 surfaces?
- Is the existing resolution service sufficient, or is a new service required?

Scope: `src/agent_operator/cli/workflows/converse.py`,
`src/agent_operator/cli/workflows/views.py`, `src/agent_operator/cli/commands/operation_detail.py`,
and existing resolution helpers.

Findings:

- `src/agent_operator/application/queries/operation_resolution.py` provides
  `load_canonical_operation_state()` and `list_canonical_operation_states()`.
- `src/agent_operator/cli/helpers/resolution.py` builds that service from settings.
- `src/agent_operator/cli/workflows/converse.py` directly uses `store.list_operations()` and
  `store.load_operation()` for fleet and operation prompts.
- `src/agent_operator/cli/workflows/views.py` uses direct snapshot load in `ask_async()` and TUI
  converse operation context.
- `src/agent_operator/cli/commands/operation_detail.py` uses direct snapshot load for `attention`,
  `tasks`, `memory`, `artifacts`, and some report/session/log flows.

Route update:

- Route: use existing helper/service.
- Prior state: selected, needs implementation details.
- New state: implementation-ready.
- Justification: no new authority abstraction is needed; the existing service is the ADR 0203
  authority.

### Iteration 3 — Option H Finalization

Pre-mortem:

- Liskov: wrong if call sites receive inconsistent settings. Mitigation: build canonical service from
  the same settings object used by each command.
- Fowler: wrong if duplicated helpers drift. Mitigation: centralize command-level loading in
  `cli.helpers.resolution`.
- Lamport: wrong if tests create snapshots. Mitigation: regression tests must create only
  event-sourced events/checkpoints.
- Hightower: wrong if the slice expands into log/session forensics. Mitigation: keep log/session
  transcript paths out of this closure unless they project canonical state.
- Leveson: wrong if ADR claims `Verified` without full smoke evidence. Mitigation: prefer
  `Implemented` unless every verification-plan item is locally evidenced.

Readiness check: enough information exists to implement the requested slice; the active route is
stable; remaining risk is bounded to verification evidence rather than design ambiguity.

Final plan:

1. Add canonical-load helpers in `cli.helpers.resolution` for one operation and fleet lists.
2. Replace direct snapshot reads in converse and TUI converse with the helpers.
3. Replace operation detail projection commands with canonical loads.
4. Add regression tests for event-sourced-only operation visibility in converse resolution/fleet and
   detail projections.
5. Run targeted tests, then full `uv run pytest`.
6. Only after evidence is complete, update ADR 0203 to `Decision Status: Accepted` and
   `Implementation Status: Implemented`; do not claim `Verified` unless the full verification plan is
   satisfied.

Required code changes:

- `src/agent_operator/cli/helpers/resolution.py`
- `src/agent_operator/cli/workflows/converse.py`
- `src/agent_operator/cli/workflows/views.py`
- `src/agent_operator/cli/commands/operation_detail.py`
- focused tests under existing CLI/converse test modules

Risks:

- Transcript/log commands may still need legacy session snapshots; forcing them through replay in
  this slice could break forensic inspection without proving ADR 0203.
- Existing unrelated dirty worktree files must remain unstaged.
- Full verification may fail for pre-existing unrelated changes; if so, ADR status must not overclaim.
