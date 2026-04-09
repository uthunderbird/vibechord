# ADR 0040: Brain Context Budgets Before Provider Caching

## Status

Stale — partially absorbed into current prompting, not tracked as a separate ADR front

## Context

`operator`'s brain is currently provider-backed:

- `decide_next_action`
- `evaluate_result`
- `normalize_artifact`
- `distill_memory`

all issue fresh structured-output LLM calls through the configured provider.

At the moment:

- there is no local request or response cache in `operator`,
- prompt payloads are built from large state dumps,
- and the biggest prompts include full harness text, broad task/session listings, current memory,
  policy state, and recent iteration excerpts.

This creates two related issues:

- token and latency cost are higher than needed,
- and reasoning quality is weakened because decision-relevant context is mixed with stale or
  low-signal context.

Provider-side prompt caching may help, but its effectiveness depends on large stable prompt
prefixes. The current prompt construction is too dynamic and too noisy for provider caching to be
the primary optimization lever.

## Decision

`operator` will optimize brain prompts by introducing typed context budgets before investing in
provider-side prompt caching as a primary optimization.

This means:

- each brain call family gets its own context shape,
- each context shape should prefer decision-relevant state over broad state dumps,
- prompt payloads should use explicit inclusion rules and limits,
- and provider caching should be treated as a second-layer optimization on top of slimmer, more
  stable prompts.

The intended sequencing is:

1. reduce and specialize prompt context,
2. stabilize prompt prefixes where appropriate,
3. then add provider caching hints such as cache keys or retention settings where supported.

## Alternatives Considered

### Option A: Add provider caching first

Rejected as the primary route.

This is easy to do, but it does not address the larger problem that the brain is currently asked
to reason over oversized and highly dynamic context.

### Option B: Keep the current full-state prompts and rely on model quality

Rejected.

This preserves unnecessary token cost, weakens signal-to-noise, and makes later caching less
effective.

### Option C: Introduce typed brain context budgets first, then layer provider caching on top

Accepted.

This improves both reasoning quality and efficiency, and it creates the conditions under which
provider caching becomes materially more useful.

## Consequences

- Positive: lower token usage for brain calls.
- Positive: better signal-to-noise for route selection and evaluation.
- Positive: provider-side prompt caching becomes more effective once prompt prefixes are
  stabilized.
- Positive: prompt construction becomes more explicit and reviewable.
- Negative: prompt shaping becomes more complex because different brain calls need different
  context policies.
- Negative: overly aggressive trimming could hide important state if not tested carefully.
- Follow-up: introduce per-call serializers or prompt-context builders for decision, evaluation,
  normalization, and memory distillation.
- Follow-up: add limits for recent iterations, result excerpts, memory entries, and task/session
  inclusion.
- Follow-up: only after that, evaluate provider-side caching hints such as prompt cache keys.

## Later outcome

The repository did move in the direction described here:

- prompt construction now uses more explicit serializers and inclusion rules
- recent-iteration shaping is more specialized than the earlier broad state-dump model

But this ADR no longer names an active implementation front of its own.

The repository has not pursued provider caching as a major standalone ADR wave, and the remaining
prompt-budget work is now better understood as ordinary prompting/runtime evolution rather than as
an open architectural fork that still needs separate closure.
