# ADR 0166: Policy Coverage And Explainability

## Decision Status

Accepted

## Implementation Status

Implemented

Implementation grounding on 2026-04-13:

- `implemented`: policy coverage is persisted as operation truth and surfaced through deterministic
  explainability paths
- `implemented`: `operator policy explain` exists as the dedicated coverage/explainability command
- `verified`: policy coverage and explainability coverage exists in `tests/test_policy_coverage.py`,
  `tests/test_policy_coverage_cli.py`, and `tests/test_policy_cli.py`

## Context

`operator` already has:

- project-local policy memory,
- explicit policy promotion and revocation,
- deterministic applicability matching,
- and CLI surfaces that show the active policy entries on an operation.

That still leaves a meaningful operator-facing gap.

A human can see which policy entries are active, but cannot yet answer the more important control
question quickly:

- does this operation have a policy scope,
- does that scope contain any policy at all,
- does any stored policy apply right now,
- and if not, why not.

Without that coverage truth, the autonomy layer stays harder to trust and harder to audit.
The runtime can carry narrow applicability selectors, but users still cannot distinguish cleanly
between:

- no scope,
- no stored policy,
- covered by matching policy,
- and uncovered because scoped policy exists but none applies now.

## Decision

`operator` will make policy coverage a first-class persisted runtime projection and expose a
dedicated explainability surface for it.

The accepted slice adds:

- a persisted `policy_coverage` summary on `OperationState`,
- deterministic coverage statuses:
  - `no_scope`
  - `no_policy`
  - `covered`
  - `uncovered`
- coverage summaries surfaced through existing operation-centric views such as `context` and
  `dashboard`,
- and a new `operator policy explain <operation-id>` command that shows:
  - which scoped policy entries apply now,
  - which scoped entries are skipped,
  - and the deterministic reasons for each outcome.

This slice remains a projection over existing persisted truth:

- operation metadata,
- scoped policy entries,
- deterministic applicability matching,
- and persisted active policy state.

It does not add:

- a new policy store,
- hidden dashboard-only state,
- or novelty-detection semantics for when the operator must raise `policy_gap` attention.

## Alternatives Considered

- Option A: keep showing only active policy entries and expect users to infer coverage manually
- Option B: let the operator brain explain policy applicability ad hoc from prompt context
- Option C: persist coverage state and add a deterministic explainability surface

Option A was rejected because it hides the most important policy-control question behind manual
reconstruction.

Option B was rejected because explainability would become less stable, less auditable, and more
dependent on LLM wording rather than persisted control truth.

Option C was accepted because it strengthens autonomy transparency without widening the runtime
surface area much.

## Consequences

- Operators can now inspect policy scope health directly instead of inferring it indirectly.
- `context` and `dashboard` become more honest about whether current autonomy is backed by policy
  precedent.
- The repo gains a clean substrate for later novelty-detection and `policy_gap` behavior.
- This ADR still does not define automatic policy promotion or the precise novelty-detection
  algorithm for when uncovered policy should force attention.
