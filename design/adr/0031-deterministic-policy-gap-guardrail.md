# ADR 0031: Deterministic Policy-Gap Guardrail

## Status

Accepted

## Context

`operator` already has:

- explicit involvement levels,
- explicit `policy_gap` attention,
- explicit project-local policy memory,
- deterministic policy applicability matching,
- and persisted policy-coverage explainability.

That still leaves a central autonomy-trust seam.

Today the operator brain is prompted to prefer `policy_gap` when uncovered policy coverage means
the next step needs reusable project precedent. But that remains only a prompt instruction unless
the runtime also enforces the boundary.

Without a deterministic guardrail, `auto`, `collaborative`, and `approval_heavy` can still drift
into silent policy invention whenever the brain chooses a non-terminal action instead of an
explicit clarification.

The repo needs a bounded runtime rule that turns policy-shaped decisions into typed attention
before side effects, without pretending to solve full novelty detection in one slice.

## Decision

`operator` will add a bounded deterministic policy-gap guardrail in the operator loop.

The first accepted guardrail is intentionally narrow:

- the brain marks a decision with `metadata.requires_policy_decision=true` when the next step
  depends on a reusable project rule or precedent,
- the runtime checks current persisted policy coverage before executing that non-terminal decision,
- and if the operation has project scope but coverage is `no_policy` or `uncovered`, the runtime
  surfaces `policy_gap` attention instead of proceeding silently.

The same guardrail also applies to `REQUEST_CLARIFICATION` decisions:

- if the brain marks `requires_policy_decision=true`, runtime forces the attention type to
  `policy_gap` even if the decision omitted or mis-labeled the type.

The first slice keeps the override bounded:

- it does not invent policy-gap attention from uncovered coverage alone,
- it still requires the brain to mark that the immediate decision needs reusable precedent,
- and it does not claim to solve the full novelty-detection problem for every strategic fork.

## Alternatives Considered

- Option A: keep policy-gap behavior entirely in prompting and trust the brain to comply
- Option B: raise `policy_gap` automatically for every `no_policy` or `uncovered` operation
- Option C: add a bounded deterministic guardrail keyed by explicit brain metadata and persisted
  policy coverage

Option A was rejected because it leaves the autonomy boundary soft and non-auditable.

Option B was rejected because it would over-fire on operations whose current step does not
actually require reusable precedent.

Option C was accepted because it closes the most important trust gap while staying narrow,
inspectable, and compatible with the accepted policy-coverage model.

## Consequences

- `auto`, `collaborative`, and `approval_heavy` gain a real runtime backstop against silent
  policy invention on policy-shaped steps.
- `unattended` can record non-blocking `policy_gap` attention and defer the step instead of
  blocking the whole operation.
- Prompting and runtime now share one explicit seam for policy-shaped decisions:
  `metadata.requires_policy_decision`.
- Full novelty detection is still a follow-up problem; this ADR only defines the first enforced
  policy-gap boundary.
