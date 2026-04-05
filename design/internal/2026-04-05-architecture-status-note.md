# Architecture Status Note — 2026-04-05

Internal note. Not public product documentation.

## Purpose

This note gives a short status update for colleagues:

- where the repository is now
- which architectural direction is currently active
- what the next logical implementation step should be

It is a synchronization memo, not a replacement for the ADRs.

## Where we are now

The repository is in a clearer architectural state than it was a few waves ago, but it is still in
transition.

### Documentation and repository structure

- `implemented`: the repository now has a real public documentation surface:
  - root `README.md`
  - public `docs/`
  - committed `design/` corpus
  - committed `policies/` tree
- `implemented`: MkDocs is the public docs toolchain, and generated API reference is limited to
  curated technical surfaces rather than the entire internal module tree.

### Verification workflow

- `implemented`: repository-local `pre-commit` runs:
  - `ruff` on changed Python files
  - `mypy` on changed Python files
  - full `pytest -q`
- `implemented`: `mkdocs build --strict` remains an explicit manual docs check rather than a
  per-commit hook.

### Module hierarchy

- `implemented`: the repository now has a repo-wide module hierarchy policy in
  [ADR 0107](/Users/thunderbird/Projects/operator/design/adr/0107-repository-module-hierarchy-policy-and-low-ambiguity-application-tightening.md).
- `planned`: `application/` is the active hierarchy-tightening target.
- `planned`: `runtime/` is the next likely hierarchy-review target, but without a fixed package map
  yet.
- `planned`: the first low-ambiguity `application/` restructuring pass is still:
  - `application.drive`
  - `application.event_sourcing`
  - relocation of `application/requests.py` into a contract-oriented namespace

### Compatibility residue

- `implemented`: the repository now has an explicit cleanup-policy ADR in
  [ADR 0108](/Users/thunderbird/Projects/operator/design/adr/0108-legacy-compatibility-retirement-fronts-and-parallel-truth-policy.md).
- `verified`: there is no obvious large pile of completely dead Python modules.
- `verified`: the stronger cleanup signal is live compatibility residue and parallel-truth debt.
- `planned`: the main retirement fronts are:
  - `snapshot_legacy`
  - missing canonical-mode hydration to `snapshot_legacy`
  - `"blocked"` to `"needs_human"` hydration
  - deprecated prompt-shaped goal compatibility
  - `LEGACY_PROMPT` / `LEGACY_MIXED_PROMPT`
  - `legacy_ambiguity_reason` propagation and trace decoration
- `partial`: `active_session`, `sync_legacy_active_session`, and legacy rate-limit recovery remain
  live debt, but are not yet in the safe-removal bucket.

## Where we are going

The current direction is not "general cleanup." It is more specific:

1. keep pushing the repository toward a small, explicit, architecture-first structure
2. reduce compatibility residue that preserves older conceptual models
3. avoid deleting still-live behavior under the misleading label of dead-code cleanup

In practical terms, the repository is moving toward:

- cleaner package boundaries
- fewer flat junk-drawer areas
- less dual conceptual language in domain and traceability models
- less hidden coexistence between old compatibility paths and newer canonical event-sourced
  direction

This is still a pre-release codebase, so the bias remains:

- prefer explicit retirement over indefinite fallback support
- prefer architectural closure over long-lived coexistence
- keep the cleanup sequence narrow and evidence-backed

## The next logical step

The next logical step is **not** another broad repo-wide cleanup pass.

The best next wave is a focused implementation plan for the first compatibility-retirement front
from [ADR 0108](/Users/thunderbird/Projects/operator/design/adr/0108-legacy-compatibility-retirement-fronts-and-parallel-truth-policy.md).

That wave should target the lower-risk conceptual residue first:

- prompt-shaped legacy goal-input compatibility
- `legacy_ambiguity_reason` propagation and decoration
- associated old-language reporting in traceability and prompting surfaces

This is the best next step because:

- it directly advances the retirement policy already recorded in `ADR 0108`
- it is narrower and safer than trying to remove `active_session` next
- it reduces old conceptual language in both domain state and operator-facing traces
- it should clarify which tests and UX surfaces still genuinely depend on the older prompt model

## What should not happen next

The following would be the wrong next move:

- a generic "dead code cleanup" PR with no architectural discrimination
- immediate removal of `active_session`
- immediate removal of legacy rate-limit recovery logic
- broad `application/operation/` repackaging by filename prefix
- repo-wide restructuring by symmetry

Those moves would create churn faster than they create clarity.

## Recommended immediate deliverable

Write a small implementation plan for the first `ADR 0108` retirement wave that:

- defines exact code surfaces to change
- defines expected behavior after prompt-compatibility retirement
- lists the tests that must be rewritten or removed
- names the traces / CLI surfaces that should stop exposing old prompt-era language

After that plan exists, the next implementation wave can be executed narrowly and verified
honestly.
