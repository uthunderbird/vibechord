# ADR 0041: Agent Turn Summaries And Full Latest Result For Brain History

## Status

Proposed

## Context

`operator` currently builds brain prompts from broad `OperationState` dumps plus recent iteration
history.

The recent-history portion is currently centered on raw agent result text:

- each recent iteration carries the prior operator decision,
- the agent result is represented mainly as a `result_excerpt`,
- and the brain is expected to infer what materially changed from the agent's prose.

This has several problems:

- long agent turns often put the real conclusion near the end,
- excerpting raw output is lossy and brittle,
- different agents format their prose differently,
- and the brain reasons over chat-like transcripts rather than operator-relevant turn records.

Real runtime evidence from live research runs shows that final route choice, final blocker
assessment, proof-state delta, and next-step recommendation often appear in the tail of the agent
message rather than near the beginning.

The recently added balanced `head + tail` excerpt is a useful immediate mitigation, but it is
still a fallback over raw prose, not a clean control-plane representation of what happened in a
turn.

## Decision

`operator` will move brain history away from raw chat excerpts and toward structured
agent-authored turn summaries.

The intended model is:

1. after each completed agent turn, the runtime records a structured
   `turn_and_next_decision_summary`,
2. older recent iterations are shown to the brain primarily through that summary and the operator's
   prior instruction,
3. the most recent completed agent result is shown to the brain in full,
4. raw excerpts remain only as fallback evidence when the structured summary is missing or judged
   insufficient.

This preserves the highest-value information from the latest turn while compressing older history
into the operator-relevant state needed for next-turn decisions.

The expected summary shape should cover fields such as:

- declared goal for the turn,
- actual work completed,
- route or target chosen,
- repository changes,
- proof/product state delta,
- verification or build status,
- remaining blockers,
- and recommended next step.

## Alternatives Considered

### Option A: Keep head-only or head-plus-tail raw excerpts as the main history format

Rejected as the final design.

This is a useful stopgap, but it still asks the brain to recover structured state from prose.

### Option B: Replace all history with operator-generated summaries only

Rejected.

This would compress aggressively, but it risks hiding the freshest and most decision-relevant
details from the latest turn.

### Option C: Use structured turn summaries for older turns and the full latest result for the most recent completed turn

Accepted.

This keeps the freshest high-value evidence intact while compressing older history into a more
stable and operator-relevant format.

## Consequences

- Positive: the brain sees operator-relevant turn state instead of mostly prose transcripts.
- Positive: the latest turn remains fully visible, preserving tail-heavy conclusions.
- Positive: older history becomes smaller, more stable, and more cache-friendly.
- Positive: decisions become less sensitive to agent writing style.
- Negative: the runtime must define, collect, and validate a structured turn-summary contract.
- Negative: poor summaries could become a new failure mode if they are over-trusted.
- Follow-up: add a turn-summary generation step after completed agent turns.
- Follow-up: update decision and evaluation prompts to prefer structured summaries for older turns.
- Follow-up: keep raw excerpts as fallback evidence rather than the primary representation.
