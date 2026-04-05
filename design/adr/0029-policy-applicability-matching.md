# ADR 0029: Define Policy Applicability Matching

## Status

Accepted

## Context

`operator` already has:

- explicit project-local policy memory
- explicit policy promotion and revocation workflows
- active policy injected into future operator decisions

But project scope alone is too coarse once a project accumulates several policy entries.

Without deterministic applicability matching, the product drifts into one of two bad states:

- every project policy is always injected, turning learned precedent into prompt clutter
- or users avoid recording narrower policy because the runtime cannot apply it honestly

The repo already contains a bounded `PolicyApplicability` shape with:

- `objective_keywords`
- `task_keywords`
- `agent_keys`
- `run_modes`
- and `involvement_levels`

What was still missing was the accepted runtime meaning of those fields.

## Decision

`operator` will apply active project policy in two stages:

1. project-scope selection
2. deterministic applicability matching

Applicability semantics are intentionally simple:

- empty applicability means the policy is global within its project scope
- within one field, matching is `any-of`
- across populated fields, matching is `all-of`
- `objective_keywords` match against the operation objective, harness, and success criteria
- `task_keywords` match against persisted task titles, goals, and notes
- `agent_keys` match against allowed or already-used adapter keys
- `run_modes` match against the persisted run mode
- `involvement_levels` match against the current persisted involvement level

The first slice also makes applicability first-class in the CLI:

- `policy record` can persist applicability selectors
- `answer --promote` can persist the same selectors
- `policy list`, `policy inspect`, `context`, and `dashboard` surface applicability summaries

## Alternatives Considered

- Option A: keep project-scope-only policy inclusion
- Option B: let the operator brain infer applicability ad hoc from raw policy text
- Option C: add bounded deterministic applicability matching

Option A was rejected because policy becomes less useful as the policy set grows.

Option B was rejected because it hides control-plane behavior inside LLM judgment and weakens
auditability.

Option C was accepted because it keeps the runtime honest, inspectable, and compatible with the
existing bounded policy model.

## Consequences

- The active policy set becomes narrower and more relevant for each operation.
- Policy recording becomes expressive enough to encode reusable but non-global project precedent.
- CLI inspection surfaces can explain not just which policy exists, but why it applies now.
- This ADR still does not define automatic policy promotion or novelty-detection semantics for
  policy gaps.
