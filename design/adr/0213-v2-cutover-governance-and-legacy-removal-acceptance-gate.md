# ADR 0213: v2 Cutover Governance And Legacy Removal Acceptance Gate

- Date: 2026-04-24

## Decision Status

Accepted

## Implementation Status

Partial

Implementation grounding on 2026-04-28:

- `implemented`: the repository now has one explicit in-repo cutover governance artifact at
  `design/internal/v2-cutover-governance-checklist.md`. That artifact records the required gate
  checklist, the current legacy inventory, the required removal order, the rollback boundary, and
  the rehearsal procedure for this ADR instead of leaving cutover approval as oral tradition.
- `implemented`: the artifact grounds the current repository inventory against real surfaces that
  still exist today, including the named snapshot fallback seams in
  `src/agent_operator/application/queries/operation_resolution.py`,
  `src/agent_operator/application/queries/operation_status_queries.py`, and
  `src/agent_operator/application/commands/operation_delivery_commands.py`, plus the transitional
  CLI aliases still published in `docs/reference/cli-command-contracts.md`.
- `implemented`: the same artifact also records already-removed slices that matter to the gate,
  including the package-root public API cleanup from `ADR 0215` and the guarded v2 mutation-path
  removal of direct `FileOperationStore.save_operation()` authority covered by
  `tests/test_application_structure.py`.
- `verified`: static regressions now fail if `ADR 0213` stops referencing the governance artifact,
  if the artifact drops a required gate section, or if it loses the canonical rehearsal commands
  and current inventory classifications. Evidence:
  `tests/test_v2_cutover_governance_docs.py`.
- `verified`: the current repository baseline is clean and green in this wave:
  `git status --short` returned no entries and `UV_CACHE_DIR=/tmp/uv-cache uv run pytest`
  passed with `1043 passed, 11 skipped` on 2026-04-28.
- `partial`: the final cutover gate is still not satisfied in repository truth. This slice defines
  and locks the governance procedure, but it does not claim that all `ADR 0203` through
  `ADR 0211` acceptance conditions are already closed for one pinned wave.
- `blocked`: one rehearsed cutover run tied to a pinned clean repository state is not yet recorded
  in-repo.
- `blocked`: upstream prerequisite ADRs in the required `ADR 0203` through `ADR 0211` set still
  remain below truthful cutover closure, including `ADR 0207`, `ADR 0209`, and `ADR 0211`.

## Context

ADR 0194 defines the full-rewrite direction for v2 and rejects long-lived backward compatibility.
ADRs 0203 through 0211 define the target persistence, control, query, runtime, CLI, and
verification contracts needed for canonical v2 behavior.

That package is still not enough to perform a trustworthy final cutover by itself. A full v2
cutover is a governance event as well as a code change:

- running work must be drained or explicitly cancelled
- destructive removal of legacy surfaces must happen in a known order
- the repository must define what counts as "v1 removed"
- the team must know whether rollback is allowed and at what boundary
- verification must be tied to a pinned repository state and rehearsed operator procedure

Without a dedicated cutover-governance ADR, the repository can reach an ambiguous state where
individual v2 tranche ADRs are accepted, but no single document defines the merge gate for
destructive removal of the remaining v1 load-bearing surfaces.

Current repository truth on 2026-04-26 is better than that but still incomplete: the repository
now has an explicit governance checklist and inventory artifact at
`design/internal/v2-cutover-governance-checklist.md`, yet the final cutover wave has not been
rehearsed and accepted on a pinned clean state.

## Decision

The repository adopts an explicit v2 cutover governance and acceptance gate.

The final destructive removal of v1 load-bearing behavior may proceed only when one named cutover
wave satisfies all of the following:

1. **Pinned repository state.** The exact commit or reviewed branch head under cutover is recorded.

2. **Drain or explicit terminal disposition.** Every running operation is either:
   - completed,
   - cancelled through the canonical control plane,
   - or explicitly documented as abandoned by policy.

3. **Canonical v2 authority is already true.** The repository state under review satisfies the
   acceptance conditions for ADRs 0203 through 0211, including required live verification evidence
   and streaming/runtime visibility requirements.

4. **Legacy removal inventory is explicit.** The cutover wave records every remaining v1
   load-bearing surface and classifies it as:
   - removed,
   - retained temporarily as migration-only or forensic-only,
   - or deferred with a named blocker ADR or backlog item.

5. **Removal order is explicit.** Destructive removal proceeds in this order:
   - legacy authority paths,
   - legacy control/query entrypoints,
   - legacy public API exports,
   - legacy tests and docs claims,
   - dormant compatibility code that no longer has a named justification.

6. **Rollback boundary is named.** The cutover wave must say whether rollback is:
   - not allowed after merge,
   - allowed only before destructive data cleanup,
   - or allowed only through git history, not runtime compatibility.

7. **Rehearsal is mandatory.** Before the final cutover, the repository must have one rehearsed,
   documented procedure showing how the cutover is executed and how success/failure is determined.

## Required Properties

- "v1 removed" has a repository-level meaning, not an informal claim.
- No destructive removal step depends on unstated operator knowledge.
- The cutover gate names all remaining exceptions instead of leaving hidden compatibility residue.
- Removal approval requires a verified repository state, not only targeted unit tests.
- The acceptance gate applies to code, public docs, and public interfaces equally.

## Acceptance Checklist

The cutover gate is not satisfied until all of the following are true:

- no v2 business path depends on `OperationState` as authority
- no v2 business path depends on `FileOperationStore.save_operation()` or `.operator/runs`
  as authority
- no public control command needed for normal v2 operation routes only through legacy services
- all surviving snapshot-era code is explicitly marked migration-only or forensic-only
- public docs no longer describe v1 behavior as current behavior
- any retained legacy fixtures are clearly separated from canonical v2 fixtures
- the final verification report names the exact commands, operation ids, dates, and environment
  assumptions used for cutover acceptance

## Verification Plan

- one rehearsed cutover checklist run recorded in-repo or in a linked cutover artifact
- one explicit legacy inventory review showing remove/retain/defer for each remaining v1 surface
- one verification pass showing that the accepted repository state satisfies ADRs 0203 through 0211
- one docs/code/API search proving that no stale "current" v1 authority claims remain
- one post-removal regression run showing the repository still supports the approved v2 workflows

Current repository evidence for this ADR slice:

- `design/internal/v2-cutover-governance-checklist.md` provides the explicit checklist, current
  legacy inventory, removal order, rollback boundary, and rehearsal procedure.
- `tests/test_v2_cutover_governance_docs.py` statically verifies that the artifact exists, is
  referenced by this ADR, retains the required gate sections, and includes the canonical rehearsal
  commands and inventory classifications.

## Related

- ADR 0194
- ADR 0203
- ADR 0204
- ADR 0205
- ADR 0206
- ADR 0207
- ADR 0208
- ADR 0209
- ADR 0210
- ADR 0211
