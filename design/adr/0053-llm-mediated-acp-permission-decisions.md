# ADR 0053: LLM-Mediated ACP Permission Decisions

## Status

Accepted

## Context

The operator already handled a narrow set of ACP permission requests with deterministic allow or deny rules inside vendor adapters. That was sufficient for known-safe cases such as specific build or staging commands, but it failed poorly for novel requests such as skill invocations. In those cases the operator either blocked generically or required adapter-local special casing.

We needed a path that:

- keeps deterministic guardrails first,
- allows inline approve or reject when the request is understandable,
- escalates uncertain or high-risk cases into explicit human attention,
- and records confirmed answers so exact future repeats do not ask again.

This decision also needed to preserve the existing operator architecture:

- the permission path must stay below the agent adapter contract,
- permission evaluation must not be folded into the operator brain loop,
- and reusable permission decisions must go into the policy store rather than hidden prompt text mutation.

## Decision

Introduce a separate provider-backed permission evaluator for unresolved ACP permission requests.

The decision order is:

1. deterministic built-in rules,
2. exact-match stored `AUTONOMY` policy by normalized permission signature,
3. inline LLM permission evaluator,
4. blocking `APPROVAL_REQUEST` attention when the evaluator escalates or remains uncertain.

The evaluator is a separate component, not a new `OperatorBrain` method. For v1 it reuses the same provider stack as the operator brain.

Permission replay is stored as project-scoped `AUTONOMY` policy with exact normalized permission signatures. The operator auto-records such policy entries when a human resolves an approval-derived attention request with a clear approve or reject answer.

That decision is now reflected in the repository shape:

- unresolved ACP permission requests can be delegated to a separate
  `ProviderBackedPermissionEvaluator`
- exact-match `AUTONOMY` policy replay is checked before calling the provider
- approval-derived attention answers can auto-record exact-match autonomy policy entries for future
  replay

## Alternatives Considered

- Keep adapter-local boolean allow or deny logic only
- Move permission reasoning into `OperatorBrain`
- Ask the human for every unresolved permission request
- Persist learned permission rules by mutating harness text directly

## Consequences

- Positive consequence: unresolved permission requests can now be handled inline without hard-coding every new case into adapters.
- Positive consequence: approval replay remains conservative and auditable because matching is exact and project-scoped.
- Positive consequence: the operator keeps deterministic rules first, so low-risk known cases do not pay an LLM round trip.
- Negative consequence: permission handling now depends on provider availability for unresolved cases.
- Negative consequence: exact-match replay is intentionally narrow, so similar-but-not-identical requests still escalate.
- Follow-up implication: richer approval UX and broader policy generalization, if ever added, should build on the normalized signature model rather than bypass it.
